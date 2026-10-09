import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from decimal import Decimal


class Conflict(ValueError):
    pass


def plain(value):
    return json.loads(
        json.dumps(
            value,
            default=lambda x: (
                (int(x) if x == x.to_integral_value() else float(x))
                if isinstance(x, Decimal)
                else str(x)
            ),
        )
    )


class Store:
    def __init__(self, local_root=None):
        self.cloud = bool(os.getenv("TABLE_NAME")) and local_root is None
        self.lock = threading.RLock()
        if self.cloud:
            import boto3

            self.table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
            self.s3 = boto3.client("s3")
            self.bucket = os.environ["BUCKET_NAME"]
        else:
            self.root = Path(local_root or os.getenv("LOCAL_ROOT", ".local/demo"))
            self.root.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(
                self.root / "state.db", check_same_thread=False, isolation_level=None
            )
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS records (pk TEXT, sk TEXT, body TEXT, PRIMARY KEY(pk,sk))"
            )

    def get(self, pk, sk):
        if self.cloud:
            item = self.table.get_item(Key=dict(pk=pk, sk=sk), ConsistentRead=True).get(
                "Item"
            )
            return plain(item["body"]) if item else None
        with self.lock:
            row = self.db.execute(
                "SELECT body FROM records WHERE pk=? AND sk=?", (pk, sk)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, pk, sk, body, new=False):
        if self.cloud:
            from botocore.exceptions import ClientError

            item = dict(
                pk=pk, sk=sk, body=json.loads(json.dumps(body), parse_float=Decimal)
            )
            if "expires_at" in body:
                item["expires_at"] = int(body["expires_at"])
            try:
                self.table.put_item(
                    Item=item,
                    **(
                        {"ConditionExpression": "attribute_not_exists(pk)"}
                        if new
                        else {}
                    ),
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise Conflict("Record already exists") from exc
                raise
        else:
            with self.lock:
                try:
                    query = (
                        "INSERT INTO records VALUES (?,?,?)"
                        if new
                        else "INSERT OR REPLACE INTO records VALUES (?,?,?)"
                    )
                    self.db.execute(query, (pk, sk, json.dumps(body, allow_nan=False)))
                except sqlite3.IntegrityError as exc:
                    raise Conflict("Record already exists") from exc

    def delete(self, pk, sk):
        if self.cloud:
            self.table.delete_item(Key=dict(pk=pk, sk=sk))
        else:
            with self.lock:
                self.db.execute("DELETE FROM records WHERE pk=? AND sk=?", (pk, sk))

    def atomic_puts(self, records):
        if self.cloud:
            import boto3
            from boto3.dynamodb.types import TypeSerializer
            from botocore.exceptions import ClientError

            serializer = TypeSerializer()
            writes = []
            for record in records:
                body = json.loads(json.dumps(record["body"]), parse_float=Decimal)
                item = dict(pk=record["pk"], sk=record["sk"], body=body)
                put = dict(
                    TableName=self.table.name,
                    Item={k: serializer.serialize(v) for k, v in item.items()},
                )
                if "old" in record:
                    put.update(
                        ConditionExpression="#body = :old",
                        ExpressionAttributeNames={"#body": "body"},
                        ExpressionAttributeValues={
                            ":old": serializer.serialize(
                                json.loads(
                                    json.dumps(record["old"]), parse_float=Decimal
                                )
                            )
                        },
                    )
                else:
                    put["ConditionExpression"] = "attribute_not_exists(pk)"
                writes.append(dict(Put=put))
            try:
                boto3.client("dynamodb").transact_write_items(TransactItems=writes)
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "TransactionCanceledException":
                    raise Conflict(
                        "Concurrent version or idempotency conflict"
                    ) from exc
                raise
        else:
            with self.lock:
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    for record in records:
                        if "old" in record:
                            self.compare_put(
                                record["pk"],
                                record["sk"],
                                record["old"],
                                record["body"],
                            )
                        else:
                            self.put(
                                record["pk"], record["sk"], record["body"], new=True
                            )
                    self.db.execute("COMMIT")
                except Exception:
                    self.db.execute("ROLLBACK")
                    raise

    def list(self, pk, prefix=""):
        if self.cloud:
            from boto3.dynamodb.conditions import Key

            items, last = [], None
            while True:
                kwargs = dict(
                    KeyConditionExpression=Key("pk").eq(pk)
                    & Key("sk").begins_with(prefix),
                    ConsistentRead=True,
                )
                if last:
                    kwargs["ExclusiveStartKey"] = last
                response = self.table.query(**kwargs)
                items.extend(plain(i["body"]) for i in response["Items"])
                last = response.get("LastEvaluatedKey")
                if not last:
                    return items
        with self.lock:
            rows = self.db.execute(
                "SELECT body FROM records WHERE pk=? AND sk LIKE ? ORDER BY sk",
                (pk, prefix + "%"),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def compare_put(self, pk, sk, old, new):
        if self.cloud:
            from botocore.exceptions import ClientError

            item = dict(
                pk=pk, sk=sk, body=json.loads(json.dumps(new), parse_float=Decimal)
            )
            if "expires_at" in new:
                item["expires_at"] = int(new["expires_at"])
            try:
                self.table.put_item(
                    Item=item,
                    ConditionExpression="#body = :old",
                    ExpressionAttributeNames={"#body": "body"},
                    ExpressionAttributeValues={
                        ":old": json.loads(json.dumps(old), parse_float=Decimal)
                    },
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise Conflict("Version changed") from exc
                raise
        else:
            with self.lock:
                row = self.db.execute(
                    "SELECT body FROM records WHERE pk=? AND sk=?", (pk, sk)
                ).fetchone()
                if not row or json.loads(row[0]) != old:
                    raise Conflict("Version changed")
                self.put(pk, sk, new)

    def object_put(self, key, body):
        raw = json.dumps(body, allow_nan=False).encode()
        if self.cloud:
            self.s3.put_object(
                Bucket=self.bucket, Key=key, Body=raw, ContentType="application/json"
            )
        else:
            path = self.root / "objects" / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        return key

    def object_get(self, key):
        if self.cloud:
            return json.loads(
                self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            )
        return json.loads((self.root / "objects" / key).read_text())

    def event(self, run_id, kind, message, detail=None, event_key=None):
        pk = f"RUN#{run_id}"
        if event_key:
            existing = self.get(pk, f"EVENTKEY#{event_key}")
            if existing:
                return existing
        for _ in range(20):
            meta = self.get(pk, "META")
            seq = meta.get("event_seq", 0) + 1
            event = dict(
                seq=seq,
                kind=kind,
                message=message,
                detail=detail or {},
                timestamp=time.time(),
                run_id=run_id,
            )
            updated = {**meta, "event_seq": seq}
            if self.cloud:
                from boto3.dynamodb.types import TypeSerializer
                from botocore.exceptions import ClientError

                serializer = TypeSerializer()

                def typed(body):
                    return {
                        k: serializer.serialize(v)
                        for k, v in json.loads(
                            json.dumps(body), parse_float=Decimal
                        ).items()
                    }

                writes = [
                    dict(
                        Put=dict(
                            TableName=self.table.name,
                            Item=typed(dict(pk=pk, sk="META", body=updated)),
                            ConditionExpression="#body = :old",
                            ExpressionAttributeNames={"#body": "body"},
                            ExpressionAttributeValues={
                                ":old": serializer.serialize(
                                    json.loads(json.dumps(meta), parse_float=Decimal)
                                )
                            },
                        )
                    ),
                    dict(
                        Put=dict(
                            TableName=self.table.name,
                            Item=typed(dict(pk=pk, sk=f"EVENT#{seq:09d}", body=event)),
                            ConditionExpression="attribute_not_exists(pk)",
                        )
                    ),
                ]
                if event_key:
                    writes.append(
                        dict(
                            Put=dict(
                                TableName=self.table.name,
                                Item=typed(
                                    dict(pk=pk, sk=f"EVENTKEY#{event_key}", body=event)
                                ),
                                ConditionExpression="attribute_not_exists(pk)",
                            )
                        )
                    )
                try:
                    import boto3

                    boto3.client("dynamodb").transact_write_items(TransactItems=writes)
                except ClientError as exc:
                    if exc.response["Error"]["Code"] == "TransactionCanceledException":
                        if event_key and (
                            existing := self.get(pk, f"EVENTKEY#{event_key}")
                        ):
                            return existing
                        continue
                    raise
            else:
                with self.lock:
                    self.db.execute("BEGIN IMMEDIATE")
                    try:
                        if self.get(pk, "META") != meta:
                            self.db.execute("ROLLBACK")
                            continue
                        self.put(pk, "META", updated)
                        self.put(pk, f"EVENT#{seq:09d}", event, new=True)
                        if event_key:
                            self.put(pk, f"EVENTKEY#{event_key}", event, new=True)
                        self.db.execute("COMMIT")
                    except Exception:
                        self.db.execute("ROLLBACK")
                        raise
            if self.cloud and os.getenv("PUBLISHER_FUNCTION"):
                import boto3

                boto3.client("lambda").invoke(
                    FunctionName=os.environ["PUBLISHER_FUNCTION"],
                    InvocationType="Event",
                    Payload=json.dumps(event).encode(),
                )
            return event
        raise Conflict("Event sequence contention; retry")


_store = None


def get_store():
    global _store
    if _store is None:
        _store = Store()
    return _store
