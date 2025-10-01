"""
Unit tests for y_server/routes/time_management.py

Tests time management endpoints including current_time and update_time.
"""
import unittest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestTimeManagement(unittest.TestCase):
    """Test cases for time management routes"""

    @classmethod
    def setUpClass(cls):
        """Set up test Flask app"""
        # Import after path is set
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
        from y_server.modals import Rounds
        self.db.session.query(Rounds).delete()
        self.db.session.commit()
        self.app_context.pop()

    def test_current_time_no_rounds(self):
        """Test current_time when no rounds exist"""
        response = self.client.get('/current_time')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should create default round
        self.assertIn('id', data)
        self.assertIn('day', data)
        self.assertIn('round', data)
        self.assertEqual(data['day'], 0)
        self.assertEqual(data['round'], 0)

    def test_current_time_with_existing_round(self):
        """Test current_time with existing round"""
        from y_server.modals import Rounds
        
        # Create a round
        round_entry = Rounds(day=5, hour=12)
        self.db.session.add(round_entry)
        self.db.session.commit()
        
        response = self.client.get('/current_time')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should return the most recent round
        self.assertEqual(data['day'], 5)
        self.assertEqual(data['round'], 12)

    def test_update_time_new_round(self):
        """Test update_time with a new round"""
        payload = {
            'day': 10,
            'round': 15
        }
        
        response = self.client.post(
            '/update_time',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should create and return new round
        self.assertEqual(data['day'], 10)
        self.assertEqual(data['round'], 15)
        self.assertIn('id', data)

    def test_update_time_existing_round(self):
        """Test update_time with an existing round"""
        from y_server.modals import Rounds
        
        # Create a round first
        round_entry = Rounds(day=3, hour=7)
        self.db.session.add(round_entry)
        self.db.session.commit()
        round_id = round_entry.id
        
        # Try to update with same values
        payload = {
            'day': 3,
            'round': 7
        }
        
        response = self.client.post(
            '/update_time',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Should return existing round
        self.assertEqual(data['day'], 3)
        self.assertEqual(data['round'], 7)
        self.assertEqual(data['id'], round_id)

    def test_update_time_multiple_rounds(self):
        """Test update_time creates separate rounds"""
        # Create first round
        payload1 = {'day': 1, 'round': 1}
        response1 = self.client.post(
            '/update_time',
            data=json.dumps(payload1),
            content_type='application/json'
        )
        data1 = json.loads(response1.data)
        
        # Create second round
        payload2 = {'day': 2, 'round': 2}
        response2 = self.client.post(
            '/update_time',
            data=json.dumps(payload2),
            content_type='application/json'
        )
        data2 = json.loads(response2.data)
        
        # IDs should be different
        self.assertNotEqual(data1['id'], data2['id'])
        
        # Current time should be the latest
        response = self.client.get('/current_time')
        data = json.loads(response.data)
        self.assertEqual(data['day'], 2)
        self.assertEqual(data['round'], 2)


if __name__ == '__main__':
    unittest.main()
