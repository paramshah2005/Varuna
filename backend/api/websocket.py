import hashlib
import json
import os
import time
from backend.api.storage import get_store


def authorizer(event, context):
    store = get_store()
    ticket = (event.get("queryStringParameters") or {}).get("ticket", "")
    if not ticket or len(ticket) != 32:
        raise Exception("Unauthorized")
    pk = f"TICKET#{hashlib.sha256(ticket.encode()).hexdigest()}"
    record = store.get(pk, "META")
    if not record or record.get("used") or record["expires_at"] <= time.time():
        raise Exception("Unauthorized")
    store.compare_put(pk, "META", record, {**record, "used": True})
    return dict(
        principalId=record["owner"],
        policyDocument=dict(
            Version="2012-10-17",
            Statement=[
                dict(
                    Action="execute-api:Invoke",
                    Effect="Allow",
                    Resource=event["methodArn"],
                )
            ],
        ),
        context=dict(owner=record["owner"]),
    )


def handler(event, context):
    store = get_store()
    request = event["requestContext"]
    connection_id = request["connectionId"]
    key = f"CONNECTION#{connection_id}"
    action = request["routeKey"]
    if action == "$connect":
        owner = request.get("authorizer", {}).get("owner")
        if not owner:
            return dict(statusCode=401)
        store.put(
            key,
            "META",
            dict(
                owner=owner,
                connection_id=connection_id,
                expires_at=int(time.time()) + 3600,
            ),
        )
        return dict(statusCode=200)
    record = store.get(key, "META")
    if action == "$disconnect":
        if record and record.get("run_id"):
            store.delete(f"RUN#{record['run_id']}", f"SUB#{connection_id}")
        store.delete(key, "META")
        return dict(statusCode=200)
    if not record or record["expires_at"] <= time.time():
        return dict(statusCode=401)
    try:
        body = json.loads(event.get("body") or "{}")
        run_id = body["run_id"]
        run = store.get(f"RUN#{run_id}", "META")
        if not run or run["owner"] != record["owner"]:
            return dict(statusCode=403)
        if record.get("run_id"):
            store.delete(f"RUN#{record['run_id']}", f"SUB#{connection_id}")
        store.put(key, "META", {**record, "run_id": run_id})
        store.put(f"RUN#{run_id}", f"SUB#{connection_id}", record)
        return dict(statusCode=200)
    except (ValueError, KeyError, TypeError):
        return dict(statusCode=400)


def publisher(event, context):
    import boto3
    from botocore.exceptions import ClientError

    store = get_store()
    run = store.get(f"RUN#{event['run_id']}", "META")
    client = boto3.client(
        "apigatewaymanagementapi", endpoint_url=os.environ["WEBSOCKET_MANAGEMENT_URL"]
    )
    for record in store.list(f"RUN#{event['run_id']}", "SUB#"):
        if record["expires_at"] <= time.time() or record["owner"] != run["owner"]:
            store.delete(f"RUN#{event['run_id']}", f"SUB#{record['connection_id']}")
            if record["expires_at"] <= time.time():
                try:
                    client.delete_connection(ConnectionId=record["connection_id"])
                except ClientError as exc:
                    if exc.response["Error"]["Code"] != "GoneException":
                        raise
                store.delete(f"CONNECTION#{record['connection_id']}", "META")
            continue
        try:
            client.post_to_connection(
                ConnectionId=record["connection_id"], Data=json.dumps(event).encode()
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "GoneException":
                store.delete(f"RUN#{event['run_id']}", f"SUB#{record['connection_id']}")
                store.delete(f"CONNECTION#{record['connection_id']}", "META")
            else:
                raise
