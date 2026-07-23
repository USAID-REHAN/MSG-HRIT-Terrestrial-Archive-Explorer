"""Run a repeatable end-to-end processing benchmark for one downloaded timeslot."""

from __future__ import annotations

import argparse
import json
import threading
from time import perf_counter

import psutil
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Timeslot
from app.db.session import session_scope
from app.processing.pipeline import process_timeslot, run_processing_worker


def _default_timeslot_id() -> int:
    with session_scope() as db:
        timeslot_id = db.execute(
            select(Timeslot.id)
            .where(Timeslot.download_status == "downloaded")
            .order_by(Timeslot.id)
            .limit(1)
        ).scalar_one_or_none()
    if timeslot_id is None:
        raise SystemExit("No downloaded timeslot is available")
    return int(timeslot_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeslot-id", type=int)
    parser.add_argument("--timeslot-ids", type=int, nargs="+")
    args = parser.parse_args()
    timeslot_ids = args.timeslot_ids or [args.timeslot_id or _default_timeslot_id()]

    stop_monitor = threading.Event()
    peak_rss = 0

    def monitor() -> None:
        nonlocal peak_rss
        parent = psutil.Process()
        while not stop_monitor.wait(0.25):
            processes = [parent, *parent.children(recursive=True)]
            rss = 0
            for process in processes:
                try:
                    rss += process.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            peak_rss = max(peak_rss, rss)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    started = perf_counter()
    if len(timeslot_ids) == 1:
        result = process_timeslot(timeslot_ids[0], get_settings())
    else:
        result = run_processing_worker(get_settings(), only_ids=timeslot_ids)
    stop_monitor.set()
    monitor_thread.join()
    result["wall_seconds"] = round(perf_counter() - started, 3)
    result["peak_worker_rss_gb"] = round(peak_rss / (1024**3), 3)
    result["timeslot_ids"] = timeslot_ids
    print(json.dumps(result, indent=2))
    ok = result.get("ok", result.get("failed", 1) == 0)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
