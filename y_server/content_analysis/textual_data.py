from nltk.sentiment import SentimentIntensityAnalyzer


def vader_sentiment(text):

    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment