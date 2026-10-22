# -*- coding: utf-8 -*-
"""Run the script-style test suite in parallel — one process per file.

The suite is seventeen ``tests/test_*.py`` files, each of which is a whole
program: it imports, prints a hundred lines of progress, and exits 0 with
``PASS`` or 1 with a traceback.  That shape has one convenient property — the
unit of work is already a process boundary — and it is why this runner can be
forty lines of ``subprocess`` instead of a pytest plugin.

**Why it is safe to run them at once.**  Every check that writes anything goes
through :func:`tempfile.mkdtemp` and its own directory (see ``test_quantity``,
``test_structure``, ``test_visualization``); nothing writes into the repository
or into a fixed path.  ``test_release`` *reads* ``dist/`` and the build script
but never builds.  The only ambient state is ``QApplication``, and a fresh
interpreter means a fresh one — which is also why this is process-parallel and
not thread-parallel: two ``QApplication`` objects in one process abort the
interpreter, and a thread pool would do exactly that.

**What is *not* parallelisable.**  ``test_gui`` alone is about half the wall
clock (it builds the real ``MainWindow`` against the real mod and drives every
action through it), so the achievable speed-up is bounded by it.  Files are
scheduled longest-first by their previous run time, remembered in
``.test_times.json``, so the tail of the run is small jobs rather than the big
one.

Usage::

    ./.venv/Scripts/python.exe tools/run_tests.py               # auto jobs
    ./.venv/Scripts/python.exe tools/run_tests.py --jobs 4
    ./.venv/Scripts/python.exe tools/run_tests.py --serial      # baseline
    ./.venv/Scripts/python.exe tools/run_tests.py --only gui qty

The exit code is the count of failed files, capped at 125, so CI and the
two-environment gate can just look at it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
TIMES = ROOT / ".test_times.json"

#: Per-file ceiling.  The slowest file is around four minutes; a file that
#: hangs is a bug (a modal dialog nobody stubbed — that has happened), and the
#: point of the ceiling is to report it as a failure instead of blocking the
#: whole run until somebody notices.
DEFAULT_TIMEOUT = 900


def discover(patterns: list[str]) -> list[Path]:
    files = sorted(p for p in TESTS.glob("test_*.py"))
    if patterns:
        files = [p for p in files
                 if any(pat.lower() in p.stem.lower() for pat in patterns)]
    return files


def remembered() -> dict[str, float]:
    """Last run's duration per file, longest first ordering."""
    try:
        return json.loads(TIMES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_one(path: Path, timeout: int, env: dict) -> dict:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        code, raw = proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as exc:
        code, raw = -9, (exc.stdout or b"") + (
            f"\n*** timed out after {timeout}s ***".encode())
    elapsed = time.perf_counter() - started
    text = raw.decode("utf-8", "replace") if raw else ""
    # ``SKIP`` is success by design: the suite is written to run against real
    # WARNO files and to read as "nothing to check here" on a machine without
    # them, rather than as a failure.
    skipped = code == 0 and "\nSKIP" in "\n" + text
    return {
        "file": path.stem,
        "path": path,
        "code": code,
        "seconds": elapsed,
        "text": text,
        "skipped": skipped,
        "ok": code == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--jobs", "-j", type=int, default=0,
                    help="parallel processes (0 = min(files, cores-2, 6))")
    ap.add_argument("--serial", action="store_true", help="one at a time")
    ap.add_argument("--only", nargs="*", default=None,
                    help="substring filter on test names")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="stream each file's output as it finishes")
    ap.add_argument("--log-dir", default=None,
                    help="keep every log here (default: temp, failures kept)")
    args = ap.parse_args()

    files = discover(args.only or [])
    if not files:
        print("no test files matched")
        return 0

    remembered_times = remembered()
    files.sort(key=lambda p: -remembered_times.get(p.stem, 0.0))

    cores = os.cpu_count() or 4
    # Two cores left alone: the machine has to stay usable, and these tests are
    # read-bound on the same files, so the last few workers buy very little.
    jobs = 1 if args.serial else (args.jobs or max(1, min(len(files), cores - 2, 6)))

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Two files (test_divisions, test_unit_universe) put ``tests/`` on the path
    # but import ``ndfbin_decks`` without going through ``_env``, so they only
    # worked when launched as ``python -m tests.test_x`` from the root.  Putting
    # the root on PYTHONPATH makes every file runnable as a plain script, which
    # is what this runner assumes — and is the usage the module docstrings
    # promise.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))

    log_dir = Path(args.log_dir) if args.log_dir else Path(
        tempfile.mkdtemp(prefix="ndfdecks-tests-"))
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"{len(files)} files, jobs={jobs}, python={sys.version.split()[0]}")
    print(f"logs: {log_dir}")

    began = time.perf_counter()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, p, args.timeout, env) for p in files]
        for fut in futures:
            r = fut.result()
            results.append(r)
            (log_dir / f"{r['file']}.log").write_text(r["text"], encoding="utf-8")
            mark = "skip" if r["skipped"] else ("PASS" if r["ok"] else "FAIL")
            print(f"  {mark:4s}  {r['file']:<26s} {r['seconds']:6.1f}s"
                  f"  [{len(results)}/{len(files)}]")
            if args.verbose or not r["ok"]:
                for line in r["text"].splitlines()[-14:]:
                    print(f"          | {line}")
    wall = time.perf_counter() - began

    serial_equiv = sum(r["seconds"] for r in results)
    failed = [r for r in results if not r["ok"]]
    skipped = [r for r in results if r["skipped"]]

    print()
    print(f"{'FAIL' if failed else 'PASS'} — {len(results) - len(failed)}"
          f"/{len(results)} files green"
          + (f", {len(skipped)} skipped" if skipped else ""))
    print(f"wall {wall:.1f}s   sum-of-parts {serial_equiv:.1f}s"
          f"   speed-up {serial_equiv / wall:.2f}x")
    if failed:
        for r in failed:
            print(f"  FAILED  {r['file']}  (exit {r['code']})"
                  f"  -> {log_dir / (r['file'] + '.log')}")

    # Remember durations for the longest-first scheduling of the next run.
    # Only a full green run is worth learning from: a run that died early
    # records misleadingly short times.
    if not failed:
        try:
            TIMES.write_text(json.dumps(
                {r["file"]: round(r["seconds"], 2) for r in results}, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    return min(len(failed), 125)


if __name__ == "__main__":
    raise SystemExit(main())
