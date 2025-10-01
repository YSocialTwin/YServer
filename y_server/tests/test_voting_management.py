"""
Unit tests for y_server/routes/voting_management.py

Tests voting/preference casting endpoints.
"""
import unittest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestVotingManagement(unittest.TestCase):
    """Test cases for voting management routes"""

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
        from y_server.modals import Voting, User_mgmt, Post
        self.db.session.query(Voting).delete()
        self.db.session.query(Post).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data"""
        from y_server.modals import User_mgmt, Post
        
        # Create test user
        user = User_mgmt(
            username='voteuser',
            password='pass',
            joined_on=1
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.user_id = user.id
        
        # Create test post
        post = Post(
            tweet='Test post for voting',
            round=1,
            user_id=user.id
        )
        self.db.session.add(post)
        self.db.session.commit()
        self.post_id = post.id

    def test_cast_preference_upvote(self):
        """Test casting an upvote preference"""
        payload = {
            'tid': 1,
            'user_id': self.user_id,
            'vote': 'upvote',
            'content_type': 'post',
            'content_id': self.post_id
        }
        
        response = self.client.post(
            '/cast_preference',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)
        
        # Verify vote was created
        from y_server.modals import Voting
        vote = Voting.query.filter_by(user_id=self.user_id).first()
        self.assertIsNotNone(vote)
        self.assertEqual(vote.preference, 'upvote')
        self.assertEqual(vote.content_type, 'post')
        self.assertEqual(vote.content_id, self.post_id)

    def test_cast_preference_downvote(self):
        """Test casting a downvote preference"""
        payload = {
            'tid': 2,
            'user_id': self.user_id,
            'vote': 'downvote',
            'content_type': 'post',
            'content_id': self.post_id
        }
        
        response = self.client.post(
            '/cast_preference',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)
        
        # Verify vote was created
        from y_server.modals import Voting
        vote = Voting.query.filter_by(user_id=self.user_id, round=2).first()
        self.assertIsNotNone(vote)
        self.assertEqual(vote.preference, 'downvote')

    def test_cast_preference_multiple_votes(self):
        """Test casting multiple votes"""
        # Cast first vote
        payload1 = {
            'tid': 1,
            'user_id': self.user_id,
            'vote': 'upvote',
            'content_type': 'post',
            'content_id': self.post_id
        }
        
        response1 = self.client.post(
            '/cast_preference',
            data=json.dumps(payload1),
            content_type='application/json'
        )
        self.assertEqual(response1.status_code, 200)
        
        # Cast second vote
        payload2 = {
            'tid': 2,
            'user_id': self.user_id,
            'vote': 'downvote',
            'content_type': 'post',
            'content_id': self.post_id
        }
        
        response2 = self.client.post(
            '/cast_preference',
            data=json.dumps(payload2),
            content_type='application/json'
        )
        self.assertEqual(response2.status_code, 200)
        
        # Verify both votes exist
        from y_server.modals import Voting
        votes = Voting.query.filter_by(user_id=self.user_id).all()
        self.assertEqual(len(votes), 2)

    def test_cast_preference_different_content_types(self):
        """Test casting votes on different content types"""
        payload = {
            'tid': 3,
            'user_id': self.user_id,
            'vote': 'upvote',
            'content_type': 'article',
            'content_id': 999
        }
        
        response = self.client.post(
            '/cast_preference',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify vote was created with correct content type
        from y_server.modals import Voting
        vote = Voting.query.filter_by(user_id=self.user_id, content_type='article').first()
        self.assertIsNotNone(vote)
        self.assertEqual(vote.content_type, 'article')


if __name__ == '__main__':
    unittest.main()
