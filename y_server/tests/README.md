# YServer Test Suite

Comprehensive unittest suite for all modules in the y_server package.

## Overview

This test suite provides 67 comprehensive unit tests covering all major components of the YServer application:

- Database models
- Utility functions
- Content analysis
- API endpoints for user management, content management, interactions, and more

## Test Files

| Test File | Module Under Test | Tests | Description |
|-----------|------------------|-------|-------------|
| `test_modals.py` | `y_server/modals.py` | 13 | Tests for all database models (User_mgmt, Post, Reactions, etc.) |
| `test_utils.py` | `y_server/utils.py` | 6 | Tests for utility functions (follow relationships, content recommendations) |
| `test_textual_data.py` | `y_server/content_analysis/textual_data.py` | 7 | Tests for sentiment analysis and toxicity detection |
| `test_time_management.py` | `y_server/routes/time_management.py` | 5 | Tests for time/round management endpoints |
| `test_voting_management.py` | `y_server/routes/voting_management.py` | 4 | Tests for voting/preference casting |
| `test_interaction_management.py` | `y_server/routes/interaction_management.py` | 5 | Tests for follow/unfollow and suggestions |
| `test_user_managment.py` | `y_server/routes/user_managment.py` | 9 | Tests for user registration, retrieval, and updates |
| `test_experiment_management.py` | `y_server/routes/experiment_management.py` | 3 | Tests for experiment reset and database operations |
| `test_image_management.py` | `y_server/routes/image_management.py` | 4 | Tests for image commenting endpoints |
| `test_news_management.py` | `y_server/routes/news_management.py` | 3 | Tests for news article commenting |
| `test_content_management.py` | `y_server/routes/content_management.py` | 8 | Tests for posting, reading, searching, and reacting |

## Running Tests

### Run all tests:
```bash
python -m unittest discover -s y_server/tests -p "test_*.py" -v
```

### Run a specific test file:
```bash
python -m unittest y_server.tests.test_modals -v
```

### Run a specific test case:
```bash
python -m unittest y_server.tests.test_modals.TestModals.test_user_mgmt_creation -v
```

## Test Features

- **Isolation**: Each test uses an in-memory SQLite database for complete isolation
- **Mocking**: External dependencies (sentiment analysis, toxicity detection) are properly mocked
- **Coverage**: Tests cover both positive and negative cases
- **Clean Setup/Teardown**: Proper cleanup ensures no test pollution
- **Self-Contained**: Each test file can be run independently

## Test Results

All 67 tests pass successfully:
```
Ran 67 tests in 0.842s
OK
```

## Dependencies

The test suite requires the following packages (listed in `requirements_server.txt`):
- Flask
- Flask-SQLAlchemy
- nltk (for sentiment analysis)
- unittest (built-in Python module)

## Notes

- Tests use Flask's test client for endpoint testing
- Database models are tested with real SQLAlchemy operations
- Sentiment analysis uses NLTK's VADER lexicon (downloaded automatically)
- Perspective API toxicity detection is mocked to avoid external API calls during testing
