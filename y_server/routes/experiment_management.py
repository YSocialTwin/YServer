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
)


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
    db.session.commit()
    return {"status": 200}
