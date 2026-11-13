"""Safety wrapper: a failure of the federation must not turn a round advance into a server error."""

import logging

log = logging.getLogger("y_server.federation")


class SafeGate:
    """Delegates to the SDK FederationGate; errors while opening a round are logged, not raised.

    The SDK redoes an interrupted opening at the next barrier (FederationGate.on_barrier_ready)."""

    def __init__(self, gate):
        self.gate = gate

    def start(self, local_round):
        return self.gate.start(local_round)

    def on_barrier_ready(self, local_round):
        return self.gate.on_barrier_ready(local_round)

    def on_round_opened(self, local_round):
        try:
            self.gate.on_round_opened(local_round)
        except Exception as exc:  # noqa: BLE001
            log.error("federation: opening of round %s failed, it will be redone at the next barrier: %s", local_round, exc)

    def on_finished(self):
        try:
            self.gate.on_finished()
        except Exception as exc:  # noqa: BLE001
            log.error("federation: could not report the end of the run: %s", exc)
