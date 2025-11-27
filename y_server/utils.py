from sqlalchemy import case, desc, func
from y_server.modals import (
    Follow,
    Post,
    Post_topics,
    Reactions,
    User_interest,
    User_mgmt,
    db,
)

# Re-export log_error for backward compatibility
from y_server.error_logging import log_error


def get_follows(uid):
    """
    Get the followers of a user.

    :param uid: the user id
    :return: a list of followers
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
    Fetch posts based on common interests with followers and others.

    :param uid: the user id
    :param visibility: the visibility threshold
    :param articles: whether to include articles
    :param follower_posts_limit: the number of posts from followers
    :param additional_posts_limit: the number of additional posts
    :return: the posts query result
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
    Fetch posts reacted by users with common interests.

    :param uid: the user id
    :param visibility: the visibility threshold
    :param articles: whether to include articles
    :return: the posts query result
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
    Fetch post related to similar agents to the target user based on specified features.

    :param uid: Target user ID
    :param visibility: Visibility threshold for posts
    :param articles: Whether to include articles
    :param limit: Number of posts to fetch
    :return: Query result with posts by similar users
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
    Fetch users similar to the given user ID based on specified features.

    :param uid: Target user ID
    :param limit: Number of similar users to fetch
    :return: Query result with similar users
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
    Fetch posts made by specified users.

    :param visibility: the visibility threshold
    :param articles: whether to include articles
    :param limit: the number of posts to fetch
    :param user_ids: the user ids
    :return: the posts query result
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
    Fetch posts reacted by specified users.

    :param visibility: the visibility threshold
    :param articles: whether to include articles
    :param limit: the number of posts to fetch
    :param user_ids: the user ids
    :param reactions_type: the type of reactions
    :return: the posts query result
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
    Fetch posts most commented by specified users.

    :param visibility: the visibility threshold
    :param articles: whether to include articles
    :param limit: the number of posts to fetch
    :param user_ids: the user ids
    :return: the posts query result
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
