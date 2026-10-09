# Verification record

Checked on 9 October 2026, Asia/Calcutta. Local environment: Windows, Python 3.12.14 in the project venv, Node 25.4.0, npm 11.16.0. Source, lockfiles, fixtures and actual evidence are included. No AWS resources were created; AWS CLI identity lookup reports missing credentials.

## Observed checks

| Check | Observed result | Boundary |
|---|---|---|
| pytest | 54 backend tests passing | Actual local physics, API, durable state and AWS adapter emulation |
| Vitest | 2 event-order/recovery tests passing | Sequence deduplication and contiguous recovery cursor |
| Playwright | 12 desktop/mobile flows passing; latest run 35.7 seconds | Actual Chromium browser against an isolated local backend |
| Frontend production build | TypeScript and Vite pass | Built static assets; not an Amplify deployment |
| CDK build/synthesis | Pass; 75 resources; no dependency cycles | Provisioning definition only |
| Linux Lambda packaging | 48 pinned runtime distributions; approximately 149 MB unpacked | Correct target wheels packaged, not invoked on Lambda |
| Groq model access | HTTP 200; configured model accessible | Real external provider account access |
| Groq structured tool call | Valid tool arguments returned | Real external completion; no credentials stored in source |
| Full live investigation, approval and report | Completed; approved result verified and persisted report reopened | Real Groq plus local SQLite/JSON; no live AWS operations |
| Secret-pattern check | No matching real key patterns in source, docs, fixtures or browser bundle | A pattern scan, not a guarantee against every possible secret representation |

The browser flows cover no initial map; Run Simulation reveal; exact-plan approval; actual report download and JSON parsing; draft preview/apply/reset; export/import; stale approval disabled; connection closure; invalid critical-demand edits; agents paused; keyboard and reduced motion; mobile overflow; theme; WebGL fallback; infeasible approval disabled; public route and closed-station rerouting. Chart assertions compare displayed supply rates with downloaded backend report volumes divided by the step duration. The added approval recovery flow checks the stale-plan message, rerunning the applied version, keyboard focus and scrolling to the response plan, and enabled decision controls without silently approving the run. The latest suite uses `.local/approval-qa`, API port 8001 and frontend port 5180; it does not edit the demonstration session. Visual inspection was performed separately in the in-app browser; `images/operating-charts.png` shows the completed baseline/approved comparison for zone B.

A live operator session exposed a confusing status: scenario v3 was awaiting approval after the applied scenario had changed to v5. Its approval was correctly disabled. The workspace now labels that state `Rerun required`, explains both versions and offers an explicit rerun action. Current runs provide `Review response plan` to reach the decision controls. The applied v5 run was started and brought to its verified plan, with approval left to the operator. `images/approval-ready.png` records the enabled controls.

Backend tests cover 24 fixture/horizon combinations, conservation, delivered/critical accounting, transfer limits, closed/unavailable links, empty storage and zero supply, overflow, capacity without added water, reproducibility, nonfinite validation, randomized cases, owner isolation, atomic scenario versions, ordered concurrent events, idempotent run/decision retries, durable node failure/restart, provider failure fallback, actual negotiation budgets/feedback, and indistinguishable loss/reading-error hypotheses. Moto tests execute boto3 DynamoDB transaction/S3 adapters and workflow-dispatch retries in emulation. They do not establish live IAM, Cognito, API Gateway, Lambda or Step Functions behavior.

## Measured simulation outputs

`simulation-benchmarks.json` contains 10 measured runs for each of eight fixtures at 3-, 6- and 12-hour horizons: 240 simulations and 24 summaries. Recorded medians range from 2.46 to 10.89 ms, with a maximum sample of 39.09 ms and maximum step mass residual of 3.19e-13 m³. All values are derived from the engine; these local measurements are not cloud latency guarantees.

`groq-access-check.json` records actual accessible-model/tool-call evidence and observed quota headers: 1,000 requests/day and 8,000 tokens/minute for the checked model/account. These are an observed snapshot and can change. Current completion attempts are bounded to three per run: one investigation call (600 completion tokens maximum) and up to two batched logical-zone negotiation rounds (1,200 each), with 12-second timeouts and no SDK retries. GPT-OSS models use low reasoning effort, supported by [Groq's API reference](https://console.groq.com/docs/api-reference); other configurable models omit that parameter.

`live-run-verification.json` records a real completed investigation and approval against a specific scenario version. The original measured edited run returned HTTP 202 in 24 ms, used one Groq completion with 997 tokens, rejected 14 candidates, and reduced simulated unmet demand from 25.12 m³ to zero while preserving 100% essential demand service. Its approved maximum step mass residual was approximately 1.94e-13 m³. The raw record identifies the scenario/version and distinguishes approval wait time from simulator runtime. If a later clean-fixture showcase run is recorded, use that file's exact current numbers; do not reuse edited-run totals as fixture constants.

The plan used additional explicitly available external supply. Total losses increased in absolute volume; the objective prioritizes meeting demand and maintaining essential service. This is not evidence that all leaks were repaired or that water-loss efficiency improved. No real-world accuracy or optimality claim is made.

`clean-run-verification.json` records the final unedited compound fixture v1 at six hours, started and approved through the in-app browser. It completed with one live Groq completion using 1,266 tokens, reduced unmet demand from 7.48 m³ to zero, preserved 100% critical service, and had an approved mass residual of 1.94e-13 m³. The agent job took 2,499.61 ms and the approved simulation took 5.06 ms locally. The total 17.87 seconds includes human approval time. Its HTTP acceptance latency was not measured. Saved-run reopening was verified in the browser and the persisted report was retrieved through the API. The in-app browser download event timed out, so final report download is not claimed as verified. Screenshots are in `images/dashboard.png` and `images/completed-run.png`. Final QA uses `.local/final-qa`; the showcase uses `.local/demo`, and earlier edited evidence remains in `.local`.

The preceding clean record is historical evidence before live negotiation was added. The current `live-negotiation-verification.json` records compound v1 at six hours with all three Groq calls completed successfully: 3,598 tokens, two live negotiation rounds and no negotiation fallback. Round two receives actual previous trades and remaining budgets. Its agent job took 3,963.61 ms and approved simulation took 5.10 ms locally; unmet demand changed from 7.48 m³ to zero and critical service stayed 100%, with residual 1.94e-13 m³. The negotiated candidate itself failed actual-scenario constraints, so the verifier selected the feasible supply-schedule alternative. Do not imply negotiated transfers were executed as the final plan. Saved-run reopening was verified again. Report downloading is now verified separately on desktop and mobile Chromium by parsing the downloaded approved evidence JSON.

`negotiation-fallback-verification.json` preserves an earlier real run with a successful first Groq round and a second-round BadRequestError, correctly labelled mixed live/fallback. The current tests also inject over-budget, duplicate, nonfinite and no-agreement proposals, completed-response checkpoint interruptions, and unresolved-attempt restarts. Recorded usage sums successful responses; tokens for failures without provider usage are unknown. QA records are preserved in `.local/negotiation-qa`; the final browser suite also ran against the live-enabled `.local/demo` backend and created additional synthetic versions/runs.

## Corrections found during verification

- Converted NumPy scalar counts before JSON persistence and added timezone data for Windows.
- Preserved integral DynamoDB numbers as integers so event/version keys serialize correctly.
- Made version/idempotency writes transactional and immutable snapshot object keys unique to their request payload.
- Removed an Amplify/Cognito circular dependency by keeping frontend environment values on the branch.
- Used explicit structured tool selection and a larger bounded completion budget after a provider response failed validation; fallback was shown truthfully during that failure.
- Prebundled lazy chart/3D development dependencies after a first-use optimizer reload reset the UI during a browser test. The expanded suite subsequently passed.
- Separated native Windows test discovery from packaged Linux Lambda dependencies.

## Remaining deployment checks and limitations

Live Amplify hosting, Cognito JWT/PKCE, API Gateway authorization, actual Lambda runtimes/cold starts, Step Functions callback/retry behavior, IAM policies, DynamoDB/S3 persistence, Secrets Manager storage, WebSocket delivery/reconnect and presigned downloads must still be tested in the authenticated AWS account. No cloud latency or deployment URL is invented. Follow `DEPLOYMENT.md` before claiming these acceptance checks complete.

The optional lazy 3D vendor chunk remains approximately 891 KB uncompressed (237 KB gzip); the production build still warns about it. Its rendering is deferred to browser idle time, renders on demand at capped DPR, and unmounts offscreen. CSS fallback and an error boundary retain all essential information. The initial application chunk is approximately 422 KB (137 KB gzip), and the expanded chart chunk is 382 KB (109 KB gzip). Font assets now include two Latin files totalling 61.76 KB instead of seven files totalling 127.56 KB; broader characters use system fallback. These changes do not establish a measured frame-rate improvement. Upstream Three/Fiber may emit a Clock deprecation warning in development.

All station/route/weather/footfall data is synthetic. Public guidance cites CDC environmental precautions and contains no diagnosis or personal illness probability. Search/planning is bounded and heuristic. Original project licensing and authenticated AWS profile/region remain owner choices. Source publication was authorized to the Varuna GitHub repository; Amplify connection and actual deployment remain pending.
