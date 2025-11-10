"""
Unit tests for y_server/utils.py

Tests utility functions for follow relationships and content recommendations.
"""
import unittest
import sys
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestUtils(unittest.TestCase):
    """Test cases for utility functions"""

    @classmethod
    def setUpClass(cls):
        """Set up test Flask app and database"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        
        # Import db and models after app config
        from y_server.modals import (
            db, User_mgmt, Post, Follow, Reactions, 
            Interests, User_interest, Post_topics, Rounds
        )
        from y_server import utils
        
        cls.db = db
        cls.db.init_app(cls.app)
        
        # Store model classes
        cls.User_mgmt = User_mgmt
        cls.Post = Post
        cls.Follow = Follow
        cls.Reactions = Reactions
        cls.Interests = Interests
        cls.User_interest = User_interest
        cls.Post_topics = Post_topics
        cls.Rounds = Rounds
        cls.utils = utils
        
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
        
        # Create test data
        self._create_test_data()

    def tearDown(self):
        """Clean up after each test"""
        # Clean up all data
        self.db.session.query(self.Post_topics).delete()
        self.db.session.query(self.User_interest).delete()
        self.db.session.query(self.Reactions).delete()
        self.db.session.query(self.Post).delete()
        self.db.session.query(self.Follow).delete()
        self.db.session.query(self.Interests).delete()
        self.db.session.query(self.User_mgmt).delete()
        self.db.session.query(self.Rounds).delete()
        self.db.session.commit()
        self.app_context.pop()

    def _create_test_data(self):
        """Create test data for utility function tests"""
        # Create users
        user1 = self.User_mgmt(
            username='user1', password='pass', joined_on=1,
            leaning='left', age=25, language='en', education_level='bachelor'
        )
        user2 = self.User_mgmt(
            username='user2', password='pass', joined_on=1,
            leaning='right', age=30, language='en', education_level='master'
        )
        user3 = self.User_mgmt(
            username='user3', password='pass', joined_on=1,
            leaning='left', age=27, language='en', education_level='bachelor'
        )
        self.db.session.add_all([user1, user2, user3])
        self.db.session.commit()
        
        # Store user IDs
        self.user1_id = user1.id
        self.user2_id = user2.id
        self.user3_id = user3.id
        
        # Create follow relationships
        # user2 follows user1, user3 follows user1
        follow1 = self.Follow(
            user_id=user1.id, follower_id=user2.id, 
            round=1, action='follow'
        )
        follow2 = self.Follow(
            user_id=user1.id, follower_id=user3.id,
            round=1, action='follow'
        )
        self.db.session.add_all([follow1, follow2])
        self.db.session.commit()
        
        # Create interests
        interest1 = self.Interests(interest='technology')
        interest2 = self.Interests(interest='politics')
        self.db.session.add_all([interest1, interest2])
        self.db.session.commit()
        
        # Create rounds
        round1 = self.Rounds(day=1, hour=1)
        self.db.session.add(round1)
        self.db.session.commit()
        
        # Create user interests
        user_int1 = self.User_interest(
            user_id=user1.id, interest_id=interest1.iid, round_id=round1.id
        )
        user_int2 = self.User_interest(
            user_id=user2.id, interest_id=interest1.iid, round_id=round1.id
        )
        self.db.session.add_all([user_int1, user_int2])
        self.db.session.commit()
        
        # Create posts
        post1 = self.Post(tweet='Test post 1', round=1, user_id=user2.id)
        post2 = self.Post(tweet='Test post 2', round=1, user_id=user3.id)
        self.db.session.add_all([post1, post2])
        self.db.session.commit()
        
        # Create post topics
        post_topic1 = self.Post_topics(post_id=post1.id, topic_id=interest1.iid)
        post_topic2 = self.Post_topics(post_id=post2.id, topic_id=interest2.iid)
        self.db.session.add_all([post_topic1, post_topic2])
        self.db.session.commit()

    def test_get_follows(self):
        """Test get_follows function"""
        # Test getting followers of user1
        followers = self.utils.get_follows(self.user1_id)
        
        # user1 should have 2 followers (user2 and user3)
        self.assertEqual(len(followers), 2)
        self.assertIn(self.user2_id, followers)
        self.assertIn(self.user3_id, followers)

    def test_get_follows_no_followers(self):
        """Test get_follows with user that has no followers"""
        # user2 has no followers
        followers = self.utils.get_follows(self.user2_id)
        self.assertEqual(len(followers), 0)

    def test_fetch_common_interest_posts(self):
        """Test fetch_common_interest_posts function"""
        # Fetch posts with common interests for user1
        result = self.utils.fetch_common_interest_posts(
            uid=self.user1_id,
            visibility=0,
            articles=False,
            follower_posts_limit=10,
            additional_posts_limit=5
        )
        
        # Result should be a list of query results
        self.assertIsInstance(result, list)

    def test_fetch_common_user_interest_posts(self):
        """Test fetch_common_user_interest_posts function"""
        # Fetch posts from users with common interests
        result = self.utils.fetch_common_user_interest_posts(
            uid=self.user1_id,
            visibility=0,
            articles=False,
            follower_posts_limit=10,
            additional_posts_limit=5,
            reactions_type='like'
        )
        
        # Result should be a query object
        self.assertIsNotNone(result)

    def test_get_posts_by_author(self):
        """Test get_posts_by_author function"""
        # Get posts by specific authors
        result = self.utils.get_posts_by_author(
            visibility=0,
            articles=False,
            limit=10,
            user_ids=[self.user2_id],
            reactions_type='like'
        )
        
        # Should return a query result
        self.assertIsNotNone(result)

    def test_get_posts_by_reactions(self):
        """Test get_posts_by_reactions function"""
        # Create some reactions first
        post = self.Post.query.filter_by(user_id=self.user2_id).first()
        reaction = self.Reactions(
            round=1,
            user_id=self.user1_id,
            post_id=post.id,
            type='like'
        )
        self.db.session.add(reaction)
        self.db.session.commit()
        
        # Get posts by reactions
        result = self.utils.get_posts_by_reactions(
            visibility=0,
            articles=False,
            limit=10,
            user_ids=[self.user1_id],
            reactions_type='like'
        )
        
        # Should return a query result
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
