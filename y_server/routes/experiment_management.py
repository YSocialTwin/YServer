"""
Experiment management routes.

This module provides REST API endpoints for managing experiments including
database switching, server shutdown, and experiment reset operations.
Includes logging configuration for experiment tracking.
"""

from flask import request
import json
from y_server import app, db
from y_server.modals import (
    User_mgmt,
    Post,
    Reactions,
    Follow,
    Hashtags,
    Post_hashtags,
    Mentions,
    Post_emotions,
    Rounds,
    Recommendations,
    Websites,
    Articles,
    Voting,
    Interests,
    Post_topics,
    User_interest,
    Images,
    Article_topics,
)
import logging, os
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create handler
logHandler = logging.StreamHandler()

# Define JSON log format
formatter = jsonlogger.JsonFormatter(
    fmt='%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d',
    datefmt='%Y-%m-%dT%H:%M:%S'
)

logHandler.setFormatter(formatter)


def rebind_db(new_uri):
    """
    Rebind the database connection to a new URI.
    
    Properly disposes of the existing database connection and creates a new
    engine with the specified URI.
    
    Args:
        new_uri (str): The new database URI to connect to.
    """
    from sqlalchemy import create_engine
    from flask import current_app

    engine = create_engine(new_uri, connect_args={"check_same_thread": False})

    with current_app.app_context():
        db.session.remove()
        db.engine.dispose()  # ✅ safe now
        db.session.configure(bind=engine)


@app.route("/change_db", methods=["POST"])
def change_db():
    """
    Switch the active database connection to a different database.
    
    Supports both PostgreSQL and SQLite databases. Configures logging
    to write to an experiment-specific log file.
    
    Expects JSON data with:
        - path (str): Database path or URI
        
    Returns:
        dict: JSON response with status code 200 on success.
    """
    # get the data from the request
    data = json.loads(request.get_data())

    # select the database type
    uri = data["path"]

    if "postgresql" in uri:
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
        db_path = "experiments" +os.sep + data['path'].split("/")[-1].replace("experiments_", "") #.split("y_web")[1].split("experiments_")[1]
        rebind_db(uri)
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:////{data['path']}"
        # Manually add check_same_thread=False
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False}
        }
        # Set up logging
        db_path = data['path'].split("y_web")[1].split("database_server.db")[0]

    log_dir = f"y_web{os.sep}{db_path}"
    log_path = os.path.join(log_dir, "_server.log")
    logHandler = logging.FileHandler(log_path)
    logger.addHandler(logHandler)
    db.init_app(app)
    return {"status": 200}


@app.route("/shutdown", methods=["POST"])
def shutdown_server():
    """
    Gracefully shutdown the Flask server.
    
    Triggers the Werkzeug server shutdown mechanism.
    
    Raises:
        RuntimeError: If not running with the Werkzeug Server.
        
    Returns:
        None
    """
    shutdown = request.environ.get("werkzeug.server.shutdown")
    if shutdown is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    shutdown()


@app.route("/reset", methods=["POST"])
def reset_experiment():
    """
    Reset the experiment by deleting all data from the database.
    
    Removes all records from all tables including users, posts, reactions,
    follows, hashtags, mentions, rounds, recommendations, websites, articles,
    interests, voting, images, and their associated junction tables.
    
    Returns:
        dict: JSON response with status code 200 on success.
    """
    db.session.query(User_mgmt).delete()
    db.session.query(Post).delete()
    db.session.query(Reactions).delete()
    db.session.query(Follow).delete()
    db.session.query(Hashtags).delete()
    db.session.query(Post_hashtags).delete()
    db.session.query(Post_emotions).delete()
    db.session.query(Mentions).delete()
    db.session.query(Rounds).delete()
    db.session.query(Recommendations).delete()
    db.session.query(Websites).delete()
    db.session.query(Articles).delete()
    db.session.query(Interests).delete()
    db.session.query(User_interest).delete()
    db.session.query(Voting).delete()
    db.session.query(Post_topics).delete()
    db.session.query(Images).delete()
    db.session.query(Article_topics).delete()
    db.session.commit()
    return {"status": 200}
