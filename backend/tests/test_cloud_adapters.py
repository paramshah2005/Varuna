import hashlib
import time
import boto3
import pytest
from moto import mock_aws
from backend.api.storage import Store, Conflict
from backend.api import websocket
from backend.api.handler import dispatch
from backend.simulation.fixtures import fixtures


@mock_aws
def test_dynamodb_transactions_s3_evidence_and_ttl(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    monkeypatch.setenv("TABLE_NAME", "aqua-test")
    monkeypatch.setenv("BUCKET_NAME", "aqua-test-evidence")
    monkeypatch.delenv("PUBLISHER_FUNCTION", raising=False)
    client = boto3.client("dynamodb")
    client.create_table(
        TableName="aqua-test",
        KeySchema=[
            dict(AttributeName="pk", KeyType="HASH"),
            dict(AttributeName="sk", KeyType="RANGE"),
        ],
        AttributeDefinitions=[
            dict(AttributeName="pk", AttributeType="S"),
            dict(AttributeName="sk", AttributeType="S"),
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    boto3.client("s3").create_bucket(
        Bucket="aqua-test-evidence",
        CreateBucketConfiguration=dict(LocationConstraint="ap-south-1"),
    )
    store = Store()
    store.atomic_puts(
        [
            dict(
                pk="RUN#cloud", sk="META", body=dict(owner="a", event_seq=0, value=2.5)
            ),
            dict(pk="OWNER#a", sk="RUN#cloud", body=dict(run_id="cloud")),
        ]
    )
    for i in range(3):
        store.event("cloud", "test", f"Measured event {i}", event_key=f"step-{i}")
    assert store.event("cloud", "test", "retry", event_key="step-0")["seq"] == 1
    assert [e["seq"] for e in store.list("RUN#cloud", "EVENT#")] == [1, 2, 3]
    old = store.get("RUN#cloud", "META")
    store.compare_put("RUN#cloud", "META", old, {**old, "value": 3.25})
    with pytest.raises(Conflict):
        store.compare_put("RUN#cloud", "META", old, old)
    key = store.object_put("runs/cloud/evidence.json", dict(balance=0.0, verified=True))
    assert store.object_get(key) == dict(balance=0.0, verified=True)
    store.put("ticket", "META", dict(expires_at=2000000000, owner="a"))
    prior = store.get("ticket", "META")
    store.compare_put("ticket", "META", prior, {**prior, "used": True})
    assert (
        client.get_item(
            TableName="aqua-test", Key=dict(pk=dict(S="ticket"), sk=dict(S="META"))
        )["Item"]["expires_at"]["N"]
        == "2000000000"
    )


def test_websocket_ticket_replay_expiry_and_wrong_owner(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(websocket, "get_store", lambda: store)
    ticket = "a" * 32
    digest = hashlib.sha256(ticket.encode()).hexdigest()
    store.put(
        f"TICKET#{digest}", "META", dict(owner="a", expires_at=int(time.time()) + 60)
    )
    event = dict(
        queryStringParameters=dict(ticket=ticket),
        methodArn="arn:aws:execute-api:ap-south-1:123456789012:test/live/$connect",
    )
    assert websocket.authorizer(event, None)["principalId"] == "a"
    with pytest.raises(Exception):
        websocket.authorizer(event, None)
    store.put("RUN#owned", "META", dict(owner="b"))
    connected = dict(
        requestContext=dict(
            connectionId="connection", routeKey="$connect", authorizer=dict(owner="a")
        )
    )
    assert websocket.handler(connected, None)["statusCode"] == 200
    subscribed = dict(
        requestContext=dict(connectionId="connection", routeKey="subscribe"),
        body='{"run_id":"owned"}',
    )
    assert websocket.handler(subscribed, None)["statusCode"] == 403
    store.put(
        "CONNECTION#expired",
        "META",
        dict(owner="a", expires_at=0, connection_id="expired"),
    )
    subscribed["requestContext"]["connectionId"] = "expired"
    assert websocket.handler(subscribed, None)["statusCode"] == 401


@mock_aws
def test_cloud_versioning_and_start_dispatch_retry(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    monkeypatch.setenv("TABLE_NAME", "aqua-version-test")
    monkeypatch.setenv("BUCKET_NAME", "aqua-version-evidence")
    monkeypatch.delenv("PUBLISHER_FUNCTION", raising=False)
    boto3.client("dynamodb").create_table(
        TableName="aqua-version-test",
        KeySchema=[
            dict(AttributeName="pk", KeyType="HASH"),
            dict(AttributeName="sk", KeyType="RANGE"),
        ],
        AttributeDefinitions=[
            dict(AttributeName="pk", AttributeType="S"),
            dict(AttributeName="sk", AttributeType="S"),
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    boto3.client("s3").create_bucket(
        Bucket="aqua-version-evidence",
        CreateBucketConfiguration=dict(LocationConstraint="ap-south-1"),
    )
    sfn = boto3.client("stepfunctions")
    arn = sfn.create_state_machine(
        name="AquaTest",
        definition='{"StartAt":"Done","States":{"Done":{"Type":"Pass","End":true}}}',
        roleArn="arn:aws:iam::123456789012:role/test",
    )["stateMachineArn"]
    monkeypatch.setenv("STATE_MACHINE_ARN", arn)
    store = Store()
    draft = fixtures()[0].model_dump(mode="json")
    code, applied = dispatch(
        "POST", "/scenarios/normal/versions", "owner", draft, {}, {}, store
    )
    assert code == 201 and applied["scenario_version"] == 2
    old = dispatch("GET", "/scenarios/normal/versions/1", "owner", {}, {}, {}, store)[1]
    assert old["scenario_version"] == 1
    real_client = boto3.client
    calls = []

    class Flaky:
        def start_execution(self, **args):
            calls.append(args)
            if len(calls) == 1:
                raise RuntimeError("Injected workflow dispatch failure")
            return sfn.start_execution(**args)

    monkeypatch.setattr(
        boto3,
        "client",
        lambda service, *args, **kwargs: (
            Flaky()
            if service == "stepfunctions"
            else real_client(service, *args, **kwargs)
        ),
    )
    request = dict(
        scenario_id="normal", scenario_version=2, horizon=3, agents_active=False
    )
    headers = {"idempotency-key": "cloud-start-001"}
    with pytest.raises(RuntimeError):
        dispatch("POST", "/runs", "owner", request, {}, headers, store)
    code, started = dispatch("POST", "/runs", "owner", request, {}, headers, store)
    assert code == 202
    assert store.get(f"RUN#{started['run_id']}", "META")["execution_arn"]
    assert dispatch("POST", "/runs", "owner", request, {}, headers, store)[1] == started
    assert len(calls) == 2
    assert len(sfn.list_executions(stateMachineArn=arn)["executions"]) == 1
