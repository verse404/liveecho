#!/usr/bin/env python3
"""Serverless background worker for GitHub Actions + Turso Cloud SQLite.

Executes ticket-drop / return-ticket / 12306 push reminders, periodic ShowStart + RSS
tour discovery, and database maintenance directly against Turso even when Render Free Tier
is asleep.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.parser import SHANGHAI_TZ
from app.reminders import run_reminder_check_cycle
from server import AppContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("concert_tracker.cloud_jobs")

DISCOVERY_INTERVAL_SECONDS = 6 * 3600


def run_due_discovery(ctx: AppContext, force: bool = False) -> dict[str, int]:
    """Runs ShowStart + RSS discovery only for users whose artists have not been checked in >= 6h."""
    now = int(time.time())
    all_auto = ctx.db.list_all_auto_discover_artists()
    due_users: set[int] = set()
    for art in all_auto:
        last_checked = int(art.get("last_checked_at") or 0)
        if force or (now - last_checked) >= DISCOVERY_INTERVAL_SECONDS:
            due_users.add(int(art["user_id"]))

    total_checked = 0
    total_new = 0
    for uid in sorted(due_users):
        stats = ctx.run_discovery_for_user(uid)
        total_checked += stats.get("artists_checked", 0)
        total_new += stats.get("new_concerts", 0)
    return {"users_scanned": len(due_users), "artists_checked": total_checked, "new_concerts": total_new}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LiveEcho Cloud Cron Runner (Turso + GitHub Actions)")
    parser.add_argument(
        "--force-discover",
        action="store_true",
        help="Force tour discovery for all tracked artists regardless of 6h cooldown.",
    )
    parser.add_argument(
        "--skip-discover",
        action="store_true",
        help="Run reminders and maintenance only without ShowStart/RSS discovery.",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="Optional local SQLite data directory override (for local testing).",
    )
    args = parser.parse_args(argv)

    data_path = Path(args.data_dir).resolve() if args.data_dir else None
    ctx = AppContext(data_dir=data_path, enable_scheduler=False)
    try:
        # 45-minute lookback safely covers 30-minute GitHub Actions cron jitter without waking Render
        sent_count = run_reminder_check_cycle(ctx.db, lookback_minutes=45.0)
        disc_stats = {"users_scanned": 0, "artists_checked": 0, "new_concerts": 0}
        if not args.skip_discover:
            disc_stats = run_due_discovery(ctx, force=args.force_discover)
        maint_stats = ctx.db.run_maintenance(uploads_dir=ctx.uploads_dir)

        logger.info(
            "Cloud cron completed (backend=%s, reminders_sent=%d, artists_checked=%d, new_concerts=%d, sessions_pruned=%d)",
            ctx.db.backend_mode,
            sent_count,
            disc_stats["artists_checked"],
            disc_stats["new_concerts"],
            maint_stats["sessions_pruned"],
        )
        return 0
    finally:
        ctx.stop()


if __name__ == "__main__":
    raise SystemExit(main())
