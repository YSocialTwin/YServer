import json
import logging
import os

from sqlalchemy.pool import NullPool

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
# The JsonFormatter will include any fields that are present in the LogRecord
# Request logs pass custom fields via 'extra' parameter which will be included automatically
formatter = jsonlogger.JsonFormatter()


def rebind_db(new_uri):
    from flask import current_app
    from sqlalchemy import create_engine

    # Only pass check_same_thread for SQLite
    if new_uri.startswith("sqlite"):
        engine = create_engine(new_uri, 
                             poolclass=NullPool,
                             connect_args={"check_same_thread": False, "timeout": 30})
    else:
        # PostgreSQL and other databases use default connection pooling
        engine = create_engine(new_uri)

    with current_app.app_context():
        db.session.remove()
        db.engine.dispose()
        db.session.configure(bind=engine)


@app.route("/change_db", methods=["POST"])
def change_db():
    """
    Change the database to the given name.

    :param db_name: the name of the database
    :return: the status of the change
    """
    import sys
    import traceback
    
    try:
        # get the data from the request
        data = json.loads(request.get_data())

        # select the database type
        uri = data["path"]

        if "postgresql" in uri:
            app.config["SQLALCHEMY_DATABASE_URI"] = uri
            app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
            # PostgreSQL uses default connection pooling (don't use NullPool)
            # Remove any SQLite-specific engine options
            if "SQLALCHEMY_ENGINE_OPTIONS" in app.config:
                del app.config["SQLALCHEMY_ENGINE_OPTIONS"]
            db_path = "experiments" + os.sep + data['path'].split("/")[-1].replace("experiments_", "")
            rebind_db(uri)
            log_dir = db_path
            cwd = os.path.abspath(os.getcwd()).split("external")[0]
            cwd = os.path.join(cwd, "y_web")
            log_dir = os.path.join(cwd, log_dir)
            rebind_db(uri)
        else:
            app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:////{data['path']}"
            app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
            # SQLite-specific: use NullPool and check_same_thread=False
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "poolclass": NullPool,
                "connect_args": {
                    "check_same_thread": False,
                    "timeout": 30
                }
            }

            log_dir = uri.split("database_server.db")[0]


        # Set up file logging
        log_path = os.path.join(f"{os.sep}{log_dir}", "_server.log")
        
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Remove all existing handlers to avoid duplicate logging
        logger.handlers.clear()
        
        # Create file handler with JSON formatter
        fileHandler = logging.FileHandler(log_path, mode='a')
        fileHandler.setFormatter(formatter)
        fileHandler.setLevel(logging.INFO)
        logger.addHandler(fileHandler)
        
        # Disable propagation to prevent logging to parent handlers
        logger.propagate = False
        
        # Ensure the log is flushed to disk
        fileHandler.flush()
        
        # Log success to application logger (will appear in Gunicorn error log)
        app.logger.info(f"Database configuration successful. URI: {uri}, Log: {log_path}")
        
        db.init_app(app)
        return {"status": 200}
        
    except Exception as e:
        # Log the full error with traceback to application logger (visible in Gunicorn logs)
        error_msg = f"ERROR in change_db: {str(e)}\n{traceback.format_exc()}"
        app.logger.error(error_msg)
        
        # Also print to stderr as fallback
        print(error_msg, file=sys.stderr)
        
        # Return error response with details
        return {"status": 500, "error": str(e), "traceback": traceback.format_exc()}, 500


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
