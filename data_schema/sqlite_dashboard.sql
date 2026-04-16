CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE IF NOT EXISTS "hashtags"
(
    hashtag TEXT not null,
    id      integer
        constraint id
            primary key
);
CREATE TABLE IF NOT EXISTS "post_hashtags"
(
    post_id    integer
        constraint post
            references post,
    hashtag_id integer
        constraint hashtag
            references hashtags,
    id         integer not null
        constraint id
            primary key autoincrement
);
CREATE TABLE IF NOT EXISTS "mentions"
(
    id      integer
        constraint id
            primary key autoincrement,
    user_id INT
        constraint user_id
            references user_mgmt,
    post_id integer
        constraint post_id
            references post
, round integer, answered integer default 0);
CREATE TABLE IF NOT EXISTS "emotions"
(
    id      integer not null
        constraint id
            primary key autoincrement,
    emotion TEXT    not null
, icon TEXT);
CREATE TABLE post_emotions
(
    id         integer
        constraint id
            primary key,
    post_id    integer
        constraint post_id
            references post,
    emotion_id integer
        constraint emotion
            references emotions
);
CREATE TABLE IF NOT EXISTS "rounds"
(
    id   integer not null
        constraint id
            primary key autoincrement,
    day  integer,
    hour integer
);
CREATE TABLE IF NOT EXISTS "follow"
(
    user_id     integer not null
        constraint "from"
            references user_mgmt,
    follower_id integer not null
        constraint "to"
            references user_mgmt,
    id          integer not null
        constraint follow_pk
            primary key autoincrement,
    action      TEXT,
    round       integer
        constraint round
            references rounds
);
CREATE TABLE IF NOT EXISTS "reactions"
(
    id      integer
        constraint id
            primary key,
    post_id integer
        constraint post_id
            references post,
    user_id integer
        constraint user_id
            references user_mgmt,
    type    TEXT,
    round   integer
        constraint round
            references rounds
);
CREATE TABLE websites
(
    id           integer not null
        constraint id
            primary key autoincrement,
    name         TEXT,
    rss          TEXT,
    leaning      TEXT,
    category     TEXT,
    last_fetched integer
, country TEXT, language TEXT);
CREATE TABLE articles
(
    id         integer not null
        constraint id
            primary key autoincrement,
    title      TEXT    not null,
    summary    TEXT,
    website_id integer not null
        constraint website_id
            references websites,
    fetched_on integer not null
, link TEXT);
CREATE TABLE recommendations
(
    id       integer not null
        constraint id
            primary key autoincrement,
    user_id  integer not null
        constraint user_id
            references user_mgmt,
    post_ids TEXT,
    round    integer not null
        constraint round
            references rounds
);
CREATE TABLE voting
(
    vid          integer not null
        constraint voting_pk
            primary key autoincrement,
    round        integer,
    user_id      integer
        constraint user_id
            references user_mgmt,
    preference   TEXT,
    content_type text,
    content_id   integer
);
CREATE TABLE user_interest
(
    id          integer not null
        constraint id
            primary key autoincrement,
    user_id     integer
        constraint user_id
            references user_mgmt,
    interest_id integer
        constraint interest_id
            references interests,
    round_id    integer
        constraint round_id
            references rounds
);
CREATE TABLE IF NOT EXISTS "interests"
(
    iid      integer not null
        constraint iid
            primary key autoincrement,
    interest TEXT
);
CREATE TABLE post_topics
(
    id       integer not null
        constraint id
            primary key autoincrement,
    post_id  integer
        constraint post_id
            references post,
    topic_id integer
        constraint topic_id
            references interests (interest)
);
CREATE TABLE IF NOT EXISTS "user_mgmt"
(
    id              INTEGER           not null
        primary key,
    username        VARCHAR(15)       not null
        unique,
    email           VARCHAR(50)       not null
        unique,
    password        VARCHAR(80)       not null,
    user_type       TEXT,
    leaning         text,
    age             integer,
    oe              TEXT,
    co              TEXT,
    ex              TEXT,
    ag              TEXT,
    ne              TEXT,
    recsys_type     TEXT,
    language        TEXT,
    owner           TEXT,
    education_level TEXT,
    joined_on       integer,
    frecsys_type    TEXT,
    round_actions   integer default 3 not null,
    gender          TEXT,
    nationality     TEXT,
    toxicity        TEXT
, is_page integer default 0 not null, left_on integer, daily_activity_level integer default 1, profession TEXT, activity_profile TEXT);
CREATE TABLE images
(
    id          integer
        constraint id
            primary key autoincrement,
    url         TEXT,
    description TEXT,
    article_id  integer
        constraint article_id
            references articles
);
CREATE TABLE IF NOT EXISTS "post"
(
    id          INTEGER not null
        primary key,
    tweet       TEXT    not null,
    post_img    VARCHAR(20),
    user_id     INTEGER not null
        references user_mgmt,
    comment_to  integer default -1,
    thread_id   integer,
    round       integer
        constraint round
            references rounds,
    news_id     integer default -1
        constraint news_id
            references articles,
    shared_from integer default -1,
    image_id    integer
        constraint image_id
            references images
, reaction_count integer default 0);
CREATE TABLE IF NOT EXISTS "article_topics"
(
    id         integer not null
        constraint id
            primary key,
    article_id integer not null
        constraint article_id
            references articles,
    topic_id   INT
        constraint topic_id
            references interests,
    constraint article_topic
        unique (article_id, topic_id)
);
CREATE TABLE IF NOT EXISTS "post_sentiment"
(
    id               integer           not null
        constraint post_sentiment_pk
            primary key autoincrement,
    post_id          integer           not null
        constraint post_sentiment_post_id_fk
            references post,
    neg              REAL,
    pos              REAL,
    neu              REAL,
    compound         REAL,
    user_id          integer           not null
        constraint post_sentiment_user_mgmt_id_fk
            references user_mgmt,
    round            integer           not null
        constraint post_sentiment_rounds_id_fk
            references rounds,
    sentiment_parent TEXT,
    topic_id         integer           not null
        constraint post_sentiment_interests_iid_fk
            references interests,
    is_post          INTEGER default 0 not null,
    is_comment       integer default 0 not null,
    is_reaction      integer default 0 not null
);
CREATE TABLE post_toxicity
(
    id                integer        not null
        constraint post_toxicity_pk
            primary key autoincrement,
    post_id           integer        not null
        constraint post_toxicity_post_id_fk
            references post,
    toxicity          REAL default 0 not null,
    severe_toxicity   REAL default 0,
    identity_attack   REAL default 0,
    insult            REAL default 0,
    profanity         REAL default 0,
    threat            REAL default 0,
    sexually_explicit REAL default 0,
    flirtation        REAL default 0
);
