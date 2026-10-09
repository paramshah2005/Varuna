# AquaAgent submission draft

## Problem and implementation

Heatwaves and supply disruptions put local water reserves, hospitals, cooling centers and other essential services under pressure. AquaAgent helps an operator examine synthetic neighborhood conditions, test responses, protect essential supply and retain the evidence behind an approved action.

Six consistent neighborhood zones connect through an abstract water-transfer network. A Python/NumPy simulator accounts for every 15-minute inflow, transfer, loss, consumption, overflow and storage change. The React/TypeScript dashboard exposes manual scenario drafts and measured before/after network effects. Bounded LangGraph investigation tests alternative loss, demand and faulty-reading explanations rather than asserting that every imbalance is a leak. Groq can select a structured hypothesis test; provider failure is labelled as deterministic fallback. A deterministic verifier rejects harmful plans, and exact-version human approval gates action simulation.

The public mobile interface independently checks synthetic station operating hours, accessibility, occupancy and water availability. It routes on a separate seeded pedestrian graph. Environmental guidance is separate from water allocation; precise GPS is not retained and no personal illness probability is produced.

## AWS use: deployment definition, pending live verification

The CDK stack defines Amplify Git hosting, Cognito, API Gateway HTTP and WebSocket, seven Python Lambdas, Step Functions Standard with server-side approval callback, DynamoDB, private S3 evidence, imported Secrets Manager credentials and CloudWatch observability. CDK synthesis and dependency checks are local evidence only. At the time of this draft, no deployed AWS use is claimed because authenticated account/profile access and repository connection are pending.

Before submitting, replace this paragraph with actual Amplify URL, region, deployment date, successful workflow/run IDs, and verified DynamoDB/S3 operations. Do not state AWS services were used in production until those checks succeed.

## Evidence and limitations

Physics/API/agent and desktop/mobile UI verification results are recorded in `VERIFICATION.md`; raw simulation measurements and provider access evidence have separate JSON files. All scenario values are synthetic. There is no trained demand predictor, hydraulic solver, pipe-level leak localization, calibrated fit probability, verified real station database, energy optimization or medical diagnosis. Bounded candidate search and greedy transfer allocation are documented heuristics. Live Groq selects investigation tools and produces batched proposals for six logical zone-agent roles in up to two negotiation rounds. Deterministic coordination and engine verification decide whether transfers and actions are feasible. These roles do not run as six independent model processes, and provider/no-agreement fallback remains explicitly labelled.

Implementation began after the event-open confirmation. Codex, an OpenAI AI coding tool, assisted implementation, test writing, debugging, UI construction and documentation. Dependency licences and font/icon/source credits are in `THIRD_PARTY.md`. No external dataset or visual reference was supplied; the fixtures and geometric accents were generated for this project.
