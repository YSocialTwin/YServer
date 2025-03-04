from nltk.sentiment import SentimentIntensityAnalyzer
from perspective import PerspectiveAPI
from y_server.modals import Post_Toxicity


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
            print(e)
            return
