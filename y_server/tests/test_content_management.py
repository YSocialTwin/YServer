"""
Unit tests for y_server/routes/content_management.py

Tests content management endpoints including posting, reading, and searching.
"""
import unittest
import json
import sys
import os
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestContentManagement(unittest.TestCase):
    """Test cases for content management routes"""

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
            User_mgmt, Post, Reactions, Emotions, Post_emotions,
            Hashtags, Post_hashtags, Mentions, Rounds, Interests,
            Post_topics, User_interest, Post_Sentiment, Recommendations
        )
        self.db.session.query(Post_emotions).delete()
        self.db.session.query(Post_hashtags).delete()
        self.db.session.query(Mentions).delete()
        self.db.session.query(Post_topics).delete()
        self.db.session.query(User_interest).delete()
        self.db.session.query(Post_Sentiment).delete()
        self.db.session.query(Reactions).delete()
        self.db.session.query(Recommendations).delete()
        self.db.session.query(Post).delete()
        self.db.session.query(Emotions).delete()
        self.db.session.query(Hashtags).delete()
        self.db.session.query(Interests).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.query(Rounds).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data"""
        from y_server.modals import User_mgmt, Post, Emotions, Interests, Rounds
        
        # Create test users
        user1 = User_mgmt(username='contentuser1', password='pass', joined_on=1)
        user2 = User_mgmt(username='contentuser2', password='pass', joined_on=1)
        self.db.session.add_all([user1, user2])
        self.db.session.commit()
        self.user1_id = user1.id
        self.user2_id = user2.id
        
        # Create emotions
        emotions = [
            Emotions(emotion='happy'),
            Emotions(emotion='sad'),
        ]
        self.db.session.add_all(emotions)
        self.db.session.commit()
        
        # Create interests/topics
        interest = Interests(interest='technology')
        self.db.session.add(interest)
        self.db.session.commit()
        
        # Create rounds
        round_entry = Rounds(day=1, hour=1)
        self.db.session.add(round_entry)
        self.db.session.commit()
        
        # Create test posts
        post1 = Post(tweet='Test post 1', round=1, user_id=user1.id, thread_id=1)
        post2 = Post(tweet='Test post 2', round=1, user_id=user2.id, thread_id=2)
        self.db.session.add_all([post1, post2])
        self.db.session.commit()
        
        # Update thread_id after commit
        post1.thread_id = post1.id
        post2.thread_id = post2.id
        self.db.session.commit()
        
        self.post1_id = post1.id
        self.post2_id = post2.id

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_post_creation(self, mock_toxicity, mock_vader):
        """Test creating a new post"""
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        payload = {
            'user_id': self.user1_id,
            'tweet': 'This is a new test post!',
            'emotions': ['happy'],
            'hashtags': ['test', 'post'],
            'mentions': [],
            'topics': [],
            'tid': 1,
            'comment_to': -1,
            'shared_from': -1
        }
        
        response = self.client.post(
            '/post',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        
        # Verify post was created
        from y_server.modals import Post
        posts = Post.query.filter_by(user_id=self.user1_id).all()
        self.assertGreater(len(posts), 1)  # Should have more than the initial post

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_post_with_comment(self, mock_toxicity, mock_vader):
        """Test creating a comment on a post"""
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        payload = {
            'user_id': self.user2_id,
            'tweet': 'This is a comment',
            'emotions': [],
            'hashtags': [],
            'mentions': [],
            'topics': [],
            'tid': 1,
            'comment_to': self.post1_id,
            'shared_from': -1
        }
        
        response = self.client.post(
            '/post',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)

    def test_read_posts(self):
        """Test reading posts"""
        payload = {
            'limit': 10,
            'mode': 'latest',
            'visibility_rounds': 0,
            'uid': self.user1_id
        }
        
        response = self.client.post(
            '/read',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        # Response should contain posts data

    def test_search_posts(self):
        """Test searching posts"""
        payload = {
            'query': 'test',
            'limit': 10,
            'uid': self.user1_id,
            'visibility_rounds': 0
        }
        
        response = self.client.post(
            '/search',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should return list of post IDs
        self.assertIsInstance(data, list)

    def test_read_mentions(self):
        """Test reading mentions for a user"""
        from y_server.modals import Mentions
        
        # Create a mention
        mention = Mentions(
            user_id=self.user1_id,
            post_id=self.post2_id,
            round=1,
            answered=0
        )
        self.db.session.add(mention)
        self.db.session.commit()
        
        payload = {
            'uid': self.user1_id,
            'user_id': self.user1_id,
            'limit': 10,
            'round_id': 1,
            'visibility_rounds': 0
        }
        
        response = self.client.post(
            '/read_mentions',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_react_to_post(self, mock_toxicity, mock_vader):
        """Test reacting to a post"""
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        payload = {
            'user_id': self.user2_id,
            'post_id': self.post1_id,
            'type': 'like',
            'tid': 1
        }
        
        response = self.client.post(
            '/reaction',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        
        # Verify reaction was created
        from y_server.modals import Reactions
        reaction = Reactions.query.filter_by(
            user_id=self.user2_id,
            post_id=self.post1_id
        ).first()
        self.assertIsNotNone(reaction)
        self.assertEqual(reaction.type, 'like')

    def test_get_thread_root(self):
        """Test getting the root of a thread"""
        payload = {'post_id': str(self.post1_id)}
        
        response = self.client.get(
            '/get_thread_root',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_share_post(self, mock_toxicity, mock_vader):
        """Test sharing a post"""
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        payload = {
            'user_id': self.user2_id,
            'tweet': 'Sharing this post',
            'emotions': [],
            'hashtags': [],
            'mentions': [],
            'topics': [],
            'tid': 1,
            'comment_to': -1,
            'shared_from': self.post1_id
        }
        
        response = self.client.post(
            '/post',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)


if __name__ == '__main__':
    unittest.main()
