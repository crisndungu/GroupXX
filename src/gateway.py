"""Gateway: opens sealed messages, enforces replay protection, decodes readings.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
"""
import json

from crypto_modes import SecureChannel


class ReplayGuard:
    """Accepts a message only if its sequence number is higher than the last one seen per device.

    Limitation (discuss in report): a device reboot that resets its counter
    will be rejected until the counter exceeds the stored value. A real design
    needs a persisted counter or a challenge-response handshake.
    """

    def __init__(self):
        self._last = {}

    def accept(self, device_id, seq):
        if seq <= self._last.get(device_id, 0):
            return False
        self._last[device_id] = seq
        return True


class Gateway:
    def __init__(self, channel: SecureChannel, replay_protection=True):
        self.channel = channel
        self.guard = ReplayGuard() if replay_protection else None
        self.accepted = []
        self.rejected = []  # (reason, device_id, seq)

    def receive(self, device_id, blob):
        try:
            seq, payload = self.channel.open(blob, device_id)
        except ValueError as exc:
            self.rejected.append((str(exc), device_id, None))
            return False
        if self.guard is not None and not self.guard.accept(device_id, seq):
            self.rejected.append(("replay", device_id, seq))
            return False
        self.accepted.append(json.loads(payload))
        return True
