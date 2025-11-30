"""
Unit tests for y_server/modals.py

Tests database models including User_mgmt, Post, Reactions, Follow,
Hashtags, Emotions, and other database models.
"""
import unittest
import sys
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestModals(unittest.TestCase):
    """Test cases for database models"""

    @classmethod
    def setUpClass(cls):
        """Set up test Flask app and database"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        
        # Import db and models after app config
        from y_server.modals import (
            db, User_mgmt, Post, Reactions, Follow, Hashtags,
            Post_hashtags, Mentions, Rounds, Recommendations,
            Articles, Websites, Voting, Interests, User_interest,
            Post_topics, Images, Article_topics, Emotions,
            Post_emotions, Post_Sentiment, Post_Toxicity
        )
        
        cls.db = db
        cls.db.init_app(cls.app)
        
        # Store model classes
        cls.User_mgmt = User_mgmt
        cls.Post = Post
        cls.Reactions = Reactions
        cls.Follow = Follow
        cls.Hashtags = Hashtags
        cls.Post_hashtags = Post_hashtags
        cls.Mentions = Mentions
        cls.Rounds = Rounds
        cls.Recommendations = Recommendations
        cls.Articles = Articles
        cls.Websites = Websites
        cls.Voting = Voting
        cls.Interests = Interests
        cls.User_interest = User_interest
        cls.Post_topics = Post_topics
        cls.Images = Images
        cls.Article_topics = Article_topics
        cls.Emotions = Emotions
        cls.Post_emotions = Post_emotions
        cls.Post_Sentiment = Post_Sentiment
        cls.Post_Toxicity = Post_Toxicity
        
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
        self.db.session.rollback()
        self.db.session.remove()
        self.app_context.pop()

    def test_user_mgmt_creation(self):
        """Test User_mgmt model creation"""
        user = self.User_mgmt(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            leaning='neutral',
            age=25,
            user_type='user',
            joined_on=1,
            oe='high',
            co='medium',
            ex='high',
            ag='low',
            ne='medium'
        )
        self.db.session.add(user)
        self.db.session.commit()
        
        retrieved_user = self.User_mgmt.query.filter_by(username='testuser').first()
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.email, 'test@example.com')
        self.assertEqual(retrieved_user.age, 25)
        self.assertEqual(retrieved_user.leaning, 'neutral')

    def test_post_creation(self):
        """Test Post model creation"""
        # Create a user first
        user = self.User_mgmt(
            username='postuser',
            password='pass',
            joined_on=1
        )
        self.db.session.add(user)
        self.db.session.commit()
        
        # Create a post
        post = self.Post(
            tweet='This is a test post',
            round=1,
            user_id=user.id
        )
        self.db.session.add(post)
        self.db.session.commit()
        
        retrieved_post = self.Post.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(retrieved_post)
        self.assertEqual(retrieved_post.tweet, 'This is a test post')
        self.assertEqual(retrieved_post.round, 1)

    def test_reactions_creation(self):
        """Test Reactions model creation"""
        # Create user and post
        user = self.User_mgmt(username='reactuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        
        post = self.Post(tweet='Test post', round=1, user_id=user.id)
        self.db.session.add(post)
        self.db.session.commit()
        
        # Create reaction
        reaction = self.Reactions(
            round=1,
            user_id=user.id,
            post_id=post.id,
            type='like'
        )
        self.db.session.add(reaction)
        self.db.session.commit()
        
        retrieved_reaction = self.Reactions.query.filter_by(post_id=post.id).first()
        self.assertIsNotNone(retrieved_reaction)
        self.assertEqual(retrieved_reaction.type, 'like')

    def test_follow_creation(self):
        """Test Follow model creation"""
        # Create two users
        user1 = self.User_mgmt(username='user1', password='pass', joined_on=1)
        user2 = self.User_mgmt(username='user2', password='pass', joined_on=1)
        self.db.session.add_all([user1, user2])
        self.db.session.commit()
        
        # Create follow relationship
        follow = self.Follow(
            user_id=user1.id,
            follower_id=user2.id,
            round=1,
            action='follow'
        )
        self.db.session.add(follow)
        self.db.session.commit()
        
        retrieved_follow = self.Follow.query.filter_by(user_id=user1.id).first()
        self.assertIsNotNone(retrieved_follow)
        self.assertEqual(retrieved_follow.follower_id, user2.id)
        self.assertEqual(retrieved_follow.action, 'follow')

    def test_hashtags_creation(self):
        """Test Hashtags model creation"""
        hashtag = self.Hashtags(hashtag='python')
        self.db.session.add(hashtag)
        self.db.session.commit()
        
        retrieved_hashtag = self.Hashtags.query.filter_by(hashtag='python').first()
        self.assertIsNotNone(retrieved_hashtag)
        self.assertEqual(retrieved_hashtag.hashtag, 'python')

    def test_rounds_creation(self):
        """Test Rounds model creation"""
        round_entry = self.Rounds(day=5, hour=12)
        self.db.session.add(round_entry)
        self.db.session.commit()
        
        retrieved_round = self.Rounds.query.filter_by(day=5, hour=12).first()
        self.assertIsNotNone(retrieved_round)
        self.assertEqual(retrieved_round.hour, 12)

    def test_articles_creation(self):
        """Test Articles model creation"""
        # Create website first
        website = self.Websites(
            name='Test News',
            rss='http://test.com/rss',
            leaning='neutral',
            category='general',
            last_fetched=1,
            language='en',
            country='US'
        )
        self.db.session.add(website)
        self.db.session.commit()
        
        # Create article
        article = self.Articles(
            title='Test Article',
            summary='This is a test article',
            website_id=website.id,
            link='http://test.com/article',
            fetched_on=1
        )
        self.db.session.add(article)
        self.db.session.commit()
        
        retrieved_article = self.Articles.query.filter_by(title='Test Article').first()
        self.assertIsNotNone(retrieved_article)
        self.assertEqual(retrieved_article.summary, 'This is a test article')

    def test_interests_creation(self):
        """Test Interests model creation"""
        interest = self.Interests(interest='technology')
        self.db.session.add(interest)
        self.db.session.commit()
        
        retrieved_interest = self.Interests.query.filter_by(interest='technology').first()
        self.assertIsNotNone(retrieved_interest)
        self.assertEqual(retrieved_interest.interest, 'technology')

    def test_user_interest_creation(self):
        """Test User_interest model creation"""
        # Create dependencies
        user = self.User_mgmt(username='intuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        
        interest = self.Interests(interest='science')
        self.db.session.add(interest)
        self.db.session.commit()
        
        round_entry = self.Rounds(day=1, hour=1)
        self.db.session.add(round_entry)
        self.db.session.commit()
        
        # Create user interest
        user_interest = self.User_interest(
            user_id=user.id,
            interest_id=interest.iid,
            round_id=round_entry.id
        )
        self.db.session.add(user_interest)
        self.db.session.commit()
        
        retrieved = self.User_interest.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.interest_id, interest.iid)

    def test_voting_creation(self):
        """Test Voting model creation"""
        # Create user and post
        user = self.User_mgmt(username='voteuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        
        post = self.Post(tweet='Vote post', round=1, user_id=user.id)
        self.db.session.add(post)
        self.db.session.commit()
        
        # Create vote
        vote = self.Voting(
            user_id=user.id,
            preference='upvote',
            content_type='post',
            content_id=post.id,
            round=1
        )
        self.db.session.add(vote)
        self.db.session.commit()
        
        retrieved_vote = self.Voting.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(retrieved_vote)
        self.assertEqual(retrieved_vote.preference, 'upvote')

    def test_images_creation(self):
        """Test Images model creation"""
        image = self.Images(
            url='http://test.com/image.jpg',
            description='Test image'
        )
        self.db.session.add(image)
        self.db.session.commit()
        
        retrieved_image = self.Images.query.filter_by(url='http://test.com/image.jpg').first()
        self.assertIsNotNone(retrieved_image)
        self.assertEqual(retrieved_image.description, 'Test image')

    def test_post_sentiment_creation(self):
        """Test Post_Sentiment model creation"""
        # Create dependencies
        user = self.User_mgmt(username='sentuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        
        post = self.Post(tweet='Sentiment post', round=1, user_id=user.id)
        self.db.session.add(post)
        self.db.session.commit()
        
        round_entry = self.Rounds(day=1, hour=1)
        self.db.session.add(round_entry)
        self.db.session.commit()
        
        interest = self.Interests(interest='politics')
        self.db.session.add(interest)
        self.db.session.commit()
        
        # Create sentiment
        sentiment = self.Post_Sentiment(
            post_id=post.id,
            user_id=user.id,
            round=round_entry.id,
            topic_id=interest.iid,
            neg=0.1,
            neu=0.5,
            pos=0.4,
            compound=0.3
        )
        self.db.session.add(sentiment)
        self.db.session.commit()
        
        retrieved = self.Post_Sentiment.query.filter_by(post_id=post.id).first()
        self.assertIsNotNone(retrieved)
        self.assertAlmostEqual(retrieved.compound, 0.3)

    def test_post_toxicity_creation(self):
        """Test Post_Toxicity model creation"""
        # Create user and post
        user = self.User_mgmt(username='toxuser', password='pass', joined_on=1)
        self.db.session.add(user)
        self.db.session.commit()
        
        post = self.Post(tweet='Toxicity post', round=1, user_id=user.id)
        self.db.session.add(post)
        self.db.session.commit()
        
        # Create toxicity record
        toxicity = self.Post_Toxicity(
            post_id=post.id,
            toxicity=0.2,
            severe_toxicity=0.1,
            identity_attack=0.05,
            insult=0.1,
            profanity=0.05,
            threat=0.02
        )
        self.db.session.add(toxicity)
        self.db.session.commit()
        
        retrieved = self.Post_Toxicity.query.filter_by(post_id=post.id).first()
        self.assertIsNotNone(retrieved)
        self.assertAlmostEqual(retrieved.toxicity, 0.2)


if __name__ == '__main__':
    unittest.main()
