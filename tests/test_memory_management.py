from __future__ import annotations

import json

import pytest

from y_server import app, db
from y_server.routes import memory_management
from y_server.modals import (
    Interests,
    MemoryCommunityDigest,
    MemoryInteractionEvent,
    MemoryItem,
    MemorySocialCard,
    MemoryThreadCard,
    User_mgmt,
)


@pytest.fixture()
def client():
    with app.app_context():
        db.create_all()
        MemoryInteractionEvent.query.delete()
        MemoryItem.query.delete()
        MemorySocialCard.query.delete()
        MemoryThreadCard.query.delete()
        MemoryCommunityDigest.query.delete()
        User_mgmt.query.filter(User_mgmt.email.in_(["a@example.test", "b@example.test"])).delete()
        db.session.commit()

        alice = User_mgmt(
            username="alice",
            email="a@example.test",
            password="x",
            joined_on=1,
        )
        bob = User_mgmt(
            username="bob",
            email="b@example.test",
            password="x",
            joined_on=1,
        )
        db.session.add(alice)
        db.session.add(bob)
        db.session.commit()

    with app.test_client() as test_client:
        yield test_client


def post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


class StubEmbeddingService:
    def __init__(self, model_name="stub-embed", vector=None):
        self.model_name = model_name
        self._vector = vector or [0.1, 0.2, 0.3]
        self.last_error = None

    @property
    def available(self):
        return True

    def embed_text(self, text):
        if not text:
            return None
        return list(self._vector)


@pytest.fixture(autouse=True)
def reset_memory_embedding():
    memory_management.configure_memory_embedding()
    yield
    memory_management.configure_memory_embedding()


def test_memory_event_creates_event_and_item(client):
    response = post_json(
        client,
        "/memory/event",
        {
            "run_id": "run-1",
            "round_id": 3,
            "actor_user_id": 1,
            "target_user_id": 2,
            "thread_root_id": 10,
            "target_post_id": 12,
            "event_type": "comment",
            "salient_claim": "I disagree with that take",
        },
    )
    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["status"] == 200

    with app.app_context():
        assert MemoryInteractionEvent.query.count() == 1
        assert MemoryItem.query.count() == 1
        item = MemoryItem.query.first()
        assert item.item_type == "event"
        assert item.other_user_id == 2
        assert item.embedding_status == "pending"


def test_memory_event_embeds_when_backend_configured(client, monkeypatch):
    monkeypatch.setattr(memory_management, "_MEMORY_EMBEDDING", StubEmbeddingService(model_name="stub-embed"))

    response = post_json(
        client,
        "/memory/event",
        {
            "run_id": "run-embed",
            "round_id": 2,
            "actor_user_id": 1,
            "event_type": "post",
            "salient_claim": "Configured embeddings should be stored",
        },
    )
    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["status"] == 200

    with app.app_context():
        item = (
            MemoryItem.query.filter_by(run_id="run-embed", agent_user_id=1)
            .order_by(MemoryItem.id.desc())
            .first()
        )
        assert item is not None
        assert item.embedding_status == "ready"
        assert item.embedding_model == "stub-embed"
        assert item.embedding_dim == 3


def test_configure_memory_embedding_requires_explicit_config():
    memory_management.configure_memory_embedding()
    assert memory_management._MEMORY_EMBEDDING is None

    memory_management.configure_memory_embedding(
        service="ollama",
        host="127.0.0.1:11434",
        model="embeddinggemma:latest",
    )
    configured = memory_management._MEMORY_EMBEDDING
    assert configured is not None
    assert configured.model_name == "embeddinggemma:latest"
    assert configured.ollama_host == "http://127.0.0.1:11434"


def test_memory_social_and_thread_upsert_and_context(client):
    post_json(
        client,
        "/memory/social/upsert",
        {
            "run_id": "run-2",
            "agent_user_id": 1,
            "other_user_id": 2,
            "affinity": 0.7,
            "trust": 0.6,
            "summary_text": "Mostly constructive exchanges with @bob",
            "event_count": 3,
        },
    )
    post_json(
        client,
        "/memory/thread/upsert",
        {
            "run_id": "run-2",
            "agent_user_id": 1,
            "thread_root_id": 50,
            "gist_text": "Conversation about electric cars",
            "my_role": "skeptic",
        },
    )
    post_json(
        client,
        "/memory/event",
        {
            "run_id": "run-2",
            "round_id": 4,
            "actor_user_id": 1,
            "target_user_id": 2,
            "thread_root_id": 50,
            "target_post_id": 51,
            "event_type": "comment",
            "salient_claim": "Battery swaps are underrated",
        },
    )

    response = post_json(
        client,
        "/memory/get_context",
        {
            "run_id": "run-2",
            "agent_user_id": 1,
            "other_user_id": 2,
            "thread_root_id": 50,
        },
    )
    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["social_card"]["affinity"] == 0.7
    assert payload["thread_card"]["my_role"] == "skeptic"
    assert payload["recent_pair_events"][0]["salient_claim"] == "Battery swaps are underrated"


def test_memory_search_lexical_fallback_returns_ranked_items(client):
    post_json(
        client,
        "/memory/item/upsert",
        {
            "run_id": "run-3",
            "agent_user_id": 1,
            "item_type": "summary",
            "text": "Alice argued that trains are better than cars for commuting",
            "other_user_id": 2,
            "round_id": 8,
            "importance": 0.8,
        },
    )
    post_json(
        client,
        "/memory/item/upsert",
        {
            "run_id": "run-3",
            "agent_user_id": 1,
            "item_type": "summary",
            "text": "Weekend baking ideas",
            "round_id": 8,
            "importance": 0.2,
        },
    )

    response = post_json(
        client,
        "/memory/search",
        {
            "run_id": "run-3",
            "agent_user_id": 1,
            "query_text": "cars commuting",
            "round_id": 8,
            "k": 2,
        },
    )
    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["status"] == 200
    assert payload["items"][0]["text"].startswith("Alice argued")
    assert payload["retrieval_meta"]["embedding_degraded"] in {True, False}
    assert payload["memory_brief"].startswith("[MEMORY SEARCH BRIEF]")


def test_memory_community_and_events_recent_and_reset(client):
    post_json(
        client,
        "/memory/community/update",
        {
            "run_id": "run-4",
            "round_id": 9,
            "digest_text": "The timeline is focused on mobility and city politics",
            "top_topics": ["transport", "elections"],
        },
    )
    post_json(
        client,
        "/memory/event",
        {
            "run_id": "run-4",
            "round_id": 9,
            "actor_user_id": 1,
            "event_type": "post",
            "salient_claim": "Cities should fund more buses",
        },
    )

    digest_response = post_json(client, "/memory/community/get", {"run_id": "run-4"})
    digest_payload = json.loads(digest_response.data)
    assert digest_response.status_code == 200
    assert digest_payload["digest_text"].startswith("The timeline")

    recent_response = post_json(client, "/memory/events_recent", {"run_id": "run-4", "limit": 10})
    recent_payload = json.loads(recent_response.data)
    assert recent_response.status_code == 200
    assert len(recent_payload["events"]) == 1

    reset_response = post_json(client, "/memory/reset", {"run_id": "run-4"})
    reset_payload = json.loads(reset_response.data)
    assert reset_response.status_code == 200
    assert reset_payload["status"] == 200

    with app.app_context():
        assert MemoryInteractionEvent.query.filter_by(run_id="run-4").count() == 0
        assert MemoryCommunityDigest.query.filter_by(run_id="run-4").count() == 0


def test_set_interests_is_idempotent(client):
    with app.app_context():
        Interests.query.filter(Interests.interest.in_(["transport", "economy"])).delete()
        db.session.commit()

    first = post_json(client, "/set_interests", ["transport", "economy"])
    second = post_json(client, "/set_interests", ["transport", "economy"])

    assert json.loads(first.data)["status"] == 200
    assert json.loads(second.data)["status"] == 200

    with app.app_context():
        interests = Interests.query.filter(Interests.interest.in_(["transport", "economy"])).all()
        assert len(interests) == 2
