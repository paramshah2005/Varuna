# API contract

The cloud base URL is the CDK `HttpUrl` output; local development uses `/api` through the Vite proxy. JSON schemas are derived from Pydantic; `data/scenario.schema.json` validates import/export. Unknown fields, nonfinite numbers, unsafe IDs, invalid ranges and cross-field inconsistencies are rejected. Public endpoints do not accept infrastructure-changing commands.

Protected endpoints require the JWT authorizer and use the verified `sub` as owner. Requests never accept an owner parameter. Wrong-owner run reads return 404. Protected scenario partitions are owner scoped; approved plans reference immutable run snapshots.

| Method | Path | Contract |
|---|---|---|
| GET | /bootstrap | Applied scenarios and original synthetic reset baselines |
| GET | /zones, /connections, /stations | Records for selected `scenario_id` |
| GET | /scenarios | Current scenario metadata |
| GET | /scenarios/{id} | Current full scenario |
| GET | /scenarios/{id}/versions/{version} | Historical snapshot |
| POST | /scenarios | Import/create; existing scenarios require current version |
| POST | /scenarios/{id}/versions | Validate and atomically create a new version from current version |
| POST | /scenario-previews | `{scenario, horizon}`; draft and applied deterministic outputs; no version change |
| POST | /runs | `{scenario_id, scenario_version, horizon, agents_active}`; HTTP 202 and run ID |
| GET | /runs | Owned run summaries for reopening |
| GET | /runs/{id} | Compact run metadata, status, versions, event sequence and measured totals |
| GET | /runs/{id}/results | Scenario snapshot, baseline/approved outputs, plan and agent evidence |
| GET | /runs/{id}/events?after_seq=N | Ordered persisted events after the last contiguous sequence |
| GET | /runs/{id}/plans/{version} | Exact current plan version |
| POST | /runs/{id}/plans/{version}/decision | `{decision,plan_version,scenario_version}`; approve/reject exact version |
| GET | /runs/{id}/report | Cloud: authorized S3 download URL valid for 300 seconds; local: report JSON |
| POST | /ws-ticket | Single-use owner-bound connection ticket valid for 60 seconds |
| GET | /public/stations | Eligible synthetic facilities and demo environmental zone context |
| POST | /public/demo-route | `{zone_id,accessible,scenario_id}` or optional coordinates; separate pedestrian route, no location retention |

Run creation and approval require `Idempotency-Key` with 8–128 letters, numbers, underscores or hyphens. Same-key run retries return the same run; changed parameters conflict. A different decision/key against an existing decision conflicts. Scenario edits invalidate old approvals. Errors use `{error, details?}` with 400/422 invalid data, 401 missing identity, 404 missing or wrong-owner record, 409 version/idempotency conflict, and 500 sanitized backend failure.

Run statuses include queued, simulating, baseline_complete, investigating, plan_ready, awaiting_approval, applying, verified, completed, infeasible, rejected, failed and job_retrying. The frontend polls compact state and fetches result payloads on status changes. No visual playback control cancels a workflow. Cloud cancellation is not exposed in this version.

DynamoDB partitions include OWNER#{sub}, RUN#{uuid}, CONNECTION#{connection_id} and TICKET#{sha256}. Sort keys identify current scenarios, historical versions, runs, idempotency requests, META, padded EVENT#{sequence}, EVENTKEY#{step}, AGENTSTATE, CALLBACK, DECISION and SUB#{connection_id}. Snapshot/result/plan/report objects use private S3 keys. Version and run-idempotency multi-record writes are transactional. Expiry is checked explicitly rather than relying on eventual DynamoDB TTL removal.

WebSocket connect supplies the short-lived ticket to a Lambda authorizer. Subscribe uses `{action:"subscribe",run_id}` and checks run ownership plus connection expiry. Publisher removes stale clients on Gone and never publishes to a different owner. Clients deduplicate by sequence; out-of-order messages do not advance the recovery cursor across gaps. Polling works independently of WebSocket connection/reconnection.
