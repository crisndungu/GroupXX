"""Tests for the 12-plant simulation: profiles, zones, and payload contents.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sensor import SITE, build_sensors  # noqa: E402


class SensorTests(unittest.TestCase):
    def test_site_has_twelve_plants_in_four_zones(self):
        self.assertEqual(len(SITE), 12)
        self.assertEqual(len({p.zone for p in SITE}), 4)
        self.assertEqual(len({p.device_id for p in SITE}), 12)

    def test_payload_contains_identity_and_threshold(self):
        sensor = build_sensors(1)[0]
        _, payload = sensor.read()
        reading = json.loads(payload)
        for key in ("id", "species", "zone", "dry_at", "seq", "ts", "moisture", "temp_c"):
            self.assertIn(key, reading)
        self.assertGreaterEqual(reading["moisture"], 0.0)
        self.assertLessEqual(reading["moisture"], 100.0)

    def test_moisture_stays_in_range_over_a_long_run(self):
        for sensor in build_sensors(12):
            for _ in range(500):
                _, payload = sensor.read()
                m = json.loads(payload)["moisture"]
                self.assertTrue(0.0 <= m <= 100.0)


if __name__ == "__main__":
    unittest.main()