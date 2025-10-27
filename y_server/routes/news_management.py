"""
News management routes.

This module provides REST API endpoints for managing news articles and related posts,
including commenting on articles, retrieving articles, and sharing article posts.
Integrates with content analysis for sentiment and toxicity detection.
"""

import json
from flask import request
from y_server import app, db
from y_server.modals import (
    Post,
    User_mgmt,
    Emotions,
    Post_emotions,
    Hashtags,
    Post_hashtags,
    Mentions,
    Articles,
    Websites,
    Interests,
    Article_topics,
    Post_topics,
    Post_Sentiment,
)

from y_server.content_analysis import vader_sentiment, toxicity


@app.route("/news", methods=["POST"])
def comment_news():
    """
    Create a comment post on a news article.
    
    Stores the news article and associated website if they don't exist, creates a post
    with the comment, performs sentiment and toxicity analysis, and associates emotions,
    hashtags, mentions, and topics.
    
    Expects JSON data with:
        - user_id (int): ID of the user posting the comment
        - tweet (str): Comment text (can be empty to just save the article)
        - emotions (list[str]): List of emotion tags
        - hashtags (list[str]): List of hashtag strings
        - mentions (list[str]): List of username mentions
        - tid (int): Round/time identifier
        - title (str): Article title
        - summary (str): Article summary
        - link (str): Article URL
        - publisher (str): Publisher name
        - rss (str): RSS feed URL
        - leaning (str): Political leaning of the source
        - country (str): Country of origin
        - language (str): Language code
        - category (str): Article category
        - fetched_on (int): Timestamp when article was fetched
        - topics (list[str], optional): List of topic strings
        
    Returns:
        str: JSON response with status 200 and article_id on success.
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
            fetched_on=fetched_on,
        )
        db.session.add(article)
        db.session.commit()
    article_id = Articles.query.filter_by(link=link, website_id=website_id).first().id

    # add post only if the text is not empty
    # (this might happen if the method is called to save the article for image processing)
    if len(text) == 0:
        post = None

    else:
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

    if post is not None and "topics" in data:
        # compute sentiment
        sentiment = vader_sentiment(text)

        toxicity(text, app.config["perspective_api"], post.id, db)

        for topic in data["topics"]:
            if len(topic) < 1:
                continue

            interests = Interests.query.filter_by(interest=topic).first()
            if interests is None:
                interests = Interests(interest=topic)
                db.session.add(interests)
                db.session.commit()

            interests = Interests.query.filter_by(interest=topic).first()

            at = Article_topics.query.filter_by(
                article_id=article_id, topic_id=interests.iid
            ).first()
            if at is None:
                at = Article_topics(article_id=article_id, topic_id=interests.iid)
                db.session.add(at)

            pt = Post_topics(post_id=post.id, topic_id=interests.iid)
            db.session.add(pt)

            post_sentiment = Post_Sentiment(
                post_id=post.id,
                user_id=user.id,
                pos=sentiment["pos"],
                neg=sentiment["neg"],
                neu=sentiment["neu"],
                compound=sentiment["compound"],
                round=tid,
                is_post=1,
                topic_id=interests.iid,
            )
            db.session.add(post_sentiment)
            db.session.commit()

    return json.dumps({"status": 200, "article_id": article_id})


@app.route("/get_article_by_title", methods=["POST", "GET"])
def article_by_title():
    """
    Retrieve a news article by its title.
    
    Expects JSON data with:
        - title (str): The article title to search for
        
    Returns:
        str: JSON response with article_id if found, or status 404 if not found.
    """
    data = json.loads(request.get_data())
    title = data["title"]

    # get article from title
    article = Articles.query.filter_by(title=title).first()
    if article is not None:
        return json.dumps({"article_id": article.news_id})
    else:
        return json.dumps({"status": 404})


@app.route(
    "/get_article",
    methods=["POST", "GET"],
)
def get_article():
    """
    Retrieve a news article associated with a post.
    
    Expects JSON data with:
        - post_id (int): The post ID to retrieve the article from
        
    Returns:
        str: JSON response with article summary and title if found, or status 404.
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
    "/share",
    methods=["POST", "GET"],
)
def share():
    """
    Share a post containing a news article.
    
    Creates a new post that shares an existing article post, with optional
    additional commentary. Performs sentiment and toxicity analysis on the share text
    and copies topic associations from the original post.
    
    Expects JSON data with:
        - user_id (int): ID of the user sharing the post
        - post_id (int): ID of the original post to share
        - text (str): Share commentary text
        - emotions (list[str]): List of emotion tags
        - hashtags (list[str]): List of hashtag strings
        - mentions (list[str]): List of username mentions
        - tid (int): Round/time identifier
        
    Returns:
        str: JSON response with status 200 on success.
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

    sentiment = vader_sentiment(text)

    toxicity(text, app.config["perspective_api"], post.id, db)

    topics = Post_topics.query.filter_by(post_id=post_id).all()

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

    for topic in topics:
        post_sentiment = Post_Sentiment(
            post_id=post.id,
            user_id=user.id,
            pos=sentiment["pos"],
            neg=sentiment["neg"],
            neu=sentiment["neu"],
            compound=sentiment["compound"],
            sentiment_parent=sentiment_parent,
            round=tid,
            is_post=1,
            topic_id=topic.topic_id,
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
