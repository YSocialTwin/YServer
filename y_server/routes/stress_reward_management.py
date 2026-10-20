import json
import uuid

from flask import current_app, request
from y_server import app, config as server_config, db
from y_server.modals import StressReward
from sqlalchemy import func, select


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _stress_reward_enabled() -> bool:
    raw_cfg = server_config.get("stress_reward") if isinstance(server_config, dict) else None
    if isinstance(raw_cfg, dict) and "enabled" in raw_cfg:
        return bool(raw_cfg.get("enabled", False))
    return bool(
        current_app.config.get(
            "stress_reward_enabled",
            current_app.config.get("stress_reward_annotation", False),
        )
    )


def _get_round_window_endpoints(tid: int, backward_rounds: int) -> tuple[int, int]:
    end_tid = int(tid)
    if backward_rounds <= 0:
        return end_tid, end_tid
    start_tid = max(0, end_tid - int(backward_rounds))
    return start_tid, end_tid


@app.route("/get_stress_reward", methods=["GET", "POST"])
def get_stress_reward():
    data = json.loads(request.get_data() or "{}")
    user_id = int(data.get("user_id", data.get("agent_id")))
    tid = int(data["tid"])
    backward_rounds = int(data.get("backward_rounds", 24))

    start_tid, end_tid = _get_round_window_endpoints(tid, backward_rounds)

    response_payload = {"stress": 0.0, "reward": 0.0, "status": 200}
    if not _stress_reward_enabled():
        return json.dumps(response_payload)

    for variable in ("stress", "reward"):
        latest_aggregate = (
            db.session.scalars(
                select(StressReward).filter(
                    StressReward.uid == user_id,
                    StressReward.variable == variable,
                    StressReward.type == "aggregate",
                    StressReward.tid < end_tid,
                ).order_by(StressReward.tid.desc())
            ).first()
        )

        anchor_value = 0.0
        anchor_tid = start_tid - 1
        if latest_aggregate is not None:
            anchor_value = float(latest_aggregate.value)
            anchor_tid = int(latest_aggregate.tid)

        variation_sum = (
            db.session.query(db.func.coalesce(db.func.sum(StressReward.value), 0.0))
            .filter(
                StressReward.uid == user_id,
                StressReward.variable == variable,
                StressReward.type == "variation",
                StressReward.tid > anchor_tid,
                StressReward.tid <= end_tid,
            )
            .scalar()
        )
        current_value = clamp(anchor_value + float(variation_sum or 0.0))
        response_payload[variable] = current_value

        existing = (
            db.session.scalars(select(StressReward).filter_by(
                uid=user_id,
                variable=variable,
                type="aggregate",
                tid=end_tid,
            )).first()
        )
        if existing is None:
            existing = StressReward(
                id=str(uuid.uuid4()),
                uid=user_id,
                variable=variable,
                value=current_value,
                type="aggregate",
                action=None,
                tid=end_tid,
            )
            db.session.add(existing)
        else:
            existing.value = current_value

    db.session.commit()
    return json.dumps(response_payload)


@app.route("/set_stress_reward_variations", methods=["POST"])
def set_stress_reward_variations():
    data = json.loads(request.get_data() or "{}")
    if not _stress_reward_enabled():
        return json.dumps({"status": 200, "written": 0})

    user_id = int(data["user_id"])
    tid = int(data["tid"])
    action_name = str(data.get("action") or "").strip() or None

    variations = data.get("variations")
    if not isinstance(variations, list):
        variations = [
            {
                "variable": data.get("variable"),
                "value": data.get("value"),
            }
        ]

    written = 0
    for variation in variations:
        variable = str(variation.get("variable") or "").strip().lower()
        if variable not in {"stress", "reward"}:
            continue
        try:
            value = float(variation.get("value"))
        except (TypeError, ValueError):
            continue
        if value < -1.0 or value > 1.0:
            continue
        entry = StressReward(
            id=str(uuid.uuid4()),
            uid=user_id,
            variable=variable,
            value=value,
            type="variation",
            action=action_name,
            tid=tid,
        )
        db.session.add(entry)
        written += 1

    db.session.commit()
    return json.dumps({"status": 200, "written": written})
