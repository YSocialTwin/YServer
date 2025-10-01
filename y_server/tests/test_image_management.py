"""
Unit tests for y_server/routes/image_management.py

Tests image commenting endpoints.
"""
import unittest
import json
import sys
import os
from unittest.mock import patch, Mock

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestImageManagement(unittest.TestCase):
    """Test cases for image management routes"""

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
            User_mgmt, Post, Images, Post_emotions,
            Emotions, Hashtags, Post_hashtags, Post_Sentiment
        )
        self.db.session.query(Post_emotions).delete()
        self.db.session.query(Post_hashtags).delete()
        self.db.session.query(Post_Sentiment).delete()
        self.db.session.query(Post).delete()
        self.db.session.query(Images).delete()
        self.db.session.query(Emotions).delete()
        self.db.session.query(Hashtags).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data"""
        from y_server.modals import User_mgmt, Emotions
        
        # Create test user
        user = User_mgmt(username='imageuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        self.user_id = user.id
        
        # Create emotions
        emotions = [
            Emotions(emotion='happy'),
            Emotions(emotion='sad'),
            Emotions(emotion='angry')
        ]
        self.db.session.add_all(emotions)
        self.db.session.commit()

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_image_new(self, mock_toxicity, mock_vader):
        """Test commenting on a new image"""
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
            'text': 'This is a beautiful image!',
            'emotions': ['happy'],
            'hashtags': ['beautiful', 'image'],
            'tid': 1,
            'image_url': 'http://example.com/image.jpg',
            'image_description': 'A beautiful landscape'
        }
        
        response = self.client.post(
            '/comment_image',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        
        # Verify image was created
        from y_server.modals import Images, Post
        image = Images.query.filter_by(url='http://example.com/image.jpg').first()
        self.assertIsNotNone(image)
        self.assertEqual(image.description, 'A beautiful landscape')
        
        # Verify post was created
        post = Post.query.filter_by(image_id=image.id).first()
        self.assertIsNotNone(post)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_image_existing(self, mock_toxicity, mock_vader):
        """Test commenting on an existing image"""
        from y_server.modals import Images
        
        # Mock sentiment analysis
        mock_vader.return_value = {
            'neg': 0.0,
            'neu': 0.5,
            'pos': 0.5,
            'compound': 0.5
        }
        mock_toxicity.return_value = None
        
        # Create image first
        image = Images(
            url='http://example.com/existing.jpg',
            description='Existing image'
        )
        self.db.session.add(image)
        self.db.session.commit()
        image_id = image.id
        
        payload = {
            'user_id': self.user_id,
            'text': 'Nice photo!',
            'emotions': ['happy'],
            'hashtags': ['nice'],
            'tid': 1,
            'image_url': 'http://example.com/existing.jpg',
            'image_description': 'Existing image'
        }
        
        response = self.client.post(
            '/comment_image',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)
        
        # Verify same image is used
        image_count = Images.query.filter_by(url='http://example.com/existing.jpg').count()
        self.assertEqual(image_count, 1)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_image_with_emotions(self, mock_toxicity, mock_vader):
        """Test commenting with emotions"""
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
            'text': 'Great image!',
            'emotions': ['happy', 'excited'],
            'hashtags': [],
            'tid': 1,
            'image_url': 'http://example.com/test.jpg',
            'image_description': 'Test image'
        }
        
        response = self.client.post(
            '/comment_image',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)

    @patch('y_server.content_analysis.vader_sentiment')
    @patch('y_server.content_analysis.toxicity')
    def test_comment_image_with_hashtags(self, mock_toxicity, mock_vader):
        """Test commenting with hashtags"""
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
            'text': 'Amazing photo!',
            'emotions': [],
            'hashtags': ['amazing', 'photo', 'nature'],
            'tid': 1,
            'image_url': 'http://example.com/nature.jpg',
            'image_description': 'Nature photo'
        }
        
        response = self.client.post(
            '/comment_image',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)
        
        # Verify hashtags were created
        from y_server.modals import Hashtags
        hashtag_count = Hashtags.query.count()
        self.assertGreater(hashtag_count, 0)


if __name__ == '__main__':
    unittest.main()
