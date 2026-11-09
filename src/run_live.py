"""Live end-to-end run: 12 sensors publish over MQTT, the gateway verifies them, the dashboard shows them.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Prerequisite: a running MQTT broker on localhost:1883 (Mosquitto).
Usage:
    python src/run_live.py --mode aes-gcm --plants 12 --seconds 0 --attack
    --seconds 0 runs until Ctrl+C. Then open http://localhost:8080
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from attack import Recorder  # noqa: E402
from crypto_modes import SecureChannel, available_modes  # noqa: E402
from dashboard import Monitor, serve  # noqa: E402
from gateway import Gateway  # noqa: E402
from sensor import build_sensors  # noqa: E402
from transport_mqtt import GatewaySubscriber, SensorPublisher  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=available_modes(), default="aes-gcm")
    p.add_argument("--plants", type=int, default=12, help="number of plants, 1 to 12")
    p.add_argument("--seconds", type=int, default=0, help="0 means run until Ctrl+C")
    p.add_argument("--attack", action="store_true", help="replay recorded traffic at 30 s")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()

    channel = SecureChannel(a.mode)
    gateway = Gateway(channel)
    monitor = Monitor(meta={"mode": a.mode, "replay_protection": True})
    recorder = Recorder()

    def on_blob(device_id: str, blob: bytes) -> None:
        before = len(gateway.rejected)
        ok = gateway.receive(device_id, blob)
        if ok:
            monitor.record_accept(device_id, gateway.accepted[-1])
        elif len(gateway.rejected) > before:
            monitor.record_reject(device_id)

    serve(monitor, a.port)
    sub = GatewaySubscriber(on_blob)
    pub = SensorPublisher()
    sensors = build_sensors(a.plants)
    print(f"dashboard: http://localhost:{a.port}   plants={len(sensors)}   cipher={a.mode}")
    print("press Ctrl+C to stop" if a.seconds == 0 else f"running for {a.seconds} s")

    start = time.time()
    attacked = False
    try:
        while a.seconds == 0 or time.time() - start < a.seconds:
            for sensor in sensors:
                seq, payload = sensor.read()
                blob = channel.seal(seq, sensor.device_id, payload)
                recorder.observe(sensor.device_id, blob)
                pub.publish(sensor.device_id, blob)
            if a.attack and not attacked and time.time() - start > 30:
                for device_id, blob in recorder.captured[:10]:
                    pub.publish(device_id, blob)  # replayed traffic
                attacked = True
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        time.sleep(0.5)
        pub.close()
        sub.close()
        print(json.dumps({"accepted": len(gateway.accepted), "rejected": len(gateway.rejected)}))


if __name__ == "__main__":
    main()