"""
Voting management routes.

This module provides REST API endpoints for managing user voting and preferences
on content within the YSocial platform.
"""

import json
from flask import request
from y_server import app, db
from y_server.modals import (
    Voting,
)


@app.route("/cast_preference", methods=["POST"])
def cast_preference():
    """
    Record a user's voting preference for content.
    
    Expects JSON data with:
        - tid (int): Round/time identifier
        - user_id (int): ID of the user casting the vote
        - vote (str): The preference/vote value
        - content_type (str): Type of content being voted on
        - content_id (int): ID of the content being voted on
    
    Returns:
        str: JSON response with status code.
    """
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
