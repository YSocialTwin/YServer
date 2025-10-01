"""
Unit tests for y_server/routes/user_managment.py

Tests user management endpoints including registration, user retrieval, and updates.
"""
import unittest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestUserManagement(unittest.TestCase):
    """Test cases for user management routes"""

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

    def tearDown(self):
        """Clean up after each test"""
        from y_server.modals import User_mgmt, Post, User_interest, Interests, Rounds
        self.db.session.query(User_interest).delete()
        self.db.session.query(Post).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.query(Interests).delete()
        self.db.session.query(Rounds).delete()
        self.db.session.commit()
        self.app_context.pop()

    def test_register_new_user(self):
        """Test registering a new user"""
        payload = {
            'name': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'leaning': 'neutral',
            'age': 25,
            'user_type': 'user',
            'oe': 'high',
            'co': 'medium',
            'ex': 'high',
            'ag': 'low',
            'ne': 'medium',
            'language': 'en',
            'education_level': 'bachelor',
            'joined_on': 1,
            'round_actions': 3,
            'owner': 'system',
            'gender': 'other',
            'nationality': 'US',
            'toxicity': 'no',
            'daily_activity_level': 1,
            'profession': 'engineer'
        }
        
        response = self.client.post(
            '/register',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        self.assertIn('id', data)
        self.assertEqual(data['username'], 'testuser')

    def test_register_duplicate_user(self):
        """Test registering a user that already exists"""
        payload = {
            'name': 'duplicate',
            'email': 'dup@example.com',
            'password': 'pass',
            'leaning': 'neutral',
            'age': 30,
            'user_type': 'user',
            'oe': 'high',
            'co': 'medium',
            'ex': 'high',
            'ag': 'low',
            'ne': 'medium',
            'language': 'en',
            'education_level': 'bachelor',
            'joined_on': 1,
            'round_actions': 3,
            'owner': 'system',
            'gender': 'other',
            'nationality': 'US',
            'toxicity': 'no',
            'daily_activity_level': 1,
            'profession': 'engineer'
        }
        
        # Register first time
        response1 = self.client.post(
            '/register',
            data=json.dumps(payload),
            content_type='application/json'
        )
        data1 = json.loads(response1.data)
        user_id = data1['id']
        
        # Register again with same username
        response2 = self.client.post(
            '/register',
            data=json.dumps(payload),
            content_type='application/json'
        )
        data2 = json.loads(response2.data)
        
        # Should return existing user
        self.assertEqual(data2['id'], user_id)

    def test_get_user(self):
        """Test getting user information"""
        # Register a user first
        from y_server.modals import User_mgmt
        user = User_mgmt(
            username='getuser',
            email='get@example.com',
            password='pass',
            joined_on=1,
            age=28
        )
        self.db.session.add(user)
        self.db.session.commit()
        
        # Get user
        payload = {'username': 'getuser'}
        response = self.client.post(
            '/get_user',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['username'], 'getuser')
        self.assertEqual(data['email'], 'get@example.com')
        self.assertEqual(data['age'], 28)

    def test_get_nonexistent_user(self):
        """Test getting a user that doesn't exist"""
        payload = {'username': 'nonexistent'}
        response = self.client.post(
            '/get_user',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('error', data)
        self.assertEqual(data['status'], 404)

    def test_user_exists(self):
        """Test checking if user exists"""
        # Create a user
        from y_server.modals import User_mgmt
        user = User_mgmt(
            username='existsuser',
            email='exists@example.com',
            password='pass',
            joined_on=1
        )
        self.db.session.add(user)
        self.db.session.commit()
        
        # Check if exists
        payload = {'name': 'existsuser', 'email': 'exists@example.com'}
        response = self.client.post(
            '/user_exists',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        self.assertIn('id', data)

    def test_user_not_exists(self):
        """Test checking if non-existent user exists"""
        payload = {'name': 'notexistsuser', 'email': 'not@example.com'}
        response = self.client.post(
            '/user_exists',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 404)

    def test_update_user(self):
        """Test updating user information"""
        # Create a user
        from y_server.modals import User_mgmt
        user = User_mgmt(
            username='updateuser',
            email='update@example.com',
            password='pass',
            joined_on=1,
            recsys_type='default'
        )
        self.db.session.add(user)
        self.db.session.commit()
        
        # Update user
        payload = {
            'username': 'updateuser',
            'email': 'update@example.com',
            'recsys_type': 'collaborative'
        }
        response = self.client.post(
            '/update_user',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        
        # Verify update
        updated_user = User_mgmt.query.filter_by(username='updateuser').first()
        self.assertEqual(updated_user.recsys_type, 'collaborative')

    def test_set_interests(self):
        """Test setting interests"""
        payload = ['technology', 'sports', 'politics']
        
        response = self.client.post(
            '/set_interests',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)
        
        # Verify interests were created
        from y_server.modals import Interests
        interests = Interests.query.all()
        self.assertEqual(len(interests), 3)

    def test_set_user_interests(self):
        """Test setting user interests"""
        from y_server.modals import User_mgmt, Interests, Rounds
        
        # Create user
        user = User_mgmt(username='intuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        
        # Create interests
        interest1 = Interests(interest='tech')
        interest2 = Interests(interest='sports')
        self.db.session.add_all([interest1, interest2])
        self.db.session.commit()
        
        # Create round
        round_entry = Rounds(day=1, hour=1)
        self.db.session.add(round_entry)
        self.db.session.commit()
        
        # Set user interests (use 'round' not 'round_id')
        payload = {
            'user_id': user.id,
            'interests': [interest1.iid, interest2.iid],
            'round': round_entry.id
        }
        
        response = self.client.post(
            '/set_user_interests',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['status'], 200)


if __name__ == '__main__':
    unittest.main()
