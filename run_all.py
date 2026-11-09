"""One-command evaluation for the team: tests, benchmarks, replay experiment, and report tables.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].

Each team member runs this on their own machine:

    python run_all.py run --label "Name-MacBook-Pro-2019" --reps 5 --messages 2000

This writes results/<label>/ with the raw data and the per-machine tables.
When every member has run it and the folders are in results/, combine them:

    python run_all.py combine

This writes results/combined_tables.md, which contains Tables 2, 4, 5 and 6 of the report
in the same layout, plus a check of hypotheses H1 to H3.
"""
import argparse
import csv
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
RESULTS = os.path.join(ROOT, "results")

from crypto_modes import MODES, SecureChannel, available_modes  # noqa: E402
from gateway import Gateway  # noqa: E402
from sensor import build_sensors  # noqa: E402

PAYLOADS = (64, 256)
REPLAY_COUNT = 10          # M: number of captured messages replayed in the attack phase
REPLAY_READINGS = 50       # readings per plant in the session before the attack
WARMUP = 500               # messages discarded before each timed repetition
AEAD_MODES = ("aes-gcm", "chacha20", "ascon-aead128")


# ---------- helpers ---------------------------------------------------------

def safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-") or "machine"


def run_cmd(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def machine_info(label: str) -> dict:
    cpu = run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])
    aes = None
    if platform.system() == "Darwin":
        aes_flag = run_cmd(["sysctl", "-n", "hw.optional.aes"])
        aes = {"1": True, "0": False}.get(aes_flag)
    elif platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                text = f.read()
            cpu = cpu or (re.search(r"model name\s*:\s*(.*)", text) or [None, ""])[1]
            aes = " aes " in text.replace("\n", " ") or " aes" in text
        except OSError:
            pass
    try:
        from importlib.metadata import version
        crypto_version = version("cryptography")
    except Exception:
        crypto_version = "unknown"
    return {
        "label": label,
        "node": platform.node(),
        "system": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "cpu": cpu or platform.processor() or "unknown",
        "aes_hardware": aes,
        "python": platform.python_version(),
        "cryptography": crypto_version,
        "ascon_built": "ascon-aead128" in available_modes(),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------- 1. automated tests ----------------------------------------------

def run_tests() -> dict:
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, "tests"))
    stream = open(os.devnull, "w")
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    result = runner.run(suite)
    stream.close()
    failures = [str(t) for t, _ in result.failures + result.errors]
    return {
        "run": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "failed": len(result.failures) + len(result.errors),
        "skipped": len(result.skipped),
        "skipped_reasons": sorted({reason for _, reason in result.skipped}),
        "failing_tests": failures,
    }


# ---------- 2. benchmark ----------------------------------------------------

def time_once(mode: str, messages: int, payload_len: int) -> tuple:
    channel = SecureChannel(mode)
    payload = os.urandom(payload_len)
    for i in range(WARMUP):
        channel.seal(i + 1, "plot-0", payload)
    blobs = []
    t0 = time.perf_counter()
    for i in range(1, messages + 1):
        blobs.append(channel.seal(i, "plot-0", payload))
    seal = (time.perf_counter() - t0) / messages * 1e6
    t0 = time.perf_counter()
    for blob in blobs:
        channel.open(blob, "plot-0")
    open_ = (time.perf_counter() - t0) / messages * 1e6
    return seal, open_, channel.overhead(), len(blobs[0])


def run_benchmark(reps: int, messages: int, modes) -> list:
    rows = []
    for rep in range(1, reps + 1):
        for payload in PAYLOADS:
            for mode in modes:
                seal, open_, overhead, wire = time_once(mode, messages, payload)
                rows.append({
                    "rep": rep, "mode": mode, "payload_bytes": payload,
                    "seal_us": round(seal, 3), "open_us": round(open_, 3),
                    "overhead_bytes": overhead, "wire_bytes": wire,
                })
                print(f"  rep {rep}/{reps}  {mode:<14} {payload:>3} B  seal {seal:8.2f} us  open {open_:8.2f} us")
    return rows


# ---------- 3. replay experiment --------------------------------------------

def replay_trial(mode: str, guard: bool, seed: int) -> dict:
    channel = SecureChannel(mode)
    gateway = Gateway(channel, replay_protection=guard)
    sensors = build_sensors(12, seed=seed)
    captured = []
    for _ in range(REPLAY_READINGS):
        for sensor in sensors:
            seq, payload = sensor.read()
            blob = channel.seal(seq, sensor.device_id, payload)
            captured.append((sensor.device_id, blob))
            gateway.receive(sensor.device_id, blob)
    legit_rejected = len(gateway.rejected)          # any rejection before the attack phase
    accepted_before = len(gateway.accepted)
    replay_accepted = 0
    for device_id, blob in captured[:REPLAY_COUNT]:
        if gateway.receive(device_id, blob):
            replay_accepted += 1
    replay_rejected = REPLAY_COUNT - replay_accepted
    return {
        "mode": mode, "guard": guard, "seed": seed,
        "legitimate_sent": len(captured),
        "legitimate_accepted": accepted_before,
        "legitimate_rejected": legit_rejected,
        "replayed": REPLAY_COUNT,
        "replayed_accepted": replay_accepted,
        "replayed_rejected": replay_rejected,
    }


def run_replay(reps: int, modes) -> list:
    rows = []
    for rep in range(1, reps + 1):
        for mode in modes:
            for guard in (True, False):
                row = replay_trial(mode, guard, seed=rep)
                row["rep"] = rep
                rows.append(row)
                print(f"  rep {rep}/{reps}  {mode:<14} guard={'on ' if guard else 'off'}  "
                      f"replayed {row['replayed']}  accepted {row['replayed_accepted']}  "
                      f"legit rejected {row['legitimate_rejected']}")
    return rows


# ---------- statistics and tables -------------------------------------------

def med_iqr(values):
    """Median and interquartile range (Q1, Q3). Robust to single slow repetitions."""
    if len(values) < 4:
        # Too few repetitions for quartiles: fall back to min and max, flagged in the output.
        return statistics.median(values), min(values), max(values)
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return statistics.median(values), q1, q3


def fmt_iqr(values, digits=2):
    m, lo, hi = med_iqr(values)
    return f"{m:.{digits}f} [{lo:.{digits}f}-{hi:.{digits}f}]"


def rank_aead(rows, payload, op):
    """Median per AEAD mode, sorted fastest first, with pairwise 'meaningful' flags."""
    stats = {}
    for mode in AEAD_MODES:
        vals = [r[f"{op}_us"] for r in rows if r["mode"] == mode and r["payload_bytes"] == payload]
        if vals:
            m, lo, hi = med_iqr(vals)
            stats[mode] = (m, hi - lo)
    order = sorted(stats, key=lambda k: stats[k][0])
    flags = []
    for a, b in zip(order, order[1:]):
        gap = stats[b][0] - stats[a][0]
        meaningful = gap > max(stats[a][1], stats[b][1])
        flags.append((a, b, round(gap, 2), meaningful))
    return order, stats, flags


def write_machine_tables(folder: str, info: dict, tests: dict, bench: list, replay: list) -> None:
    lines = [f"# Results for {info['label']}", "",
             f"Statistic: median with interquartile range (Q1-Q3) over {len({r['rep'] for r in bench})} repetitions. "
             "Ranges use the same IQR, so single slow repetitions do not decide a ranking.", "",
             f"Machine: {info['cpu']} | AES hardware: {info['aes_hardware']} | "
             f"Python {info['python']} | cryptography {info['cryptography']} | "
             f"Ascon built: {info['ascon_built']} | {info['timestamp']}", ""]
    lines += ["## Automated tests", "",
              f"Run {tests['run']}, passed {tests['passed']}, failed {tests['failed']}, "
              f"skipped {tests['skipped']} ({', '.join(tests['skipped_reasons']) or 'none'}).", ""]
    if tests["failing_tests"]:
        lines += ["Failing tests (fix before any measurement is used):"] + [f"- {t}" for t in tests["failing_tests"]] + [""]

    lines += ["## Table 4 (this machine): median [Q1-Q3] us per message", "",
              "| Mode | Seal 64 B | Open 64 B | Seal 256 B | Open 256 B |", "|---|---|---|---|---|"]
    for mode in MODES:
        cells = []
        for payload in PAYLOADS:
            for op in ("seal", "open"):
                vals = [r[f"{op}_us"] for r in bench if r["mode"] == mode and r["payload_bytes"] == payload]
                cells.append(fmt_iqr(vals) if vals else "not run")
        lines.append(f"| {mode} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")
    lines.append("")

    lines += ["## Table 5 (this machine): AEAD ranking, fastest first", "",
              "A gap is meaningful only if it exceeds the larger of the two interquartile ranges (Section 5.5).", ""]
    for payload in PAYLOADS:
        for op in ("seal", "open"):
            order, stats, flags = rank_aead(bench, payload, op)
            if not order:
                continue
            ranking = " < ".join(order)
            detail = "; ".join(f"{a} vs {b}: gap {g} us, {'meaningful' if m else 'within noise'}"
                               for a, b, g, m in flags)
            lines.append(f"- {op} {payload} B: {ranking}. {detail}")
    lines.append("")

    lines += ["## Table 6 (this machine): replay experiment, summed over repetitions", "",
              "| Guard | Replayed | Accepted | Rejected | Legitimate messages rejected |", "|---|---|---|---|---|"]
    for guard in (False, True):
        for mode in AEAD_MODES + ("plain",):
            subset = [r for r in replay if r["guard"] == guard and r["mode"] == mode]
            if not subset:
                continue
            n = sum(r["replayed"] for r in subset)
            acc = sum(r["replayed_accepted"] for r in subset)
            rej = sum(r["replayed_rejected"] for r in subset)
            legit = sum(r["legitimate_rejected"] for r in subset)
            lines.append(f"| {'enabled' if guard else 'disabled'}, {mode} | {n} | {acc} | {rej} | {legit} |")
    lines.append("")
    with open(os.path.join(folder, "tables.md"), "w") as f:
        f.write("\n".join(lines))


def cmd_run(args) -> None:
    label = safe_label(args.label)
    folder = os.path.join(RESULTS, label)
    os.makedirs(folder, exist_ok=True)
    info = machine_info(label)
    modes = available_modes()
    if "ascon-aead128" not in modes:
        print("NOTE: native Ascon library not built. Run `sh native/build.sh` and re-run for Ascon results.")
    print(f"Machine {label}: {info['cpu']}, AES hardware {info['aes_hardware']}")

    print("\n[1/3] Automated tests")
    tests = run_tests()
    print(f"  run {tests['run']}, passed {tests['passed']}, failed {tests['failed']}, skipped {tests['skipped']}")

    print(f"\n[2/3] Benchmark: {args.reps} repetitions, {args.messages} messages each, warm-up {WARMUP}")
    bench = run_benchmark(args.reps, args.messages, modes)

    print(f"\n[3/3] Replay experiment: {args.reps} repetitions, guard on and off")
    replay = run_replay(args.reps, modes)

    with open(os.path.join(folder, "machine.json"), "w") as f:
        json.dump(info, f, indent=2)
    with open(os.path.join(folder, "tests.json"), "w") as f:
        json.dump(tests, f, indent=2)
    for name, rows in (("benchmark_raw.csv", bench), ("replay_raw.csv", replay)):
        if rows:
            with open(os.path.join(folder, name), "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
    write_machine_tables(folder, info, tests, bench, replay)
    print(f"\nDone. Results in {folder}/ (tables.md, benchmark_raw.csv, replay_raw.csv, machine.json)")


def load_machine(folder: str):
    with open(os.path.join(folder, "machine.json")) as f:
        info = json.load(f)
    with open(os.path.join(folder, "tests.json")) as f:
        tests = json.load(f)
    bench, replay = [], []
    with open(os.path.join(folder, "benchmark_raw.csv")) as f:
        for r in csv.DictReader(f):
            r["rep"] = int(r["rep"]); r["payload_bytes"] = int(r["payload_bytes"])
            r["seal_us"] = float(r["seal_us"]); r["open_us"] = float(r["open_us"])
            r["overhead_bytes"] = int(r["overhead_bytes"]); r["wire_bytes"] = int(r["wire_bytes"])
            bench.append(r)
    with open(os.path.join(folder, "replay_raw.csv")) as f:
        for r in csv.DictReader(f):
            r["guard"] = r["guard"] == "True"
            for k in ("replayed", "replayed_accepted", "replayed_rejected", "legitimate_rejected", "rep"):
                r[k] = int(r[k])
            replay.append(r)
    return info, tests, bench, replay


def cmd_combine(_args) -> None:
    folders = sorted(d for d in (os.path.join(RESULTS, x) for x in os.listdir(RESULTS))
                     if os.path.isdir(d) and os.path.exists(os.path.join(d, "machine.json")))
    if not folders:
        print("No machine results found in results/. Run `python run_all.py run` first.")
        return
    machines = [load_machine(f) for f in folders]
    lines = ["# Combined results (paste into the report)", "",
             f"Machines included: {len(machines)}. Statistic: median with interquartile range (Q1-Q3) "
             "over repetitions, as in Section 5.5 of the report.", ""]

    lines += ["## Table 2: Experimental machines", "",
              "| Machine | Processor | AES hardware | Python | cryptography | Ascon built |", "|---|---|---|---|---|---|"]
    for info, _, _, _ in machines:
        lines.append(f"| {info['label']} | {info['cpu']} | {info['aes_hardware']} | {info['python']} | "
                     f"{info['cryptography']} | {info['ascon_built']} |")
    lines.append("")

    lines += ["## Automated tests (Appendix A)", "", "| Machine | Run | Passed | Failed | Skipped |", "|---|---|---|---|---|"]
    for info, tests, _, _ in machines:
        lines.append(f"| {info['label']} | {tests['run']} | {tests['passed']} | {tests['failed']} | {tests['skipped']} |")
    lines.append("")

    lines += ["## Table 4: Median [Q1-Q3] processing time per message, microseconds", "",
              "| Machine | Mode | Seal 64 B | Open 64 B | Seal 256 B | Open 256 B |", "|---|---|---|---|---|---|"]
    for info, _, bench, _ in machines:
        for mode in MODES:
            cells = []
            for payload in PAYLOADS:
                for op in ("seal", "open"):
                    vals = [r[f"{op}_us"] for r in bench if r["mode"] == mode and r["payload_bytes"] == payload]
                    cells.append(fmt_iqr(vals) if vals else "not run")
            lines.append(f"| {info['label']} | {mode} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")
    lines.append("")

    lines += ["## Table 5: AEAD ranking by machine (fastest first), with H2 check", "",
              "| Machine | Payload | Op | Ranking | Adjacent gaps meaningful? |", "|---|---|---|---|---|"]
    seal64_rankings = {}
    for info, _, bench, _ in machines:
        for payload in PAYLOADS:
            for op in ("seal", "open"):
                order, _, flags = rank_aead(bench, payload, op)
                if not order:
                    continue
                if op == "seal":
                    seal64_rankings.setdefault(payload, {})[info["label"]] = tuple(order)
                detail = "; ".join(f"{a}-{b}: {'yes' if m else 'no'}" for a, b, _, m in flags) or "n/a"
                lines.append(f"| {info['label']} | {payload} B | {op} | {' < '.join(order)} | {detail} |")
    lines.append("")

    lines += ["## Table 6: Replay experiment, summed over repetitions and machines", "",
              "| Guard | Replayed | Accepted | Rejected | Legitimate messages rejected |", "|---|---|---|---|---|"]
    all_replay = [r for _, _, _, rp in machines for r in rp]
    totals = {}
    for guard in (False, True):
        for mode in AEAD_MODES + ("plain",):
            subset = [r for r in all_replay if r["guard"] == guard and r["mode"] == mode]
            if not subset:
                continue
            n = sum(r["replayed"] for r in subset)
            acc = sum(r["replayed_accepted"] for r in subset)
            rej = sum(r["replayed_rejected"] for r in subset)
            legit = sum(r["legitimate_rejected"] for r in subset)
            totals[(guard, mode)] = (n, acc, rej, legit)
            lines.append(f"| {'enabled' if guard else 'disabled'}, {mode} | {n} | {acc} | {rej} | {legit} |")
    lines.append("")

    lines += ["## Hypothesis checks", ""]
    overheads = {(r["mode"], r["payload_bytes"]): r["overhead_bytes"] for _, _, b, _ in machines for r in b}
    aead_over = [v for (m, _), v in overheads.items() if m in AEAD_MODES]
    h1 = bool(aead_over) and max(aead_over) <= 36 and (max(aead_over) - min(aead_over)) <= 4
    lines.append(f"- H1 (overhead at most 36 bytes, spread at most 4): {'SUPPORTED' if h1 else 'NOT SUPPORTED'} "
                 f"(observed {min(aead_over) if aead_over else 'n/a'} to {max(aead_over) if aead_over else 'n/a'} bytes).")
    for payload, by_machine in seal64_rankings.items():
        distinct = set(by_machine.values())
        verdict = "SUPPORTED" if len(distinct) > 1 else "NOT SUPPORTED (same ranking on every machine)"
        lines.append(f"- H2 at {payload} B seal (rankings differ across machines): {verdict}. Rankings: "
                     + "; ".join(f"{k}: {' < '.join(v)}" for k, v in by_machine.items()) + ".")
    guarded = [v for (g, _), v in totals.items() if g]
    if guarded:
        acc = sum(v[1] for v in guarded); legit = sum(v[3] for v in guarded)
        h3 = acc == 0 and legit == 0
        lines.append(f"- H3 (guard accepts no replay and rejects no legitimate message): "
                     f"{'SUPPORTED' if h3 else 'NOT SUPPORTED'} (accepted {acc}, legitimate rejected {legit}).")
    lines.append("")
    out = os.path.join(RESULTS, "combined_tables.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"Combined {len(machines)} machine(s). Written to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run tests, benchmark and replay experiment on this machine")
    run.add_argument("--label", default=platform.node() or "machine", help="name for this machine, e.g. Alex-MacBook-2019")
    run.add_argument("--reps", type=int, default=5, help="repetitions per configuration (use at least 5)")
    run.add_argument("--messages", type=int, default=2000, help="messages timed per repetition")
    run.set_defaults(func=cmd_run)
    comb = sub.add_parser("combine", help="combine every machine in results/ into the report tables")
    comb.set_defaults(func=cmd_combine)
    args = parser.parse_args()
    if getattr(args, "cmd", None) == "run" and args.reps < 1:
        parser.error("--reps must be at least 1")
    if getattr(args, "cmd", None) == "run" and args.reps < 4:
        print("WARNING: fewer than 4 repetitions. Quartiles are not meaningful; use --reps 10 or more.")
    args.func(args)


if __name__ == "__main__":
    main()