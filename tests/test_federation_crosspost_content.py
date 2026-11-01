"""P13: with crosspost.content including "news" the content of a post about an article carries the article link."""

import pytest

from tests.test_federation_bus import client  # noqa: F401  (fixture)
from y_server import app, db
from y_server.federation.adapter import YServerAdapter
from y_server.modals import Articles, Post

pytest.importorskip("ysocial_federation")


def _news_post(uid, text):
    art = Articles(title="t", summary="s", website_id=1, link="https://example.org/story", fetched_on=0)
    db.session.add(art)
    db.session.flush()
    post = Post(tweet=text, round=0, user_id=uid, news_id=str(art.id), comment_to=-1)
    plain = Post(tweet="no article", round=0, user_id=uid, comment_to=-1)
    db.session.add_all([post, plain])
    db.session.commit()
    return post, plain


def _content(content_policy):
    a = YServerAdapter("micro", 1, accounts={"g1": 1}, crosspost_content=content_policy)
    with app.app_context():
        news, plain = _news_post(1, "headline without url")
        return a._content(news), a._content(plain)


def test_the_link_travels_only_when_the_policy_asks_for_news(client):  # noqa: F811
    news, plain = _content(["news"])
    assert news["link"] == "https://example.org/story" and "link" not in plain


@pytest.mark.parametrize("policy", [None, ["all"], ["images"], ["own_posts"]])
def test_without_news_the_message_is_unchanged(client, policy):  # noqa: F811
    news, plain = _content(policy)
    assert "link" not in news and "link" not in plain


def test_an_invalid_policy_is_refused(client):  # noqa: F811
    with pytest.raises(ValueError):
        YServerAdapter("micro", 1, crosspost_content=["video"])
