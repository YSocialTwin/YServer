from flask import request
from sqlalchemy import desc
from sqlalchemy.sql.expression import func
import json
from y_server import app, db
import numpy as np
from y_server.modals import (
    User_mgmt,
    Post,
    Reactions,
    Follow,
    Hashtags,
    Post_hashtags,
    Mentions,
    Emotions,
    Post_emotions,
    Rounds,
    Recommendations,
    Websites,
    Articles,
)


@app.route("/reset", methods=["POST"])
def reset_experiment():
    """
    Reset the experiment.
    Delete all the data from the database.

    :return: the status of the reset
    """
    db.session.query(User_mgmt).delete()
    db.session.query(Post).delete()
    db.session.query(Reactions).delete()
    db.session.query(Follow).delete()
    db.session.query(Hashtags).delete()
    db.session.query(Post_hashtags).delete()
    db.session.query(Post_emotions).delete()
    db.session.query(Mentions).delete()
    db.session.query(Rounds).delete()
    db.session.query(Recommendations).delete()
    db.session.query(Websites).delete()
    db.session.query(Articles).delete()
    db.session.commit()
    return {"status": 200}


@app.route("/current_time", methods=["GET"])
def current_time():
    """
    Get the current time of the simulation.

    :return: a json object with the current time
    """
    cround = Rounds.query.order_by(desc(Rounds.id)).first()
    if cround is None:
        cround = Rounds(day=0, hour=0)
        db.session.add(cround)
        db.session.commit()
        cround = Rounds.query.order_by(desc(Rounds.id)).first()

    return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})


@app.route("/update_time", methods=["POST"])
def update_time():
    """
    Update the time of the simulation.

    :return: a json object with the updated time
    """
    data = json.loads(request.get_data())
    day = int(data["day"])
    hour = int(data["round"])

    cround = Rounds.query.filter_by(day=day, hour=hour).first()
    if cround is None:
        cround = Rounds(day=day, hour=hour)
        db.session.add(cround)
        db.session.commit()
        cround = Rounds.query.filter_by(day=day, hour=hour).first()

    return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})


@app.route("/search", methods=["POST"])
def search():
    """
    Search posts based on the most recently used hashtags for the user.

    :return: a json object with the post ids
    """
    data = json.loads(request.get_data())
    uid = int(data["uid"])
    vround = int(data["visibility_rounds"])

    # visibility
    current_round = Rounds.query.order_by(desc(Rounds.id)).first()
    visibility = current_round.id - vround

    recent_user_hashtags = Hashtags.query.filter(
        Hashtags.id
        == db.session.query(Post_hashtags.hashtag_id).filter(
            Post_hashtags.post_id
            == db.session.query(Post.id).filter(
                Post.user_id == uid, Post.round >= visibility
            )
        )
    ).limit(10)

    if recent_user_hashtags is not None:
        hashtag_ids = []
        for hashtag in recent_user_hashtags:
            hashtag_ids.append(hashtag.id)

        hashtag_ids = list(set(hashtag_ids))

        recent_posts_with_hashtags = (
            Post_hashtags.query.filter(Post_hashtags.hashtag_id.in_(hashtag_ids))
            .filter(
                Post.id == Post_hashtags.post_id,
                Post.user_id != uid,
                Post.round >= visibility,
            )
            .order_by(func.random())
            .limit(10)
        )

        res = []
        for post in recent_posts_with_hashtags:
            res.append(post.post_id)

        return json.dumps(res)

    json.dumps({"status": 404})


@app.route("/read_mentions", methods=["POST"])
def read_mention():
    """
    Search for recent mentions for the user.

    :return: a json object with the post ids mentioning the user
    """
    data = json.loads(request.get_data())
    uid = int(data["uid"])
    vround = int(data["visibility_rounds"])

    # visibility
    current_round = Rounds.query.order_by(desc(Rounds.id)).first()
    visibility = current_round.id - vround

    mention = (
        Mentions.query.filter(
            Mentions.user_id == uid,
            Mentions.round >= visibility,
            Mentions.answered == 0,
        )
        .order_by(func.random())
        .first()
    )

    if mention is not None:
        mention.answered = 1
        db.session.commit()
        return json.dumps([mention.post_id])

    else:
        return json.dumps({"status": 404})


@app.route("/read", methods=["POST"])
def read():
    """
    Return a list of candidate posts for the user as filtered by the content recommendation system.

    :return: a json object with the post ids
    """
    data = json.loads(request.get_data())
    limit = data["limit"]
    mode = data["mode"]
    vround = int(data["visibility_rounds"])
    try:
        uid = int(data["uid"])
        fratio = float(data["followers_ratio"])
    except:
        uid = None
        fratio = 1
    articles = False
    if "article" in data:
        articles = True

    # visibility
    current_round = Rounds.query.order_by(desc(Rounds.id)).first()
    visibility = current_round.id - vround

    if mode == "rchrono":
        # get posts in reverse chronological order
        if articles:
            posts = [
                db.session.query(Post)
                .filter(Post.round >= visibility, Post.news_id != -1)
                .order_by(desc(Post.id))
                .limit(10)
            ]
        else:
            posts = [
                db.session.query(Post)
                .filter(Post.round >= visibility)
                .order_by(desc(Post.id))
                .limit(10)
            ]

    elif mode == "rchrono_popularity":
        # get posts ordered by likes in reverse chronological order
        if articles:
            posts = [
                (
                    db.session.query(Post, func.count(Reactions.user_id).label("total"))
                    .filter(Post.round >= visibility, Post.news_id != -1)
                    .join(Reactions)
                    .group_by(Post)
                    .order_by(desc("total"), desc(Post.id))
                ).limit(limit)
            ]
        else:
            posts = [
                (
                    db.session.query(Post, func.count(Reactions.user_id).label("total"))
                    .filter(Post.round >= visibility)
                    .join(Reactions)
                    .group_by(Post)
                    .order_by(desc("total"), desc(Post.id))
                ).limit(limit)
            ]

    elif mode == "rchrono_followers":
        if fratio < 1:
            follower_posts_limit = int(limit * fratio)
            additional_posts_limit = limit - follower_posts_limit
        else:
            follower_posts_limit = limit
            additional_posts_limit = 0

        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower]

        # get posts from followers in reverse chronological order
        if articles:
            posts = (
                Post.query.filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(follower_ids),
                )
                .order_by(desc(Post.id))
                .limit(follower_posts_limit)
            )
        else:
            posts = (
                Post.query.filter(
                    Post.round >= visibility, Post.user_id.in_(follower_ids)
                )
                .order_by(desc(Post.id))
                .limit(follower_posts_limit)
            )

        if additional_posts_limit != 0:
            if articles:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility, Post.news_id != -1)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )
            else:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )

            posts = [posts, additional_posts]

    elif mode == "rchrono_followers_popularity":
        if fratio < 1:
            follower_posts_limit = int(limit * fratio)
            additional_posts_limit = limit - follower_posts_limit
        else:
            follower_posts_limit = limit
            additional_posts_limit = 0

        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower]

        # get posts from followers ordered by likes and reverse chronologically
        if articles:
            posts = (
                db.session.query(Post, func.count(Reactions.user_id).label("total"))
                .join(Reactions)
                .filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(follower_ids),
                )
                .group_by(Post)
                .order_by(desc("total"), desc(Post.id))
                .limit(follower_posts_limit)
            )
        else:
            posts = (
                db.session.query(Post, func.count(Reactions.user_id).label("total"))
                .join(Reactions)
                .filter(Post.round >= visibility, Post.user_id.in_(follower_ids))
                .group_by(Post)
                .order_by(desc("total"), desc(Post.id))
                .limit(follower_posts_limit)
            )

        if additional_posts_limit != 0:
            if articles:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility, Post.news_id != -1)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )
            else:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )

        posts = [posts, additional_posts]

    else:
        # get posts in random order
        if articles:
            posts = [
                (
                    Post.query.filter(Post.round >= visibility, Post.news_id != -1)
                    .order_by(func.random())
                    .limit(limit)
                )
            ]
        else:
            posts = [
                (
                    Post.query.filter(Post.round >= visibility)
                    .order_by(func.random())
                    .limit(limit)
                )
            ]

    res = []
    for post_type in posts:
        for post in post_type:
            try:
                res.append(post[0].id)
            except:
                res.append(post.id)

    # save recommendations
    current_round = Rounds.query.order_by(desc(Rounds.id)).first()
    recs = Recommendations(
        user_id=uid, post_ids="|".join([str(x) for x in res]), round=current_round.id
    )
    db.session.add(recs)
    db.session.commit()
    return json.dumps(res)


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
            "nationality": user.nationality
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
            nationality=nationality
        )
        db.session.add(user)
        db.session.commit()

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


@app.route("/post", methods=["POST"])
def add_post():
    """
    Add a new post.

    :return: a json object with the status of the post
    """
    data = json.loads(request.get_data())
    account_id = data["user_id"]
    text = data["tweet"].strip('"')
    emotions = data["emotions"]
    hastags = data["hashtags"]
    mentions = data["mentions"]
    tid = int(data["tid"])

    user = User_mgmt.query.filter_by(id=account_id).first()

    post = Post(
        tweet=text,
        round=tid,
        user_id=user.id,
        comment_to=-1,
    )

    db.session.add(post)
    db.session.commit()

    post.thread_id = post.id
    db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
            db.session.add(post_emotion)
            db.session.commit()

    for tag in hastags:
        if len(tag) < 4:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            ht = Hashtags(hashtag=tag)
            db.session.add(ht)
            db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()

        # existing user and not self
        if us is not None and us.id != user.id:
            mention = Mentions(user_id=us.id, post_id=post.id, round=tid)
            db.session.add(mention)
            db.session.commit()

    return json.dumps({"status": 200})


@app.route(
    "/share",
    methods=["POST", "GET"],
)
def share():
    """
    Share a post containing a news article.

    :return: a json object with the status of the share
    """
    data = json.loads(request.get_data())
    account_id = data["user_id"]
    post_id = data["post_id"]
    text = data["text"].strip('"')
    emotions = data["emotions"]
    hastags = data["hashtags"]
    mentions = data["mentions"]
    tid = int(data["tid"])

    user = User_mgmt.query.filter_by(id=account_id).first()
    post = Post.query.filter_by(id=post_id).first()

    post = Post(
        tweet=text,
        round=tid,
        user_id=user.id,
        shared_from=post_id,
        news_id=post.news_id,
    )

    db.session.add(post)
    db.session.commit()

    post.thread_id = post.id
    db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
            db.session.add(post_emotion)
            db.session.commit()

    for tag in hastags:
        if len(tag) < 1:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            ht = Hashtags(hashtag=tag)
            db.session.add(ht)
            db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()
        if us is not None:
            mention = Mentions(user_id=us.id, post_id=post.id, round=tid)
            db.session.add(mention)
            db.session.commit()

    return json.dumps({"status": 200})


@app.route(
    "/comment",
    methods=["POST", "GET"],
)
def add_comment():
    """
    Comment on a post.

    :return: a json object with the status of the comment
    """
    data = json.loads(request.get_data())
    account_id = data["user_id"]
    post_id = data["post_id"]
    text = data["text"].strip('"')
    emotions = data["emotions"]
    hastags = data["hashtags"]
    mentions = data["mentions"]
    tid = int(data["tid"])

    user = User_mgmt.query.filter_by(id=account_id).first()
    post = Post.query.filter_by(id=post_id).first()

    post = Post(
        tweet=text,
        round=tid,
        user_id=user.id,
        comment_to=post_id,
        thread_id=post.thread_id,
    )

    db.session.add(post)
    db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
            db.session.add(post_emotion)
            db.session.commit()

    for tag in hastags:
        if len(tag) < 1:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            ht = Hashtags(hashtag=tag)
            db.session.add(ht)
            db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()
        if us is not None:
            mention = Mentions(user_id=us.id, post_id=post.id, round=tid)
            db.session.add(mention)
            db.session.commit()

    return json.dumps({"status": 200})


@app.route("/news", methods=["POST"])
def comment_news():
    """
    Comment on a news article.

    :return: a json object with the status of the comment
    """
    data = json.loads(request.get_data())
    account_id = data["user_id"]
    text = data["tweet"].strip('"')
    emotions = data["emotions"]
    hastags = data["hashtags"]
    mentions = data["mentions"]
    tid = int(data["tid"])
    title = data["title"]
    summary = data["summary"]
    link = data["link"]
    published = data["published"]
    publisher = data["publisher"]
    rss = data["rss"]
    leaning = data["leaning"]
    country = data["country"]
    language = data["language"]
    category = data["category"]
    fetched_on = data["fetched_on"]

    user = User_mgmt.query.filter_by(id=account_id).first()

    # check if website exists
    website = Websites.query.filter_by(rss=rss).first()
    if website is None:
        website = Websites(
            name=publisher,
            rss=rss,
            leaning=leaning,
            category=category,
            language=language,
            country=country,
            last_fetched=fetched_on,
        )
        db.session.add(website)
        db.session.commit()

    website_id = Websites.query.filter_by(rss=rss).first().id

    # check if article exists
    article = Articles.query.filter_by(link=link, website_id=website_id).first()
    if article is None:
        article = Articles(
            title=title,
            summary=summary,
            link=link,
            website_id=website_id,
            fetched_on=published,
        )
        db.session.add(article)
        db.session.commit()
    article_id = Articles.query.filter_by(link=link, website_id=website_id).first().id

    post = Post(
        tweet=text,
        round=tid,
        user_id=user.id,
        comment_to=-1,
        news_id=article_id,
    )

    db.session.add(post)
    db.session.commit()

    post.thread_id = post.id
    db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
            db.session.add(post_emotion)
            db.session.commit()

    for tag in hastags:
        if len(tag) < 4:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            ht = Hashtags(hashtag=tag)
            db.session.add(ht)
            db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()
        if us is not None:
            mention = Mentions(user_id=us.id, post_id=post.id, round=tid)
            db.session.add(mention)
            db.session.commit()

    return json.dumps({"status": 200})


@app.route(
    "/post_thread",
    methods=["POST", "GET"],
)
def post_thread():
    """
    Get the thread of a post.

    :return: a json object with the thread
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]

    post = Post.query.filter_by(id=post_id).first()
    thread_id = Post.query.filter_by(thread_id=post.thread_id)

    res = []

    for post in thread_id:
        user = post.user_id
        res.append(
            f"{User_mgmt.query.filter_by(id=user).first().username}: {post.tweet}\n"
        )
    return json.dumps(res)


@app.route(
    "/get_post",
    methods=["POST", "GET"],
)
def get_post():
    """
    Get the post.

    :return: a json object with the post
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]

    post = Post.query.filter_by(id=post_id).first()

    return json.dumps(post.tweet)


@app.route(
    "/get_article",
    methods=["POST", "GET"],
)
def get_article():
    """
    Get the news article.

    :return: a json object with the article
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]

    # get article from post_id
    article = Post.query.filter_by(id=post_id).first().news_id
    article = Articles.query.filter_by(id=article).first()
    if article is not None:
        return json.dumps({"summary": article.summary, "title": article.title})
    else:
        return json.dumps({"status": 404})


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


@app.route(
    "/reaction",
    methods=["POST"],
)
def add_reaction():
    """
    Add a reaction to a post/comment.

    :return: a json object with the status of the reaction
    """
    data = json.loads(request.get_data())
    account_id = data["user_id"]
    post_id = data["post_id"]
    rtype = data["type"]
    tid = int(data["tid"])

    user = User_mgmt.query.filter_by(id=account_id).first()

    react = Reactions(post_id=post_id, user_id=user.id, round=tid, type=rtype)

    db.session.add(react)
    try:
        db.session.commit()
    except:
        pass

    return json.dumps({"status": 200})


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