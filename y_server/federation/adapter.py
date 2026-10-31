"""PlatformAdapter of YServer (microblogging, Standard backend).

Clock part (F2.3): canonical time of the rounds table, which is base 0 (day 0, hour 0 is the first round; F0.4).
Bus, membership and attention are filled in by later phases (F3 and F4): until then the adapter exports nothing,
materialises nothing and ignores membership and attention, so a federated run behaves like a standalone one."""

from ysocial_federation.adapter import IngestReport, PlatformAdapter
from ysocial_federation.timebase import ZERO_BASED


class YServerAdapter(PlatformAdapter):
    platform = "microblogging"

    def __init__(self, member, federation_id=1):
        self.member = member
        self.federation_id = federation_id

    def to_tick(self, local_round):
        day, hour = local_round
        return ZERO_BASED.to_tick(int(day), int(hour))

    def from_tick(self, tick):
        return ZERO_BASED.from_tick(tick)

    def export_outbox(self, tick):
        return []  # F3

    def ingest_inbox(self, tick, envelopes):
        return IngestReport(skipped={"not_supported_yet": len(envelopes)} if envelopes else {})  # F3

    def apply_membership(self, changes):
        return None  # F3.4

    def affective_report(self, day):
        return []  # F4

    def apply_attention(self, day, multipliers):
        return None  # F4
