import json
import sys

from flask import request
from sqlalchemy import desc
from y_server import app, db
from y_server.modals import (
    Agent_Custom_Feature,
    Agent_Opinion,
    Follow,
    Interests,
    Post,
    Reactions,
    Rounds,
    User_interest,
    User_mgmt,
)
from sqlalchemy import func


def _normalize_custom_features_payload(raw_features):
    normalized = []
    if isinstance(raw_features, dict):
        for key, value in raw_features.items():
            feature_key = str(key or "").strip()
            if not feature_key:
                continue
            normalized.append(
                {
                    "feature_type": "custom",
                    "key": feature_key,
                    "value": "" if value is None else str(value),
                }
            )
        return normalized
    if not isinstance(raw_features, list):
        return normalized
    for item in raw_features:
        if not isinstance(item, dict):
            continue
        feature_key = str(item.get("key") or "").strip()
        if not feature_key:
            continue
        normalized.append(
            {
                "feature_type": str(item.get("feature_type") or "custom").strip() or "custom",
                "key": feature_key,
                "value": "" if item.get("value") is None else str(item.get("value")),
            }
        )
    return normalized


def _normalize_stubborn_topics(raw_stubborn_topics):
    if isinstance(raw_stubborn_topics, dict):
        return {
            str(topic).strip()
            for topic, is_stubborn in raw_stubborn_topics.items()
            if str(topic).strip() and bool(is_stubborn)
        }
    if isinstance(raw_stubborn_topics, (list, tuple, set)):
        return {str(topic).strip() for topic in raw_stubborn_topics if str(topic).strip()}
    return set()


def _latest_agent_opinion(agent_id, topic_id):
    return (
        Agent_Opinion.query.filter_by(agent_id=agent_id, topic_id=topic_id)
        .order_by(Agent_Opinion.tid.desc(), Agent_Opinion.id.desc())
        .first()
    )


@app.route("/get_user_id", methods=["GET", "POST"])
def get_user_id():
    """
    Get the user id.

    :return: a json object with the user id
    """
    raw = request.get_data()
    if raw:
        data = json.loads(raw)
        username = data["username"]
    else:
        username = request.args.get("username")

    user = User_mgmt.query.filter_by(username=username).first()
    if user is None:
        return json.dumps({"id": None})

    return json.dumps({"id": user.id})


@app.route("/get_user", methods=["POST"])
def get_user():
    """
    Get user information.

    :return: a json object with the user information
    """
    data = json.loads(request.get_data())
    username = data["username"]
    # email = data["email"]

    user = User_mgmt.query.filter_by(username=username).first()

    if user is None:
        return json.dumps({"error": "User not found", "status": 404, "username": username})

    return json.dumps(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "leaning": user.leaning,
            "age": int(user.age),
            "user_type": user.user_type,
            "password": user.password,
            "ag": user.ag,
            "ne": user.ne,
            "ex": user.ex,
            "co": user.co,
            "oe": user.oe,
            "rec_sys": user.recsys_type,
            "language": user.language,
            "education_level": user.education_level,
            "joined_on": user.joined_on,
            "owner": user.owner,
            "round_actions": user.round_actions,
            "frec_sys": user.frecsys_type,
            "gender": user.gender,
            "nationality": user.nationality,
            "toxicity": user.toxicity,
            "is_page": user.is_page,
            "activity_profile": user.activity_profile if user.is_page == 0 else "Always On",
            "profession": user.profession if user.is_page == 0 else "",
            "archetype": user.archetype if user.is_page == 0 else "",
        }
    )


@app.route("/register", methods=["POST"])
def register():
    """
    Register a new user.

    :return: a json object with the status of the registration
    """
    data = json.loads(request.get_data())
    username = data["name"]
    email = data["email"]
    password = data["password"]

    leaning = data["leaning"]
    age = int(data["age"])
    user_type = data["user_type"]
    oe = data["oe"]
    co = data["co"]
    ex = data["ex"]
    ag = data["ag"]
    ne = data["ne"]
    recsys_type = "default"
    language = data["language"]
    education_level = data["education_level"]
    joined_on = int(data["joined_on"])
    round_actions = int(data["round_actions"])
    owner = data["owner"]
    gender = data["gender"]
    nationality = data["nationality"]
    toxicity = data["toxicity"]
    daily_activity_level = data["daily_activity_level"]
    activity_profile = data["activity_profile"]

    profession = data["profession"]

    if "is_page" in data:
        is_page = data["is_page"]
    else:
        is_page = 0

    user = User_mgmt.query.filter_by(username=data["name"]).first()

    if user is None:
        user = User_mgmt(
            username=username,
            email=email,
            password=password,
            leaning=leaning,
            age=age,
            user_type=user_type,
            oe=oe,
            co=co,
            ex=ex,
            ag=ag,
            ne=ne,
            recsys_type=recsys_type,
            language=language,
            education_level=education_level,
            joined_on=joined_on,
            round_actions=round_actions,
            owner=owner,
            gender=gender,
            nationality=nationality,
            toxicity=toxicity,
            is_page=is_page,
            daily_activity_level=daily_activity_level,
            profession=profession,
            activity_profile=activity_profile,
        )

        db.session.add(user)
        db.session.commit()

        return json.dumps({"status": 200, "id": user.id, "username": user.username})

    else:
        return json.dumps({"status": 200, "id": user.id, "username": user.username})


@app.route("/churn", methods=["POST"])
def churn_agents():
    """
    Churn users that do not post for a while.

    :return:
    """

    data = json.loads(request.get_data())
    left_on = data["left_on"]

    user_id = data.get("user_id")
    if user_id is not None:
        user = User_mgmt.query.filter_by(id=int(user_id)).first()
        if user is None:
            return json.dumps({"status": 404, "removed": {}})
        user.left_on = left_on
        db.session.commit()
        return json.dumps({"status": 200, "removed": {int(user_id): None}})

    n_users = data["n_users"]

    #  get the max round value from the post table for each user
    query = (
        (
            db.session.query(Post.user_id, db.func.max(Post.round))
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .filter(User_mgmt.left_on.is_(None), User_mgmt.is_page == 0)
            .group_by(Post.user_id)
        )
        .order_by(db.func.max(Post.round).asc())
        .limit(n_users)
    )

    results = query.all()

    removed = {}
    for user_id, _ in results:
        user = User_mgmt.query.filter_by(id=user_id).first()
        user.left_on = left_on
        db.session.commit()
        removed[user_id] = None

    return json.dumps({"status": 200, "removed": removed})


@app.route("/update_user", methods=["POST"])
def update_user():
    """
    Update user information.

    :return: a json object with the status of the update
    """
    data = json.loads(request.get_data())

    user = User_mgmt.query.filter_by(
        username=data["username"], email=data["email"]
    ).first()

    if user is not None:
        if "recsys_type" in data:
            recsys_type = data["recsys_type"]
            user.recsys_type = recsys_type
            db.session.commit()

        if "frecsys_type" in data:
            frecsys_type = data["frecsys_type"]
            user.frecsys_type = frecsys_type
            db.session.commit()

    return json.dumps({"status": 200})


@app.route("/user_exists", methods=["POST"])
def user_exists():
    """
    Check if the user exists.

    :return: a json object with the status of the user
    """
    data = json.loads(request.get_data())
    user = User_mgmt.query.filter_by(username=data["name"], email=data["email"]).first()

    if user is None:
        return json.dumps({"status": 404})

    return json.dumps({"status": 200, "id": user.id})


@app.route(
    "/get_user_from_post",
    methods=["POST", "GET"],
)
def get_user_from_post():
    """
    Get the author of a post.

    :return: a json object with the author
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]
    post = Post.query.filter_by(id=post_id).first()

    if post is None:
        return json.dumps({"error": "Post not found", "status": 404})

    return json.dumps(post.user_id)


@app.route("/timeline", methods=["GET"])
def get_timeline():
    """
    Get the timeline of a user.

    :return: a json object with the timeline
    """
    data = json.loads(request.get_data())
    user_id = data["user_id"]

    all_posts = Post.query.filter_by(user_id=user_id).order_by(desc(Post.id))
    res = []
    for post in all_posts:
        reposts = Post.query.filter_by(shared_from=post.id).count()
        likes = Reactions.query.filter_by(post_id=post.id, type="like").count()
        dislikes = Reactions.query.filter_by(post_id=post.id, type="dislike").count()
        comments = Post.query.filter_by(comment_to=post.id).count()
        res.append(
            {
                "post_id": post.id,
                "post": post.tweet,
                "round": post.round,
                "reposts": reposts,
                "likes": likes,
                "dislikes": dislikes,
                "comments": comments,
            }
        )

    return json.dumps(res)


@app.route("/set_interests", methods=["POST"])
def set_interests():
    """
    Set the interests of a user.

    :return: a json object with the status of the update
    """
    data = json.loads(request.get_data())

    for interest in data:
        existing = Interests.query.filter_by(interest=interest).first()
        if existing is None:
            ints = Interests(
                interest=interest,
            )
            db.session.add(ints)

    db.session.commit()

    return json.dumps({"status": 200})


@app.route("/set_user_interests", methods=["POST"])
def set_user_interests():
    """
    Set the interests of a user.

    :return: a json object with the status of the update
    """
    data = json.loads(request.get_data())
    user_id = data["user_id"]
    interests = data["interests"]
    round_id = data["round"]

    for interest in interests:
        # check if the interest is specified as id or by name
        iid = None
        if isinstance(interest, str):
            try:
                iid = Interests.query.filter_by(interest=interest).first().iid
            except:
                # add interest to the interest table
                ints = Interests(
                    interest=interest,
                )
                db.session.add(ints)
                db.session.commit()
                iid = Interests.query.filter_by(interest=interest).first().iid

        else:
            iid = interest

        user_interest = User_interest(
            user_id=user_id, interest_id=iid, round_id=round_id
        )
        db.session.add(user_interest)
        db.session.commit()

    return json.dumps({"status": 200})


@app.route("/get_user_interests", methods=["GET"])
def get_user_interests():
    """
    Get the interests of a user.

    :return: a json object with the interests
    """
    data = json.loads(request.get_data())
    user_id = int(data["user_id"])
    round_id = int(data["round_id"])
    n_interests = int(data["n_interests"])
    time_window = int(data["time_window"])
    base_rounds = max(0, round_id - time_window)

    # get the top n_interests interests of the user in the time window
    interests = (
        db.session.query(
            User_interest.interest_id,
            Interests.interest,
            db.func.count(User_interest.interest_id).label("count"),
        )
        .join(Interests, User_interest.interest_id == Interests.iid)
        .filter(
            User_interest.user_id == user_id,
            User_interest.round_id >= base_rounds,
            User_interest.round_id <= round_id,
        )
        .group_by(User_interest.interest_id, Interests.interest)
        .order_by(db.desc(db.func.count(User_interest.interest_id)))
        .limit(n_interests)
        .all()
    )

    res = []
    for interest in interests:
        res.append({"id": int(interest[0]), "topic": interest.interest})

    return json.dumps(res)


@app.route("/get_user_opinions", methods=["POST"])
def get_user_opinions():
    """
    Get the opinions of a user mapped to interest names.

    :return: a json object with the opinions {interest_name: opinion_value}
    """
    data = json.loads(request.get_data())
    user_id = int(data["user_id"])

    # Subquery: for this agent, get the latest tid for each topic_id
    # (This ensures we only get the most recent opinion per topic)
    subq = (
        db.session.query(
            Agent_Opinion.topic_id,
            func.max(Agent_Opinion.tid).label("max_tid")
        )
        .filter(Agent_Opinion.agent_id == user_id)
        .group_by(Agent_Opinion.topic_id)
        .subquery()
    )

    # Main query: Join Agent_Opinion with Subquery (for latest) AND Interest (for name)
    # We query specific columns: Interest.interest and Agent_Opinion.opinion
    rows = (
        db.session.query(Interests.interest, Interests.iid, Agent_Opinion.opinion)
        .join(
            subq,
            (Agent_Opinion.topic_id == subq.c.topic_id) &
            (Agent_Opinion.tid == subq.c.max_tid)
        )
        .join(Interests, Agent_Opinion.topic_id == Interests.iid)  # Join to get the interest name
        .filter(Agent_Opinion.agent_id == user_id)
        .all()
    )

    # Construct the dictionary using the Interest name as the key
    res = {row.interest: [float(row.opinion), row.iid] for row in rows}

    return json.dumps(res)


@app.route("/get_users_opinions", methods=["POST"])
def get_users_opinions():
    """
    Get the opinions of a user mapped to interest names.

    :return: a json object with the opinions {interest_name: opinion_value}
    """
    data = json.loads(request.get_data())
    user_id = int(data["user_id"])
    topic = data["topic"]

    # get topic id from Interests table
    interest = Interests.query.filter_by(interest=topic).first()
    if interest is not None:
        target_topic_id = int(interest.iid)
    else:
        return []

    followee_ids = [f.follower_id for f in Follow.query.filter_by(user_id=user_id, action="follow").all()]

    # ---------------------------------------------------------
    # Subquery: Get the latest tid per AGENT for this specific TOPIC
    # ---------------------------------------------------------
    subq = (
        db.session.query(
            Agent_Opinion.agent_id,
            func.max(Agent_Opinion.tid).label("max_tid")
        )
        .filter(
            Agent_Opinion.topic_id == target_topic_id,  # Filter for the input topic
            Agent_Opinion.agent_id.in_(followee_ids)  # Filter for the list of agents
        )
        .group_by(Agent_Opinion.agent_id)  # Group by agent (one opinion per person)
        .subquery()
    )

    # ---------------------------------------------------------
    # Main Query: Join back to get the actual opinion text
    # ---------------------------------------------------------
    rows = (
        db.session.query(
            Agent_Opinion.agent_id,  # Include this so you know WHO said it
            Interests.interest,  # The topic name
            Agent_Opinion.opinion
        )
        .join(
            subq,
            (Agent_Opinion.agent_id == subq.c.agent_id) &
            (Agent_Opinion.tid == subq.c.max_tid)
        )
        .join(Interests, Agent_Opinion.topic_id == Interests.iid)
        # We repeat the filters here for query optimizer safety,
        # though the join on subq technically limits the rows already.
        .filter(
            Agent_Opinion.topic_id == target_topic_id,
            Agent_Opinion.agent_id.in_(followee_ids)
        )
        .all()
    )

    res = [float(row.opinion) for row in rows]

    return json.dumps(res)


@app.route("/set_user_opinions", methods=["POST"])
def set_user_opinions():
    """
    Set the opinions of a user.

    :return: a json object with the status of the update
    """
    data = json.loads(request.get_data())

    agent_id = data.get("user_id")
    opinions = data.get("opinions", {})
    tid = data.get("round")
    id_interacted_with = data.get("id_interacted_with", -1)
    id_post = data.get("id_post", -1)
    stubborn_topics = _normalize_stubborn_topics(data.get("stubborn_topics"))

    try:
        for topic_id, opinion_value in opinions.items():

            # if topic_id is a string, get the iid from the Interests table
            if isinstance(topic_id, str):
                try:
                    topic_id = int(topic_id)
                    # check if the topic_id exists in the Interests table
                    interest = Interests.query.filter_by(iid=topic_id).first()
                    if interest is None:
                        raise ValueError(f"Interest ID {topic_id} does not exist.")
                except:
                    interest = Interests.query.filter_by(interest=topic_id).first()
                    if interest is None:
                        # create the interest
                        new_interest = Interests(interest=topic_id)
                        db.session.add(new_interest)
                        db.session.commit()
                        topic_id = new_interest.iid
                    else:
                        topic_id = interest.iid

            latest_opinion = _latest_agent_opinion(agent_id, topic_id)
            is_stubborn = bool(latest_opinion.stubborn) if latest_opinion is not None else False
            if isinstance(topic_id, int):
                interest_name = (
                    Interests.query.filter_by(iid=topic_id).with_entities(Interests.interest).scalar()
                )
            else:
                interest_name = str(topic_id)
            if interest_name and interest_name in stubborn_topics:
                is_stubborn = True
            stored_opinion = (
                float(latest_opinion.opinion)
                if latest_opinion is not None and bool(latest_opinion.stubborn)
                else float(opinion_value)
            )

            new_record = Agent_Opinion(
                    agent_id=agent_id,
                    tid=tid,
                    topic_id=topic_id,
                    id_interacted_with=id_interacted_with,
                    id_post=id_post,
                    opinion=stored_opinion,
                    stubborn=1 if is_stubborn else 0,
            )
            db.session.add(new_record)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": 400, "error": str(e)})

    return json.dumps({"status": 200})


@app.route("/set_user_custom_features", methods=["POST"])
def set_user_custom_features():
    data = json.loads(request.get_data())
    user_id = int(data.get("user_id"))
    features = _normalize_custom_features_payload(data.get("custom_features"))

    try:
        Agent_Custom_Feature.query.filter_by(user_id=user_id).delete()
        for feature in features:
            db.session.add(
                Agent_Custom_Feature(
                    user_id=user_id,
                    feature_type=feature["feature_type"],
                    key=feature["key"],
                    value=feature["value"],
                )
            )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return json.dumps({"status": 400, "error": str(exc)})

    return json.dumps({"status": 200})


@app.route("/get_user_custom_features", methods=["POST"])
def get_user_custom_features():
    data = json.loads(request.get_data())
    user_id = int(data.get("user_id"))
    rows = Agent_Custom_Feature.query.filter_by(user_id=user_id).all()
    return json.dumps(
        [
            {
                "feature_type": row.feature_type,
                "key": row.key,
                "value": row.value,
            }
            for row in rows
        ]
    )
