# Simulation accounting and assumptions

Rates are m³/hour; storage and step amounts are m³. Each step is 0.25 hours. Horizons are 3, 6 or 12 hours. Configurations distinguish population, baseline demand, explicit demand multiplier, external throughput, upstream available supply, scheduled supply, initial storage, storage capacity, minimum reserve, critical demand, service target and allocation priority. Temperature and humidity have synthetic source/timestamp metadata and do not independently change consumption.

For zone i:

`S_end = S_start + external_gross - supply_loss + incoming_received - outgoing_donor - delivered - overflow`

Supply loss is `external_gross × supply_loss_fraction`; its denominator is gross external inflow before that water enters the usable pool. Connection loss is `donor_outflow × connection_loss_fraction`; receiver inflow is donor outflow minus this loss. A donor's reported connection-loss attribution is informational; the full donor outflow already includes that loss, so it is never subtracted again from donor storage.

External water enters the available pool once. Transfers then exchange water, demand is delivered from the pool, and overflow is recorded before storage is capped. Connections use one actual direction per step and respect control/availability/throughput and donor surplus. Donors retain local requested demand and minimum reserve before offering water. Stable IDs break ties. This deterministic greedy allocator is a reproducible bounded heuristic, not a globally optimal hydraulic solver.

Essential demand is a subset of total demand: `critical_served = min(critical_requested, delivered)`. It is not added to requested total a second time. The deterministic verifier checks essential demand and minimum total-service fraction for every zone in every step. A plan that meets aggregate critical totals but harms essential demand in one step is rejected.

Network conservation checks start storage plus gross external inflow against end storage plus delivered demand, all supply/connection losses, and overflow. Internal transfers cancel. Each step uses a scale-aware tolerance of `1e-8 × max(1, starting_storage + external_inflow)`; measured residuals are saved. Storage is clipped only after verified accounting, and overflow explains the excess explicitly.

Increasing storage/transfer capacity never adds water. A supply schedule may draw only up to explicit available upstream supply, never merely nominal throughput. Upstream external supply represents an explicitly scheduled boundary inflow; no shared finite reservoir is implied. Local storage is finite. A future shared reservoir requires a separate storage balance and withdrawal limit.

Repairs consume one crew for the configured duration. Completion restores a connection to configured capacity and the nominal 2% connection loss. These are synthetic engineering assumptions. Restoring a connection does not guarantee that essential demand can be met; candidate and final outcomes are simulated again. Supply-restoration fixtures carry an explicit hour and recovered supply, validated against configured upstream availability.

The engine exposes configuration hashes, versions, per-step timestamps, source/data-quality labels, time to reserve where a declining trajectory makes it meaningful, classification and reasons. Forecast tools vary demand by ±10% around the applied multiplier and label resulting storage bounds scenario ranges, not calibrated intervals. A single deterministic engine output has no claim to real-world predictive accuracy.

Injected incident loss values are withheld from the agent configuration. Agents receive nominal loss assumptions and aggregate observations; verifier jobs hold the simulator's complete scenario. Candidate localization compares residual fit and keeps alternatives. No fit is a calibrated probability, and faulty aggregate readings can be indistinguishable from losses.

Hypothesis magnitudes are estimated from observed residuals and explicit inflow/step units, then simulated. A constant measurement bias and supply-loss fraction can fit the same aggregate residual equally well; a regression test preserves that ambiguity. Demand alternatives simulate additional unobserved consumption against nominal demand. Existing station requirements are included in each zone's baseline total; proposed new points add 2 m³/h separately. Candidate site footfall is a synthetic 12% of zone population, capacity is 60, and C/F candidate sites are ineligible for pedestrian access. These are disclosed fixture assumptions, not a trained siting model.
