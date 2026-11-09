"""Simulated soil-moisture and temperature sensor.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
"""
import json
import random
import time


class SoilSensor:
    def __init__(self, device_id, seed=None):
        self.device_id = device_id
        self.seq = 0
        self._rng = random.Random(seed)
        self._moisture = self._rng.uniform(40, 70)  # percent volumetric water

    def read(self):
        """Advance the simulation one step and return (seq, payload bytes)."""
        self._moisture = min(100.0, max(0.0, self._moisture + self._rng.uniform(-3, 1)))
        self.seq += 1
        reading = {
            "id": self.device_id,
            "seq": self.seq,
            "ts": round(time.time(), 1),
            "moisture": round(self._moisture, 1),
            "temp_c": round(self._rng.uniform(14, 26), 1),
        }
        return self.seq, json.dumps(reading, separators=(",", ":")).encode()
