import hashlib
import json
import os
import re
import threading
import time
import uuid
from pydantic import ValidationError
from backend.api.storage import Conflict, get_store
from backend.api.public import available_stations, route, zone_from_coordinates
from backend.simulation.models import Decision, RunRequest, Scenario
from backend.simulation.fixtures import fixtures
from backend.simulation.engine import simulate
from backend.workflows.jobs import local_apply, local_start, status


class ApiError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def response(code, body):
    return dict(
        statusCode=code,
        headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
        body=json.dumps(body, allow_nan=False),
    )


def require_key(headers):
    key = headers.get("idempotency-key", "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{8,128}", key):
        raise ApiError(400, "Idempotency-Key must have 8–128 safe characters")
    return key


def run_owned(store, owner, run_id):
    meta = store.get(f"RUN#{run_id}", "META")
    if not meta or meta["owner"] != owner:
        raise ApiError(404, "Run not found")
    return meta


def ensure_seeds(store, owner):
    pk = f"OWNER#{owner}"
    for scenario in fixtures():
        if not store.get(pk, f"SCENARIO#{scenario.scenario_id}"):
            key = f"scenarios/{owner}/{scenario.scenario_id}/1.json"
            store.object_put(key, scenario.model_dump(mode="json"))
            record = dict(
                scenario_id=scenario.scenario_id,
                scenario_version=1,
                snapshot_key=key,
                name=scenario.name,
                description=scenario.description,
            )
            try:
                store.atomic_puts(
                    [
                        dict(pk=pk, sk=f"SCENARIO#{scenario.scenario_id}", body=record),
                        dict(
                            pk=pk,
                            sk=f"VERSION#{scenario.scenario_id}#000001",
                            body=record,
                        ),
                    ]
                )
            except Conflict:
                pass


def scenario_record(store, owner, sid, version=None):
    key = f"VERSION#{sid}#{version:06d}" if version is not None else f"SCENARIO#{sid}"
    record = store.get(f"OWNER#{owner}", key)
    if not record:
        raise ApiError(404, "Scenario not found")
    return record


def safe_meta(meta):
    return {
        k: v
        for k, v in meta.items()
        if not k.endswith("_key") and k not in {"execution_arn", "owner"}
    }


def ensure_started(store, run_id):
    pk = f"RUN#{run_id}"
    meta = store.get(pk, "META")
    if store.cloud:
        if meta.get("execution_arn"):
            return
        import boto3
        from botocore.exceptions import ClientError

        machine = os.environ["STATE_MACHINE_ARN"]
        try:
            execution = boto3.client("stepfunctions").start_execution(
                stateMachineArn=machine,
                name=run_id,
                input=json.dumps(dict(run_id=run_id)),
            )
            arn = execution["executionArn"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ExecutionAlreadyExists":
                raise
            arn = machine.replace(":stateMachine:", ":execution:") + ":" + run_id
        status(store, run_id, None, execution_arn=arn)
    elif not meta.get("started"):
        try:
            store.compare_put(pk, "META", meta, {**meta, "started": True})
        except Conflict:
            return
        threading.Thread(target=local_start, args=(run_id, store), daemon=True).start()


def dispatch(method, path, owner, body, query, headers, store):
    if path.startswith("/public/"):
        scenario = fixtures()[0]
        if (
            query.get("scenario_id") == "station-outage"
            or body.get("scenario_id") == "station-outage"
        ):
            scenario = fixtures()[7]
        if method == "GET" and path == "/public/stations":
            return 200, dict(
                stations=available_stations(scenario),
                synthetic=True,
                zones=[
                    dict(
                        id=z.id,
                        name=z.name,
                        temperature=z.temperature,
                        humidity=z.humidity,
                        centroid=z.centroid,
                    )
                    for z in scenario.zones
                ],
            )
        if method == "POST" and path == "/public/demo-route":
            allowed = {"zone_id", "accessible", "latitude", "longitude", "scenario_id"}
            if set(body) - allowed:
                raise ApiError(400, "Unknown routing parameter")
            zid = body.get("zone_id")
            if "latitude" in body and "longitude" in body:
                zid = zone_from_coordinates(
                    scenario, float(body["latitude"]), float(body["longitude"])
                )
            return 200, route(scenario, zid, body.get("accessible", True))
        raise ApiError(404, "Public endpoint not found")
    if not owner:
        raise ApiError(401, "Operator authentication required")
    ensure_seeds(store, owner)
    pk = f"OWNER#{owner}"
    if method == "GET" and path == "/bootstrap":
        scenarios = [
            store.object_get(r["snapshot_key"]) for r in store.list(pk, "SCENARIO#")
        ]
        return 200, dict(
            scenarios=scenarios,
            baseline_scenarios=[s.model_dump(mode="json") for s in fixtures()],
            mode="aws" if store.cloud else "local development",
            owner=owner,
        )
    if method == "GET" and path in {
        "/zones",
        "/connections",
        "/stations",
        "/scenarios",
    }:
        if path == "/scenarios":
            return 200, dict(
                scenarios=[
                    {k: v for k, v in r.items() if k != "snapshot_key"}
                    for r in store.list(pk, "SCENARIO#")
                ]
            )
        selected = scenario_record(store, owner, query.get("scenario_id", "normal"))
        return 200, {path[1:]: store.object_get(selected["snapshot_key"])[path[1:]]}
    match = re.fullmatch(r"/scenarios/([\w-]+)(?:/versions/(\d+))?", path)
    if match and method == "GET":
        record = scenario_record(
            store, owner, match[1], int(match[2]) if match[2] else None
        )
        return 200, store.object_get(record["snapshot_key"])
    if method == "POST" and path == "/scenario-previews":
        if set(body) != {"scenario", "horizon"}:
            raise ApiError(400, "Preview requires scenario and horizon")
        draft = Scenario.model_validate(body["scenario"])
        applied = store.object_get(
            scenario_record(store, owner, draft.scenario_id)["snapshot_key"]
        )
        return 200, dict(
            draft=simulate(draft, body["horizon"]),
            applied=simulate(Scenario.model_validate(applied), body["horizon"]),
            isolated=True,
        )
    if method == "POST" and (
        path == "/scenarios" or re.fullmatch(r"/scenarios/[\w-]+/versions", path)
    ):
        scenario = Scenario.model_validate(body)
        sid = scenario.scenario_id
        if path != "/scenarios" and path.split("/")[2] != sid:
            raise ApiError(400, "Path and scenario IDs differ")
        previous = store.get(pk, f"SCENARIO#{sid}")
        if previous and previous["scenario_version"] != scenario.scenario_version:
            raise Conflict("Scenario version changed; reload before applying")
        scenario.scenario_version = previous["scenario_version"] + 1 if previous else 1
        key = f"scenarios/{owner}/{sid}/{scenario.scenario_version}-{uuid.uuid4().hex}.json"
        record = dict(
            scenario_id=sid,
            scenario_version=scenario.scenario_version,
            snapshot_key=key,
            name=scenario.name,
            description=scenario.description,
        )
        lock_key = f"VERSION#{sid}#{scenario.scenario_version:06d}"
        store.object_put(key, scenario.model_dump(mode="json"))
        current_write = dict(pk=pk, sk=f"SCENARIO#{sid}", body=record)
        if previous:
            current_write["old"] = previous
        store.atomic_puts([current_write, dict(pk=pk, sk=lock_key, body=record)])
        return 201, scenario.model_dump(mode="json")
    if method == "GET" and path == "/runs":
        return 200, dict(
            runs=sorted(
                [
                    safe_meta(run_owned(store, owner, r["run_id"]))
                    for r in store.list(pk, "RUN#")
                ],
                key=lambda r: r["created_at"],
            )
        )
    if method == "POST" and path == "/runs":
        request = RunRequest.model_validate(body)
        key = require_key(headers)
        payload_hash = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        idem_sk = f"IDEMPOTENCY#run#{key}"
        existing = store.get(pk, idem_sk)
        if existing:
            if existing["hash"] != payload_hash:
                raise Conflict("Idempotency key was used for different run parameters")
            ensure_started(store, existing["run_id"])
            return 202, dict(run_id=existing["run_id"])
        current = scenario_record(store, owner, request.scenario_id)
        if current["scenario_version"] != request.scenario_version:
            raise Conflict("Run must use the current scenario version")
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"aquaagent:{owner}:{key}"))
        snapshot_key = f"runs/{run_id}/scenario-{payload_hash}.json"
        store.object_put(snapshot_key, store.object_get(current["snapshot_key"]))
        meta = dict(
            run_id=run_id,
            owner=owner,
            **request.model_dump(),
            snapshot_key=snapshot_key,
            status="queued",
            event_seq=0,
            created_at=time.time(),
            updated_at=time.time(),
            deployment="aws" if store.cloud else "local development",
        )
        try:
            store.atomic_puts(
                [
                    dict(pk=f"RUN#{run_id}", sk="META", body=meta),
                    dict(pk=pk, sk=f"RUN#{run_id}", body=dict(run_id=run_id)),
                    dict(
                        pk=pk, sk=idem_sk, body=dict(run_id=run_id, hash=payload_hash)
                    ),
                    dict(
                        pk=pk,
                        sk=f"SCENARIO#{request.scenario_id}",
                        old=current,
                        body=current,
                    ),
                ]
            )
        except Conflict:
            existing = store.get(pk, idem_sk)
            if existing and existing["hash"] == payload_hash:
                ensure_started(store, existing["run_id"])
                return 202, dict(run_id=existing["run_id"])
            raise
        store.event(
            run_id, "queued", "Scenario snapshotted; run accepted", event_key="queued"
        )
        ensure_started(store, run_id)
        return 202, dict(run_id=run_id)
    match = re.fullmatch(
        r"/runs/([\w-]+)(?:/(results|events|report|plans)(?:/(\d+)(?:/(decision))?)?)?",
        path,
    )
    if match:
        run_id, resource = match[1], match[2]
        meta = run_owned(store, owner, run_id)
        run_pk = f"RUN#{run_id}"
        if method == "GET" and resource is None:
            return 200, safe_meta(meta)
        if method == "GET" and resource == "events":
            after = int(query.get("after_seq", 0))
            return 200, dict(
                events=[e for e in store.list(run_pk, "EVENT#") if e["seq"] > after],
                last_seq=meta["event_seq"],
            )
        if method == "GET" and resource == "results":
            return 200, dict(
                scenario=store.object_get(meta["snapshot_key"]),
                baseline=store.object_get(meta["baseline_key"])
                if meta.get("baseline_key")
                else None,
                approved=store.object_get(meta["result_key"])
                if meta.get("result_key")
                else None,
                plan=store.object_get(meta["plan_key"])
                if meta.get("plan_key")
                else None,
                agent=store.object_get(meta["agent_key"])
                if meta.get("agent_key")
                else None,
            )
        if method == "GET" and resource == "plans":
            if not meta.get("plan_key") or int(match[3] or 1) != meta["plan_version"]:
                raise ApiError(404, "Plan version not found")
            return 200, store.object_get(meta["plan_key"])
        if method == "GET" and resource == "report":
            if not meta.get("report_key"):
                raise Conflict("Report is not ready")
            if store.cloud:
                url = store.s3.generate_presigned_url(
                    "get_object",
                    Params=dict(Bucket=store.bucket, Key=meta["report_key"]),
                    ExpiresIn=300,
                )
                return 200, dict(download_url=url, expires_seconds=300)
            return 200, dict(report=store.object_get(meta["report_key"]))
        if method == "POST" and resource == "plans" and match[4] == "decision":
            decision = Decision.model_validate(body)
            idem = require_key(headers)
            if (
                decision.plan_version != int(match[3])
                or decision.plan_version != meta.get("plan_version")
                or decision.scenario_version != meta["scenario_version"]
            ):
                raise Conflict("Stale plan or scenario version")
            current = scenario_record(store, owner, meta["scenario_id"])
            if current["scenario_version"] != decision.scenario_version:
                raise Conflict("Scenario edits invalidated this approval")
            prior = store.get(run_pk, "DECISION")
            exact = {**decision.model_dump(), "idempotency_key": idem}
            if prior:
                if any(prior.get(k) != v for k, v in exact.items()):
                    raise Conflict("A different decision already exists")
                if not prior.get("dispatched"):
                    dispatch_decision(store, run_id, meta, prior)
                return 200, dict(accepted=True, duplicate=True)
            if meta["status"] != "awaiting_approval":
                raise Conflict("Run is not waiting for approval")
            plan = store.object_get(meta["plan_key"])
            if decision.decision == "approve" and not plan["feasible"]:
                raise Conflict("Infeasible plan cannot be approved")
            record = {**exact, "timestamp": time.time(), "dispatched": False}
            store.atomic_puts(
                [
                    dict(pk=run_pk, sk="DECISION", body=record),
                    dict(
                        pk=pk,
                        sk=f"SCENARIO#{meta['scenario_id']}",
                        old=current,
                        body=current,
                    ),
                    dict(pk=run_pk, sk="META", old=meta, body=meta),
                ]
            )
            dispatch_decision(store, run_id, meta, record)
            return 200, dict(accepted=True, duplicate=False)
    if method == "POST" and path == "/ws-ticket":
        if not store.cloud:
            return 200, dict(
                transport="polling", reason="Local development uses polling"
            )
        ticket = uuid.uuid4().hex
        digest = hashlib.sha256(ticket.encode()).hexdigest()
        store.put(
            f"TICKET#{digest}",
            "META",
            dict(owner=owner, expires_at=int(time.time()) + 60),
            new=True,
        )
        return 200, dict(ticket=ticket, expires_seconds=60)
    raise ApiError(404, "Endpoint not found")


def dispatch_decision(store, run_id, meta, record):
    pk = f"RUN#{run_id}"
    if store.cloud:
        callback = store.get(pk, "CALLBACK")
        if not callback:
            raise Conflict("Approval callback not yet ready; retry with same key")
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("stepfunctions")
        try:
            client.send_task_success(
                taskToken=callback["token"],
                output=json.dumps(dict(run_id=run_id, decision=record["decision"])),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {
                "TaskDoesNotExist",
                "InvalidToken",
                "TaskTimedOut",
            }:
                raise
            history = client.get_execution_history(
                executionArn=meta["execution_arn"],
                reverseOrder=True,
                maxResults=30,
                includeExecutionData=True,
            )["events"]
            callback_finished = False
            for entry in history:
                if entry.get("type") != "TaskSucceeded":
                    continue
                try:
                    payload = json.loads(
                        entry.get("taskSucceededEventDetails", {}).get("output", "{}")
                    )
                except ValueError:
                    continue
                if (
                    payload.get("run_id") == run_id
                    and payload.get("decision") == record["decision"]
                ):
                    callback_finished = True
                    break
            if not callback_finished:
                raise Conflict(
                    "Approval token expired or already used; inspect run state"
                ) from exc
    store.put(pk, "DECISION", {**record, "dispatched": True})
    store.event(
        run_id,
        "decision",
        f"Operator {record['decision']}d exact plan version {record['plan_version']}",
        event_key="decision",
    )
    if record["decision"] == "reject":
        status(store, run_id, "rejected")
    elif not store.cloud:
        status(store, run_id, "applying")
        threading.Thread(target=local_apply, args=(run_id, store), daemon=True).start()


def handler(event, context=None):
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        path = event.get("rawPath", "/")
        if path.startswith("/api"):
            path = path[4:] or "/"
        claims = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )
        owner = claims.get("sub")
        body = json.loads(event.get("body") or "{}")
        if not isinstance(body, dict):
            raise ApiError(400, "JSON body must be an object")
        if len(event.get("body") or "") > 150000:
            raise ApiError(413, "Request too large")
        headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
        code, result = dispatch(
            method,
            path,
            owner,
            body,
            event.get("queryStringParameters") or {},
            headers,
            get_store(),
        )
        return response(code, result)
    except ApiError as exc:
        return response(exc.code, dict(error=exc.message))
    except Conflict as exc:
        return response(409, dict(error=str(exc)))
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, ValidationError):
            return response(
                422,
                dict(
                    error="Invalid parameters",
                    details=[
                        dict(field=".".join(str(v) for v in e["loc"]), message=e["msg"])
                        for e in exc.errors()
                    ],
                ),
            )
        return response(400, dict(error=str(exc)[:250]))
    except Exception as exc:
        print(
            json.dumps(
                dict(
                    error_type=type(exc).__name__,
                    request_id=event.get("requestContext", {}).get("requestId"),
                )
            )
        )
        return response(
            500,
            dict(error="Backend request failed; see protected CloudWatch diagnostics"),
        )
