import json
import math
import re

from flask import request
from sqlalchemy import desc, inspect, text

from y_server import app, db
from y_server.memory_embedding import MemoryEmbeddingService, cosine_similarity, lexical_relevance
from y_server.modals import (
    MemoryCommunityDigest,
    MemoryInteractionEvent,
    MemoryItem,
    MemorySocialCard,
    MemoryThreadCard,
    User_mgmt,
)


_MEMORY_SCHEMA_READY = False
_MEMORY_EMBEDDING = None
_PROMPT_SCAFFOLD_PATTERNS = [
    re.compile(r"\bmemory context\b", re.IGNORECASE),
    re.compile(r"\bmemory search brief\b", re.IGNORECASE),
    re.compile(r"\bmemory pack\b", re.IGNORECASE),
]


def _normalize_embedding_host(value):
    host = str(value or "").strip()
    if not host:
        return ""
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    host = host.rstrip("/")
    if host.endswith("/v1"):
        host = host[:-3].rstrip("/")
    return host


def configure_memory_embedding(service=None, host=None, model=None):
    global _MEMORY_EMBEDDING

    normalized_service = str(service or "").strip().lower()
    normalized_host = _normalize_embedding_host(host)
    normalized_model = str(model or "").strip()

    if normalized_service == "ollama" and normalized_host and normalized_model:
        _MEMORY_EMBEDDING = MemoryEmbeddingService(
            model_name=normalized_model,
            ollama_host=normalized_host,
        )
    else:
        _MEMORY_EMBEDDING = None

    try:
        app.logger.info(
            "memory_embedding_configured",
            extra={
                "service": normalized_service or "disabled",
                "host": normalized_host,
                "model": normalized_model,
                "available": bool(_MEMORY_EMBEDDING and _MEMORY_EMBEDDING.available),
                "error": None if _MEMORY_EMBEDDING is None else _MEMORY_EMBEDDING.last_error,
            },
        )
    except Exception:
        pass


def configure_memory_embedding_from_config(config_data):
    settings = {}
    if isinstance(config_data, dict):
        settings = config_data.get("memory_embeddings") or {}
    if not isinstance(settings, dict):
        settings = {}
    configure_memory_embedding(
        service=settings.get("service"),
        host=settings.get("host"),
        model=settings.get("model"),
    )


def _ensure_index(table_name, index_name, columns):
    cols = ", ".join(columns)
    with db.engine.begin() as conn:
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({cols})"))


def _ensure_memory_schema():
    global _MEMORY_SCHEMA_READY
    if _MEMORY_SCHEMA_READY:
        return
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if "memory_items" in tables:
            _ensure_index("memory_items", "idx_memory_items_run_agent_type", ["run_id", "agent_user_id", "item_type"])
            _ensure_index("memory_items", "idx_memory_items_run_agent_round", ["run_id", "agent_user_id", "round_id"])
        if "memory_interaction_events" in tables:
            _ensure_index("memory_interaction_events", "idx_memory_events_run_actor", ["run_id", "actor_user_id"])
        _MEMORY_SCHEMA_READY = True


def _looks_like_prompt_scaffold(text_value):
    text = str(text_value or "").strip()
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return any(pattern.search(normalized) for pattern in _PROMPT_SCAFFOLD_PATTERNS)


def _sanitize_generated_text(text_value, *, max_len=None):
    text = str(text_value or "")
    if not text.strip():
        return ""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _looks_like_prompt_scaffold(line):
            continue
        lines.append(raw_line)
    cleaned = "\n".join(lines).strip()
    if max_len is not None and len(cleaned) > int(max_len):
        cleaned = cleaned[: int(max_len)]
    return cleaned


def _payload_has_prompt_scaffold(value):
    if isinstance(value, str):
        return _looks_like_prompt_scaffold(value)
    if isinstance(value, (list, dict)):
        try:
            return _looks_like_prompt_scaffold(json.dumps(value))
        except Exception:
            return False
    return False


def _json_loads_maybe(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def _normalize_username(value):
    if value is None:
        return None
    text = str(value).strip().lstrip("@")
    return text or None


def _normalize_memory_query_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_memory_query_variants(query_text):
    base = str(query_text or "").strip()
    normalized = _normalize_memory_query_text(base)
    out = []
    for candidate in [base, normalized]:
        if candidate and candidate.lower() not in {x.lower() for x in out}:
            out.append(candidate)
    return out[:8]


def _lexical_match_details(query_text, memory_text):
    q_tokens = set(re.findall(r"[a-z0-9]+", str(query_text or "").lower()))
    m_tokens = set(re.findall(r"[a-z0-9]+", str(memory_text or "").lower()))
    if not q_tokens or not m_tokens:
        return {"score": 0.0, "matched_terms": []}
    inter = sorted(q_tokens & m_tokens)
    if not inter:
        return {"score": 0.0, "matched_terms": []}
    return {"score": float(len(inter) / math.sqrt(len(q_tokens) * len(m_tokens))), "matched_terms": inter[:10]}


def _build_user_map(user_ids):
    ids = []
    for raw in user_ids:
        try:
            uid = int(raw)
        except Exception:
            continue
        if uid > 0:
            ids.append(uid)
    if not ids:
        return {}
    rows = User_mgmt.query.filter(User_mgmt.id.in_(sorted(set(ids)))).all()
    return {int(row.id): _normalize_username(row.username) for row in rows if _normalize_username(row.username)}


def _humanize_memory_text(text_value, user_map):
    return str(text_value or "").strip()


def _estimate_importance(event_type="", relation_label=None, tone_label=None, salient_claim=None, **kwargs):
    score = 0.25
    if event_type in {"comment", "post"}:
        score += 0.15
    if relation_label in {"friend", "ally", "conflict", "argument"}:
        score += 0.20
    if tone_label in {"heated", "supportive", "hostile"}:
        score += 0.15
    if salient_claim:
        score += 0.15
    return max(0.0, min(1.0, score))


def _normalize_event_text(
    *,
    event_type,
    target_user_id=None,
    relation_label=None,
    tone_label=None,
    salient_claim=None,
    **kwargs,
):
    bits = [str(event_type or "event")]
    if target_user_id is not None:
        bits.append(f"with user {int(target_user_id)}")
    if relation_label:
        bits.append(f"relation={relation_label}")
    if tone_label:
        bits.append(f"tone={tone_label}")
    if salient_claim:
        bits.append(str(salient_claim))
    return " | ".join(bits)


def _to_int_or_none(value):
    try:
        return int(value)
    except Exception:
        return None


@app.route("/memory/reset", methods=["POST"])
def memory_reset():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        return json.dumps({"status": 400, "error": "run_id required"}), 400
    MemoryInteractionEvent.query.filter_by(run_id=run_id).delete()
    MemoryItem.query.filter_by(run_id=run_id).delete()
    MemorySocialCard.query.filter_by(run_id=run_id).delete()
    MemoryThreadCard.query.filter_by(run_id=run_id).delete()
    MemoryCommunityDigest.query.filter_by(run_id=run_id).delete()
    db.session.commit()
    return json.dumps({"status": 200})


@app.route("/memory/event", methods=["POST"])
def memory_event():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        return json.dumps({"status": 400, "error": "run_id required"}), 400
    try:
        round_id = int(data.get("round_id"))
        actor_user_id = int(data.get("actor_user_id"))
    except Exception:
        return json.dumps({"status": 400, "error": "round_id and actor_user_id required"}), 400
    event_type = str(data.get("event_type") or "").strip().lower()
    if event_type not in {"comment", "post", "upvote", "downvote"}:
        return json.dumps({"status": 400, "error": "invalid event_type"}), 400

    target_user_id = _to_int_or_none(data.get("target_user_id"))
    thread_root_id = _to_int_or_none(data.get("thread_root_id"))
    target_post_id = _to_int_or_none(data.get("target_post_id"))
    actor_post_id = _to_int_or_none(data.get("actor_post_id"))
    relation_label = str(data.get("relation_label") or "").strip().lower()[:16] or None
    tone_label = str(data.get("tone_label") or "").strip().lower()[:16] or None
    topics = data.get("topics")
    topics_json = json.dumps(topics) if isinstance(topics, (dict, list)) else (topics if isinstance(topics, str) else None)
    salient_claim = _sanitize_generated_text(data.get("salient_claim"), max_len=200) or None
    event_text = _sanitize_generated_text(data.get("event_text"), max_len=4000)
    if not event_text:
        event_text = _normalize_event_text(
            event_type=event_type,
            target_user_id=target_user_id,
            relation_label=relation_label,
            tone_label=tone_label,
            salient_claim=salient_claim,
        )
    importance = data.get("importance")
    try:
        importance = float(importance)
    except Exception:
        importance = _estimate_importance(
            event_type=event_type,
            relation_label=relation_label,
            tone_label=tone_label,
            salient_claim=salient_claim,
        )
    importance = max(0.0, min(1.0, float(importance)))

    ev = MemoryInteractionEvent(
        run_id=run_id,
        round_id=round_id,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        thread_root_id=thread_root_id,
        target_post_id=target_post_id,
        actor_post_id=actor_post_id,
        event_type=event_type,
        relation_label=relation_label,
        tone_label=tone_label,
        topics_json=topics_json,
        salient_claim=salient_claim,
        weight=float(data.get("weight") or 1.0),
        event_text=event_text,
        importance=importance,
        last_accessed_round=round_id,
        access_count=0,
    )
    db.session.add(ev)
    db.session.flush()

    item = MemoryItem(
        run_id=run_id,
        agent_user_id=actor_user_id,
        item_type="event",
        text=event_text,
        metadata_json=json.dumps(
            {
                "event_type": event_type,
                "target_user_id": target_user_id,
                "thread_root_id": thread_root_id,
                "target_post_id": target_post_id,
                "actor_post_id": actor_post_id,
                "salient_claim": salient_claim,
            }
        ),
        source_event_id=ev.id,
        thread_root_id=thread_root_id,
        other_user_id=target_user_id,
        topic_tags_json=topics_json,
        round_id=round_id,
        importance=importance,
        recency_anchor_round=round_id,
        last_accessed_round=round_id,
        access_count=0,
        embedding_status="pending",
    )
    if _MEMORY_EMBEDDING and _MEMORY_EMBEDDING.available:
        vec = _MEMORY_EMBEDDING.embed_text(item.text)
        if vec:
            item.embedding_json = json.dumps(vec)
            item.embedding_dim = len(vec)
            item.embedding_model = _MEMORY_EMBEDDING.model_name
            item.embedding_status = "ready"
    db.session.add(item)
    db.session.commit()
    return json.dumps({"status": 200, "event_id": ev.id, "memory_item_id": item.id})


@app.route("/memory/social/upsert", methods=["POST"])
def memory_social_upsert():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    agent_user_id = _to_int_or_none(data.get("agent_user_id"))
    other_user_id = _to_int_or_none(data.get("other_user_id"))
    if not run_id or agent_user_id is None or other_user_id is None:
        return json.dumps({"status": 400, "error": "run_id, agent_user_id and other_user_id required"}), 400
    card = MemorySocialCard.query.filter_by(run_id=run_id, agent_user_id=agent_user_id, other_user_id=other_user_id).first()
    if card is None:
        card = MemorySocialCard(run_id=run_id, agent_user_id=agent_user_id, other_user_id=other_user_id)
        db.session.add(card)
    for key in ["affinity", "conflict", "humor", "trust"]:
        if key in data:
            try:
                setattr(card, key, float(data.get(key)))
            except Exception:
                pass
    for key in ["last_round_id", "last_thread_root_id", "last_updated_round", "event_count"]:
        if key in data:
            setattr(card, key, _to_int_or_none(data.get(key)))
    card.last_relation_label = str(data.get("last_relation_label") or "").strip().lower()[:16] or None
    if "summary_text" in data:
        card.summary_text = _sanitize_generated_text(data.get("summary_text"), max_len=4000) or None
    if "evidence_tail" in data and not _payload_has_prompt_scaffold(data.get("evidence_tail")):
        value = data.get("evidence_tail")
        card.evidence_tail_json = json.dumps(value) if isinstance(value, (list, dict)) else (_sanitize_generated_text(value, max_len=4000) or None)
    db.session.commit()
    return json.dumps({"status": 200})


@app.route("/memory/thread/upsert", methods=["POST"])
def memory_thread_upsert():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    agent_user_id = _to_int_or_none(data.get("agent_user_id"))
    thread_root_id = _to_int_or_none(data.get("thread_root_id"))
    if not run_id or agent_user_id is None or thread_root_id is None:
        return json.dumps({"status": 400, "error": "run_id, agent_user_id and thread_root_id required"}), 400
    card = MemoryThreadCard.query.filter_by(run_id=run_id, agent_user_id=agent_user_id, thread_root_id=thread_root_id).first()
    if card is None:
        card = MemoryThreadCard(run_id=run_id, agent_user_id=agent_user_id, thread_root_id=thread_root_id)
        db.session.add(card)
    if "gist_text" in data:
        card.gist_text = _sanitize_generated_text(data.get("gist_text"), max_len=4000) or None
    card.my_role = str(data.get("my_role") or "").strip().lower()[:16] or None
    for key, col in [("participants_top", "participants_top_json"), ("entry_points", "entry_points_json")]:
        if key in data and not _payload_has_prompt_scaffold(data.get(key)):
            value = data.get(key)
            setattr(card, col, json.dumps(value) if isinstance(value, (list, dict)) else (_sanitize_generated_text(value, max_len=4000) or None))
    if "last_seen_round_id" in data:
        card.last_seen_round_id = _to_int_or_none(data.get("last_seen_round_id"))
    db.session.commit()
    return json.dumps({"status": 200})


@app.route("/memory/community/get", methods=["POST"])
def memory_community_get():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        return json.dumps({"status": 400, "error": "run_id required"}), 400
    digest = MemoryCommunityDigest.query.filter_by(run_id=run_id).order_by(desc(MemoryCommunityDigest.id)).first()
    if digest is None:
        return json.dumps({"status": 404}), 404
    return json.dumps({
        "status": 200,
        "run_id": run_id,
        "round_id": digest.round_id,
        "digest_text": digest.digest_text,
        "top_topics": digest.top_topics_json,
        "norms": digest.norms_json,
        "memes": digest.memes_json,
        "polarizing_issues": digest.polarizing_issues_json,
    })


@app.route("/memory/community/update", methods=["POST"])
def memory_community_update():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        return json.dumps({"status": 400, "error": "run_id required"}), 400
    digest = MemoryCommunityDigest.query.filter_by(run_id=run_id).order_by(desc(MemoryCommunityDigest.id)).first()
    if digest is None:
        digest = MemoryCommunityDigest(run_id=run_id)
        db.session.add(digest)
    digest.round_id = _to_int_or_none(data.get("round_id"))
    for field, col in [
        ("digest_text", "digest_text"),
        ("top_topics", "top_topics_json"),
        ("norms", "norms_json"),
        ("memes", "memes_json"),
        ("polarizing_issues", "polarizing_issues_json"),
    ]:
        if field not in data:
            continue
        value = data.get(field)
        if _payload_has_prompt_scaffold(value):
            setattr(digest, col, None)
        elif isinstance(value, (list, dict)):
            setattr(digest, col, json.dumps(value))
        else:
            setattr(digest, col, _sanitize_generated_text(value, max_len=4000) or None)
    db.session.commit()
    return json.dumps({"status": 200})


@app.route("/memory/item/upsert", methods=["POST"])
def memory_item_upsert():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    agent_user_id = _to_int_or_none(data.get("agent_user_id"))
    item_type = str(data.get("item_type") or "").strip().lower()
    text_value = _sanitize_generated_text(data.get("text"), max_len=4000)
    if not run_id or agent_user_id is None:
        return json.dumps({"status": 400, "error": "run_id and agent_user_id required"}), 400
    if item_type not in {"event", "reflection", "summary"}:
        return json.dumps({"status": 400, "error": "invalid item_type"}), 400
    if not text_value:
        return json.dumps({"status": 400, "error": "text required"}), 400
    item_id = _to_int_or_none(data.get("id"))
    item = MemoryItem.query.filter_by(id=item_id, run_id=run_id, agent_user_id=agent_user_id).first() if item_id else None
    if item is None:
        item = MemoryItem(run_id=run_id, agent_user_id=agent_user_id, item_type=item_type, text=text_value)
        db.session.add(item)
    else:
        item.item_type = item_type
        item.text = text_value
    item.metadata_json = json.dumps(data.get("metadata")) if isinstance(data.get("metadata"), (list, dict)) else (_sanitize_generated_text(data.get("metadata"), max_len=4000) or None)
    item.source_event_id = _to_int_or_none(data.get("source_event_id"))
    item.thread_root_id = _to_int_or_none(data.get("thread_root_id"))
    item.other_user_id = _to_int_or_none(data.get("other_user_id"))
    item.topic_tags_json = json.dumps(data.get("topic_tags")) if isinstance(data.get("topic_tags"), (list, dict)) else (_sanitize_generated_text(data.get("topic_tags"), max_len=4000) or None)
    item.round_id = _to_int_or_none(data.get("round_id"))
    item.importance = max(0.0, min(1.0, float(data.get("importance", 0.5 if item_type == "reflection" else 0.35))))
    item.recency_anchor_round = _to_int_or_none(data.get("recency_anchor_round")) or item.round_id
    item.last_accessed_round = _to_int_or_none(data.get("last_accessed_round")) or item.round_id
    item.access_count = _to_int_or_none(data.get("access_count")) or 0
    if bool(data.get("force_sync_embedding")) and _MEMORY_EMBEDDING and _MEMORY_EMBEDDING.available:
        vec = _MEMORY_EMBEDDING.embed_text(item.text)
        if vec:
            item.embedding_json = json.dumps(vec)
            item.embedding_dim = len(vec)
            item.embedding_model = _MEMORY_EMBEDDING.model_name
            item.embedding_status = "ready"
    elif not item.embedding_status:
        item.embedding_status = "pending"
    db.session.commit()
    return json.dumps({"status": 200, "id": item.id, "embedding_status": item.embedding_status})


@app.route("/memory/search", methods=["POST"])
def memory_search():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    agent_user_id = _to_int_or_none(data.get("agent_user_id"))
    query_text = str(data.get("query_text") or "").strip()
    if not run_id or agent_user_id is None or not query_text:
        return json.dumps({"status": 400, "error": "run_id, agent_user_id and query_text required"}), 400

    other_user_id = _to_int_or_none(data.get("other_user_id"))
    thread_root_id = _to_int_or_none(data.get("thread_root_id"))
    current_round = _to_int_or_none(data.get("round_id"))
    time_window_rounds = _to_int_or_none(data.get("time_window_rounds"))
    k = max(1, min(_to_int_or_none(data.get("k")) or 8, 40))
    max_chars = max(50, min(_to_int_or_none(data.get("max_chars")) or 1200, 6000))
    types = data.get("types")
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list) or not types:
        types = ["event", "reflection", "summary"]
    types = [str(value).strip().lower() for value in types if str(value).strip()]

    query = MemoryItem.query.filter(
        MemoryItem.run_id == run_id,
        MemoryItem.agent_user_id == agent_user_id,
        MemoryItem.item_type.in_(types),
    )
    if other_user_id is not None:
        query = query.filter(MemoryItem.other_user_id == other_user_id)
    if thread_root_id is not None:
        query = query.filter(MemoryItem.thread_root_id == thread_root_id)
    if current_round is not None and time_window_rounds is not None and time_window_rounds > 0:
        query = query.filter((MemoryItem.round_id == None) | (MemoryItem.round_id >= (current_round - time_window_rounds)))  # noqa: E711
    candidates = query.order_by(desc(MemoryItem.round_id), desc(MemoryItem.id)).limit(300).all()

    query_variants = _build_memory_query_variants(query_text)
    query_embedding = _MEMORY_EMBEDDING.embed_text(query_text) if _MEMORY_EMBEDDING and _MEMORY_EMBEDDING.available else None
    query_has_embedding = isinstance(query_embedding, list) and bool(query_embedding)
    results = []
    ready_count = 0
    pending_count = 0
    failed_count = 0

    for item in candidates:
        if item.embedding_status == "ready":
            ready_count += 1
        elif item.embedding_status == "pending":
            pending_count += 1
        elif item.embedding_status == "failed":
            failed_count += 1
        item_text = str(item.text or "")
        item_embedding = _json_loads_maybe(item.embedding_json)
        if query_has_embedding and isinstance(item_embedding, list):
            relevance = cosine_similarity(query_embedding, item_embedding)
        else:
            best = 0.0
            for variant in query_variants:
                details = _lexical_match_details(variant, item_text)
                best = max(best, float(details.get("score") or 0.0))
            relevance = max(best, lexical_relevance(query_text, item_text))
        if current_round is not None and item.round_id is not None:
            delta = max(0, current_round - int(item.round_id))
            recency = math.exp(-(math.log(2.0) / 96.0) * float(delta))
        else:
            recency = 1.0
        importance = max(0.0, min(1.0, float(item.importance or 0.0)))
        score = (0.55 * relevance) + (0.25 * recency) + (0.20 * importance)
        results.append((score, relevance, recency, importance, item))

    results.sort(key=lambda row: (row[0], row[3], row[4].id), reverse=True)
    top = results[:k]
    user_ids = {agent_user_id}
    for _, _, _, _, item in top:
        if item.other_user_id is not None:
            user_ids.add(int(item.other_user_id))
    user_map = _build_user_map(user_ids)
    items_payload = []
    brief_lines = ["[MEMORY SEARCH BRIEF]"]
    for score, relevance, recency, importance, item in top:
        text_humanized = _humanize_memory_text(item.text, user_map)
        items_payload.append(
            {
                "item_id": item.id,
                "item_type": item.item_type,
                "text": item.text,
                "text_humanized": text_humanized,
                "score": score,
                "relevance": relevance,
                "recency": recency,
                "importance": importance,
                "round_id": item.round_id,
                "thread_root_id": item.thread_root_id,
                "other_user_id": item.other_user_id,
                "other_username": _normalize_username(user_map.get(item.other_user_id)),
                "metadata": _json_loads_maybe(item.metadata_json) or {},
            }
        )
        brief_text = text_humanized[:280] + ("..." if len(text_humanized) > 280 else "")
        brief_lines.append(f"- ({item.item_type}, r{item.round_id if item.round_id is not None else '?'}, s={score:.2f}): {brief_text}")
        try:
            item.access_count = int(item.access_count or 0) + 1
        except Exception:
            item.access_count = 1
        if current_round is not None:
            item.last_accessed_round = current_round
    if top:
        db.session.commit()
    memory_brief = "\n".join(brief_lines)
    if len(memory_brief) > max_chars:
        memory_brief = memory_brief[: max_chars - 3].rstrip() + "..."
    return json.dumps(
        {
            "status": 200,
            "run_id": run_id,
            "items": items_payload,
            "memory_brief": memory_brief,
            "retrieval_meta": {
                "candidate_count": len(candidates),
                "returned_k": len(top),
                "degraded_mode": not query_has_embedding,
                "embedding_degraded": not query_has_embedding,
                "no_ready_candidates": ready_count <= 0,
                "query_variants": query_variants,
                "embedding_status_summary": {
                    "ready": ready_count,
                    "pending": pending_count,
                    "failed": failed_count,
                    "query_embedding_available": bool(query_has_embedding),
                },
            },
            "user_map": {str(k): v for k, v in user_map.items() if v},
        }
    )


@app.route("/memory/get_context", methods=["POST"])
def memory_get_context():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    agent_user_id = _to_int_or_none(data.get("agent_user_id"))
    if not run_id or agent_user_id is None:
        return json.dumps({"status": 400, "error": "run_id and agent_user_id required"}), 400
    other_user_id = _to_int_or_none(data.get("other_user_id"))
    thread_root_id = _to_int_or_none(data.get("thread_root_id"))
    pair_limit = max(1, min(_to_int_or_none(data.get("pair_limit")) or 5, 20))

    pair_rows = []
    if other_user_id is not None:
        pair_rows = (
            MemoryInteractionEvent.query.filter(MemoryInteractionEvent.run_id == run_id)
            .filter(
                (
                    (MemoryInteractionEvent.actor_user_id == agent_user_id)
                    & (MemoryInteractionEvent.target_user_id == other_user_id)
                )
                | (
                    (MemoryInteractionEvent.actor_user_id == other_user_id)
                    & (MemoryInteractionEvent.target_user_id == agent_user_id)
                )
            )
            .order_by(desc(MemoryInteractionEvent.id))
            .limit(pair_limit)
            .all()[::-1]
        )

    username_ids = {agent_user_id}
    if other_user_id is not None:
        username_ids.add(other_user_id)
    for ev in pair_rows:
        if ev.actor_user_id is not None:
            username_ids.add(int(ev.actor_user_id))
        if ev.target_user_id is not None:
            username_ids.add(int(ev.target_user_id))
    user_map = _build_user_map(username_ids)

    social_card = None
    if other_user_id is not None:
        sc = MemorySocialCard.query.filter_by(run_id=run_id, agent_user_id=agent_user_id, other_user_id=other_user_id).first()
        if sc is not None:
            social_card = {
                "affinity": sc.affinity,
                "conflict": sc.conflict,
                "humor": sc.humor,
                "trust": sc.trust,
                "last_relation_label": sc.last_relation_label,
                "last_round_id": sc.last_round_id,
                "last_thread_root_id": sc.last_thread_root_id,
                "last_updated_round": sc.last_updated_round,
                "event_count": sc.event_count,
                "summary_text": sc.summary_text,
                "evidence_tail": sc.evidence_tail_json,
                "other_username": _normalize_username(user_map.get(other_user_id)),
            }

    thread_card = None
    if thread_root_id is not None:
        tc = MemoryThreadCard.query.filter_by(run_id=run_id, agent_user_id=agent_user_id, thread_root_id=thread_root_id).first()
        if tc is not None:
            thread_card = {
                "gist_text": tc.gist_text,
                "my_role": tc.my_role,
                "participants_top": tc.participants_top_json,
                "entry_points": tc.entry_points_json,
                "last_seen_round_id": tc.last_seen_round_id,
            }

    community_digest = None
    dg = MemoryCommunityDigest.query.filter_by(run_id=run_id).order_by(desc(MemoryCommunityDigest.id)).first()
    if dg is not None:
        community_digest = {
            "round_id": dg.round_id,
            "digest_text": dg.digest_text,
            "top_topics": dg.top_topics_json,
            "norms": dg.norms_json,
            "memes": dg.memes_json,
            "polarizing_issues": dg.polarizing_issues_json,
        }

    recent_pair_events = [
        {
            "round_id": ev.round_id,
            "actor_user_id": ev.actor_user_id,
            "actor_username": _normalize_username(user_map.get(ev.actor_user_id)),
            "target_user_id": ev.target_user_id,
            "target_username": _normalize_username(user_map.get(ev.target_user_id)),
            "event_type": ev.event_type,
            "relation_label": ev.relation_label,
            "tone_label": ev.tone_label,
            "thread_root_id": ev.thread_root_id,
            "target_post_id": ev.target_post_id,
            "salient_claim": ev.salient_claim,
        }
        for ev in pair_rows
    ]

    return json.dumps(
        {
            "status": 200,
            "run_id": run_id,
            "user_map": {str(k): v for k, v in user_map.items() if v},
            "other_username": _normalize_username(user_map.get(other_user_id)),
            "social_card": social_card,
            "thread_card": thread_card,
            "community_digest": community_digest,
            "recent_pair_events": recent_pair_events,
        }
    )


@app.route("/memory/events_recent", methods=["POST"])
def memory_events_recent():
    _ensure_memory_schema()
    data = json.loads(request.get_data() or "{}")
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        return json.dumps({"status": 400, "error": "run_id required"}), 400
    limit = max(1, min(_to_int_or_none(data.get("limit")) or 80, 200))
    rows = MemoryInteractionEvent.query.filter(MemoryInteractionEvent.run_id == run_id).order_by(desc(MemoryInteractionEvent.id)).limit(limit).all()[::-1]
    return json.dumps(
        {
            "status": 200,
            "run_id": run_id,
            "events": [
                {
                    "round_id": ev.round_id,
                    "actor_user_id": ev.actor_user_id,
                    "target_user_id": ev.target_user_id,
                    "event_type": ev.event_type,
                    "relation_label": ev.relation_label,
                    "tone_label": ev.tone_label,
                    "thread_root_id": ev.thread_root_id,
                    "target_post_id": ev.target_post_id,
                    "salient_claim": ev.salient_claim,
                    "importance": ev.importance,
                    "event_text": ev.event_text,
                }
                for ev in rows
            ],
        }
    )
