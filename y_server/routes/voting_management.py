import json

from flask import request
from y_server import app, db
from y_server.modals import (
    Voting,
)


@app.route("/cast_preference", methods=["POST"])
def cast_preference():
    data = json.loads(request.get_data())

    # add data to Vote table
    vote = Voting(
        round=int(data["tid"]),
        user_id=int(data["user_id"]),
        preference=data["vote"],
        content_type=data["content_type"],
        content_id=int(data["content_id"]),
    )
    db.session.add(vote)
    db.session.commit()

    res = {"status": 200}
    return json.dumps(res)
