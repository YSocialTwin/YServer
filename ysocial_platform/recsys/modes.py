"""The content recommender systems a person can pick on this platform: names, aliases and explanations.

``normalize`` turns what the interface or the database stores into a canonical mode name, ``is_supported`` says
whether the platform implements it and ``describe`` returns the plain-language explanation shown to participants.
"""

from y_web.sdk import N_

try:  # PLATFORM_API 1.4; with an older core the fixed-order recommenders are simply not offered
    from y_web.sdk.fixed_recsys import canonical as _fixed_canonical
    from y_web.sdk.fixed_recsys import is_fixed_mode
except ImportError:  # pragma: no cover - exercised by tests through a reload

    def is_fixed_mode(mode):
        return False

    def _fixed_canonical(mode):
        return mode

SUPPORTED_CONTENT_RECSYS_MODES = frozenset(
    {
        "Random",
        "ReverseChrono",
        "ReverseChronoPopularity",
        "ReverseChronoFollowers",
        "ReverseChronoFollowersPopularity",
        "ReverseChronoComments",
        "CommonInterests",
        "CommonUserInterests",
        "SimilarUsersReactions",
        "SimilarUsersPosts",
        "CollaborativeUserUser",
        "CollaborativeItemItem",
        "ContentBasedFeatures",
        "ContentBasedVector",
        "HybridLinearRanker",
        "FilterBubble",
    }
)


def _normalize_content_recsys_mode(mode):
    """Normalize UI/backend content-rec sys aliases to canonical mode names."""
    raw = str(mode or "").strip()
    if not raw:
        return "Random"
    if is_fixed_mode(raw):
        return _fixed_canonical(raw)

    compact = raw.replace("_", "").replace("-", "").replace(" ", "").strip().lower()
    mode_aliases = {
        # ── existing ──────────────────────────────────────────────────────
        "reversechrono": "ReverseChrono",
        "rc": "ReverseChrono",
        "reversechronopopularity": "ReverseChronoPopularity",
        "rcp": "ReverseChronoPopularity",
        "reversechronofollowers": "ReverseChronoFollowers",
        "rcf": "ReverseChronoFollowers",
        "reversechronofollowerspopularity": "ReverseChronoFollowersPopularity",
        "fp": "ReverseChronoFollowersPopularity",
        "contentrecsys": "Random",
        "default": "Random",
        "random": "Random",
        # ── Standard (HPC,Standard) ───────────────────────────────────────
        "reversechronocomments": "ReverseChronoComments",
        "rcc": "ReverseChronoComments",
        "commoninterests": "CommonInterests",
        "ci": "CommonInterests",
        "commonuserinterests": "CommonUserInterests",
        "cui": "CommonUserInterests",
        "similarusersreactions": "SimilarUsersReactions",
        "sir": "SimilarUsersReactions",
        "similarusersposts": "SimilarUsersPosts",
        "sip": "SimilarUsersPosts",
        # ── HPC-only ──────────────────────────────────────────────────────
        "collaborativeuseruser": "CollaborativeUserUser",
        "cuu": "CollaborativeUserUser",
        "collaborativeitemitem": "CollaborativeItemItem",
        "cii": "CollaborativeItemItem",
        "contentbasedfeatures": "ContentBasedFeatures",
        "cbf": "ContentBasedFeatures",
        "contentbasedvector": "ContentBasedVector",
        "cbv": "ContentBasedVector",
        "hybridlinearranker": "HybridLinearRanker",
        "hlr": "HybridLinearRanker",
        # ── Human-only ───────────────────────────────────────────────────────
        "filterbubble": "FilterBubble",
        "fb": "FilterBubble",
        "personalizedfeed": "FilterBubble",
        "pf": "FilterBubble",
        # db row stored as filter_bubble_v1 → compact = filterbubblev1
        "filterbubblev1": "FilterBubble",
    }
    return mode_aliases.get(compact, raw)


def is_supported_content_recsys_mode(mode):
    """Return whether a stored/UI value resolves to executable code."""
    canonical = _normalize_content_recsys_mode(mode)
    return canonical in SUPPORTED_CONTENT_RECSYS_MODES or is_fixed_mode(canonical)


# Plain-language explanations of the content recommender systems, keyed by canonical mode name.
_RECSYS_DESCRIPTIONS = {
    "Random": N_(
        "Posts from other users in random order, regardless of you or the posts."
    ),
    "ReverseChrono": N_(
        "All posts from other users, newest first. No personalisation."
    ),
    "ReverseChronoPopularity": N_("Posts from other users, the most reacted first."),
    "ReverseChronoFollowers": N_(
        "Mostly posts from the people you follow, newest first, completed with the newest posts from everybody."
    ),
    "ReverseChronoFollowersPopularity": N_(
        "Mostly posts from the people you follow, the most reacted first, completed with the newest posts from everybody."
    ),
    "ReverseChronoComments": N_(
        "Newest posts first; within the same hour, the most commented come first."
    ),
    "CommonInterests": N_(
        "Posts about the topics you are interested in, newest first."
    ),
    "CommonUserInterests": N_(
        "Posts from users who share your interests, newest first, completed with the newest posts from everybody."
    ),
    "SimilarUsersReactions": N_(
        "Posts reacted to by users with your same political leaning, completed with the newest posts from everybody."
    ),
    "SimilarUsersPosts": N_(
        "Posts written by users with your same political leaning, completed with the newest posts from everybody."
    ),
    "CollaborativeUserUser": N_(
        "Posts liked by users who reacted to the same posts as you, newest first."
    ),
    "CollaborativeItemItem": N_(
        "Posts reacted to by the people who reacted to the same posts as you, newest first."
    ),
    "ContentBasedFeatures": N_(
        "Posts about your topics of interest, newest first, then the most reacted."
    ),
    "ContentBasedVector": N_(
        "Posts ranked by how many of your topics of interest they cover."
    ),
    "HybridLinearRanker": N_(
        "Posts ranked by how well they match your topics of interest, with a bonus for popular ones."
    ),
    "FilterBubble": N_(
        "Posts are scored by your topics of interest and by how close the author's opinion is to yours. "
        "Your interests adapt to what you like, share and comment, so over time the feed can narrow to like-minded content."
    ),
}


_FIXED_DESCRIPTION = N_(
    "Only the posts chosen by the experiment authors, in the order they defined."
)


def describe(mode):
    """Explanation (a translatable message id) of a canonical mode, or ``None`` when it has none."""
    if is_fixed_mode(mode):
        return _FIXED_DESCRIPTION
    return _RECSYS_DESCRIPTIONS.get(mode)
