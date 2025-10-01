"""
Unit tests for y_server/routes/interaction_management.py

Tests follow management and follow suggestion endpoints.
"""
import unittest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestInteractionManagement(unittest.TestCase):
    """Test cases for interaction management routes"""

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
        from y_server.modals import Follow, User_mgmt
        self.db.session.query(Follow).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data"""
        from y_server.modals import User_mgmt
        
        # Create test users
        user1 = User_mgmt(
            username='user1',
            password='pass',
            joined_on=1,
            leaning='left'
        )
        user2 = User_mgmt(
            username='user2',
            password='pass',
            joined_on=1,
            leaning='right'
        )
        user3 = User_mgmt(
            username='user3',
            password='pass',
            joined_on=1,
            leaning='neutral'
        )
        self.db.session.add_all([user1, user2, user3])
        self.db.session.commit()
        
        self.user1_id = user1.id
        self.user2_id = user2.id
        self.user3_id = user3.id

    def test_add_follow(self):
        """Test adding a follow relationship"""
        payload = {
            'user_id': self.user1_id,
            'target': self.user2_id,
            'action': 'follow',
            'tid': 1
        }
        
        response = self.client.post(
            '/follow',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)
        
        # Verify follow was created
        from y_server.modals import Follow
        follow = Follow.query.filter_by(
            user_id=self.user1_id,
            follower_id=self.user2_id
        ).first()
        self.assertIsNotNone(follow)
        self.assertEqual(follow.action, 'follow')

    def test_followers_list(self):
        """Test getting followers list"""
        from y_server.modals import Follow
        
        # Create follow relationships
        follow1 = Follow(
            user_id=self.user1_id,
            follower_id=self.user2_id,
            round=1,
            action='follow'
        )
        follow2 = Follow(
            user_id=self.user1_id,
            follower_id=self.user3_id,
            round=1,
            action='follow'
        )
        self.db.session.add_all([follow1, follow2])
        self.db.session.commit()
        
        # Get followers
        payload = {'user_id': self.user1_id}
        response = self.client.get(
            '/followers',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should have 2 followers
        self.assertEqual(len(data), 2)

    def test_follow_suggestions_random(self):
        """Test random follow suggestions"""
        payload = {
            'user_id': self.user1_id,
            'n_neighbors': 2,
            'leaning_biased': 0,
            'mode': 'random'
        }
        
        response = self.client.post(
            '/follow_suggestions',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should return suggestions
        self.assertIsInstance(data, dict)

    def test_follow_suggestions_preferential_attachment(self):
        """Test preferential attachment follow suggestions"""
        from y_server.modals import Follow
        
        # Create some follow relationships to test preferential attachment
        follow = Follow(
            user_id=self.user2_id,
            follower_id=self.user3_id,
            round=1,
            action='follow'
        )
        self.db.session.add(follow)
        self.db.session.commit()
        
        payload = {
            'user_id': self.user1_id,
            'n_neighbors': 2,
            'leaning_biased': 0,
            'mode': 'preferential_attachment'
        }
        
        response = self.client.post(
            '/follow_suggestions',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should return suggestions
        self.assertIsInstance(data, dict)

    def test_multiple_follow_actions(self):
        """Test multiple follow/unfollow actions"""
        from y_server.modals import Follow
        
        # User2 follows user1
        follow1 = Follow(
            user_id=self.user1_id,
            follower_id=self.user2_id,
            round=1,
            action='follow'
        )
        self.db.session.add(follow1)
        self.db.session.commit()
        
        # User2 unfollows user1
        follow2 = Follow(
            user_id=self.user1_id,
            follower_id=self.user2_id,
            round=2,
            action='unfollow'
        )
        self.db.session.add(follow2)
        self.db.session.commit()
        
        # Check that both actions are recorded
        follows = Follow.query.filter_by(
            user_id=self.user1_id,
            follower_id=self.user2_id
        ).all()
        self.assertEqual(len(follows), 2)


if __name__ == '__main__':
    unittest.main()
