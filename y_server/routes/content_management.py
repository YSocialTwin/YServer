import json
from flask import request
from y_server import app, db
from sqlalchemy import desc
from sqlalchemy.sql.expression import func
from y_server.modals import (
    Hashtags,
    Post_hashtags,
    Rounds,
    Post,
    Recommendations,
    Follow,
    Reactions,
    Mentions,
    User_mgmt,
    Emotions,
    Post_emotions,
    Post_topics,
    Post_Sentiment,
    Interests
)
from y_server.content_analysis import vader_sentiment, toxicity


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
    except:
        uid = None
    try:
        fratio = float(data["followers_ratio"])
    except:
        fratio = 1
    articles = False
    if "article" in data:
        articles = True
        # get the user
        us = User_mgmt.query.filter_by(id=uid).first()
        # get news pages ids having the same user leaning
        pages = User_mgmt.query.filter_by(is_page=1, leaning=us.leaning).all()
        if pages is not None:
            pages = [x.id for x in pages]
        else:
            pages = []

    # visibility
    current_round = Rounds.query.order_by(desc(Rounds.id)).first()
    visibility = current_round.id - vround

    if mode == "rchrono":
        # get posts in reverse chronological order
        if articles:
            posts = [
                db.session.query(Post)
                .filter(Post.round >= visibility, Post.news_id != -1, Post.user_id in pages)
                .order_by(desc(Post.id))
                .limit(10)
            ]
        else:
            posts = [
                db.session.query(Post)
                .filter(Post.round >= visibility, Post.user_id != uid)
                .order_by(desc(Post.id))
                .limit(10)
            ]

    elif mode == "rchrono_popularity":
        # get posts ordered by likes in reverse chronological order
        if articles:
            posts = [
                (
                    db.session.query(Post, func.count(Reactions.user_id).label("total"))
                    .filter(
                        Post.round >= visibility,
                        Post.news_id != -1,
                        Post.user_id in pages,
                    )
                    .join(Reactions)
                    .group_by(Post)
                    .order_by(desc("total"), desc(Post.id))
                ).limit(limit)
            ]
        else:
            posts = [
                (
                    db.session.query(Post, func.count(Reactions.user_id).label("total"))
                    .filter(Post.round >= visibility, Post.user_id != uid)
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
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers in reverse chronological order
        if articles:
            posts = (
                Post.query.filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id in pages,
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
                    Post.query.filter(
                        Post.round >= visibility,
                        Post.news_id != -1,
                        Post.user_id != uid,
                    )
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )
            else:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility, Post.user_id != uid)
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
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers ordered by likes and reverse chronologically
        if articles:
            posts = (
                db.session.query(Post, func.count(Reactions.user_id).label("total"))
                .join(Reactions)
                .filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id in pages,
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
                    Post.query.filter(Post.round >= visibility, Post.news_id != -1, Post.user_id in pages)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )
            else:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility, Post.user_id != uid)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                )

            posts = [posts, additional_posts]

    else:
        # get posts in random order
        if articles:
            posts = [
                (
                    Post.query.filter(Post.round >= visibility, Post.news_id != -1, Post.user_id in pages)
                    .order_by(func.random())
                    .limit(limit)
                )
            ]
        else:
            posts = [
                (
                    Post.query.filter(Post.round >= visibility, Post.user_id != uid)
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
    topics = data["topics"]
    tid = int(data["tid"])

    user = User_mgmt.query.filter_by(id=account_id).first()

    text = text.strip("-")

    post = Post(
        tweet=text,
        round=tid,
        user_id=user.id,
        comment_to=-1,
    )

    db.session.add(post)
    db.session.commit()

    sentiment = vader_sentiment(text)

    toxicity(text, app.config["perspective_api"], post.id, db)

    post.thread_id = post.id
    db.session.commit()

    for topic_id in topics:
        tp = Post_topics(post_id=post.id, topic_id=topic_id)
        db.session.add(tp)
        db.session.commit()

        post_sentiment = Post_Sentiment(
            post_id=post.id,
            user_id=user.id,
            pos=sentiment["pos"],
            neg=sentiment["neg"],
            neu=sentiment["neu"],
            compound=sentiment["compound"],
            round=tid,
            is_post=1,
            topic_id=topic_id
        )
        db.session.add(post_sentiment)
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
            mn = Mentions(user_id=us.id, post_id=post.id, round=tid)
            db.session.add(mn)
            db.session.commit()
        else:
            text = text.replace(mention, "")

            # update post
            post.tweet = text.lstrip().rstrip()
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

    text = text.strip("-")

    new_post = Post(
        tweet=text,
        round=tid,
        user_id=user.id,
        comment_to=post_id,
        thread_id=post.thread_id,
    )

    db.session.add(new_post)
    db.session.commit()

    # get sentiment of the post is responding to
    sentiment_parent = Post_Sentiment.query.filter_by(post_id=post_id).first()
    if sentiment_parent is not None:
        sentiment_parent = sentiment_parent.compound
        # thresholding
        if sentiment_parent > 0.05:
            sentiment_parent = "pos"
        elif sentiment_parent < -0.05:
            sentiment_parent = "neg"
        else:
            sentiment_parent = "neu"
    else:
        sentiment_parent = ""

    sentiment = vader_sentiment(text)

    toxicity(text, app.config["perspective_api"], new_post.id, db)

    # get topics associated to post.id
    post_topics = Post_topics.query.filter_by(post_id=post.thread_id).all()
    for topic in post_topics:

        post_sentiment = Post_Sentiment(
            post_id=new_post.id,
            user_id=user.id,
            pos=sentiment["pos"],
            neg=sentiment["neg"],
            neu=sentiment["neu"],
            compound=sentiment["compound"],
            sentiment_parent=sentiment_parent,
            round=tid,
            is_comment=1,
            topic_id=topic.topic_id
        )
        db.session.add(post_sentiment)
        db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=new_post.id, emotion_id=em.id)
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

        post_tag = Post_hashtags(post_id=new_post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()
        if us is not None:
            mn = Mentions(user_id=us.id, post_id=new_post.id, round=tid)
            db.session.add(mn)
            db.session.commit()
        else:
            text = text.replace(mention, "")

            # update post
            post.tweet = text.lstrip().rstrip()

            # more than one word
            if len(post.tweet.split(" ")) > 1:
                db.session.commit()
            else:
                db.session.delete(post)
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
            f"@{User_mgmt.query.filter_by(id=user).first().username} - {post.tweet}\n"
        )
    return json.dumps(res)


@app.route("/get_post_topics_name", methods=["GET", "POST"])
def get_post_topics_name():
    """
    Get the topics of a post.

    :return: a json object with the topics
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]

    post_topics = Post_topics.query.filter_by(post_id=post_id).all()

    res = []
    for topic in post_topics:
        tp = Interests.query.filter_by(iid=topic.topic_id).first()
        if tp is not None:
            res.append(tp.interest)

    return json.dumps(res)


@app.route("/get_sentiment", methods=["POST", "GET"])
def get_sentiment():
    """
    Get the sentiment of a post.

    :return: a json object with the sentiment
    """
    data = json.loads(request.get_data())
    user_id = data["user_id"]
    interests = data["interests"]

    res = []

    for interest in interests:
        topic = Interests.query.filter_by(interest=interest).first()
        post_sentiment = Post_Sentiment.query.filter_by(user_id=user_id, topic_id=topic.iid).order_by(desc(Post_Sentiment.id)).first()
        if post_sentiment is not None:
            # thresholding compound
            if post_sentiment.compound > 0.05:
                sentiment = "positive"
            elif post_sentiment.compound < -0.05:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            res.append({"topic": interest, "sentiment": sentiment})

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

    # get compound sentiment of post
    post_sentiment = Post_Sentiment.query.filter_by(post_id=int(post_id)).all()
    for topic_sentiment in post_sentiment:
        topic_id = topic_sentiment.topic_id
        compound = topic_sentiment.compound
        # thresholding compound
        if compound > 0.05:
            sentiment = "pos"
        elif compound < -0.05:
            sentiment = "neg"
        else:
            sentiment = "neu"

        # create reaction sentiment
        reaction_sentiment = Post_Sentiment(
            post_id=post_id,
            user_id=user.id,
            pos=0 if rtype == "dislike" else 1,
            neg=0 if rtype == "like" else 1,
            neu=0,
            compound=1 if rtype == "like" else -1,
            sentiment_parent=sentiment,
            round=tid,
            is_reaction=1,
            topic_id=topic_id
        )
        db.session.add(reaction_sentiment)
        db.session.commit()

    return json.dumps({"status": 200})


@app.route("/get_post_topics", methods=["GET"])
def get_post_topics():
    """
    Get the topics of a post.

    :return: a json object with the topics
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]

    post_topics = Post_topics.query.filter_by(post_id=post_id)

    res = []
    for topic in post_topics:
        res.append(topic.topic_id)

    return json.dumps(res)


@app.route("/get_thread_root", methods=["GET"])
def get_thread_root():
    """
    Get the root of a thread.

    :return: a json object with the root
    """
    data = json.loads(request.get_data())
    post_id = data["post_id"]

    post = Post.query.filter_by(id=post_id).first()

    return json.dumps(post.thread_id)
