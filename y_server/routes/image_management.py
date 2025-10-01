"""
Image management routes.

This module provides REST API endpoints for managing image posts and comments,
including image storage, sentiment analysis, toxicity detection, and emotion/hashtag tagging.
"""

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

from y_server.content_analysis import vader_sentiment, toxicity


@app.route("/comment_image", methods=["POST"])
def post_image():
    """
    Create a post commenting on an image.
    
    Stores the image if it doesn't exist, creates a post with the comment,
    performs sentiment and toxicity analysis, and associates emotions and hashtags.
    
    Expects JSON data with:
        - user_id (int): ID of the user posting the comment
        - text (str): Comment text
        - emotions (list[str]): List of emotion tags
        - hashtags (list[str]): List of hashtag strings
        - tid (int): Round/time identifier
        - image_url (str): URL of the image
        - image_description (str): Description of the image
        - article_id (int, optional): Associated article ID if applicable
        
    Returns:
        str: JSON response with status code 200 on success.
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
    image_id = Images.query.filter_by(url=image_url).first()

    post = Post(
        tweet=text,
        round=tid,
        user_id=account_id,
        image_id=image_id.id,
        comment_to=-1,
    )

    db.session.add(post)
    db.session.commit()

    sentiment = vader_sentiment(text)

    toxicity(text, app.config["perspective_api"], post.id, db)

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
