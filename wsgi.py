"""
WSGI entry point for YServer.

This module provides the WSGI application object for production deployment
with servers like Gunicorn.

Usage:
    gunicorn wsgi:app
    gunicorn -w 4 -b 0.0.0.0:5010 wsgi:app
    
    # With custom config file:
    YSERVER_CONFIG=/path/to/config.json gunicorn -c gunicorn_config.py wsgi:app
"""
import json
import os

from y_server import app

# Read configuration and set Flask app config values
# This ensures the same config values are set as in start_server()
config_file = os.environ.get('YSERVER_CONFIG', os.path.join('config_files', 'exp_config.json'))
if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Set Flask app config values from the experiment config
    app.config["perspective_api"] = config.get("perspective_api")
    app.config["sentiment_annotation"] = config.get("sentiment_annotation", False)
    app.config["emotion_annotation"] = config.get("emotion_annotation", False)

# The app object is automatically created when y_server is imported
# and can be used directly by WSGI servers like Gunicorn
if __name__ == "__main__":
    # This allows testing the WSGI module directly
    app.run()
