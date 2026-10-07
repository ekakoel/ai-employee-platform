"""
Automation tick worker (Job 13).

Usage:
  python -m app.workers.automation_worker --company-id <uuid>
  python -m app.workers.automation_worker --all --once
"""

from __future__ import annotations

import argparse
import logging
import time

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.models.entities import Company
from app.services.automation import tick_schedules
from sqlalchemy import select

logger = logging.getLogger("app.worker.automation")


def run_once(company_id: str | None = None) -> int:
    init_db()
    total = 0
    with SessionLocal() as db:
        if company_id:
            ids = [company_id]
        else:
            ids = list(db.scalars(select(Company.id)).all())
        for cid in ids:
            runs = tick_schedules(db, company_id=cid, user_id=None)
            total += len(runs)
            if runs:
                logger.info("company=%s runs=%s", cid, len(runs))
    return total


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Automation schedule worker")
    parser.add_argument("--company-id", default=None)
    parser.add_argument("--all", action="store_true", help="Tick all companies")
    parser.add_argument("--once", action="store_true", help="Single pass then exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.worker_poll_seconds,
        help="Seconds between ticks when looping",
    )
    args = parser.parse_args()

    if not args.company_id and not args.all:
        parser.error("Provide --company-id or --all")

    while True:
        n = run_once(None if args.all else args.company_id)
        logger.info("tick complete runs=%s", n)
        if args.once:
            break
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
