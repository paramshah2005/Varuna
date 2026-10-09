# YouTube demo script

Target length: 2 minutes 45 seconds. This is a script, not a rendered video. Use a completed verified run when discussing outcomes; do not present a replay as a live inference call. Do not show secrets or AWS callback tokens.

| Time | Screen/action | Narration |
|---|---|---|
| 0:00–0:15 | Initial dashboard, empty forecast KPIs | “AquaAgent helps neighborhoods respond to heatwaves and water disruptions. These six zones are synthetic. Before a run, forecast values stay empty.” |
| 0:15–0:35 | Choose compound scenario; Run Simulation | “Demand changes through an explicit scenario multiplier. Starting the simulation reveals the workspace. Every value comes from the same 15-minute water-balance engine.” |
| 0:35–0:55 | Select affected zone; storage chart and balance residual | “We account for inflow, transfers, losses, consumption, overflow and finite storage. The saved residual shows whether water conservation holds.” |
| 0:55–1:15 | Agent activity, candidate fits and zone proposals | “The agent tests ambiguous observations. Groq also proposes bounded offers and requests for six logical zone roles. The next round receives actual trade feedback. Deterministic code checks every proposal; fallback is labelled.” |
| 1:15–1:35 | Expand rejected candidates; show verified plan | “Closing connections can harm essential supply. The verifier rejects those candidates and checks every step. Available upstream supply limits the proposed schedule; capacity alone creates no water.” |
| 1:35–1:55 | Approve exact plan; outcome comparison; evidence report | “Approval belongs to this exact scenario and plan version. The backend simulates the actions again, verifies the outcome, and persists the evidence.” |
| 1:55–2:15 | Demand edit; Preview; Apply; stale approval disabled | “An isolated draft shows network effects without changing applied data. Applying creates a new version and invalidates earlier approval. JSON export and saved runs keep scenarios reviewable.” |
| 2:15–2:35 | Public page; choose zone; station closure; walking route | “The public view filters eligible synthetic cooling centers and uses a separate walking graph. It does not diagnose illness or store precise location.” |
| 2:35–2:45 | Verified deployment/evidence page | “AquaAgent combines measurable simulation, bounded investigation and human oversight. The documentation records exactly what has been tested and what remains a model assumption.” |

Show actual AWS evidence only after deployment smoke tests pass. Until then describe the cloud architecture as provisionable infrastructure, not a live hosted demonstration. Keep the final edit below 3:00 including titles and transitions.
