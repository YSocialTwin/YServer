import json

from flask import request
from sqlalchemy import desc
from y_server import app, db
from y_server.modals import (
    Rounds,
)


@app.route("/current_time", methods=["GET"])
def current_time():
    """
    Get the current time of the simulation.

    :return: a json object with the current time
    """
    try:
        cround = Rounds.query.order_by(desc(Rounds.id)).first()
        if cround is None:
            cround = Rounds(day=0, hour=0)
            db.session.add(cround)
            db.session.commit()
            cround = Rounds.query.order_by(desc(Rounds.id)).first()

        return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})
    except Exception as e:
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        return json.dumps({"error": str(e), "status": 500}), 500


@app.route("/update_time", methods=["POST"])
def update_time():
    """
    Update the time of the simulation.

    :return: a json object with the updated time
    """
    try:
        data = json.loads(request.get_data())
        day = int(data["day"])
        hour = int(data["round"])

        cround = Rounds.query.filter_by(day=day, hour=hour).first()
        if cround is None:
            cround = Rounds(day=day, hour=hour)
            db.session.add(cround)
            db.session.commit()
            cround = Rounds.query.filter_by(day=day, hour=hour).first()

        return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})
    except Exception as e:
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        return json.dumps({"error": str(e), "status": 500}), 500
