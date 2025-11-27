import sys
import traceback
from datetime import datetime

from nltk.sentiment import SentimentIntensityAnalyzer
from perspective import PerspectiveAPI
from y_server.modals import Post_Toxicity


def _log_error_stderr(message):
    """
    Log an error message to stderr with timestamp formatting.
    
    Each write starts with "### date and time ###\n" and ends with "\n####".
    Uses flush=True to ensure immediate output for debugging.
    
    :param message: the error message to log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"### {timestamp} ###\n{message}\n####", file=sys.stderr, flush=True)


def vader_sentiment(text):
    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def toxicity(text, api_key, post_id, db):
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
            _log_error_stderr(f"Toxicity API error for post_id={post_id}: {str(e)}\nText: {text[:100]}...\nTraceback: {traceback.format_exc()}")
            return
