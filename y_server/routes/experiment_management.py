import json
import logging
import os

from flask import request
from pythonjsonlogger import jsonlogger
from y_server import app, db
from y_server.modals import (
    Article_topics,
    Articles,
    Follow,
    Hashtags,
    Images,
    Interests,
    Mentions,
    Post,
    Post_emotions,
    Post_hashtags,
    Post_topics,
    Reactions,
    Recommendations,
    Rounds,
    User_interest,
    User_mgmt,
    Voting,
    Websites,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Define JSON log format
# Include custom fields from the request logger (remote_addr, method, path, etc.)
formatter = jsonlogger.JsonFormatter(
    fmt='%(remote_addr)s %(method)s %(path)s %(status_code)s %(duration)s %(time)s %(tid)s %(day)s %(hour)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)


def rebind_db(new_uri):
    from flask import current_app
    from sqlalchemy import create_engine

    engine = create_engine(new_uri, connect_args={"check_same_thread": False})

    with current_app.app_context():
        db.session.remove()
        db.engine.dispose()  # ✅ safe now
        db.session.configure(bind=engine)


@app.route("/change_db", methods=["POST"])
def change_db():
    """
    Change the database to the given name.

    :param db_name: the name of the database
    :return: the status of the change
    """
    import sys
    
    # get the data from the request
    data = json.loads(request.get_data())

    # select the database type
    uri = data["path"]

    try:
        if "postgresql" in uri:
            app.config["SQLALCHEMY_DATABASE_URI"] = uri
            db_path = "experiments" +os.sep + data['path'].split("/")[-1].replace("experiments_", "")
            rebind_db(uri)
        else:
            app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:////{data['path']}"
            # Manually add check_same_thread=False
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "connect_args": {"check_same_thread": False}
            }

        # Set up file logging
        log_dir = uri.split("database_server.db")[0]
        log_path = os.path.join(f"{os.sep}{log_dir}", "_server.log")
        
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Remove all existing handlers to avoid duplicate logging
        logger.handlers.clear()
        
        # Create file handler with JSON formatter
        # Only log messages that are already JSON formatted (from the request logger)
        fileHandler = logging.FileHandler(log_path, mode='a')
        fileHandler.setFormatter(formatter)
        fileHandler.setLevel(logging.INFO)
        logger.addHandler(fileHandler)
        
        # Disable propagation to prevent logging to parent handlers
        logger.propagate = False
        
        # Ensure the log is flushed to disk
        fileHandler.flush()
        
        print(f"Logging successfully configured. File: {log_path}", file=sys.stderr)
        
    except Exception as e:
        # If logging setup fails, log the error to stderr but don't fail the request
        import traceback
        print(f"ERROR in change_db logging setup: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    
    db.init_app(app)
    return {"status": 200}


@app.route("/shutdown", methods=["POST"])
def shutdown_server():
    """
    Shutdown the server
    """
    shutdown = request.environ.get("werkzeug.server.shutdown")
    if shutdown is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    shutdown()


@app.route("/reset", methods=["POST"])
def reset_experiment():
    """
    Reset the experiment.
    Delete all the data from the database.

    :return: the status of the reset
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
