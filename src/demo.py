"""Run one simulated session: sensors -> channel -> gateway, with an optional replay attack.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Usage: python src/demo.py --mode chacha20 --readings 50 --attack
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from attack import Recorder  # noqa: E402
from crypto_modes import SecureChannel, available_modes  # noqa: E402
from gateway import Gateway  # noqa: E402
from sensor import build_sensors  # noqa: E402


def run(mode, readings, sensors=3, attack=False, replay_protection=True):
    channel = SecureChannel(mode)
    gateway = Gateway(channel, replay_protection=replay_protection)
    recorder = Recorder()
    devices = build_sensors(sensors)
    for _ in range(readings):
        for dev in devices:
            seq, payload = dev.read()
            blob = channel.seal(seq, dev.device_id, payload)
            recorder.observe(dev.device_id, blob)
            gateway.receive(dev.device_id, blob)
    replayed = recorder.replay_all(gateway) if attack else 0
    return {
        "mode": mode,
        "accepted": len(gateway.accepted),
        "rejected": len(gateway.rejected),
        "replays_accepted": replayed,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=available_modes(), default="chacha20")
    p.add_argument("--readings", type=int, default=20)
    p.add_argument("--attack", action="store_true")
    p.add_argument("--no-replay-protection", action="store_true")
    a = p.parse_args()
    print(run(a.mode, a.readings, attack=a.attack,
              replay_protection=not a.no_replay_protection))