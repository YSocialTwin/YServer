import json
from flask import request
from y_server import app, db
from y_server.modals import (
    Images,
    Post,
    Emotions,
    Post_emotions,
    Hashtags,
    Post_hashtags,
    Post_Sentiment,
)

from y_server.content_analysis import vader_sentiment


@app.route("/comment_image", methods=["POST"])
def post_image():
    """
    Comment on an image.

    :return:
    """
    data = json.loads(request.get_data())
    account_id = int(data["user_id"])
    text = data["text"].strip('"')
    emotions = data["emotions"]
    hashtags = data["hashtags"]
    tid = int(data["tid"])
    image_url = data["image_url"]
    image_description = data["image_description"]
    try:
        article_id = int(data["article_id"])
    except:
        article_id = None

    # check if image exists
    image = Images.query.filter_by(url=image_url).first()
    if image is None:
        image = Images(
            url=image_url,
            description=image_description,
            article_id=article_id,
        )
        db.session.add(image)
        db.session.commit()

    # get image id
    image_id = Images.query.filter_by(url=image_url).first().id

    post = Post(
        tweet=text,
        round=tid,
        user_id=account_id,
        image_id=image_id,
        comment_to=-1,
    )

    db.session.add(post)
    db.session.commit()

    sentiment = vader_sentiment(text)
    post_sentiment = Post_Sentiment(
        post_id=post.id,
        user_id=account_id,
        pos=sentiment["pos"],
        neg=sentiment["neg"],
        neu=sentiment["neu"],
        compound=sentiment["compound"],
        round=tid,
        is_post=1,
        topic_id=-1,
    )
    db.session.add(post_sentiment)
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

    for tag in hashtags:
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

    return json.dumps({"status": 200})
