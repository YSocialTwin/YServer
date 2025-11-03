"""
WSGI entry point for YServer.

This module provides the WSGI application object for production deployment
with servers like Gunicorn.

Usage:
    # Default config (config_files/exp_config.json):
    gunicorn wsgi:app
    
    # With custom config file via environment variable:
    YSERVER_CONFIG=/path/to/config.json gunicorn wsgi:app
    
Note for running multiple instances:
    Each Gunicorn process should be started in a separate subprocess with its own
    YSERVER_CONFIG environment variable. Since each process has its own Python
    interpreter and imports, they won't interfere with each other.
    
    Example:
        env1 = os.environ.copy()
        env1['YSERVER_CONFIG'] = '/path/to/config1.json'
        proc1 = subprocess.Popen(['gunicorn', 'wsgi:app', '-b', '127.0.0.1:5010'], env=env1)
        
        env2 = os.environ.copy()
        env2['YSERVER_CONFIG'] = '/path/to/config2.json'
        proc2 = subprocess.Popen(['gunicorn', 'wsgi:app', '-b', '127.0.0.1:5020'], env=env2)
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
