"""
Unit tests for y_server/routes/experiment_management.py

Tests experiment management endpoints including reset and database operations.
"""
import unittest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestExperimentManagement(unittest.TestCase):
    """Test cases for experiment management routes"""

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
        from y_server.modals import (
            User_mgmt, Post, Reactions, Follow, Hashtags,
            Post_hashtags, Mentions, Post_emotions, Rounds,
            Recommendations, Websites, Articles, Voting,
            Interests, Post_topics, User_interest, Images,
            Article_topics
        )
        # Clean all tables
        self.db.session.query(Post_hashtags).delete()
        self.db.session.query(Post_emotions).delete()
        self.db.session.query(Post_topics).delete()
        self.db.session.query(User_interest).delete()
        self.db.session.query(Article_topics).delete()
        self.db.session.query(Mentions).delete()
        self.db.session.query(Reactions).delete()
        self.db.session.query(Follow).delete()
        self.db.session.query(Recommendations).delete()
        self.db.session.query(Voting).delete()
        self.db.session.query(Post).delete()
        self.db.session.query(Articles).delete()
        self.db.session.query(Websites).delete()
        self.db.session.query(Hashtags).delete()
        self.db.session.query(Interests).delete()
        self.db.session.query(Images).delete()
        self.db.session.query(User_mgmt).delete()
        self.db.session.query(Rounds).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data"""
        from y_server.modals import User_mgmt, Post, Follow, Reactions
        
        # Create test users
        user1 = User_mgmt(username='user1', password='pass', joined_on=1)
        user2 = User_mgmt(username='user2', password='pass', joined_on=1)
        self.db.session.add_all([user1, user2])
        self.db.session.commit()
        
        # Create test posts
        post = Post(tweet='Test post', round=1, user_id=user1.id)
        self.db.session.add(post)
        self.db.session.commit()
        
        # Create test follow
        follow = Follow(
            user_id=user1.id,
            follower_id=user2.id,
            round=1,
            action='follow'
        )
        self.db.session.add(follow)
        self.db.session.commit()
        
        # Create test reaction
        reaction = Reactions(
            round=1,
            user_id=user1.id,
            post_id=post.id,
            type='like'
        )
        self.db.session.add(reaction)
        self.db.session.commit()

    def test_reset_experiment(self):
        """Test resetting the experiment"""
        from y_server.modals import User_mgmt, Post, Reactions, Follow
        
        # Verify data exists before reset
        users_before = User_mgmt.query.count()
        posts_before = Post.query.count()
        
        self.assertGreater(users_before, 0)
        self.assertGreater(posts_before, 0)
        
        # Reset experiment
        response = self.client.post('/reset')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)
        
        # Verify all data is deleted
        users_after = User_mgmt.query.count()
        posts_after = Post.query.count()
        reactions_after = Reactions.query.count()
        follows_after = Follow.query.count()
        
        self.assertEqual(users_after, 0)
        self.assertEqual(posts_after, 0)
        self.assertEqual(reactions_after, 0)
        self.assertEqual(follows_after, 0)

    def test_reset_experiment_empty_database(self):
        """Test resetting an already empty database"""
        from y_server.modals import User_mgmt, Post
        
        # Clear database first
        self.client.post('/reset')
        
        # Verify empty
        self.assertEqual(User_mgmt.query.count(), 0)
        self.assertEqual(Post.query.count(), 0)
        
        # Reset again (should still succeed)
        response = self.client.post('/reset')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 200)

    def test_reset_clears_all_tables(self):
        """Test that reset clears all relevant tables"""
        from y_server.modals import (
            User_mgmt, Post, Reactions, Follow, Hashtags,
            Rounds, Recommendations, Articles, Websites,
            Voting, Interests
        )
        
        # Add additional data
        hashtag = Hashtags(hashtag='test')
        self.db.session.add(hashtag)
        
        round_entry = Rounds(day=1, hour=1)
        self.db.session.add(round_entry)
        
        interest = Interests(interest='technology')
        self.db.session.add(interest)
        
        self.db.session.commit()
        
        # Reset
        response = self.client.post('/reset')
        self.assertEqual(response.status_code, 200)
        
        # Verify all tables are empty
        self.assertEqual(User_mgmt.query.count(), 0)
        self.assertEqual(Post.query.count(), 0)
        self.assertEqual(Reactions.query.count(), 0)
        self.assertEqual(Follow.query.count(), 0)
        self.assertEqual(Hashtags.query.count(), 0)
        self.assertEqual(Rounds.query.count(), 0)
        self.assertEqual(Interests.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
