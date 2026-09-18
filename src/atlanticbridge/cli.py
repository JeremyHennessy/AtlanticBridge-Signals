from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

from .db import (
    connect,
    insert_investment_canada_records,
    insert_source_snapshot,
    investment_canada_summary,
)
from .sources.investment_canada import (
    SOURCE_NAME,
    fetch_bucket,
    parse_index_html,
)


def _split_buckets(value: str) -> list[str]:
    buckets = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not buckets:
        raise argparse.ArgumentTypeError("At least one bucket is required")
    return buckets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlanticbridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create/upgrade the local SQLite store")
    init_db.add_argument("--db", required=True)

    ingest = subparsers.add_parser(
        "ingest-investment-canada",
        help="Fetch and ingest Investment Canada Decisions and Notification Index records",
    )
    ingest.add_argument("--db", required=True)
    ingest.add_argument(
        "--buckets",
        type=_split_buckets,
        default=["all"],
        help="Comma-separated index buckets; default: all",
    )

    summary = subparsers.add_parser(
        "summarize-investment-canada",
        help="Emit deterministic Investment Canada label coverage summary as JSON",
    )
    summary.add_argument("--db", required=True)

    return parser


def _ingest(db_path: str, buckets: list[str]) -> int:
    conn = connect(db_path)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    total_seen = 0
    total_inserted = 0

    for bucket in buckets:
        url, html = fetch_bucket(bucket)
        records = parse_index_html(
            html,
            source_url_value=url,
            source_bucket=bucket,
        )
        total_seen += len(records)
        total_inserted += insert_investment_canada_records(
            conn,
            records,
            observed_at=retrieved_at,
        )
        insert_source_snapshot(
            conn,
            source_name=SOURCE_NAME,
            source_url=url,
            source_bucket=bucket,
            retrieved_at=retrieved_at,
            sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
            record_count=len(records),
        )

    print(
        json.dumps(
            {
                "source": SOURCE_NAME,
                "buckets": buckets,
                "records_seen": total_seen,
                "records_inserted": total_inserted,
                "retrieved_at": retrieved_at,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-db":
        connect(args.db).close()
        return 0

    if args.command == "ingest-investment-canada":
        try:
            return _ingest(args.db, args.buckets)
        except Exception as exc:
            print(f"Investment Canada ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-investment-canada":
        conn = connect(args.db)
        print(json.dumps(investment_canada_summary(conn), indent=2, sort_keys=True))
        return 0

    return 2
