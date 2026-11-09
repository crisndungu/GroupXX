"""Tests for the dashboard status logic and an optional MQTT round trip.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
The MQTT test needs a broker on localhost:1883 and is skipped otherwise.
"""
import os
import socket
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from dashboard import Monitor, plant_status  # noqa: E402


def broker_running(host="localhost", port=1883):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


class StatusTests(unittest.TestCase):
    def test_healthy(self):
        now = time.time()
        self.assertEqual(plant_status({"moisture": 55.0}, now, now, 0), "healthy")

    def test_dry(self):
        now = time.time()
        self.assertEqual(plant_status({"moisture": 20.0}, now, now, 0), "dry")

    def test_stale(self):
        now = time.time()
        self.assertEqual(plant_status({"moisture": 55.0}, now - 60, now, 0), "stale")

    def test_alert_overrides_everything(self):
        now = time.time()
        self.assertEqual(plant_status({"moisture": 20.0}, now, now, 1), "alert")

    def test_monitor_counts_rejections(self):
        m = Monitor()
        m.record_accept("plot-0", {"moisture": 50.0, "temp_c": 20.0})
        m.record_reject("plot-0")
        devices = m.snapshot()["devices"]
        self.assertEqual(devices["plot-0"]["rejected_total"], 1)
        self.assertEqual(devices["plot-0"]["status"], "alert")


class HistoryTests(unittest.TestCase):
    def test_history_and_totals(self):
        m = Monitor(meta={"mode": "aes-gcm", "replay_protection": True})
        for v in (50.0, 45.0, 40.0):
            m.record_accept("plot-0", {"moisture": v, "temp_c": 20.0})
        m.record_reject("plot-1")
        state = m.snapshot()
        self.assertEqual(state["devices"]["plot-0"]["history"], [50.0, 45.0, 40.0])
        self.assertEqual(state["devices"]["plot-0"]["accepted_total"], 3)
        self.assertEqual(state["totals"]["accepted"], 3)
        self.assertEqual(state["totals"]["rejected"], 1)
        self.assertEqual(state["meta"]["mode"], "aes-gcm")

    def test_event_log_records_status_changes(self):
        m = Monitor()
        m.record_accept("plot-0", {"moisture": 55.0, "temp_c": 19.0, "dry_at": 30})
        m.record_accept("plot-0", {"moisture": 20.0, "temp_c": 19.0, "dry_at": 30})
        m.record_accept("plot-0", {"moisture": 35.0, "temp_c": 19.0, "dry_at": 30})
        kinds = [e["message"] for e in m.events()]
        self.assertTrue(any("needs water" in k for k in kinds))
        self.assertTrue(any("back above threshold" in k for k in kinds))

    def test_rejections_in_one_burst_become_one_event(self):
        m = Monitor()
        m.record_accept("plot-0", {"moisture": 55.0, "temp_c": 19.0, "dry_at": 30})
        for dev in ("plot-0", "plot-1", "plot-2"):
            m.record_reject(dev)
        security = [e for e in m.events() if e["kind"] == "security"]
        self.assertEqual(len(security), 1)
        self.assertEqual(security[0]["count"], 3)
        self.assertIn("3 replayed", security[0]["message"])

    def test_watering_events_are_rate_limited(self):
        m = Monitor()
        m.record_accept("plot-0", {"moisture": 20.0, "temp_c": 19.0, "dry_at": 30})
        m.record_accept("plot-0", {"moisture": 40.0, "temp_c": 19.0, "dry_at": 30})
        m.record_accept("plot-0", {"moisture": 15.0, "temp_c": 19.0, "dry_at": 30})
        m.record_accept("plot-0", {"moisture": 35.0, "temp_c": 19.0, "dry_at": 30})
        water = [e for e in m.events() if e["kind"] == "water"]
        self.assertEqual(len(water), 1)

    def test_dry_at_comes_from_the_plant(self):
        m = Monitor()
        m.record_accept("cy-03", {"moisture": 20.0, "temp_c": 20.0, "dry_at": 15})
        self.assertEqual(m.snapshot()["devices"]["cy-03"]["status"], "healthy")

    def test_zones_grouped(self):
        m = Monitor()
        m.record_accept("gn-01", {"moisture": 50.0, "temp_c": 20.0, "dry_at": 35, "zone": "Greenhouse North"})
        m.record_accept("hg-01", {"moisture": 50.0, "temp_c": 20.0, "dry_at": 20, "zone": "Herb Garden"})
        zones = m.snapshot()["zones"]
        self.assertEqual(zones["Greenhouse North"], ["gn-01"])
        self.assertEqual(zones["Herb Garden"], ["hg-01"])

    def test_dashboard_page_and_state_served(self):
        import threading
        import urllib.request
        from dashboard import serve
        m = Monitor(meta={"mode": "chacha20", "replay_protection": True})
        m.record_accept("plot-0", {"moisture": 55.0, "temp_c": 19.0})
        server = serve(m, port=8091)
        try:
            page = urllib.request.urlopen("http://127.0.0.1:8091/").read().decode()
            state = urllib.request.urlopen("http://127.0.0.1:8091/state").read().decode()
            events = urllib.request.urlopen("http://127.0.0.1:8091/events").read().decode()
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("Smart Plant Monitor", page)
        self.assertIn("plot-0", state)
        self.assertTrue(events.startswith("["))


@unittest.skipUnless(broker_running(), "no MQTT broker on localhost:1883")
class MqttRoundTripTests(unittest.TestCase):
    def test_sealed_message_round_trip(self):
        from crypto_modes import SecureChannel
        from transport_mqtt import GatewaySubscriber, SensorPublisher
        received = []
        sub = GatewaySubscriber(lambda dev, blob: received.append((dev, blob)))
        pub = SensorPublisher()
        ch = SecureChannel("chacha20")
        blob = ch.seal(1, "test-plot", b'{"moisture":50}')
        pub.publish("test-plot", blob)
        deadline = time.time() + 5
        while time.time() < deadline and not received:
            time.sleep(0.05)
        pub.close()
        sub.close()
        self.assertTrue(received)
        dev, got = received[0]
        self.assertEqual(dev, "test-plot")
        self.assertEqual(ch.open(got, "test-plot"), (1, b'{"moisture":50}'))


if __name__ == "__main__":
    unittest.main()