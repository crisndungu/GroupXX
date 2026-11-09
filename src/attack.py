"""Replay attacker: records sealed messages off the simulated network and resends them.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Run against your own simulated network only.
"""


class Recorder:
    def __init__(self):
        self.captured = []  # (device_id, blob)

    def observe(self, device_id, blob):
        self.captured.append((device_id, blob))

    def replay_all(self, gateway):
        """Resend every captured message and return how many the gateway accepted."""
        return sum(1 for device_id, blob in self.captured if gateway.receive(device_id, blob))
