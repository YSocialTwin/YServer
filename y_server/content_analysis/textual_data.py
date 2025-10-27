"""
Textual data analysis module.

This module provides functions for analyzing textual content, including
sentiment analysis using VADER and toxicity detection using Perspective API.
"""

from nltk.sentiment import SentimentIntensityAnalyzer
from perspective import PerspectiveAPI
from y_server.modals import Post_Toxicity


def vader_sentiment(text):
    """
    Perform sentiment analysis on text using VADER (Valence Aware Dictionary and sEntiment Reasoner).
    
    Args:
        text (str): The text to analyze for sentiment.
        
    Returns:
        dict: A dictionary containing sentiment scores with keys:
            - 'neg': Negative sentiment score
            - 'neu': Neutral sentiment score
            - 'pos': Positive sentiment score
            - 'compound': Compound sentiment score (-1 to 1)
    """
    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def toxicity(text, api_key, post_id, db):
    """
    Analyze text for toxicity using the Perspective API.
    
    This function evaluates various aspects of toxicity including general toxicity,
    severe toxicity, identity attacks, insults, profanity, threats, sexually explicit
    content, and flirtation. Results are stored in the database.
    
    Args:
        text (str): The text content to analyze.
        api_key (str): Perspective API key. If None, toxicity analysis is skipped.
        post_id (int): The ID of the post being analyzed.
        db: Database session object for storing toxicity scores.
        
    Returns:
        None: Results are stored directly in the database.
        
    Note:
        If the API call fails or api_key is None, the function returns without error.
    """
    if api_key is not None:
        try:
            p = PerspectiveAPI(api_key)
            toxicity_score = p.score(
                text,
                tests=[
                    "TOXICITY",
                    "SEVERE_TOXICITY",
                    "IDENTITY_ATTACK",
                    "INSULT",
                    "PROFANITY",
                    "THREAT",
                    "SEXUALLY_EXPLICIT",
                    "FLIRTATION",
                ],
            )
            post_toxicity = Post_Toxicity(
                post_id=post_id,
                toxicity=toxicity_score["TOXICITY"],
                severe_toxicity=toxicity_score["SEVERE_TOXICITY"],
                identity_attack=toxicity_score["IDENTITY_ATTACK"],
                insult=toxicity_score["INSULT"],
                profanity=toxicity_score["PROFANITY"],
                threat=toxicity_score["THREAT"],
                sexually_explicit=toxicity_score["SEXUALLY_EXPLICIT"],
                flirtation=toxicity_score["FLIRTATION"],
            )

            db.session.add(post_toxicity)
            db.session.commit()

        except Exception as e:
            print(e)
            return
