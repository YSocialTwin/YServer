from __future__ import annotations

from y_server.modals import Post_Toxicity


def vader_sentiment(text):
    try:
        from nltk.sentiment import SentimentIntensityAnalyzer

        sia = SentimentIntensityAnalyzer()
        return sia.polarity_scores(str(text or ""))
    except Exception:
        return {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}


def toxicity(text, api_key, post_id, db):
    if not api_key:
        return

    try:
        from perspective import PerspectiveAPI

        client = PerspectiveAPI(api_key)
        scores = client.score(
            str(text or ""),
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
            toxicity=float(scores.get("TOXICITY", 0.0)),
            severe_toxicity=float(scores.get("SEVERE_TOXICITY", 0.0)),
            identity_attack=float(scores.get("IDENTITY_ATTACK", 0.0)),
            insult=float(scores.get("INSULT", 0.0)),
            profanity=float(scores.get("PROFANITY", 0.0)),
            threat=float(scores.get("THREAT", 0.0)),
            sexually_explicit=float(scores.get("SEXUALLY_EXPLICIT", 0.0)),
            flirtation=float(scores.get("FLIRTATION", 0.0)),
        )
        db.session.add(post_toxicity)
        db.session.commit()
    except Exception:
        return
