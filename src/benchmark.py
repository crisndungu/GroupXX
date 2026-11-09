"""Measure per-message overhead and seal/open time for each mode.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Usage: python src/benchmark.py --messages 5000 --payload 64
Writes results/benchmark.csv
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from crypto_modes import SecureChannel, available_modes  # noqa: E402


def bench(mode, messages, payload_len):
    ch = SecureChannel(mode)
    payload = os.urandom(payload_len)
    blobs = []
    t0 = time.perf_counter()
    for i in range(1, messages + 1):
        blobs.append(ch.seal(i, "plot-0", payload))
    t_seal = time.perf_counter() - t0
    t0 = time.perf_counter()
    for i, blob in enumerate(blobs, start=1):
        ch.open(blob, "plot-0")
    t_open = time.perf_counter() - t0
    return {
        "mode": mode,
        "payload_bytes": payload_len,
        "overhead_bytes": ch.overhead(),
        "wire_bytes": len(blobs[0]),
        "seal_us_per_msg": round(t_seal / messages * 1e6, 2),
        "open_us_per_msg": round(t_open / messages * 1e6, 2),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--messages", type=int, default=5000)
    p.add_argument("--payload", type=int, default=64)
    a = p.parse_args()
    rows = [bench(m, a.messages, a.payload) for m in available_modes()]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "benchmark.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)
