import json

from flask import request
from y_server import app, db
from y_server.modals import StressReward, Rounds


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@app.route("/get_stress_reward", methods=["GET"])
def get_stress_reward():
    data = json.loads(request.get_data())
    user_id = data["user_id"]
    tid = data["tid"]
    backward_rounds = data["backward_rounds"]

    # get latest stress/reward aggregate for user_id
    latest_stress = (
        StressReward.query
        .filter_by(uid=user_id, variable="stress", type="aggregate")
        .order_by(StressReward.tid.desc())
        .first()
    )
    latest_reward = (
        StressReward.query
        .filter_by(uid=user_id, variable="reward", type="aggregate")
        .order_by(StressReward.tid.desc())
        .first()
    )
    stress_anchor = latest_stress.value if latest_stress is not None else 0.0
    reward_anchor = latest_reward.value if latest_reward is not None else 0.0

    # get all stress/reward variations for user_id from tid backward for backward_rounds
    # build a subquery of the backward_rounds most recent round IDs up to (and including) tid
    recent_round_ids_sq = (
        db.session.query(Rounds.id)
        .filter(Rounds.id <= tid)
        .order_by(Rounds.id.desc())
        .limit(backward_rounds)
        .subquery()
    )
    stress_variations = (
        StressReward.query
        .filter(
            StressReward.uid == user_id,
            StressReward.variable == "stress",
            StressReward.type == "variation",
            StressReward.tid.in_(recent_round_ids_sq),
        )
        .all()
    )
    reward_variations = (
        StressReward.query
        .filter(
            StressReward.uid == user_id,
            StressReward.variable == "reward",
            StressReward.type == "variation",
            StressReward.tid.in_(recent_round_ids_sq),
        )
        .all()
    )

    stress_variation_sum = sum(entry.value for entry in stress_variations)
    reward_variation_sum = sum(entry.value for entry in reward_variations)

    stress = clamp(stress_anchor + stress_variation_sum)
    reward = clamp(reward_anchor + reward_variation_sum)

    str = StressReward(
        uid=user_id,
        variable="stress",
        value=stress,
        type="aggregate",
        tid=tid
    )

    rwd = StressReward(
        uid=user_id,
        variable="reward",
        value=reward,
        type="aggregate",
        tid=tid
    )

    db.session.add(str)
    db.session.add(rwd)
    db.session.commit()

    res = {"stress": stress, "reward": reward, "status": 200}
    return json.dumps(res)


@app.route("/set_stress_reward_variations", methods=["POST"])
def set_stress_reward_variations():
    data = json.loads(request.get_data())

    # write the stress/reward variations in the db
    sr = StressReward(
        uid=data["user_id"],
        variable=data["variable"],
        value=data["value"],
        type="variation",
        tid=data["tid"]
    )

    db.session.add(sr)
    db.session.commit()

    res = {"status": 200}
    return json.dumps(res)