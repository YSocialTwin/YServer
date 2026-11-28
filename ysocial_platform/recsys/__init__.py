"""The recommender systems of the people who use this platform's frontend.

``content_recsys`` ranks the feed, ``follow_recsys`` proposes people and pages to follow, ``modes`` names the modes
and explains them. ``RECSYS`` is what the platform hands to YSocial (``provider.human_recsys``).
"""

from y_web.sdk import HumanRecsysTraits
from y_web.sdk.models import db
from y_web.sdk.web import load_ui_settings

from .content_recsys import (  # noqa: F401
    PersonalizedFeedRankingError,
    _update_filter_bubble_interests,
    get_suggested_posts,
)
from .follow_recsys import get_suggested_users  # noqa: F401
from .modes import (  # noqa: F401
    _normalize_content_recsys_mode,
    describe,
    is_supported_content_recsys_mode,
)


def _learn_from_interaction(exp_id, exp_user, post_id, interaction_type):
    """The FilterBubble mode adapts the person's interests to what they like, share and comment.

    Silently does nothing when it does not apply (another mode, no experiment database): the interaction itself is
    never blocked.
    """
    try:
        if (
            _normalize_content_recsys_mode(getattr(exp_user, "recsys_type", ""))
            != "FilterBubble"
        ):
            return
        from flask import current_app

        exp_engine = db.engines.get("db_exp")
        if exp_engine is None:
            exp_engine = db.get_engine(current_app, bind="db_exp")
        settings = load_ui_settings(exp_id)
        try:
            learning_rate = float(settings.get("filter_bubble_lr", 0.05))
        except (TypeError, ValueError):
            learning_rate = 0.05
        learning_rate = max(0.0, min(1.0, learning_rate))
        _update_filter_bubble_interests(
            user_id=exp_user.id,
            post_id=post_id,
            interaction_type=interaction_type,
            exp_engine=exp_engine,
            lr=learning_rate,
        )
    except Exception:
        pass


RECSYS = HumanRecsysTraits(
    normalize=_normalize_content_recsys_mode,
    is_supported=is_supported_content_recsys_mode,
    describe=describe,
    suggested_posts=get_suggested_posts,
    suggested_users=get_suggested_users,
    on_interaction=_learn_from_interaction,
)
