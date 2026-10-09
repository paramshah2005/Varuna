from backend.simulation.models import Action
from backend.simulation.models import StrictModel
from pydantic import Field
from math import floor


class CheckpointFailure(RuntimeError):
    pass


class ZoneProposal(StrictModel):
    zone_id: str = Field(pattern=r"^[A-F]$")
    request_rate: float = Field(ge=0, le=1000)
    offer_rate: float = Field(ge=0, le=1000)
    reason: str = Field(min_length=1, max_length=180)


class RoundProposals(StrictModel):
    proposals: list[ZoneProposal] = Field(min_length=6, max_length=6)


def negotiate(scenario, horizon, baseline, rounds=2, propose=None):
    states = {s["id"]: s for s in baseline["time_series"][-1]["zones"]}
    requests = {
        z.id: max(0, z.reserve - states[z.id]["storage"]) / horizon
        for z in scenario.zones
    }
    offers = {
        z.id: max(0, states[z.id]["storage"] - z.reserve) / horizon
        for z in scenario.zones
    }
    messages, trades, used = [], [], {c.id: 0.0 for c in scenario.connections}
    priorities = {z.id: z.priority for z in scenario.zones}
    live_rounds, fallback_reasons = 0, []
    for round_number in range(1, rounds + 1):
        if not any(value > 1e-8 for value in requests.values()):
            break
        decisions = None
        if propose:
            context = dict(
                round=round_number,
                zones=[dict(zone_id=z.id, priority=z.priority,
                            maximum_request_rate=floor(requests[z.id] * 1000) / 1000,
                            maximum_offer_rate=floor(offers[z.id] * 1000) / 1000) for z in scenario.zones],
                connections=[dict(id=c.id, source=c.source, target=c.target,
                                  bidirectional=c.bidirectional, capacity=c.capacity,
                                  available=c.available, control=c.control, loss=c.loss)
                             for c in scenario.connections],
                previous_trades=trades,
            )
            try:
                proposals = RoundProposals.model_validate(propose(context)).proposals
                if {p.zone_id for p in proposals} != set(requests):
                    raise ValueError("Each zone must propose exactly once")
                if any(p.request_rate > requests[p.zone_id] + 1e-6
                       or p.offer_rate > offers[p.zone_id] + 1e-6 for p in proposals):
                    raise ValueError("Proposal exceeds measured water budget")
                decisions = {p.zone_id: p for p in proposals}
                live_rounds += 1
            except CheckpointFailure:
                raise
            except Exception as exc:
                fallback_reasons.append(f"Round {round_number}: {type(exc).__name__}; deterministic fallback")
        round_requests = {z: decisions[z].request_rate if decisions else requests[z] for z in requests}
        round_offers = {z: decisions[z].offer_rate if decisions else offers[z] * 0.5 for z in offers}
        for z in scenario.zones:
            messages.append(
                dict(
                    round=round_number,
                    zone_id=z.id,
                    request_rate=round_requests[z.id],
                    offer_rate=round_offers[z.id],
                    maximum_offer_rate=offers[z.id],
                    maximum_request_rate=requests[z.id],
                    reason=decisions[z.id].reason if decisions else "Forecast reserve deficit or finite storage surplus; donor retains its minimum reserve",
                    decision_mode="live Groq zone proposal" if decisions else "deterministic fallback",
                )
            )
        progress = False
        for receiver in sorted(requests, key=lambda z: (-priorities[z], z)):
            for c in sorted(scenario.connections, key=lambda c: c.id):
                if (
                    not c.available
                    or c.control == "closed"
                    or receiver not in {c.source, c.target}
                ):
                    continue
                donor = c.source if receiver == c.target else c.target
                if donor == c.target and not c.bidirectional:
                    continue
                capacity = c.capacity * (0.5 if c.control == "restricted" else 1)
                amount = min(
                    round_offers[donor],
                    offers[donor],
                    round_requests[receiver] / (1 - c.loss),
                    requests[receiver] / (1 - c.loss),
                    max(0, capacity - used[c.id]),
                )
                if amount <= 1e-8:
                    continue
                received = amount * (1 - c.loss)
                offers[donor] -= amount
                requests[receiver] -= received
                round_offers[donor] -= amount
                round_requests[receiver] -= received
                used[c.id] += amount
                trades.append(
                    dict(
                        round=round_number,
                        connection_id=c.id,
                        donor=donor,
                        receiver=receiver,
                        outflow_rate=amount,
                        inflow_rate=received,
                        loss_rate=amount - received,
                    )
                )
                progress = True
        if not progress and decisions:
            fallback = negotiate(scenario, horizon, baseline, rounds=rounds)
            fallback["messages"] = [*messages, *fallback["messages"]]
            fallback["fallback_reasons"] = [*fallback_reasons, "Live proposals reached no agreement; deterministic fallback"]
            fallback["live_rounds"] = live_rounds
            return fallback
        if not progress:
            break
    actions = [
        Action(type="connection", target=c.id, value=used[c.id])
        for c in scenario.connections
    ]
    return dict(
        messages=messages,
        trades=trades,
        actions=actions,
        remaining_requests=requests,
        remaining_offers=offers,
        mode="live Groq zone negotiation + deterministic coordinator" if live_rounds and live_rounds == len({m['round'] for m in messages}) else "mixed live Groq proposals + deterministic fallback" if live_rounds else "deterministic fallback",
        live_rounds=live_rounds,
        fallback_reasons=fallback_reasons,
    )
