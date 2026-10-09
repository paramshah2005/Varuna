# AquaAgent implementation plan

Planning document prepared on 2026-10-09, Asia/Calcutta. The user confirmed the hackathon has opened on 2026-10-09 before implementation began. The supplied specification is the source of truth.

## Blocking inputs and verified environment

- Implementation timing confirmed by the user. Preserve genuine timestamps; do not backdate commits.
- The workspace was empty and was not a Git repository when inspected.
- Git, Node.js 25.4.0, npm 11.16.0, Python 3.11.9, and AWS CLI 1.46.1 are available. Select a supported Node LTS release for reproducible development and Amplify builds before implementation.
- The supplied name `yoopat` is not an available AWS CLI profile: `aws sts get-caller-identity --profile yoopat` failed with profile not found. Account identity, target region, permissions, and Groq secret remain unverified.
- No WaterWise HTML or dashboard reference image was supplied. Use the written operational-dashboard direction.
- AWS Amplify is the requested hosting target. No alternative hosting platform is planned.

## Implementation sequence and evidence gates

1. Build Pydantic configuration/state/output models, eight scenario fixtures, and the deterministic NumPy simulation. Test mass conservation and boundary cases before adding agent decisions. Benchmark every fixture at 3, 6, and 12 hours; record actual timings and errors.
2. Build React/Vite dashboard, six-zone table, responsive public page shell, and the Scenario lab. Reveal the SVG simulation graph only after Run Simulation. Add isolated drafts, previews, versioned apply, reset, validated JSON import/export, and before/after charts driven by simulator outputs.
3. Provision Cognito, HTTP API, WebSocket API, bounded Python Lambdas, Step Functions Standard, DynamoDB, S3, Secrets Manager integration, and CloudWatch through TypeScript CDK. Deploy and test the actual AWS request lifecycle before claiming cloud operation.
4. Add bounded LangGraph investigation, typed simulation tools, persistent state, exact-version plans, deterministic verification, and callback approval. Probe Groq account model access and tool calling before enabling a configurable live model. Display deterministic fallback when the provider is unavailable.
5. Add bounded zone negotiation, isolation search, repair sequences, operating schedules, and candidate water-point evaluation. Simulate proposals and record both rejected and accepted candidates.
6. Add seeded pedestrian routing and station eligibility filters. Use manual location selection by default; request GPS only on user action and do not persist precise location. Keep environmental guidance independent of simulated allocation.
7. Complete restrained R3F/Drei accents, GSAP transitions, reduced-motion and WebGL fallbacks, Vitest/Playwright flows, deployment smoke tests, credits, disclosure, submission text, and a timed demo script under three minutes.

## Deterministic accounting convention

Use steps of 0.25 hours. Rates are cubic metres per hour; storage and per-step accounting are cubic metres. Configurations distinguish supply capacity from scheduled and available supply.

For each step, compute scheduled external inflow capped by available throughput, then deduct supply loss once from that gross inflow. Put usable inflow into the zone pool with starting storage. Compute one signed flow per connection; clip it by capacity, availability, control, direction, and donor water. Donor outflow equals receiver inflow plus connection loss. Never compute independent opposite flows on the same connection.

Allocate delivered demand from the resulting pool, with critical demand as a subset of total requested demand. Account for any configured zone-pool loss at its documented location and denominator exactly once. Record overflow explicitly when water exceeds storage capacity after transfers and consumption. End storage equals start storage plus usable external inflow plus received transfers minus outgoing transfers minus delivered demand minus zone-pool loss minus overflow.

Network verification sums start storage and gross external input against end storage, delivered consumption, supply losses, zone losses, connection losses, and overflow. Internal transfers cancel. Use a documented scale-aware floating-point tolerance and save residuals. Temperature changes demand only through the explicit scenario multiplier.

Transfer allocation is deterministic, uses stable ID ordering for ties, and cannot borrow water from a future step. Candidate schedules must pass the same engine and verifier. Capacity edits never alter starting water. Shared reservoirs, if used, are explicit finite sources with their own balance and withdrawal caps.

## Schema and version boundaries

Keep zone configuration, simulation state, derived outputs, observations, incident ground truth, connection configuration, and station records separate. Exported operator scenarios contain visible configuration, not hidden evaluation truth or secrets.

All protected records carry operator ownership. Runs identify scenario ID/version, model version, seed, horizon, and a hash of the complete simulation configuration. Plans identify run ID and plan version plus the source scenario version. Applied edits restart from edited initial conditions in v1; they create a scenario version and invalidate earlier approval eligibility.

Observations may be missing or faulty. Agent inputs include only the declared observation view. An imbalance triggers investigation rather than a leak assertion. Candidate fits are rankings, not calibrated probabilities. Forecast bands are labelled scenario ranges.

## API surface

Protected endpoints:

- GET /zones, /connections, /stations, /scenarios
- GET /scenarios/{scenario_id}/versions/{scenario_version}
- POST /scenarios and POST /scenarios/{scenario_id}/versions
- POST /scenario-previews for isolated draft comparison
- POST /runs with an idempotency key; return HTTP 202 with run ID
- GET /runs/{run_id}, /runs/{run_id}/results, /runs/{run_id}/events?after_seq=N
- GET /runs/{run_id}/plans/{plan_version}
- POST /runs/{run_id}/plans/{plan_version}/decision with approval/rejection, exact scenario version, and idempotency key
- GET /runs/{run_id}/report for an authorized short-lived S3 download
- POST /ws-ticket for a short-lived, single-use, owner-bound connection ticket

Read-only public endpoints:

- GET /public/stations with eligibility filters
- POST /public/demo-route to calculate a route on a separate pedestrian graph without retaining the request location or modifying infrastructure state

Document schemas, errors, ownership checks, and version conflicts. Cloud run cancellation is a separate endpoint only if implemented and verified; visual playback controls must not imply cancellation.

## Cloud persistence and workflow

Use a DynamoDB partition/sort-key design for owner-scoped scenarios, run metadata, padded monotonic event sequence keys, plan versions, approval decisions, idempotency records, WebSocket tickets/connections/subscriptions, and bounded agent state. Use conditional version writes and transactions for cross-record invariants. TTL is cleanup only; explicitly reject expired tickets and connections at request time.

Store complete scenario snapshots, long time series, candidate evidence, and reports in private S3 objects. DynamoDB and Step Functions carry object keys and compact summaries, not large arrays. Use least-privilege grants and short-lived authorized presigned downloads. Public station output cannot expose protected operator records.

Step Functions owns orchestration: snapshot -> baseline -> investigation/planning -> verifier -> approval callback -> approved simulation -> outcome verification -> report. An infeasible plan records shortfalls and escalation instead of entering executable approval. A preparation Lambda stores the callback token server-side and returns; no invocation waits for approval. Decisions are bound to the exact current plan and scenario. Duplicate decision retries must return the original result and must not execute actions twice. Workflow errors persist an explicit failed status and event.

LangGraph owns bounded tool selection inside agent jobs. Persist explicit JSON graph state, completed node/tool IDs, counters, next node, and configuration hash after each bounded step. On retry, load the saved state and continue from the persisted boundary; do not describe an in-memory saver as durable. Tool result writes and graph state advancement must share an idempotent boundary. Step Functions retries resume these jobs without starting a competing supervisor.

WebSocket $connect uses a Lambda authorizer and an owner-bound ticket rather than sending a long-lived access token in a URL. Every subscribe operation validates ownership, connection expiry, and run ID. Persist events before publishing; clients recover missed events from HTTP using the last contiguous sequence number. Deduplicate repeated events. Polling remains a working fallback. Remove stale clients when the management API reports Gone.

## Agent budgets and tools

The implemented limit is three completion attempts per run: one investigation call and up to two batched logical-zone negotiation rounds. Investigation allows 600 completion tokens; each negotiation round allows 1,200. Timeouts are 12 seconds and SDK retries are disabled. Persist attempt reservations and completed round responses, and cache deterministic tool results by complete input/model hash.

Validate typed tools for zone state, history, baseline comparison, candidate faults, forecasts, isolation, allocation, supply schedules, recovery, plan validation, station discovery, water-point sites, and evidence reports. Reject invalid IDs, nonfinite values, unknown action types, malformed model arguments, and constraint violations. Never execute generated code.

Persist tool arguments/results, model identity, provider call/token counts, timings, mode (live Groq or deterministic fallback), and concise public reasons. Do not store private chain-of-thought. Verify a forced structured tool call and rate-limit headers using the selected account; public model documentation is not proof of account access or quota.

## Frontend and public experience

Use pale blue backgrounds, white rounded cards, navy text, royal-blue controls, and soft borders. Provide the five requested sidebar destinations, search, explicit synthetic/live labels, and accessible theme controls. Display an empty/not-run state for forecast-only KPIs.

The workspace contains SVG zone selection, connection controls, parameter draft/apply state, backend-driven charts, neighbor comparison, progress, and tool evidence. Preserve applied versions while previews are in flight; discard stale preview responses after newer drafts. Accessible labels include units and loss denominators. Disable approval after scenario changes.

Use ordinary matte geometry with orthographic cameras, capped pixel ratio, offscreen pausing, shared canvases where practical, and SVG/CSS equivalents. Respect reduced motion for transitions and scrolling. Essential values always appear in text.

Station eligibility independently checks operating hours/timezone, open status, accessibility, remaining occupancy, water availability, source age, and synthetic designation. Candidate water points are proposals and include simulated additional demand. Seeded walking paths do not use the water-transfer graph. No illness probability or LLM diagnosis is planned; any symptom content requires a separately reviewed authoritative deterministic rule set.

## Acceptance evidence and delivery

Record pytest physics/property and API ownership/version/idempotency results, Vitest form/state results, and Playwright critical-flow/mobile/keyboard/reduced-motion results. Include WebSocket missed-event recovery and polling, durable agent retry, provider failure, hidden-truth exclusion, and hard-constraint rejection tests.

Cloud smoke tests must prove Cognito authorization, accepted run response, Step Functions execution, Lambda operations, DynamoDB ordered events, S3 evidence, exact-version approval, and Amplify SPA navigation. Report actual measured latency, calls, invariant residuals, and deployment URLs. Clearly distinguish local tests, CDK synthesis, and live AWS verification.

Deliver pinned manifests and lockfiles, example environments with placeholders, JSON schemas and fixtures, CDK and Amplify build/rewrite settings, architecture/setup/demo/cleanup documentation, licence credits, AI-tool disclosure, measured limitations, submission writeup, and an under-three-minute demo script. Do not commit/push until explicitly authorized; preserve actual event-dated history.

## Primary references checked

- AWS callback integrations: https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html
- AWS WebSocket Lambda authorization: https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-lambda-auth.html
- Amplify redirects and SPA rewrites: https://docs.aws.amazon.com/amplify/latest/userguide/redirects.html
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- Groq models: https://console.groq.com/docs/models
- Groq tool use: https://console.groq.com/docs/tool-use/overview
- Groq quotas and rate-limit headers: https://console.groq.com/docs/rate-limits
