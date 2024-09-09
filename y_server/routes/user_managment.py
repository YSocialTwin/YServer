import json
from flask import request
from y_server import app, db
from sqlalchemy import desc
from y_server.modals import (
    Post,
    User_mgmt,
    Reactions,
)

@app.route("/get_user", methods=["POST"])
def get_user():
    """
    Get user information.

    :return: a json object with the user information
    """
    data = json.loads(request.get_data())
    username = data["username"]
    email = data["email"]

    user = User_mgmt.query.filter_by(username=username, email=email).first()

    return json.dumps(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "interests": user.interests.split("|"),
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
    interests = "|".join(data["interests"])

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

    user = User_mgmt.query.filter_by(username=data["name"], email=data["email"]).first()

    if user is None:
        user = User_mgmt(
            username=username,
            email=email,
            password=password,
            interests=interests,
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
        )
        db.session.add(user)
        try:
            db.session.commit()
        except:
            return json.dumps({"status": 404})

    return json.dumps({"status": 200})


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

    return json.dumps(post.user_id)

@app.route("/timeline", methods=["GET"])
def get_timeline():
    """
    Get the timeline of a user.

    :return: a json object with the timeline
    """
    data = json.loads(request.get_data())
    user_id = data["user_id"]

    user = User_mgmt.query.filter_by(id=user_id).first()
    all_posts = Post.query.filter_by(user_id=user.id).order_by(desc(Post.id))
    res = []
    for post in all_posts:
        res.append(
            {
                "post_id": post.id,
                "post": post.tweet,
                "round": post.round,
                "reposts": len(post.retweets),
                "likes": len(list(Reactions.query.filter_by(id=post.id, type="like"))),
                "dislikes": len(
                    list(Reactions.query.filter_by(id=post.id, type="dislike"))
                ),
                "comments": len(list(Post.query.filter_by(comment_to=post.id))),
            }
        )

    return json.dumps(res)