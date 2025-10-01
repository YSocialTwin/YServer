"""
Unit tests for y_server/routes/news_management.py

Tests news article commenting endpoints.
"""
import unittest
import json
import sys
import os
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestNewsManagement(unittest.TestCase):
    """Test cases for news management routes"""

    @classmethod
    def setUpClass(cls):
        """Set up test Flask app"""
        from y_server import app, db
        
        cls.app = app
        cls.db = db
        
        # Configure for testing
        cls.app.config['TESTING'] = True
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['perspective_api'] = None  # Disable perspective API for tests
        
        cls.client = cls.app.test_client()
        
        with cls.app.app_context():
            cls.db.create_all()

    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.drop_all()

    def setUp(self):
        """Set up before each test"""
        self.app_context = self.app.app_context()
        self.app_context.push()
        self._create_test_data()

    def tearDown(self):
        """Clean up after each test"""
        from y_server.modals import (
            User_mgmt, Post, Articles, Websites, Emotions,
            Post_emotions, Hashtags, Post_hashtags, Mentions,
            Interests, Post_topics, Article_topics, Post_Sentiment
        )
        self.db.session.query(Post_emotions).delete()
        self.db.session.query(Post_hashtags).delete()
        self.db.session.query(Mentions).delete()
        self.db.session.query(Post_topics).delete()
        self.db.session.query(Article_topics).delete()
        self.db.session.query(Post_Sentiment).delete()
        self.db.session.query(Post).delete()
        self.db.session.query(Articles).delete()
        self.db.session.query(Websites).delete()
        self.db.session.query(Emotions).delete()
        self.db.session.query(Hashtags).delete()
        self.db.session.query(Interests).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data"""
        from y_server.modals import User_mgmt, Emotions, Interests
        
        # Create test user
        user = User_mgmt(username='newsuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        self.user_id = user.id
        
        # Create emotions
        emotions = [
            Emotions(emotion='happy'),
            Emotions(emotion='sad'),
        ]
        self.db.session.add_all(emotions)
        self.db.session.commit()
        
        # Create interests
        interest = Interests(interest='politics')
        self.db.session.add(interest)
        self.db.session.commit()

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_news(self, mock_toxicity, mock_vader):
        """Test commenting on a news article"""
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        payload = {
            'user_id': self.user_id,
            'tweet': 'Interesting article!',
            'emotions': ['happy'],
            'hashtags': ['news', 'interesting'],
            'mentions': [],
            'tid': 1,
            'title': 'Breaking News',
            'summary': 'This is a summary of the news',
            'link': 'http://news.com/article',
            'publisher': 'News Site',
            'rss': 'http://news.com/rss',
            'leaning': 'neutral',
            'country': 'US',
            'language': 'en',
            'category': 'general',
            'fetched_on': 1
        }
        
        response = self.client.post(
            '/news',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        
        # Verify article was created
        from y_server.modals import Articles, Websites
        website = Websites.query.filter_by(name='News Site').first()
        self.assertIsNotNone(website)
        
        article = Articles.query.filter_by(title='Breaking News').first()
        self.assertIsNotNone(article)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_existing_news(self, mock_toxicity, mock_vader):
        """Test commenting on an existing news article"""
        from y_server.modals import Websites, Articles
        
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        # Create website and article
        website = Websites(
            name='Existing News',
            rss='http://existing.com/rss',
            leaning='neutral',
            category='general',
            last_fetched=1,
            language='en',
            country='US'
        )
        self.db.session.add(website)
        self.db.session.commit()
        
        article = Articles(
            title='Existing Article',
            summary='Summary',
            website_id=website.id,
            link='http://existing.com/article',
            fetched_on=1
        )
        self.db.session.add(article)
        self.db.session.commit()
        
        payload = {
            'user_id': self.user_id,
            'tweet': 'Comment on existing article',
            'emotions': [],
            'hashtags': [],
            'mentions': [],
            'tid': 1,
            'title': 'Existing Article',
            'summary': 'Summary',
            'link': 'http://existing.com/article',
            'publisher': 'Existing News',
            'rss': 'http://existing.com/rss',
            'leaning': 'neutral',
            'country': 'US',
            'language': 'en',
            'category': 'general',
            'fetched_on': 1
        }
        
        response = self.client.post(
            '/news',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify only one article with this link exists
        article_count = Articles.query.filter_by(link='http://existing.com/article').count()
        self.assertEqual(article_count, 1)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_news_with_mentions(self, mock_toxicity, mock_vader):
        """Test commenting on news with mentions"""
        from y_server.modals import User_mgmt
        
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        # Create another user to mention
        user2 = User_mgmt(username='mentioned', password='pass', joined_on=1)
        self.db.session.add(user2)
        self.db.session.commit()
        
        payload = {
            'user_id': self.user_id,
            'tweet': 'Check this out @mentioned',
            'emotions': [],
            'hashtags': [],
            'mentions': ['mentioned'],
            'tid': 1,
            'title': 'News Title',
            'summary': 'News summary',
            'link': 'http://news.com/article2',
            'publisher': 'News Site',
            'rss': 'http://news.com/rss',
            'leaning': 'neutral',
            'country': 'US',
            'language': 'en',
            'category': 'general',
            'fetched_on': 1
        }
        
        response = self.client.post(
            '/news',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify mention was created
        from y_server.modals import Mentions
        mention = Mentions.query.filter_by(user_id=user2.id).first()
        self.assertIsNotNone(mention)


if __name__ == '__main__':
    unittest.main()
