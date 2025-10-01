"""
Unit tests for y_server/content_analysis/textual_data.py

Tests sentiment analysis and toxicity detection functions.
"""
import unittest
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestTextualData(unittest.TestCase):
    """Test cases for textual data analysis functions"""

    def setUp(self):
        """Set up before each test"""
        from y_server.content_analysis import textual_data
        self.textual_data = textual_data

    def test_vader_sentiment_positive(self):
        """Test vader_sentiment with positive text"""
        text = "This is a wonderful and amazing day!"
        result = self.textual_data.vader_sentiment(text)
        
        # Check that result contains expected keys
        self.assertIn('neg', result)
        self.assertIn('neu', result)
        self.assertIn('pos', result)
        self.assertIn('compound', result)
        
        # Positive text should have high positive score
        self.assertGreater(result['pos'], 0)
        self.assertGreater(result['compound'], 0)

    def test_vader_sentiment_negative(self):
        """Test vader_sentiment with negative text"""
        text = "This is terrible and awful!"
        result = self.textual_data.vader_sentiment(text)
        
        # Check that result contains expected keys
        self.assertIn('neg', result)
        self.assertIn('neu', result)
        self.assertIn('pos', result)
        self.assertIn('compound', result)
        
        # Negative text should have high negative score
        self.assertGreater(result['neg'], 0)
        self.assertLess(result['compound'], 0)

    def test_vader_sentiment_neutral(self):
        """Test vader_sentiment with neutral text"""
        text = "The cat is on the mat."
        result = self.textual_data.vader_sentiment(text)
        
        # Check that result contains expected keys
        self.assertIn('neg', result)
        self.assertIn('neu', result)
        self.assertIn('pos', result)
        self.assertIn('compound', result)
        
        # Neutral text should have high neutral score
        self.assertGreater(result['neu'], 0)

    def test_vader_sentiment_empty_string(self):
        """Test vader_sentiment with empty string"""
        text = ""
        result = self.textual_data.vader_sentiment(text)
        
        # Should still return valid structure
        self.assertIn('neg', result)
        self.assertIn('neu', result)
        self.assertIn('pos', result)
        self.assertIn('compound', result)

    @patch('y_server.content_analysis.textual_data.PerspectiveAPI')
    def test_toxicity_with_api_key(self, mock_perspective):
        """Test toxicity function with API key"""
        # Mock the PerspectiveAPI
        mock_api = Mock()
        mock_api.score.return_value = {
            'TOXICITY': 0.5,
            'SEVERE_TOXICITY': 0.1,
            'IDENTITY_ATTACK': 0.05,
            'INSULT': 0.2,
            'PROFANITY': 0.1,
            'THREAT': 0.05,
            'SEXUALLY_EXPLICIT': 0.01,
            'FLIRTATION': 0.02
        }
        mock_perspective.return_value = mock_api
        
        # Create mock database and session
        mock_db = Mock()
        mock_session = Mock()
        mock_db.session = mock_session
        
        # Test the function
        self.textual_data.toxicity(
            text="Test text",
            api_key="test_key",
            post_id=1,
            db=mock_db
        )
        
        # Verify PerspectiveAPI was called
        mock_perspective.assert_called_once_with("test_key")
        mock_api.score.assert_called_once()

    def test_toxicity_without_api_key(self):
        """Test toxicity function without API key"""
        # Create mock database
        mock_db = Mock()
        
        # Test the function with None API key
        result = self.textual_data.toxicity(
            text="Test text",
            api_key=None,
            post_id=1,
            db=mock_db
        )
        
        # Should return without doing anything
        self.assertIsNone(result)

    @patch('y_server.content_analysis.textual_data.PerspectiveAPI')
    def test_toxicity_with_exception(self, mock_perspective):
        """Test toxicity function when API raises exception"""
        # Mock the PerspectiveAPI to raise exception
        mock_api = Mock()
        mock_api.score.side_effect = Exception("API Error")
        mock_perspective.return_value = mock_api
        
        # Create mock database
        mock_db = Mock()
        
        # Test the function - should handle exception gracefully
        result = self.textual_data.toxicity(
            text="Test text",
            api_key="test_key",
            post_id=1,
            db=mock_db
        )
        
        # Should return None when exception occurs
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
