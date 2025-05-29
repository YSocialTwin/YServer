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


@app.route("/change_db", methods=["POST"])
def change_db():
    """
    Change the database to the given name.

    :param db_name: the name of the database
    :return: the status of the change
    """
    # get the data from the request
    data = json.loads(request.get_data())
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:////{data['path']}"

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
