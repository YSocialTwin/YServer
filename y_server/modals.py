"""
Database models for the YSocial platform.

This module defines all SQLAlchemy ORM models used in the YSocial microblogging
platform, including user management, posts, interactions, recommendations, and
content analysis results.

Models:
    User_mgmt: User account and profile information
    Post: User-generated posts and comments
    Hashtags: Hashtag definitions
    Emotions: Emotion definitions
    Post_emotions: Links posts to emotions
    Post_hashtags: Links posts to hashtags
    Mentions: User mentions in posts
    Reactions: User reactions (likes, etc.) to posts
    Follow: User follow relationships
    Rounds: Simulation time rounds
    Recommendations: Recommended posts for users
    Articles: News articles
    Websites: News sources/websites
    Voting: User voting preferences
    Interests: Topic interests
    User_interest: Links users to their interests
    Post_topics: Links posts to topics
    Images: Image content
    Article_topics: Links articles to topics
    Post_Sentiment: Sentiment analysis results for posts
    Post_Toxicity: Toxicity analysis results for posts
"""

from y_server import db
from flask_login import UserMixin


class User_mgmt(UserMixin, db.Model):
    """
    User management model for storing user profiles and attributes.
    
    Stores comprehensive user information including demographics, personality traits
    (Big Five: openness, conscientiousness, extraversion, agreeableness, neuroticism),
    recommendation system preferences, and activity tracking.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(50), nullable=True, default="")
    password = db.Column(db.String(80), nullable=False)
    leaning = db.Column(db.String(10), default="neutral")
    user_type = db.Column(db.String(10), nullable=False, default="user")
    age = db.Column(db.Integer, default=0)
    oe = db.Column(db.String(50))  # Openness
    co = db.Column(db.String(50))  # Conscientiousness
    ex = db.Column(db.String(50))  # Extraversion
    ag = db.Column(db.String(50))  # Agreeableness
    ne = db.Column(db.String(50))  # Neuroticism
    recsys_type = db.Column(db.String(50), default="default")
    frecsys_type = db.Column(db.String(50), default="default")
    language = db.Column(db.String(10), default="en")
    owner = db.Column(db.String(10), default=None)
    education_level = db.Column(db.String(10), default=None)
    joined_on = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), default=None)
    nationality = db.Column(db.String(15), default=None)
    round_actions = db.Column(db.Integer, default=3)
    toxicity = db.Column(db.String(10), default="no")
    is_page = db.Column(db.Integer, default=0)
    left_on = db.Column(db.Integer, default=None)
    daily_activity_level = db.Column(db.Integer(), default=1)
    profession = db.Column(db.String(50), default="")

    posts = db.relationship("Post", backref="author", lazy=True)
    liked = db.relationship("Reactions", backref="liked_by", lazy=True)


class Post(db.Model):
    """
    Model for storing user posts, comments, and shares.
    
    Supports threaded conversations, image attachments, news article references,
    and post sharing functionality.
    """
    id = db.Column(db.Integer, primary_key=True)
    tweet = db.Column(db.String(500), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    post_img = db.Column(db.String(20))
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    comment_to = db.Column(db.Integer, default=-1)
    thread_id = db.Column(db.Integer)
    news_id = db.Column(db.String(50), db.ForeignKey("articles.id"), default=None)
    image_id = db.Column(db.Integer(), db.ForeignKey("images.id"), default=None)
    shared_from = db.Column(db.Integer, default=-1)
    reaction_count = db.Column(db.Integer, default=0)


class Hashtags(db.Model):
    """Model for storing unique hashtags."""
    id = db.Column(db.Integer, primary_key=True)
    hashtag = db.Column(db.String(20), nullable=False)


class Emotions(db.Model):
    """Model for storing emotion types."""
    id = db.Column(db.Integer, primary_key=True)
    emotion = db.Column(db.String(20), nullable=False)


class Post_emotions(db.Model):
    """Association table linking posts to emotions."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    emotion_id = db.Column(db.Integer, db.ForeignKey("emotions.id"), nullable=False)


class Post_hashtags(db.Model):
    """Association table linking posts to hashtags."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    hashtag_id = db.Column(db.Integer, db.ForeignKey("hashtags.id"), nullable=False)


class Mentions(db.Model):
    """
    Model for tracking user mentions in posts.
    
    Records when users are mentioned in posts and whether they have responded.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    answered = db.Column(db.Integer, default=0)


class Reactions(db.Model):
    """Model for storing user reactions to posts (likes, etc.)."""
    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)


class Follow(db.Model):
    """
    Model for tracking follower relationships between users.
    
    Records follow and unfollow actions over time.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    follower_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(10), nullable=False)


class Rounds(db.Model):
    """Model for tracking simulation time (day and hour)."""
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, nullable=False)
    hour = db.Column(db.Integer, nullable=False)


class Recommendations(db.Model):
    """Model for storing post recommendations generated for users."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_ids = db.Column(db.String(500), nullable=False)
    round = db.Column(db.Integer, nullable=False)


class Articles(db.Model):
    """Model for storing news articles from external sources."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(500), nullable=False)
    website_id = db.Column(db.Integer, db.ForeignKey("websites.id"), nullable=False)
    link = db.Column(db.String(200), nullable=False)
    fetched_on = db.Column(db.Integer, nullable=False)


class Websites(db.Model):
    """
    Model for storing news website information and RSS feeds.
    
    Includes metadata about political leaning, category, language, and country.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    rss = db.Column(db.String(200), nullable=False)
    leaning = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    last_fetched = db.Column(db.Integer, nullable=False)
    language = db.Column(db.String(10), nullable=False)
    country = db.Column(db.String(10), nullable=False)


class Voting(db.Model):
    """Model for storing user voting preferences on content."""
    vid = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    preference = db.Column(db.String(10), nullable=False)
    content_type = db.Column(db.String(10), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)


class Interests(db.Model):
    """Model for storing topic/interest definitions."""
    iid = db.Column(db.Integer, primary_key=True)
    interest = db.Column(db.String(20), nullable=False)


class User_interest(db.Model):
    """Association table linking users to their interests over time."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    interest_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)


class Post_topics(db.Model):
    """Association table linking posts to topics."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)


class Images(db.Model):
    """Model for storing image URLs and descriptions."""
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(400), nullable=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=True)


class Article_topics(db.Model):
    """Association table linking articles to topics."""
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)


class Post_Sentiment(db.Model):
    """
    Model for storing sentiment analysis results for posts.
    
    Captures VADER sentiment scores (negative, neutral, positive, compound)
    and contextual information about the post type and relationships.
    """
    __tablename__ = "post_sentiment"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    round = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    is_post = db.Column(db.Integer, default=0)
    is_comment = db.Column(db.Integer, default=0)
    is_reaction = db.Column(db.Integer, default=0)
    neg = db.Column(db.REAL)
    neu = db.Column(db.REAL)
    pos = db.Column(db.REAL)
    compound = db.Column(db.REAL)
    sentiment_parent = db.Column(db.String(5), default="")


class Post_Toxicity(db.Model):
    """
    Model for storing toxicity analysis results for posts.
    
    Captures various toxicity metrics from Perspective API including general toxicity,
    severe toxicity, identity attacks, insults, profanity, threats, sexually explicit
    content, and flirtation.
    """
    __tablename__ = "post_toxicity"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    toxicity = db.Column(db.REAL, default=0)
    severe_toxicity = db.Column(db.REAL, default=0)
    identity_attack = db.Column(db.REAL, default=0)
    insult = db.Column(db.REAL, default=0)
    profanity = db.Column(db.REAL, default=0)
    threat = db.Column(db.REAL, default=0)
    sexually_explicit = db.Column(db.REAL, default=0)
    flirtation = db.Column(db.REAL, default=0)
