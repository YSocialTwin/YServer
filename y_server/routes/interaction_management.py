from flask import request
from sqlalchemy.sql.expression import func
import json
from y_server import app, db
import numpy as np
from y_server.modals import (
    User_mgmt,
    Follow,
)

@app.route(
    "/follow",
    methods=["POST"],
)
def add_follow():
    """
    Add a follow/unfollow relationship.

    :return: a json object with the status of the follow
    """
    data = json.loads(request.get_data())
    user_id = data["user_id"]
    target = data["target"]
    action = data["action"]
    tid = int(data["tid"])

    user_id = User_mgmt.query.filter_by(id=user_id).first()
    target = User_mgmt.query.filter_by(id=target).first()

    # cannot follow yourself
    if user_id.id == target.id:
        return json.dumps({"status": 200})

    exiting_rel = (
        Follow.query.filter_by(user_id=user_id.id, follower_id=target.id)
        .order_by(Follow.round.desc())
        .first()
    )

    if exiting_rel is not None:
        # cannot perform the same action twice in a row
        if exiting_rel.action == action:
            return json.dumps({"status": 200})
    # cannot unfollow if there is no follow
    elif exiting_rel is None and action == "unfollow":
        return json.dumps({"status": 200})

    rel = Follow(user_id=user_id.id, follower_id=target.id, round=tid, action=action)

    db.session.add(rel)
    db.session.commit()

    return json.dumps({"status": 200})


@app.route(
    "/followers",
    methods=["GET"],
)
def followers():
    """
    Get the followers of a user.

    :return: a json object with the followers
    """
    data = json.loads(request.get_data())
    user_id = data["user_id"]

    user = User_mgmt.query.filter_by(id=user_id).first()
    all_followers = Follow.query.filter_by(user_id=user.id)

    res = []
    for follower in all_followers:
        res.append(
            {
                "user_id": follower.follower_id,
                "username": User_mgmt.query.filter_by(id=user_id).first().username,
                "since": follower.round,
            }
        )

    return json.dumps(res)



@app.route("/follow_suggestions", methods=["POST"])
def get_follow_suggestions():
    """
    Get follow suggestions for a user based on the follow recommender system.

    :return: a json object with the follow suggestions
    """
    data = json.loads(request.get_data())
    user_id = int(data["user_id"])
    n_neighbors = int(data["n_neighbors"])
    leaning_biased = int(data["leaning_biased"])

    try:
        rectype = data["mode"]
    except:
        rectype = "random"

    res = {}

    if rectype == "random":
        # get random users
        users = User_mgmt.query.order_by(func.random()).limit(n_neighbors)

        for user in users:
            res[user.id] = 1 / n_neighbors

    if rectype == "preferential_attachment":
        # get random nodes ordered by degree
        followers = (
            (
                db.session.query(
                    Follow, func.count(Follow.user_id).label("total")
                ).filter(Follow.action == "follow")
            )
            .group_by(Follow.follower_id)
            .order_by(func.count(Follow.user_id).desc())
        ).limit(n_neighbors)

        for follower in followers:
            res[follower[0].follower_id] = int(follower[1])

        # normalize pa to probabilities
        total_degree = sum(res.values())
        res = {k: v / total_degree for k, v in res.items()}

    if rectype == "common_neighbors":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        for target, neighbors in candidates.items():
            res[target] = len(neighbors & first_order_followers)

        total = sum(res.values())
        # normalize cn to probabilities
        res = {k: v / total for k, v in res.items() if v > 0}

    if rectype == "jaccard":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        for candidate in candidates:
            res[candidate] = len(first_order_followers & candidates[candidate]) / len(
                first_order_followers | candidates[candidate]
            )

        total = sum(res.values())
        res = {k: v / total for k, v in res.items() if v > 0}

    elif rectype == "adamic_adar":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        res = {}
        for target, neighbors in candidates.items():
            res[target] = neighbors & first_order_followers

        for target in res:
            res[target] = sum(
                [
                    1 / np.log(len(Follow.query.filter_by(user_id=neighbor).all()))
                    for neighbor in res[target]
                ]
            )

        total = sum([v for v in res.values() if v != np.inf])
        res = {k: v / total for k, v in res.items() if v > 0 and v != np.inf}

    l_source = User_mgmt.query.filter_by(id=user_id).first().leaning
    leanings = __get_users_leanings(res.keys())
    for user in res:
        if leanings[user] == l_source:
            res[user] = res[user] * leaning_biased
    res = {k: v / total for k, v in res.items() if v > 0}

    return json.dumps(res)


def __get_two_hops_neighbors(node_id):
    """
    Get the two hops neighbors of a user.

    :param node_id: the user id
    :return: the two hops neighbors
    """
    # (node_id, direct_neighbors)
    first_order_followers = set(
        [
            f.follower_id
            for f in Follow.query.filter_by(user_id=node_id, action="follow")
        ]
    )
    # (direct_neighbors, second_order_followers)
    second_order_followers = Follow.query.filter(
        Follow.user_id.in_(first_order_followers), Follow.action == "follow"
    )
    # (second_order_followers, third_order_followers)
    third_order_followers = Follow.query.filter(
        Follow.user_id.in_([f.follower_id for f in second_order_followers]),
        Follow.action == "follow",
    )

    candidate_to_follower = {}
    for node in third_order_followers:
        if node.user_id not in candidate_to_follower:
            candidate_to_follower[node.user_id] = set()
        candidate_to_follower[node.user_id].add(node.follower_id)

    return first_order_followers, candidate_to_follower


def __get_users_leanings(agents):
    """
    Get the political leaning of a list of users.

    :param agents: the list of users
    :return: the political leaning of the users
    """
    leanings = {}
    for agent in agents:
        leanings[agent] = User_mgmt.query.filter_by(id=agent).first().leaning
    return leanings
