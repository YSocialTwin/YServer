"""PlatformAdapter of YServer (microblogging, Standard backend).

Clock (F2.3): canonical time of the rounds table, base 0 (day 0, hour 0 is the first round; F0.4).
Bus and membership (F3.4a):
- apply_membership stores the state of each account in federation_membership; accounts that are not active are
  invisible (see visibility.py) and the clients are told which they are (/federation/inactive_users) so they do not act.
- export_outbox turns the root posts that the agents marked for cross-post (optional `crosspost` field of /post), or all
  root posts of active authors with export_policy = "all", into content.v1 for the coordinator.
- ingest_inbox materialises crosspost.v1 as a post of the author on this platform, once per fed_msg_id (INV-05), and records it in
  federation_ref.
Attention and affective reports are filled in by F4."""

import logging

from sqlalchemy import desc, select

from ysocial_federation.adapter import IngestReport, PlatformAdapter
from ysocial_federation.envelope import COORDINATOR, Envelope
from ysocial_federation.schemas import TEXT_EXCERPT_MAX
from ysocial_federation.timebase import ZERO_BASED

log = logging.getLogger("y_server.federation")


class YServerAdapter(PlatformAdapter):
    platform = "microblogging"

    def __init__(self, member, federation_id=1, accounts=None, export_policy="marked"):
        """accounts: {global_agent_id: local user id}; without an entry the global id is the local user id."""
        if export_policy not in ("marked", "all"):
            raise ValueError("export_policy must be 'marked' or 'all'")
        self.member = member
        self.federation_id = federation_id
        self.export_policy = export_policy
        self._accounts = {str(k): int(v) for k, v in (accounts or {}).items()}
        self._by_user = {v: k for k, v in self._accounts.items()}

    # -- clock -------------------------------------------------------------------------
    def to_tick(self, local_round):
        day, hour = local_round
        return ZERO_BASED.to_tick(int(day), int(hour))

    def from_tick(self, tick):
        return ZERO_BASED.from_tick(tick)

    # -- identity ----------------------------------------------------------------------
    def user_of(self, global_agent_id):
        gid = str(global_agent_id)
        if gid in self._accounts:
            return self._accounts[gid]
        return int(gid) if gid.isdigit() else None

    def agent_of(self, user_id):
        return self._by_user.get(int(user_id), str(int(user_id)))

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
        topics = [i.interest for i in db.session.scalars(
            select(Interests).join(Post_topics, Post_topics.topic_id == Interests.iid)
            .where(Post_topics.post_id == post.id).order_by(Interests.iid)).all()]
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
            query = select(Post).where(Post.id > watermark, Post.comment_to == -1, Post.shared_from == -1,
                                       Post.moderated == 0, Post.id.not_in(exported), Post.id.not_in(materialised))
            pending = [p for p in db.session.scalars(query.order_by(Post.id)).all()
                       if self._active(p.user_id) and (self.export_policy == "all" or self._marked(p.id))]
            for seq, post in enumerate(pending):
                db.session.merge(FederationExport(post_id=post.id, tick=tick, seq=seq))
            db.session.commit()
            already = db.session.scalars(select(FederationExport).where(FederationExport.tick == tick)
                                         .order_by(FederationExport.seq)).all()
        out = []
        for row in already:
            post = db.session.get(Post, row.post_id)
            out.append(Envelope.create(self.federation_id, self.member, COORDINATOR, tick, row.seq, "content.v1", self._content(post)))
        return out

    def _marked(self, post_id):
        from y_server import db
        from .tables import FederationExport

        row = db.session.get(FederationExport, post_id)
        return row is not None and row.tick is None

    def mark_for_export(self, post_id):
        """The agent chose to cross-post this post (D-07): it will be exported at the next barrier."""
        from y_server import db
        from .tables import FederationExport, ensure_tables

        ensure_tables()
        if db.session.get(FederationExport, int(post_id)) is None:
            db.session.add(FederationExport(post_id=int(post_id), tick=None, seq=None))
            db.session.commit()

    # -- bus: ingest -------------------------------------------------------------------
    def ingest_inbox(self, tick, envelopes):
        from y_server import db
        from y_server.modals import Post, Rounds, User_mgmt
        from .tables import FederationRef, ensure_tables

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
            post = Post(tweet=payload["text_excerpt"], round=current.id if current else 0, user_id=uid, comment_to=-1)
            db.session.add(post)
            db.session.flush()
            post.thread_id = post.id
            db.session.add(FederationRef(local_kind="post", local_id=post.id, source_ref=payload["source_ref"],
                                         fed_msg_id=env.fed_msg_id))
            db.session.commit()  # post and reference together: a crash leaves neither, so the message comes again
            report.materialized += 1
        return report

    def affective_report(self, day):
        return []  # F4

    def apply_attention(self, day, multipliers):
        return None  # F4
