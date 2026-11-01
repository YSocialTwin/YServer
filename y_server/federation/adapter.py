"""PlatformAdapter of YServer (microblogging, Standard backend).

Clock (F2.3): canonical time of the rounds table, base 0 (day 0, hour 0 is the first round; F0.4).
Bus and membership (F3.4a):
- apply_membership stores the state of each account in federation_membership; accounts that are not active are
  invisible (see visibility.py) and the clients are told which they are (/federation/inactive_users) so they do not act.
- export_outbox turns the root posts that the agents marked for cross-post (optional `crosspost` field of /post), or all
  root posts of active authors with export_policy = "all", into content.v1 for the coordinator.
- ingest_inbox materialises crosspost.v1 as a post of the author on this platform, once per fed_msg_id (INV-05), and records it in
  federation_ref.
Exposures (F4.4b, option emit_exposures): views and interactions with materialised cross-posts as exposure.v1.
Affective report (F4.1): native stress/reward read from the stress_reward table. Attention (F4.3): multipliers stored per account, read by the clients."""

import logging

from sqlalchemy import desc, false, func, or_, select

from ysocial_federation.adapter import IngestReport, PlatformAdapter
from ysocial_federation.envelope import COORDINATOR, Envelope
from ysocial_federation import quoted as fed_quoted
from ysocial_federation.schemas import TEXT_EXCERPT_MAX
from ysocial_federation.timebase import ZERO_BASED

log = logging.getLogger("y_server.federation")


class YServerAdapter(PlatformAdapter):
    platform = "microblogging"

    def __init__(self, member, federation_id=1, accounts=None, export_policy="marked", emit_exposures=False,
                 crosspost_mode="coordinator_rule", topic_migration=True):
        """accounts: {global_agent_id: local user id}; without an entry the global id is the local user id."""
        if export_policy not in ("marked", "all"):
            raise ValueError("export_policy must be 'marked' or 'all'")
        self.member = member
        self.federation_id = federation_id
        self.export_policy = export_policy
        self.emit_exposures = bool(emit_exposures)
        if crosspost_mode not in ("coordinator_rule", "agent_action"):
            raise ValueError("crosspost_mode must be 'coordinator_rule' or 'agent_action'")
        self.crosspost_mode = crosspost_mode
        self.topic_migration = bool(topic_migration)  # False: received content attaches no topic and creates none
        self._destinations = {}  # {global_agent_id: [{"member", "local_account_id"}]}, set by the gate before each export
        self._accounts = {str(k): int(v) for k, v in (accounts or {}).items()}
        self._by_user = {v: k for k, v in self._accounts.items()}

    # -- clock -------------------------------------------------------------------------
    def to_tick(self, local_round):
        day, hour = local_round
        return ZERO_BASED.to_tick(int(day), int(hour))

    def from_tick(self, tick):
        return ZERO_BASED.from_tick(tick)

    # -- identity ----------------------------------------------------------------------
    def _humans(self):
        """{local user id: identity "human:<id>"} of the accounts of people: the identity map entries with the reserved
        prefix and the accounts the human gateway enrolled. A person never takes the identity of an agent."""
        out = {uid: gid for uid, gid in self._by_user.items() if gid.startswith("human:")}
        from y_server.gateway.tables import human_users

        out.update({uid: hid for uid, hid in human_users().items() if hid})
        return out

    def user_of(self, global_agent_id):
        gid = str(global_agent_id)
        if gid in self._accounts:
            return self._accounts[gid]
        if gid.startswith("human:"):
            return next((uid for uid, hid in self._humans().items() if hid == gid), None)
        return int(gid) if gid.isdigit() else None

    def agent_of(self, user_id):
        uid = int(user_id)
        if uid in self._by_user:
            return self._by_user[uid]
        human = self._humans().get(uid)
        return human if human is not None else str(uid)  # a person has no fallback to the local id (it could be an agent's)

    def _human_uids(self):
        return set(self._humans())

    # -- membership --------------------------------------------------------------------
    def apply_membership(self, changes):
        from y_server import db
        from .tables import FederationMembership, ensure_tables

        ensure_tables()
        for ch in changes:
            uid = self.user_of(ch.global_agent_id)
            if uid is None:
                log.warning("federation: membership change for unknown agent %s ignored", ch.global_agent_id)
                continue
            row = db.session.get(FederationMembership, uid)
            if row is None:
                row = FederationMembership(user_id=uid, global_agent_id=str(ch.global_agent_id), state=ch.state,
                                           since_tick=ch.tick, reason=ch.reason)
                db.session.add(row)
            else:
                row.state, row.since_tick, row.reason = ch.state, ch.tick, ch.reason
        db.session.commit()

    # -- bus: export -------------------------------------------------------------------
    def _active(self, user_id):
        from y_server import db
        from .tables import FederationMembership

        row = db.session.get(FederationMembership, user_id)
        return row is None or row.state == "active"

    def _watermark(self):
        from y_server import db
        from y_server.modals import Post
        from .tables import FederationState

        row = db.session.get(FederationState, "post_watermark")
        if row is None:  # posts that exist when the federation starts are not exported
            last = db.session.scalar(select(Post.id).order_by(desc(Post.id)).limit(1)) or 0
            row = FederationState(key="post_watermark", value=str(last))
            db.session.add(row)
            db.session.commit()
        return int(row.value)

    def _content(self, post):
        from y_server import db
        from y_server.modals import Images, Interests, Post_topics, User_mgmt

        user = db.session.get(User_mgmt, post.user_id)
        # a share has no topics of its own: it carries the ones of the post it shares
        topic_post = post.id
        if post.shared_from not in (None, -1) and db.session.scalar(select(Post_topics.id).where(Post_topics.post_id == post.id)) is None:
            topic_post = post.shared_from
        topics = [i.interest for i in db.session.scalars(
            select(Interests).join(Post_topics, Post_topics.topic_id == Interests.iid)
            .where(Post_topics.post_id == topic_post).order_by(Interests.iid)).all()]
        image = db.session.get(Images, post.image_id) if post.image_id else None
        return {"global_agent_id": self.agent_of(post.user_id),
                "source_ref": f"ysocial://{self.federation_id}/{self.member}/post/{post.id}",
                "kind": "post", "text_excerpt": (post.tweet or "")[:TEXT_EXCERPT_MAX],
                "image_ref": image.url if image is not None and image.url else None,
                "topics": topics, "lang": (user.language if user is not None and user.language else "en")}

    def export_outbox(self, tick):
        from y_server import db
        from y_server.modals import Post
        from .tables import FederationExport, FederationRef, ensure_tables

        ensure_tables()
        watermark = self._watermark()
        already = db.session.scalars(select(FederationExport).where(FederationExport.tick == tick)
                                     .order_by(FederationExport.seq)).all()
        if not already:  # first call for this tick: choose the posts and fix their sequence numbers
            exported = select(FederationExport.post_id).where(FederationExport.tick.is_not(None))
            materialised = select(FederationRef.local_id).where(FederationRef.local_kind == "post")
            marked_ids = select(FederationExport.post_id)  # F8: a share leaves only when the agent marked it
            query = select(Post).where(Post.id > watermark, Post.comment_to == -1,
                                       or_(Post.shared_from == -1, Post.id.in_(marked_ids) if self.crosspost_mode == "agent_action" else false()),
                                       Post.moderated == 0, Post.id.not_in(exported), Post.id.not_in(materialised))
            pending = [p for p in db.session.scalars(query.order_by(Post.id)).all()
                       if self._active(p.user_id) and (self.export_policy == "all" or self._marked(p.id))]
            for seq, post in enumerate(pending):
                db.session.merge(FederationExport(post_id=post.id, tick=tick, seq=seq))
            db.session.commit()
            if self.crosspost_mode == "agent_action":
                self._fix_crossposts(tick, [p for p in pending], len(pending))
            already = db.session.scalars(select(FederationExport).where(FederationExport.tick == tick)
                                         .order_by(FederationExport.seq)).all()
        out = []
        asked = self._crossposts_of(tick) if self.crosspost_mode == "agent_action" else []
        by_post = {r.post_id for r in asked}
        for row in already:
            if row.post_id in by_post:  # the agent chose where to post it: the cross-posts are the message
                continue
            post = db.session.get(Post, row.post_id)
            out.append(Envelope.create(self.federation_id, self.member, COORDINATOR, tick, row.seq, "content.v1", self._content(post)))
        for req in asked:
            post = db.session.get(Post, req.post_id)
            content = self._content(post)
            if req.text:
                content["text_excerpt"] = req.text[:TEXT_EXCERPT_MAX]
            body = dict(content, target_account_id=req.account_id)
            quoted = self._quoted(post)
            if quoted is not None:
                body["quoted"] = quoted
            out.append(Envelope.create(self.federation_id, self.member, req.member, tick, req.seq, "crosspost.v1", body))
        if self.emit_exposures:
            quoting = self._quote_pairs(asked)
            rows = self._exposure_rows(tick)
            if quoting:
                rows = rows + self._ensure_quote_exposures(tick, rows, quoting)
            front = []
            for row in rows:
                env = Envelope.create(self.federation_id, self.member, COORDINATOR, tick, max((e.seq for e in out + front), default=-1) + 1, "exposure.v1", {
                    "viewer_global_agent_id": self.agent_of(row.viewer_uid), "source_ref": row.source_ref, "tick": tick,
                    "exact": bool(row.exact), "kind": row.kind, "tie": row.tie})
                (front if (row.viewer_uid, row.source_ref) in quoting else out).append(env)
            # P3: the exposure of the agent to the foreign content it quotes leaves before the cross-post that quotes it
            first = min((i for i, e in enumerate(out) if e.payload_type == "crosspost.v1" and e.payload.get("quoted")), default=len(out))
            out[first:first] = front
        return out

    def _quote_pairs(self, asked):
        """P3: {(viewer account, source_ref)} of the cross-posts that quote content materialised on this platform (seen here
        by the quoting agent, who is neither a person nor inactive)."""
        from y_server import db
        from y_server.modals import Post
        from .tables import FederationRef

        humans = self._human_uids()
        pairs = set()
        for req in asked:
            post = db.session.get(Post, req.post_id)
            quoted = self._quoted(post)
            if quoted is None or post.user_id in humans or not self._active(post.user_id):
                continue
            if db.session.scalar(select(FederationRef.local_id).where(FederationRef.local_kind == "post", FederationRef.source_ref == quoted["source_ref"])) is not None:
                pairs.add((post.user_id, quoted["source_ref"]))
        return pairs

    def _ensure_quote_exposures(self, tick, rows, pairs):
        """P3: an interact exposure (exact) for each (viewer, ref) pair with no exposure of that viewer to that content yet
        (this tick or an earlier one). Stored in federation_exposure after the rows of the tick, so a retry gives the same."""
        from y_server import db
        from y_server.modals import Post
        from .tables import FederationExposure, FederationRef

        have = {(r.viewer_uid, r.source_ref) for r in db.session.scalars(select(FederationExposure).where(FederationExposure.tick <= tick)).all()}
        seq = max((r.seq for r in rows), default=-1) + 1
        added = []
        for viewer, ref in sorted(pairs - have):
            local = db.session.scalar(select(FederationRef.local_id).where(FederationRef.local_kind == "post", FederationRef.source_ref == ref))
            author = db.session.get(Post, local).user_id
            row = FederationExposure(tick=tick, seq=seq, viewer_uid=viewer, source_ref=ref, kind="interact", tie=self._tie(viewer, author), exact=True)
            db.session.add(row)
            added.append(row)
            seq += 1
        db.session.commit()
        return added

    def _quoted(self, post):
        """F8: `quoted` of a post that shares another one (None for any other post): the original author, this platform
        and the original text. The author is a federation identity only when the account is in the identity map."""
        if post.shared_from in (None, -1):
            return None
        from y_server import db
        from y_server.modals import Post, User_mgmt
        from .tables import FederationRef

        original = db.session.get(Post, post.shared_from)
        if original is None:
            return None
        author = db.session.get(User_mgmt, original.user_id)
        gid = self._by_user.get(int(original.user_id))
        ref = db.session.scalar(select(FederationRef.source_ref).where(FederationRef.local_kind == "post", FederationRef.local_id == original.id))
        ref = ref or f"ysocial://{self.federation_id}/{self.member}/post/{original.id}"
        return fed_quoted.build(author.username if author is not None else "unknown", gid, self.member, ref, original.tweet)

    def _tie(self, viewer, author):
        """none / follow / mutual between a viewer and the author of a post, from the latest follow rows."""
        from y_server import db
        from y_server.modals import Follow

        def follows(a, b):
            row = db.session.scalars(select(Follow).filter_by(user_id=a, follower_id=b).order_by(Follow.round.desc(), Follow.id.desc())).first()
            return row is not None and row.action == "follow"
        if not follows(viewer, author):
            return "none"
        return "mutual" if follows(author, viewer) else "follow"

    def _exposure_rows(self, tick):
        """Views (posts recommended in the round: approximate, exact = false) and interactions (reaction, comment or share:
        exact) of active accounts with the materialised cross-posts of the round of the tick, in a stable order."""
        from y_server import db
        from y_server.modals import Post, Reactions, Recommendations, Rounds
        from .tables import FederationExposure, FederationRef, FederationState

        done = db.session.get(FederationState, "exposure_tick")
        if done is not None and int(done.value) >= tick:
            return list(db.session.scalars(select(FederationExposure).where(FederationExposure.tick == tick)
                                           .order_by(FederationExposure.seq)).all())
        day, hour = self.from_tick(tick)
        rnd = db.session.scalars(select(Rounds).where(Rounds.day == day, Rounds.hour == hour)).first()
        found = {}
        refs = {r.local_id: r.source_ref for r in db.session.scalars(
            select(FederationRef).where(FederationRef.local_kind == "post")).all()} if rnd is not None else {}
        humans = self._human_uids()
        if refs:
            author = {pid: uid for pid, uid in db.session.execute(select(Post.id, Post.user_id).where(Post.id.in_(list(refs)))).all()}

            def add(viewer, pid, kind, exact):
                if viewer is None or viewer == author.get(pid) or not self._active(viewer) or viewer in humans:
                    return
                found.setdefault((viewer, refs[pid], kind), exact)
            for rec in db.session.scalars(select(Recommendations).where(Recommendations.round == rnd.id)).all():
                for raw in (rec.post_ids or "").split(","):
                    if raw.strip().isdigit() and int(raw) in refs:
                        add(rec.user_id, int(raw), "view", False)
            for r in db.session.scalars(select(Reactions).where(Reactions.round == rnd.id, Reactions.post_id.in_(list(refs)))).all():
                add(r.user_id, r.post_id, "interact", True)
            for c in db.session.scalars(select(Post).where(Post.round == rnd.id, (Post.comment_to.in_(list(refs))) | (Post.shared_from.in_(list(refs))))).all():
                add(c.user_id, c.comment_to if c.comment_to in refs else c.shared_from, "interact", True)
            by_ref = {v: k for k, v in refs.items()}
            for seq, ((viewer, ref, kind), exact) in enumerate(sorted(found.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))):
                db.session.add(FederationExposure(tick=tick, seq=seq, viewer_uid=viewer, source_ref=ref, kind=kind,
                                                  tie=self._tie(viewer, author[by_ref[ref]]), exact=exact))
        if done is None:
            db.session.add(FederationState(key="exposure_tick", value=str(tick)))
        else:
            done.value = str(tick)
        db.session.commit()
        return list(db.session.scalars(select(FederationExposure).where(FederationExposure.tick == tick).order_by(FederationExposure.seq)).all())

    def _marked(self, post_id):
        from y_server import db
        from .tables import FederationExport

        row = db.session.get(FederationExport, post_id)
        return row is not None and row.tick is None

    def mark_for_export(self, post_id, targets=None):
        """The agent chose to cross-post this post (D-07): it will be exported at the next barrier.

        targets (crosspost.mode = agent_action): [{"member", "text"}], where the agent wants it and with which text."""
        from y_server import db
        from .tables import FederationCrosspost, FederationExport, ensure_tables

        ensure_tables()
        if db.session.get(FederationExport, int(post_id)) is None:
            db.session.add(FederationExport(post_id=int(post_id), tick=None, seq=None))
        if self.crosspost_mode == "agent_action":
            for target in targets or []:
                member = str(target.get("member") or "")
                if member and member != self.member and db.session.get(FederationCrosspost, (int(post_id), member)) is None:
                    db.session.add(FederationCrosspost(post_id=int(post_id), member=member, text=str(target.get("text") or "")))
        db.session.commit()

    # -- agent-action cross-posts (F6.2) -------------------------------------------------
    def set_destinations(self, destinations):
        self._destinations = {str(k): list(v) for k, v in (destinations or {}).items()}

    def destination_members(self, user_id):
        """Members where this account's agent could cross-post now (as of the last barrier)."""
        return sorted(d["member"] for d in self._destinations.get(self.agent_of(user_id), []))

    def _fix_crossposts(self, tick, posts, first_seq):
        """First export of the tick: give each requested cross-post its account, tick and sequence number (a request
        for a platform where the author has no active account is dropped)."""
        from y_server import db
        from .tables import FederationCrosspost

        seq = first_seq
        for post in posts:
            wanted = self._destinations.get(self.agent_of(post.user_id), [])
            rows = db.session.scalars(select(FederationCrosspost).where(FederationCrosspost.post_id == post.id,
                                                                        FederationCrosspost.tick.is_(None))
                                      .order_by(FederationCrosspost.member)).all()
            for row in rows:
                account = next((d["local_account_id"] for d in wanted if d["member"] == row.member), None)
                row.tick = tick
                if account is None:
                    log.info("federation: cross-post of post %s to %s dropped: no active account", post.id, row.member)
                    continue
                row.account_id, row.seq = str(account), seq
                seq += 1
        db.session.commit()

    def _crossposts_of(self, tick):
        from y_server import db
        from .tables import FederationCrosspost

        return list(db.session.scalars(select(FederationCrosspost).where(FederationCrosspost.tick == tick, FederationCrosspost.seq.is_not(None))
                                       .order_by(FederationCrosspost.seq)).all())

    # -- bus: ingest -------------------------------------------------------------------
    def ingest_inbox(self, tick, envelopes):
        from y_server import db
        from y_server.modals import Interests, Post, Post_topics, Rounds, User_mgmt
        from .tables import FederationQuoted, FederationRef, FederationTopic, ensure_tables

        ensure_tables()
        report = IngestReport()

        def skip(reason):
            report.skipped[reason] = report.skipped.get(reason, 0) + 1

        for env in envelopes:
            if env.payload_type != "crosspost.v1":
                skip("skipped_unsupported")
                continue
            if db.session.scalar(select(FederationRef.local_id).where(FederationRef.fed_msg_id == env.fed_msg_id)) is not None:
                report.duplicates += 1  # INV-05: already materialised
                continue
            payload = env.payload
            try:
                uid = int(payload["target_account_id"])
            except (TypeError, ValueError):
                skip("skipped_ineligible")
                continue
            user = db.session.get(User_mgmt, uid)
            if user is None or not self._active(uid):
                skip("skipped_ineligible")
                continue
            current = db.session.scalars(select(Rounds).order_by(desc(Rounds.id))).first()
            quoted = payload.get("quoted")
            post = Post(tweet=fed_quoted.render(payload["text_excerpt"], quoted) if quoted else payload["text_excerpt"],
                        round=current.id if current else 0, user_id=uid, comment_to=-1)
            db.session.add(post)
            db.session.flush()
            if quoted:
                db.session.add(FederationQuoted(post_id=post.id, author_name=quoted["author_name"], global_agent_id=quoted["global_agent_id"],
                                                member=quoted["member"], source_ref=quoted["source_ref"], text_excerpt=quoted["text_excerpt"]))
            post.thread_id = post.id
            seen = set()
            for full in (payload.get("topics") or []) if self.topic_migration else []:  # topics travel with the content
                full = " ".join(str(full).split())[:200]
                if not full or full.lower() in seen:
                    continue
                seen.add(full.lower())
                interest = self._topic_for(full, tick, env.source_member)
                db.session.add(Post_topics(post_id=post.id, topic_id=interest.iid))
            db.session.add(FederationRef(local_kind="post", local_id=post.id, source_ref=payload["source_ref"],
                                         fed_msg_id=env.fed_msg_id))
            db.session.commit()  # post and reference together: a crash leaves neither, so the message comes again
            report.materialized += 1
        return report

    def _topic_for(self, full, tick, source_member):
        """The topic of a migrated name: an existing one (case-insensitive), or a new one created and recorded. The name is
        cut to 20 characters; when that cut already belongs to a topic migrated under a different full name, a stable
        suffix (`~` and 4 hex digits of the full name's hash) keeps the two apart. Same name, same topic, always."""
        import hashlib

        from y_server import db
        from y_server.modals import Interests
        from .tables import FederationTopic, FederationTopicOrigin

        key = full.lower()
        known = db.session.get(FederationTopicOrigin, key)
        if known is not None:
            return db.session.get(Interests, known.interest_id)
        cut = full[:20]
        interest = db.session.scalars(select(Interests).where(func.lower(Interests.interest) == cut.lower())
                                      .order_by(Interests.iid)).first()
        if interest is not None and len(full) > 20:
            other = db.session.scalars(select(FederationTopicOrigin).where(FederationTopicOrigin.interest_id == interest.iid)).first()
            if other is not None and other.original_key != key:  # the cut is taken by a different long name
                cut = full[:15] + "~" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:4]
                interest = db.session.scalars(select(Interests).where(func.lower(Interests.interest) == cut.lower())
                                              .order_by(Interests.iid)).first()
        if interest is None:
            interest = Interests(interest=cut)
            db.session.add(interest)
            db.session.flush()
            db.session.add(FederationTopic(name=cut, interest_id=interest.iid, created_tick=tick, source_member=source_member))
        db.session.add(FederationTopicOrigin(original_key=key, full_name=full, interest_id=interest.iid, resolved_name=interest.interest[:20]))
        return interest

    def affective_report(self, day):
        """Native stress/reward of the active accounts at the end of the canonical day (F4.1), read from the runtime's
        stress_reward table with the rule of /get_stress_reward (latest aggregate + later variations, clamped), without
        writing; actions = posts and reactions of the account in the day, exposures = posts recommended to it."""
        from y_server import db
        from y_server.modals import Post, Reactions, Recommendations, Rounds, StressReward
        from ysocial_federation.schemas import AffectiveSample
        from .tables import FederationMembership, ensure_tables

        ensure_tables()
        rounds = list(db.session.scalars(select(Rounds.id).where(Rounds.day == int(day)).order_by(Rounds.id)).all())
        if not rounds:
            return []
        lo, hi = rounds[0], rounds[-1]

        def value(uid, variable):
            anchor = db.session.scalars(select(StressReward).where(
                StressReward.uid == uid, StressReward.variable == variable, StressReward.type == "aggregate",
                StressReward.tid < hi).order_by(StressReward.tid.desc())).first()
            base, anchor_tid = (float(anchor.value), int(anchor.tid)) if anchor is not None else (0.0, lo - 1)
            total = db.session.query(db.func.coalesce(db.func.sum(StressReward.value), 0.0)).filter(
                StressReward.uid == uid, StressReward.variable == variable, StressReward.type == "variation",
                StressReward.tid > anchor_tid, StressReward.tid <= hi).scalar()
            return max(0.0, min(1.0, base + float(total or 0.0)))

        out = []
        humans = self._human_uids()  # people are not part of the group mechanisms (INV-15)
        for row in db.session.scalars(select(FederationMembership).where(FederationMembership.state == "active")
                                      .order_by(FederationMembership.user_id)).all():
            uid = row.user_id
            if uid in humans:
                continue
            posts = db.session.query(db.func.count(Post.id)).filter(Post.user_id == uid, Post.round >= lo, Post.round <= hi).scalar()
            reacts = db.session.query(db.func.count(Reactions.id)).filter(Reactions.user_id == uid, Reactions.round >= lo,
                                                                         Reactions.round <= hi).scalar()
            exposures = sum(len([p for p in (r.post_ids or "").split(",") if p.strip()]) for r in db.session.scalars(
                select(Recommendations).where(Recommendations.user_id == uid, Recommendations.round >= lo,
                                              Recommendations.round <= hi)).all())
            out.append(AffectiveSample(self.agent_of(uid), int(day), value(uid, "stress"), value(uid, "reward"),
                                       int(posts or 0) + int(reacts or 0), int(exposures)))
        return out

    def churned_agents(self, day):
        """Agents of this platform that left on their own (users.left_on set at a round up to the end of the day, F4.5): the
        coordinator records them as left with reason churn. Only accounts the federation still sees as active."""
        from y_server import db
        from y_server.modals import Rounds, User_mgmt
        from .tables import FederationMembership, ensure_tables

        ensure_tables()
        last = db.session.scalar(select(db.func.max(Rounds.id)).where(Rounds.day <= int(day)))
        if last is None:
            return []
        out = []
        humans = self._human_uids()
        for row in db.session.scalars(select(FederationMembership).where(FederationMembership.state == "active")).all():
            if row.user_id in humans:
                continue
            user = db.session.get(User_mgmt, row.user_id)
            if user is not None and user.left_on is not None and int(user.left_on) <= last:
                out.append(row.global_agent_id)
        return sorted(out)

    def apply_attention(self, day, multipliers):
        """Store the multipliers of the day (F4.3): accounts that are not in the dictionary go back to 1; unknown agents are
        ignored. The clients read them with GET /federation/attention and apply them where they choose how much an agent acts."""
        from y_server import db
        from .tables import FederationAttention, ensure_tables

        ensure_tables()
        wanted = {}
        for gid, value in (multipliers or {}).items():
            uid = self.user_of(gid)
            if uid is not None and uid not in self._human_uids() and float(value) != 1.0:
                wanted[uid] = float(value)
        db.session.query(FederationAttention).delete()
        for uid, value in sorted(wanted.items()):
            db.session.add(FederationAttention(user_id=uid, day=int(day), multiplier=value))
        db.session.commit()

    def attention_multipliers(self):
        """{local user id: multiplier} of the current day (accounts not listed: 1)."""
        from y_server import db
        from .tables import FederationAttention, ensure_tables

        ensure_tables()
        return {r.user_id: r.multiplier for r in db.session.scalars(select(FederationAttention)).all()}
