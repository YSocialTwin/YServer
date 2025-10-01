"""
Utility functions for content recommendation and user similarity analysis.

This module provides helper functions for fetching and filtering posts based on various
criteria including user interests, follower relationships, user similarity, and content
reactions. These utilities support the recommendation system and content discovery features
of the YSocial platform.

Functions:
    get_follows: Get the followers of a user
    fetch_common_interest_posts: Fetch posts based on common interests
    fetch_common_user_interest_posts: Fetch posts reacted by users with common interests
    fetch_similar_users_posts: Fetch posts from similar users
    get_posts_by_author: Fetch posts by specified authors
    get_posts_by_reactions: Fetch posts with reactions from specified users
"""

from sqlalchemy import func, desc, case
from y_server.modals import (
    db,
    Post,
    Post_topics,
    User_interest,
    Follow,
    Reactions,
    User_mgmt,
)


def get_follows(uid):
    """
    Get the followers of a user based on follow relationships.
    
    Retrieves users who are currently following the specified user by analyzing
    follow/unfollow actions (counting modulo 2 to determine current state).
    
    Args:
        uid (int): The user ID whose followers to retrieve.
        
    Returns:
        list[int]: List of user IDs who are currently following the specified user.
    """
    # Get the latest round for each follower-user relationship
    # res = Follow_status.query.filter_by(user_id=uid).all()

    # get the followers of the user with the given uid
    res = (
        Follow.query.filter(Follow.user_id == uid, Follow.follower_id != uid)
        .group_by(Follow.follower_id)
        .having(func.count().op("%")(2) == 1)
        .all()
    )

    res = [x.follower_id for x in res]

    return res


def fetch_common_interest_posts(
    uid, visibility, articles, follower_posts_limit, additional_posts_limit
):
    """
    Fetch posts based on common topic interests with the user.
    
    Retrieves posts that match the user's interests, prioritizing posts from followers
    and then from other users. Posts are ranked by the number of matching topics.
    
    Args:
        uid (int): The user ID for whom to fetch posts.
        visibility (int): Minimum round number for post visibility (filters old posts).
        articles (bool): Whether to include article-based posts.
        follower_posts_limit (int): Maximum number of posts from followers to return.
        additional_posts_limit (int): Maximum number of posts from non-followers to return.
        
    Returns:
        list: List of query results containing posts sorted by topic match count.
              Returns two groups: [follower_posts, additional_posts]
    """
    user_interests = (
        db.session.query(User_interest.interest_id).filter_by(user_id=uid).distinct()
    )
    follower_ids = get_follows(uid)

    # fetch posts by followers with common interests
    base_query = (
        db.session.query(Post, func.count(Post_topics.topic_id).label("match_count"))
        .join(Post_topics, Post.id == Post_topics.post_id)
        .filter(
            Post.round >= visibility,
            Post.user_id != uid,
            Post.news_id != -1 if articles else True,
        )
        .group_by(Post.id)
        .order_by(desc("match_count"))
    )

    # Helper to create queries
    def create_query(user_filter, topic_filter, lit):
        res = base_query.filter(user_filter, topic_filter).limit(lit).all()
        return res

    posts = []

    # Posts by followers with common interests
    posts.append(
        create_query(
            Post.user_id.in_(follower_ids),
            Post_topics.topic_id.in_(user_interests),
            follower_posts_limit,
        )
    )

    # Additional posts with common interests
    if additional_posts_limit > 0:
        posts.append(
            create_query(
                Post.user_id.notin_(follower_ids),
                Post_topics.topic_id.in_(user_interests),
                additional_posts_limit,
            )
        )

    return posts


def fetch_common_user_interest_posts(
    uid,
    visibility,
    articles,
    follower_posts_limit,
    additional_posts_limit,
    reactions_type,
):
    """
    Fetch posts reacted to by users who share common interests with the target user.
    
    Identifies users with overlapping interests and retrieves posts they have reacted to,
    prioritizing posts from followers over others.
    
    Args:
        uid (int): The user ID for whom to fetch posts.
        visibility (int): Minimum round number for post visibility.
        articles (bool): Whether to include article-based posts.
        follower_posts_limit (int): Maximum posts from followers with common interests.
        additional_posts_limit (int): Maximum posts from other users with common interests.
        reactions_type (str or list): Type(s) of reactions to consider (e.g., 'like').
        
    Returns:
        list: List containing [posts_from_followers, posts_from_others]
    """

    # get users with common topic interests
    user_interests = db.session.query(User_interest.interest_id).filter_by(user_id=uid)
    common_users = (
        db.session.query(
            User_mgmt.id.label("user_id"),
            func.count(User_interest.interest_id).label("match_count"),
        )
        .join(User_interest, User_mgmt.id == User_interest.user_id)
        .filter(User_mgmt.id != uid, User_interest.interest_id.in_(user_interests))
        .group_by(User_mgmt.id)
        .order_by(desc("match_count"))
        .subquery()
    )

    # Separate common followers and other users

    follower_ids = get_follows(uid)

    common_follower_ids = [
        row.user_id
        for row in db.session.query(common_users.c.user_id)
        .filter(common_users.c.user_id.in_(follower_ids))
        .all()
    ]
    other_user_ids = [
        row.user_id
        for row in db.session.query(common_users.c.user_id)
        .filter(~common_users.c.user_id.in_(common_follower_ids))
        .all()
    ]
    # Fetch posts for each group
    posts_followers = get_posts_by_reactions(
        visibility, articles, follower_posts_limit, common_follower_ids, reactions_type
    )

    posts_additional = get_posts_by_reactions(
        visibility, articles, additional_posts_limit, other_user_ids, reactions_type
    )

    return [posts_followers, posts_additional]


def fetch_similar_users_posts(
    uid,
    visibility,
    articles,
    limit,
    filter_function,
    reactions_type,
):
    """
    Fetch posts related to users similar to the target user.
    
    Identifies users similar to the target user based on demographic and personality
    features, then fetches posts using the provided filter function.
    
    Args:
        uid (int): Target user ID for finding similar users.
        visibility (int): Minimum round number for post visibility.
        articles (bool): Whether to include article-based posts.
        limit (int): Maximum number of posts to fetch.
        filter_function (callable): Function to apply for filtering posts
                                   (e.g., get_posts_by_author, get_posts_by_reactions).
        reactions_type (str or list): Type(s) of reactions to consider.
        
    Returns:
        list: List containing query results with posts by similar users.
    """
    # Fetch similar users
    similar_users = __get_similar_users(uid, limit)

    # fetch posts based on the filter function
    posts = filter_function(
        visibility=visibility,
        articles=articles,
        limit=limit,
        user_ids=similar_users,
        reactions_type=reactions_type,
    )

    return [posts]


def __get_similar_users(uid, limit=10):
    """
    Identify users similar to the target user based on multiple features.
    
    Calculates similarity scores based on categorical matches (political leaning,
    language, education, gender, toxicity, Big Five personality traits) and
    numeric similarity (age). Returns users ordered by similarity score.
    
    Args:
        uid (int): Target user ID to find similar users for.
        limit (int, optional): Maximum number of similar users to return. Defaults to 10.
        
    Returns:
        list[int]: List of user IDs most similar to the target user.
        
    Raises:
        ValueError: If the target user does not exist in the database.
    """
    # Fetch target user's features
    target_user = db.session.query(User_mgmt).filter_by(id=uid).first()
    if not target_user:
        raise ValueError(f"User with id {uid} does not exist.")

    # Build the similarity query
    target = target_user
    user = User_mgmt  # Alias for better readability
    age_weight = 1 / 100

    similarity_query = (
        db.session.query(
            user.id,
            (
                # Categorical exact matches
                func.sum(
                    case([(user.leaning == target.leaning, 1)], else_=0)
                    + case([(user.language == target.language, 1)], else_=0)
                    + case(
                        [(user.education_level == target.education_level, 1)], else_=0
                    )
                    + case([(user.gender == target.gender, 1)], else_=0)
                    + case([(user.toxicity == target.toxicity, 1)], else_=0)
                    + case([(user.oe == target.oe, 1)], else_=0)
                    + case([(user.co == target.co, 1)], else_=0)
                    + case([(user.ex == target.ex, 1)], else_=0)
                    + case([(user.ag == target.ag, 1)], else_=0)
                    + case([(user.ne == target.ne, 1)], else_=0)
                )
                # Numeric partial match (age)
                + (1 - func.abs(user.age - target.age) * age_weight)
            ).label("similarity_score"),
        )
        .filter(user.id != uid)
        .order_by(desc("similarity_score"))
        .limit(limit)
    )

    res = similarity_query.all()
    res = [x[0] for x in res]

    return res


def get_posts_by_author(
    visibility,
    articles,
    limit,
    user_ids,
    reactions_type,
):
    """
    Fetch posts authored by specified users.
    
    Args:
        visibility (int): Minimum round number for post visibility.
        articles (bool): Whether to include article-based posts.
        limit (int): Maximum number of posts to return.
        user_ids (list[int]): List of user IDs whose posts to retrieve.
        reactions_type (str or list): Unused parameter (kept for API compatibility).
        
    Returns:
        Query: SQLAlchemy query result containing matching posts.
    """
    posts = Post.query.filter(
        Post.user_id.in_(user_ids),
        Post.round >= visibility,
        Post.news_id != -1 if articles else True,
    ).limit(limit)

    return posts


def get_posts_by_reactions(
    visibility,
    articles,
    limit,
    user_ids,
    reactions_type,
):
    """
    Fetch posts that have been reacted to by specified users.
    
    Retrieves posts based on user reactions, sorted by reaction count and post ID.
    Falls back to general post visibility if no reacted posts are found.
    
    Args:
        visibility (int): Minimum round number for post visibility.
        articles (bool): Whether to include article-based posts.
        limit (int): Maximum number of posts to return.
        user_ids (list[int]): List of user IDs whose reactions to consider.
        reactions_type (str or list[str]): Type(s) of reactions to filter by (e.g., 'like').
        
    Returns:
        list: List of Post objects or (Post, count) tuples sorted by reaction count.
    """
    if isinstance(reactions_type, str):
        reactions_type = [reactions_type]

    posts = (
        db.session.query(Post, func.count(Reactions.user_id).label("total"))
        .join(Reactions, Post.id == Reactions.post_id)
        .filter(
            Reactions.user_id.in_(user_ids),
            Reactions.type.in_(reactions_type),
            Post.round >= visibility,
            Post.news_id != -1 if articles else True,
        )
        .group_by(Post.id)
        .order_by(desc("total"), desc(Post.id))
        .limit(limit)
    ).all()

    # If no posts found, fetch posts based on visibility and articles
    if len(posts) == 0:
        posts = (
            db.session.query(Post)
            .filter(
                Post.round >= visibility,
                Post.news_id != -1 if articles else True,
            )
            .group_by(Post.id)
            .limit(limit)
        ).all()

    return posts


def __get_posts_by_comments(visibility, articles, limit, user_ids):
    """
    Fetch posts with the most comments, optionally filtered by user IDs.
    
    Args:
        visibility (int): Minimum round number for post visibility.
        articles (bool): Whether to include article-based posts.
        limit (int): Maximum number of posts to return.
        user_ids (list[int] or None): Optional list of user IDs to filter by.
        
    Returns:
        Query: SQLAlchemy query result containing posts sorted by comment count.
    """
    # get posts with the most comments
    posts = (
        db.session.query(Post, func.count(Post.thread_id).label("comment_count"))
        .filter(
            Post.round >= visibility,
            Post.comment_to != -1,
            Post.news_id != -1 if articles else True,
        )
        .group_by(Post.thread_id)
        .order_by(desc("comment_count"), desc(Post.id))
        .limit(limit)
        .all()
    )

    if user_ids:
        # filter posts by specified users
        posts = posts.filter(Post.user_id.in_(user_ids))

    return posts
