"""Standard (non-HPC) materialization adapter (piano tecnico §18): the
21-step publish algorithm for a microblogging experiment with
``simulator_type == "Standard"`` -- plain ``INTEGER`` autoincrement ids,
single transaction on the shared ``db_exp`` bind.

Why a single ``db.session`` already gives the "one transaction" property
the piano tecnico asks for (§18 step 8/§21): every table this adapter
writes to -- ``Post`` and its satellites (core, ``__bind_key__="db_exp"``)
*and* every ``sd_*`` table (same bind, see models.py) -- share the exact
same Flask-SQLAlchemy session/connection for that bind. As long as this
adapter never calls ``db.session.commit()`` before the final step, and
always calls ``db.session.rollback()`` on any failure, every row written
here (core and plugin tables alike) commits or rolls back together,
without a second, separate transaction boundary to coordinate by hand. A
rolled-back ``sd_publication``/``sd_id_mapping`` row was only ever
``flush()``-ed, never committed, so a failed publish leaves zero trace in
either -- not a row marked "failed", nothing at all (piano tecnico §18
step 21: "nessuna riga orfana").

Lock (step 1): implemented as *informational* columns on ``sd_scenario``
(``lock_token``/``locked_by``/``locked_at``) rather than a real
cross-process lock protocol -- this plugin is SQLite-only (decisions.md
§F3.x and others), and SQLite's own file-level writer lock already
prevents two concurrent publish transactions from interleaving their
writes (a second writer blocks/fails at the storage layer, not at this
adapter's application logic). The lock columns exist so an admin UI can
show "being published by X since Y" and so a *stale* lock (an app crash
mid-publish) does not permanently wedge a scenario -- they are not this
plugin's only concurrency guard. Documented as a Fase 6 design decision
(decisions.md §F6), not a corner cut silently.

Metadata satellite writes (step 13) use ``metadata_mapping.py``'s pure
``build_satellite_row`` -- see that module's docstring for why
sentiment/opinion require an explicit ``topic_id`` in the stored JSON
(``Post_Sentiment``/``Agent_Opinion`` carry NOT NULL FKs this plugin's own
schema cannot default safely) while toxicity/topic/emotion do not.

``round`` assignment (steps 10/11): every materialized ``Post`` gets
``round = MAX(Rounds.id)`` for the target experiment at publish time (0 if
the experiment has never run), i.e. "as of right now" -- the same concept
``base_fingerprint`` already uses for its own snapshot (piano tecnico
§12), applied consistently here rather than inventing a second notion of
"current time" for materialized content.
"""
from __future__ import annotations

import secrets
import json
import re
from datetime import datetime

# Publication adapter of this platform. It started as a copy of the plugin's own adapter and keeps its body
# unchanged (a test of the core compares both); what comes from the plugin arrives through ``S``, the plugin's
# ``kits.support`` handed over to the driver (SCENARIO_API 1.3), because a platform cannot import the plugin.
from . import scenario_design as _scenario_design

S = _scenario_design.support()
MaterializationAdapter = S.MaterializationAdapter
MaterializationAdapterError = S.MaterializationAdapterError
PreviewResult = S.PreviewResult
PublishResult = S.PublishResult
ValidationResult = S.ValidationResult
compute_experiment_fingerprint = S.compute_experiment_fingerprint
post_attributes = S.post_attributes
MetadataMappingError = S.MetadataMappingError
build_satellite_row = S.build_satellite_row
parse_metadata_value = S.parse_metadata_value
ThreadInvariantError = S.ThreadInvariantError
topological_order = S.topological_order
validate_whole_thread = S.validate_whole_thread
_ = S._

# An app crash mid-publish leaves a stale lock; after this many seconds a
# lock held by someone else is treated as abandoned and may be reclaimed
# (see module docstring: this is a diagnostic/UX safeguard, not the
# adapter's actual concurrency guarantee -- SQLite's own writer lock is).
_LOCK_STALE_AFTER_SECONDS = 600


def _generation_constraints(draft_post):
    """Return the composer settings persisted with a draft post.

    The JSON is owned by this plugin and can predate newer fields, so an
    absent value is simply an empty settings object. Invalid legacy values
    are surfaced by validation instead of failing publish midway through a
    transaction.
    """
    try:
        value = json.loads(draft_post.generation_constraints or "{}")
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _hashtags_from_constraints(constraints, content):
    if not constraints.get("use_hashtags"):
        return []
    explicit = constraints.get("hashtags") or []
    if not isinstance(explicit, list):
        explicit = []
    tags = [str(tag).strip().lstrip("#") for tag in explicit]
    tags.extend(re.findall(r"(?<!\w)#([A-Za-z0-9_]+)", content or ""))
    normalized = {}
    for tag in tags:
        if tag:
            normalized.setdefault(tag.lower(), tag)
    return list(normalized.values())


def _load_scenario_graph(scenario_id):
    """Load every thread/post/metadata row for *scenario_id*. Returns
    ``(threads, posts_by_thread, metadata_by_draft_post_id)`` -- read-only,
    no writes. Shared by validate/preview/publish so all three see the
    same snapshot of the scenario within one request."""
    from y_web.sdk.models import db

    _m = S.models()
    ScenarioDesignDraftMetadata = _m.ScenarioDesignDraftMetadata
    ScenarioDesignDraftPost = _m.ScenarioDesignDraftPost
    ScenarioDesignThread = _m.ScenarioDesignThread

    threads = (
        db.session.query(ScenarioDesignThread)
        .filter_by(scenario_id=scenario_id)
        .order_by(ScenarioDesignThread.id.asc())
        .all()
    )

    posts_by_thread = {}
    all_draft_post_ids = []
    for thread in threads:
        posts = (
            db.session.query(ScenarioDesignDraftPost).filter_by(thread_id=thread.id).all()
        )
        posts_by_thread[thread.id] = posts
        all_draft_post_ids.extend(p.id for p in posts)

    metadata_by_draft_post_id = {}
    if all_draft_post_ids:
        rows = (
            db.session.query(ScenarioDesignDraftMetadata)
            .filter(ScenarioDesignDraftMetadata.draft_post_id.in_(all_draft_post_ids))
            .all()
        )
        for row in rows:
            metadata_by_draft_post_id.setdefault(row.draft_post_id, []).append(row)

    return threads, posts_by_thread, metadata_by_draft_post_id


class StandardMaterializationAdapter(MaterializationAdapter):
    def validate(self, scenario) -> ValidationResult:
        from y_web.sdk.models import db
        from y_web.sdk.models import Emotions, Interests, OpinionGroup, User_mgmt

        errors = []
        threads, posts_by_thread, metadata_by_draft_post_id = _load_scenario_graph(scenario.id)

        if not threads:
            errors.append(
                {"code": "empty_scenario", "message": _("Scenario has no threads to publish.")}
            )
            return ValidationResult(errors=errors)

        # Draft ids are stored as VARCHAR so they can also carry HPC UUIDs.
        # Standard's User_mgmt ids are integers; compare their normalized
        # representations to avoid rejecting every valid Standard author.
        valid_author_ids = {str(uid) for (uid,) in db.session.query(User_mgmt.id).all()}
        valid_topic_ids = {tid for (tid,) in db.session.query(Interests.iid).all()}
        # A topic already in the experiment is reused as it is whatever its length; the 20-character limit
        # (the column of a new row) applies only to a topic that publishing would have to create.
        known_topics = {
            (name or "").strip().lower() for (name,) in db.session.query(Interests.interest).all()
        }
        valid_emotion_ids = {eid for (eid,) in db.session.query(Emotions.id).all()}
        valid_emotions = {
            (label or "").strip().lower()
            for (label,) in db.session.query(Emotions.emotion).all()
        }
        opinion_groups = {
            str(group.id): group
            for group in db.session.query(OpinionGroup).all()
        }

        for thread in threads:
            posts = posts_by_thread.get(thread.id, [])
            if not posts:
                errors.append(
                    {
                        "code": "empty_thread",
                        "message": _("Thread %(tmp_id)r has no posts.", tmp_id=thread.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    }
                )
                continue

            edges = {p.tmp_id: p.parent_tmp_id for p in posts}
            try:
                validate_whole_thread(edges)
            except ThreadInvariantError as exc:
                errors.append(
                    {"code": exc.code, "message": exc.message, "thread_tmp_id": thread.tmp_id}
                )

            for post in posts:
                if str(post.author_user_id) not in valid_author_ids:
                    errors.append(
                        {
                            "code": "unknown_author",
                            "message": _("Post %(tmp_id)r: author_user_id=%(author_user_id)s does not exist.", tmp_id=post.tmp_id, author_user_id=post.author_user_id),
                            "thread_tmp_id": thread.tmp_id,
                        }
                    )

                constraints = _generation_constraints(post)
                if constraints is None:
                    errors.append({
                        "code": "invalid_generation_constraints",
                        "message": _("Post %(tmp_id)r: generation settings are invalid.", tmp_id=post.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    })
                    continue
                topic = constraints.get("topic")
                if topic and (
                    not isinstance(topic, str)
                    or (len(topic.strip()) > 20 and topic.strip().lower() not in known_topics)
                ):
                    errors.append({
                        "code": "invalid_topic", "message": _("Post %(tmp_id)r: the topic %(topic)r is not in this experiment and is longer than 20 characters (the limit for a new topic). Choose an existing topic or shorten it.", tmp_id=post.tmp_id, topic=str(topic)),
                        "thread_tmp_id": thread.tmp_id,
                    })
                emotions = constraints.get("emotions") or []
                if not isinstance(emotions, list) or any(
                    not isinstance(emotion, str) or emotion.strip().lower() not in valid_emotions
                    for emotion in emotions
                ):
                    errors.append({
                        "code": "unknown_emotion", "message": _("Post %(tmp_id)r: select emotions from this experiment's vocabulary.", tmp_id=post.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    })
                mentioned_user_id = constraints.get("mentioned_user_id")
                if mentioned_user_id is not None and (
                    post.parent_tmp_id is None or str(mentioned_user_id) not in valid_author_ids
                ):
                    errors.append({
                        "code": "invalid_mention", "message": _("Post %(tmp_id)r: mentions are available only for comments and must name an experiment agent.", tmp_id=post.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    })
                hashtags = _hashtags_from_constraints(constraints, post.content)
                if any(len(tag) > 20 for tag in hashtags):
                    errors.append({
                        "code": "invalid_hashtag", "message": _("Post %(tmp_id)r: hashtags must be at most 20 characters.", tmp_id=post.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    })
                if constraints.get("opinion") not in (None, ""):
                    try:
                        opinion = float(constraints["opinion"])
                    except (TypeError, ValueError):
                        opinion = None
                    group = opinion_groups.get(str(constraints.get("opinion_group_id") or ""))
                    if opinion is None:
                        reason = _("the value is not a number")
                    elif not topic:
                        reason = _("an opinion needs a topic")
                    elif group is None:
                        reason = _("no opinion scale is selected")
                    elif not (group.lower_bound <= opinion <= group.upper_bound):
                        reason = _("%(value)s is outside the scale %(low)s to %(high)s", value=opinion, low=group.lower_bound, high=group.upper_bound)
                    else:
                        reason = None
                    if reason:
                        errors.append({
                            "code": "invalid_opinion", "message": _("Post %(tmp_id)r: opinion must be numeric, linked to a topic, and within its selected admin scale (%(reason)s).", tmp_id=post.tmp_id, reason=reason),
                            "thread_tmp_id": thread.tmp_id,
                        })
                has_day = constraints.get("round_day") not in (None, "")
                has_hour = constraints.get("round_hour") not in (None, "")
                if has_day != has_hour:
                    errors.append({
                        "code": "invalid_round", "message": _("Post %(tmp_id)r: day and hour must be set together.", tmp_id=post.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    })
                elif has_day and has_hour:
                    try:
                        if int(constraints["round_day"]) < 0 or int(constraints["round_hour"]) < 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append({
                            "code": "invalid_round", "message": _("Post %(tmp_id)r: day and hour must be non-negative integers.", tmp_id=post.tmp_id),
                            "thread_tmp_id": thread.tmp_id,
                        })

                for code, message in post_attributes.problems(constraints):
                    errors.append({
                        "code": code,
                        "message": _("Post %(tmp_id)r: %(message)s", tmp_id=post.tmp_id, message=message),
                        "thread_tmp_id": thread.tmp_id,
                    })
                likes, dislikes = post_attributes.reaction_counts(constraints)
                if likes + dislikes > len(valid_author_ids - {str(post.author_user_id)}):
                    errors.append({
                        "code": "not_enough_reactors",
                        "message": _("Post %(tmp_id)r: %(count)s reactions are requested but the experiment has only %(available)s other agents.", tmp_id=post.tmp_id, count=likes + dislikes, available=len(valid_author_ids - {str(post.author_user_id)})),
                        "thread_tmp_id": thread.tmp_id,
                    })

                for meta in metadata_by_draft_post_id.get(post.id, []):
                    try:
                        payload = parse_metadata_value(meta.metadata_value)
                        _table_name, kwargs = build_satellite_row(
                            meta.metadata_type,
                            payload,
                            post_id=0,
                            author_user_id=post.author_user_id,
                            parent_post_id=0,
                            round_number=0,
                            is_root=post.parent_tmp_id is None,
                        )
                    except MetadataMappingError as exc:
                        errors.append(
                            {
                                "code": exc.code,
                                "message": _("Post %(tmp_id)r, metadata %(metadata_type)r: %(message)s", tmp_id=post.tmp_id, metadata_type=meta.metadata_type, message=exc.message),
                                "thread_tmp_id": thread.tmp_id,
                            }
                        )
                        continue

                    if "topic_id" in kwargs and kwargs["topic_id"] not in valid_topic_ids:
                        errors.append(
                            {
                                "code": "unknown_topic",
                                "message": _("Post %(tmp_id)r: topic_id=%(topic_id)s does not exist.", tmp_id=post.tmp_id, topic_id=kwargs['topic_id']),
                                "thread_tmp_id": thread.tmp_id,
                            }
                        )
                    if "emotion_id" in kwargs and kwargs["emotion_id"] not in valid_emotion_ids:
                        errors.append(
                            {
                                "code": "unknown_emotion",
                                "message": _("Post %(tmp_id)r: emotion_id=%(emotion_id)s does not exist.", tmp_id=post.tmp_id, emotion_id=kwargs['emotion_id']),
                                "thread_tmp_id": thread.tmp_id,
                            }
                        )

        return ValidationResult(errors=errors)

    def preview(self, scenario) -> PreviewResult:
        threads, posts_by_thread, metadata_by_draft_post_id = _load_scenario_graph(scenario.id)
        post_count = sum(len(posts) for posts in posts_by_thread.values())
        metadata_count = sum(len(rows) for rows in metadata_by_draft_post_id.values())
        for posts in posts_by_thread.values():
            for post in posts:
                constraints = _generation_constraints(post) or {}
                metadata_count += int(bool(constraints.get("topic")))
                metadata_count += len({
                    str(emotion).strip().lower()
                    for emotion in constraints.get("emotions") or []
                })
                metadata_count += len(_hashtags_from_constraints(constraints, post.content))
                metadata_count += int(
                    post.parent_tmp_id is not None
                    and constraints.get("mentioned_user_id") is not None
                )
                metadata_count += int(bool(constraints.get("topic")) and constraints.get("opinion") not in (None, ""))
                metadata_count += post_attributes.metadata_units(constraints)
        return PreviewResult(
            post_count=post_count, metadata_count=metadata_count, thread_count=len(threads)
        )

    def publish(
        self,
        scenario,
        *,
        requested_by_user_id,
        idempotency_key=None,
        replace_thread_id=None,
        _fail_after_step=None,  # test-only fault-injection hook, decisions.md §F6
    ) -> PublishResult:
        from y_web.sdk.models import db
        from y_web.sdk.models import Exps, Rounds

        _m = S.models()
        PUBLICATION_STATUS_RUNNING = _m.PUBLICATION_STATUS_RUNNING
        PUBLICATION_STATUS_SUCCEEDED = _m.PUBLICATION_STATUS_SUCCEEDED
        STATUS_PUBLISHED = _m.STATUS_PUBLISHED
        ScenarioDesignIdMapping = _m.ScenarioDesignIdMapping
        ScenarioDesignPublication = _m.ScenarioDesignPublication

        def _fault(step_number):
            if _fail_after_step == step_number:
                raise RuntimeError(f"injected test failure after step {step_number}")

        # Idempotency replay: a short-circuit *before* the publish
        # transaction opens at all -- no lock taken, nothing re-validated,
        # nothing written. Only a prior *successful* publication under the
        # same key is replayed (a failed one leaves no row at all, see
        # module docstring, so there is nothing to replay for that case --
        # a retry with the same key simply runs fresh).
        if idempotency_key:
            existing = (
                db.session.query(ScenarioDesignPublication)
                .filter_by(scenario_id=scenario.id, idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None and existing.status == PUBLICATION_STATUS_SUCCEEDED:
                mapping_rows = (
                    db.session.query(ScenarioDesignIdMapping)
                    .filter_by(publication_id=existing.id)
                    .all()
                )
                return PublishResult(
                    publication_id=existing.id,
                    post_count_created=existing.post_count_created or 0,
                    metadata_count_created=existing.metadata_count_created or 0,
                    id_mapping={m.tmp_id: m.real_id for m in mapping_rows},
                    idempotent_replay=True,
                )
            if existing is not None and existing.status == PUBLICATION_STATUS_RUNNING:
                raise MaterializationAdapterError(
                    "publish_in_progress",
                    _("A publication with this idempotency key is already running."),
                )

        exp = db.session.get(Exps, scenario.exp_id)
        if exp is None:
            raise MaterializationAdapterError(
                "experiment_not_found", _("Experiment not found."), http_status=404
            )

        # Step 2 (re-verify simulator_type -- platform_type/eligibility is
        # the route's responsibility via require_supported_experiment;
        # defended again here in case a caller bypassed get_adapter_for).
        if (exp.simulator_type or "Standard") != "Standard":
            raise MaterializationAdapterError(
                "unsupported_simulator_type",
                _("This adapter only publishes Standard experiments, got %(simulator_type)r.", simulator_type=exp.simulator_type),
            )

        # Step 3
        if exp.running:
            raise MaterializationAdapterError(
                "experiment_running", _("Cannot publish while the experiment is running.")
            )

        # Step 1 (application-level lock, see module docstring)
        now = datetime.utcnow()
        if (
            scenario.lock_token
            and scenario.locked_at
            and (now - scenario.locked_at).total_seconds() < _LOCK_STALE_AFTER_SECONDS
            and scenario.locked_by != requested_by_user_id
        ):
            raise MaterializationAdapterError(
                "scenario_locked",
                _("Scenario is currently being published by user %(locked_by)r.", locked_by=scenario.locked_by),
            )
        scenario.lock_token = secrets.token_hex(16)
        scenario.locked_by = requested_by_user_id
        scenario.locked_at = now

        # Step 5 (fingerprint)
        current_fingerprint = compute_experiment_fingerprint(exp)
        if scenario.base_fingerprint and scenario.base_fingerprint != current_fingerprint:
            db.session.rollback()
            raise MaterializationAdapterError(
                "fingerprint_mismatch",
                _("The base experiment changed since this scenario was last opened; reload the scenario before publishing."),
            )

        # Step 6 (structural validation, whole scenario)
        validation = self.validate(scenario)
        if not validation.is_valid:
            db.session.rollback()
            raise MaterializationAdapterError(
                "validation_failed",
                "Scenario failed structural validation: "
                + "; ".join(e["message"] for e in validation.errors),
            )

        # Step 7 (preview recount -- never trust a UI-cached count)
        preview = self.preview(scenario)
        threads, posts_by_thread, metadata_by_draft_post_id = _load_scenario_graph(scenario.id)

        # sd_publication row created up front (status=running): it is
        # itself the audit/result record (step 20) and is what an
        # idempotency-key replay looks up.
        publication = ScenarioDesignPublication(
            scenario_id=scenario.id,
            exp_id=scenario.exp_id,
            status=PUBLICATION_STATUS_RUNNING,
            idempotency_key=idempotency_key,
            requested_by_user_id=requested_by_user_id,
            started_at=now,
            fingerprint_at_publish=current_fingerprint,
        )
        db.session.add(publication)

        try:
            db.session.flush()  # obtain publication.id

            # Step 9 (optional controlled deletion of pre-existing content)
            if replace_thread_id is not None:
                self._delete_existing_thread(replace_thread_id)
            # Publishing again replaces what this scenario published before: the posts of its earlier publications
            # leave the base experiment, otherwise every republication would add the whole scenario once more.
            self._delete_earlier_publications(scenario.id, publication.id)
            _fault(9)

            round_number = db.session.query(db.func.max(Rounds.id)).scalar() or 0

            tmp_to_real: dict = {}
            post_count_created = 0
            metadata_count_created = 0

            for thread in threads:
                posts = posts_by_thread.get(thread.id, [])
                edges = {p.tmp_id: p.parent_tmp_id for p in posts}
                posts_by_tmp_id = {p.tmp_id: p for p in posts}
                order = topological_order(edges)

                real_thread_id = None  # the root's own real id, propagated unchanged
                for tmp_id in order:
                    draft_post = posts_by_tmp_id[tmp_id]
                    is_root = draft_post.parent_tmp_id is None
                    real_parent_id = (
                        None if is_root else tmp_to_real.get(draft_post.parent_tmp_id)
                    )

                    image_id, news_id = self._materialize_link_attachment(
                        scenario=scenario, draft_post=draft_post
                    )

                    post_round = self._resolve_round(round_number, _generation_constraints(draft_post) or {})
                    post = self._insert_post(
                        content=draft_post.content or "",
                        round_number=post_round,
                        author_user_id=draft_post.author_user_id,
                        is_root=is_root,
                        real_parent_id=real_parent_id,
                        image_id=image_id,
                        news_id=news_id,
                    )

                    if is_root:
                        real_thread_id = post.id
                    post.thread_id = real_thread_id

                    tmp_to_real[tmp_id] = post.id
                    post_count_created += 1

                    db.session.add(
                        ScenarioDesignIdMapping(
                            publication_id=publication.id, tmp_id=tmp_id, real_id=str(post.id)
                        )
                    )

                    # Step 13 (optional metadata)
                    for meta in metadata_by_draft_post_id.get(draft_post.id, []):
                        payload = parse_metadata_value(meta.metadata_value)
                        table_name, kwargs = build_satellite_row(
                            meta.metadata_type,
                            payload,
                            post_id=post.id,
                            author_user_id=draft_post.author_user_id,
                            parent_post_id=real_parent_id,
                            round_number=post_round,
                            is_root=is_root,
                        )
                        db.session.add(self._build_satellite_instance(table_name, kwargs))
                        metadata_count_created += 1

                    metadata_count_created += self._materialize_generation_constraints(
                        draft_post=draft_post,
                        post=post,
                        round_number=post_round,
                    )

                _fault(13)

            _fault(17)
            # Step 17 (post-write verification against the step-7 preview)
            if post_count_created != preview.post_count:
                raise RuntimeError(
                    f"post count mismatch: preview={preview.post_count} "
                    f"created={post_count_created}"
                )
            if metadata_count_created != preview.metadata_count:
                raise RuntimeError(
                    f"metadata count mismatch: preview={preview.metadata_count} "
                    f"created={metadata_count_created}"
                )

            # Step 18 (finalize status, still inside the one transaction)
            publication.status = PUBLICATION_STATUS_SUCCEEDED
            publication.finished_at = datetime.utcnow()
            publication.post_count_created = post_count_created
            publication.metadata_count_created = metadata_count_created
            scenario.status = STATUS_PUBLISHED
            scenario.lock_token = None
            scenario.locked_by = None
            scenario.locked_at = None
            # The publication itself added posts to the base experiment: the scenario's snapshot is the base *as it is
            # now*, otherwise the next publication would find the experiment "changed" by our own previous one.
            db.session.flush()
            scenario.base_fingerprint = compute_experiment_fingerprint(exp)

            # Step 19 (single commit -- core + sd_* tables together)
            db.session.commit()
        except Exception:
            # Step 21: any failure from step 8 onward rolls back
            # *everything* written in this transaction -- core Post/
            # satellite rows, sd_id_mapping rows, and the sd_publication
            # row itself (only ever flushed, never committed).
            db.session.rollback()
            raise

        return PublishResult(
            publication_id=publication.id,
            post_count_created=post_count_created,
            metadata_count_created=metadata_count_created,
            id_mapping=tmp_to_real,
        )

    @staticmethod
    def _resolve_round(default_round, constraints):
        from y_web.sdk.models import db
        from y_web.sdk.models import Rounds

        if constraints.get("round_day") in (None, ""):
            return default_round
        day = int(constraints["round_day"])
        hour = int(constraints["round_hour"])
        round_row = db.session.query(Rounds).filter_by(day=day, hour=hour).first()
        if round_row is None:
            round_row = Rounds(day=day, hour=hour)
            db.session.add(round_row)
            db.session.flush()
        return round_row.id

    @staticmethod
    def _insert_post(
        *, content, round_number, author_user_id, is_root, real_parent_id,
        image_id=None, news_id=None,
    ):
        """Step 10/11: insert one ``Post`` row and flush to obtain its
        real id. ``thread_id`` is written as a placeholder here and
        corrected by the caller immediately after (the root's own real id
        is not known until *this* flush returns) -- kept as a tiny
        dedicated step so the placeholder-then-correct dance is visible in
        one place rather than inlined into the main loop twice.

        ``image_id``/``news_id`` (Fase 9 follow-up: link attachments) are
        plain optional passthroughs to the real ``Post`` columns of the
        same name -- the row materializing them (``Images``/``Articles``)
        was already created by ``_materialize_link_attachment`` before
        this call, same ordering as every other FK this adapter writes."""
        from y_web.sdk.models import db
        from y_web.sdk.models import Post

        post = Post(
            tweet=content,
            round=round_number,
            user_id=author_user_id,
            comment_to=-1 if is_root else real_parent_id,
            thread_id=0,
            image_id=image_id,
            news_id=news_id,
        )
        db.session.add(post)
        db.session.flush()
        return post

    @staticmethod
    def _get_or_create_sentinel_website(scenario):
        """Fase 9 follow-up: one ``Websites`` row per *scenario*,
        created lazily on the first draft post with ``link_kind=="news"``
        and reused for every subsequent one from the same scenario
        (docs/decisions.md -- "sentinella per scenario", confirmed with
        the product owner). Never a global/shared sentinel and never one
        per external domain: this keeps the real domain out of
        ``Websites.name`` (admins can see the real link in
        ``Articles.link``/the post itself; this row only satisfies the
        NOT NULL ``website_id`` FK) while still making it obvious, from
        the sentinel's own name, which scenario an admin-attached news
        link came from.
        """
        from y_web.sdk.models import db
        from y_web.sdk.models import Websites

        if scenario.news_sentinel_website_id:
            existing = db.session.get(Websites, int(scenario.news_sentinel_website_id))
            if existing is not None:
                return existing

        website = Websites(
            name=f"Scenario Design — scenario #{scenario.id}",
            rss="",
            leaning="unknown",
            category="scenario_design_link",
            last_fetched=0,
            language="unknown",
            country="unknown",
        )
        db.session.add(website)
        db.session.flush()
        scenario.news_sentinel_website_id = str(website.id)
        return website

    #: ``Images.url``/``Articles.link`` are both VARCHAR(200) in
    #: Standard's schema (y_web/src/models/experiment.py) -- unlike HPC's
    #: counterparts, which are unbounded ``Text`` (YSimulator's
    #: models.py). ``link_url`` itself is allowed up to 2,048 chars at
    #: the sanitize.py/PUT layer (MAX_LINK_URL_LENGTH) since that layer
    #: is shared by both families; a URL longer than what *this* family
    #: can actually store is rejected here, at materialization time,
    #: rather than silently truncated (truncating the URL itself -- not
    #: just its title -- would materialize a broken link/image).
    _STANDARD_LINK_URL_MAX_LENGTH = 200

    @classmethod
    def _materialize_link_attachment(cls, *, scenario, draft_post):
        """Fase 9 follow-up: if *draft_post* has a link attachment
        (``link_kind`` set), create the real ``Images``/``Articles`` row
        it needs and return ``(image_id, news_id)`` -- exactly one of the
        two is non-``None``, matching ``Post.image_id``/``Post.news_id``
        being two independent, both-nullable columns. Returns
        ``(None, None)`` for a draft post with no attachment, the common
        case, so every call site stays a plain passthrough."""
        from y_web.sdk.models import db
        from y_web.sdk.models import Articles, Images

        if draft_post.link_kind in ("image", "news"):
            link_url = draft_post.link_url or ""
            if len(link_url) > cls._STANDARD_LINK_URL_MAX_LENGTH:
                raise MaterializationAdapterError(
                    "link_url_too_long",
                    _("This experiment's Standard schema cannot store a link URL longer than %(max_length)s characters; shorten the URL (e.g. remove tracking query parameters) before publishing.", max_length=cls._STANDARD_LINK_URL_MAX_LENGTH),
                    http_status=422,
                )

        if draft_post.link_kind == "image":
            image = Images(
                url=draft_post.link_url,
                description=draft_post.link_summary or "",
                article_id=None,
            )
            db.session.add(image)
            db.session.flush()
            return image.id, None

        if draft_post.link_kind == "news":
            website = cls._get_or_create_sentinel_website(scenario)
            # Articles.title is VARCHAR(200) NOT NULL -- link_title is
            # already capped to that length by sanitize.py, but the
            # link_url fallback (up to 2048 chars, though the guard
            # above already rejected anything over 200 for this family)
            # is truncated too, defensively, rather than relying solely
            # on the guard above.
            article = Articles(
                title=(draft_post.link_title or draft_post.link_url or "")[:200],
                summary=draft_post.link_summary or "",
                website_id=website.id,
                link=draft_post.link_url,
                fetched_on=0,
            )
            db.session.add(article)
            db.session.flush()
            return None, article.id

        return None, None

    @staticmethod
    def _materialize_generation_constraints(*, draft_post, post, round_number):
        """Write structured composer choices to the experiment's core tables."""
        from y_web.sdk.models import db
        from y_web.sdk.models import Agent_Opinion, Emotions, Hashtags, Interests, Mentions, Post_emotions, Post_hashtags, Post_Sentiment, Post_Toxicity, Post_topics, Reactions, User_mgmt

        constraints = _generation_constraints(draft_post) or {}
        count = 0
        topic_id = None
        topic = (constraints.get("topic") or "").strip()
        if topic:
            existing_topic = next(
                (row for row in db.session.query(Interests).all()
                 if (row.interest or "").strip().lower() == topic.lower()),
                None,
            )
            if existing_topic is None:
                existing_topic = Interests(interest=topic)
                db.session.add(existing_topic)
                db.session.flush()
            topic_id = existing_topic.iid
            db.session.add(Post_topics(post_id=post.id, topic_id=topic_id))
            count += 1

        emotion_names = {str(name).strip().lower() for name in constraints.get("emotions") or []}
        if emotion_names:
            for emotion in db.session.query(Emotions).all():
                if (emotion.emotion or "").strip().lower() in emotion_names:
                    db.session.add(Post_emotions(post_id=post.id, emotion_id=emotion.id))
                    count += 1

        for tag in _hashtags_from_constraints(constraints, draft_post.content):
            existing_tag = next(
                (row for row in db.session.query(Hashtags).all()
                 if (row.hashtag or "").strip().lower() == tag.lower()),
                None,
            )
            if existing_tag is None:
                existing_tag = Hashtags(hashtag=tag)
                db.session.add(existing_tag)
                db.session.flush()
            db.session.add(Post_hashtags(post_id=post.id, hashtag_id=existing_tag.id))
            count += 1

        mentioned_user_id = constraints.get("mentioned_user_id")
        if draft_post.parent_tmp_id is not None and mentioned_user_id is not None:
            db.session.add(Mentions(
                user_id=int(mentioned_user_id), post_id=post.id,
                round=round_number, answered=0,
            ))
            count += 1

        if topic_id is not None and constraints.get("opinion") not in (None, ""):
            db.session.add(Agent_Opinion(
                agent_id=int(draft_post.author_user_id), tid=round_number,
                topic_id=topic_id,
                id_interacted_with=int(mentioned_user_id or draft_post.author_user_id),
                id_post=post.id, opinion=float(constraints["opinion"]),
            ))
            count += 1

        # Hand-set attributes (see post_attributes.py): sentiment, toxicity, likes and dislikes.
        is_root = draft_post.parent_tmp_id is None
        sentiment = post_attributes.sentiment_row(constraints)
        if sentiment is not None and topic_id is not None:
            db.session.add(Post_Sentiment(
                post_id=post.id, user_id=int(draft_post.author_user_id), round=round_number,
                topic_id=topic_id, is_post=1 if is_root else 0, is_comment=0 if is_root else 1,
                **sentiment,
            ))
            count += 1
        toxicity = post_attributes.toxicity_row(constraints)
        if toxicity is not None:
            db.session.add(Post_Toxicity(post_id=post.id, **toxicity))
            count += 1
        likes, dislikes = post_attributes.reaction_counts(constraints)
        if likes + dislikes:
            picked = post_attributes.pick_reactors(
                [uid for (uid,) in db.session.query(User_mgmt.id).all()],
                draft_post.author_user_id, likes, dislikes, draft_post.tmp_id,
            )
            if picked is None:
                raise MaterializationAdapterError(
                    "not_enough_reactors",
                    _("Post %(tmp_id)r: not enough other agents to give it %(count)s reactions.", tmp_id=draft_post.tmp_id, count=likes + dislikes),
                    http_status=422,
                )
            for reaction_type, user_ids in (("like", picked[0]), ("dislike", picked[1])):
                for user_id in user_ids:
                    db.session.add(Reactions(post_id=post.id, user_id=user_id, type=reaction_type, round=round_number))
                    count += 1
            post.reaction_count = likes + dislikes
        return count

    @staticmethod
    def _build_satellite_instance(table_name: str, kwargs: dict):
        from y_web.sdk.models import Agent_Opinion, Post_emotions, Post_Sentiment, Post_Toxicity, Post_topics

        model_by_table = {
            "post_topics": Post_topics,
            "post_emotions": Post_emotions,
            "post_sentiment": Post_Sentiment,
            "post_toxicity": Post_Toxicity,
            "agent_opinion": Agent_Opinion,
        }
        return model_by_table[table_name](**kwargs)

    @staticmethod
    def _delete_existing_thread(real_thread_id) -> None:
        """Piano tecnico §20 (optional "sostituisci thread X"): delete
        every ``Post`` row sharing *real_thread_id* and its satellite
        rows, inside the same still-open transaction, before inserting the
        new content. Satellite rows are deleted explicitly rather than
        relied upon to cascade: the core schema's ``post.id`` FKs on the
        satellite tables carry no ``ON DELETE`` clause (verified in
        ``y_web/src/models/experiment.py``), so cascading is not
        guaranteed at the database level regardless of
        ``PRAGMA foreign_keys``.
        """
        from y_web.sdk.models import db
        from y_web.sdk.models import Agent_Opinion, Mentions, Post, Post_emotions, Post_hashtags, Post_Sentiment, Post_Toxicity, Post_topics, Reactions

        post_ids = [
            pid
            for (pid,) in db.session.query(Post.id)
            .filter(Post.thread_id == real_thread_id)
            .all()
        ]
        StandardMaterializationAdapter._delete_posts(post_ids)

    @staticmethod
    def _delete_earlier_publications(scenario_id, current_publication_id) -> None:
        """Remove the posts that earlier, succeeded publications of *scenario_id* created (found through the id
        mapping each publication recorded); a post already gone is skipped."""
        from y_web.sdk.models import db

        _m = S.models()
        PUBLICATION_STATUS_SUCCEEDED = _m.PUBLICATION_STATUS_SUCCEEDED
        ScenarioDesignIdMapping = _m.ScenarioDesignIdMapping
        ScenarioDesignPublication = _m.ScenarioDesignPublication

        earlier = [
            pid
            for (pid,) in db.session.query(ScenarioDesignPublication.id)
            .filter(
                ScenarioDesignPublication.scenario_id == scenario_id,
                ScenarioDesignPublication.status == PUBLICATION_STATUS_SUCCEEDED,
                ScenarioDesignPublication.id != current_publication_id,
            )
            .all()
        ]
        if not earlier:
            return
        real_ids = []
        for (real,) in db.session.query(ScenarioDesignIdMapping.real_id).filter(
            ScenarioDesignIdMapping.publication_id.in_(earlier)
        ):
            try:
                real_ids.append(int(real))
            except (TypeError, ValueError):
                continue
        StandardMaterializationAdapter._delete_posts(real_ids)

    @staticmethod
    def _delete_posts(post_ids) -> None:
        from y_web.sdk.models import db
        from y_web.sdk.models import Agent_Opinion, Mentions, Post, Post_emotions, Post_hashtags, Post_Sentiment, Post_Toxicity, Post_topics, Reactions

        post_ids = [pid for (pid,) in db.session.query(Post.id).filter(Post.id.in_(post_ids)).all()] if post_ids else []
        if not post_ids:
            return

        for model_cls, column_name in (
            (Post_emotions, "post_id"),
            (Post_hashtags, "post_id"),
            (Post_topics, "post_id"),
            (Post_Sentiment, "post_id"),
            (Post_Toxicity, "post_id"),
            (Agent_Opinion, "id_post"),
            (Reactions, "post_id"),
            (Mentions, "post_id"),
        ):
            column = getattr(model_cls, column_name)
            db.session.query(model_cls).filter(column.in_(post_ids)).delete(
                synchronize_session=False
            )

        db.session.query(Post).filter(Post.id.in_(post_ids)).delete(synchronize_session=False)
