from nltk.sentiment import SentimentIntensityAnalyzer
import nltk
import os

#try:
#    nltk.data.find(f'sentiment{os.sep}vader_lexicon.zip')
#    print("VADER lexicon is installed.")
#except LookupError:
#    print("VADER lexicon is NOT installed. Installing now...")
#    nltk.download('vader_lexicon')


def vader_sentiment(text):

    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment