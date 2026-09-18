from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .db import (
    connect,
    cordis_summary,
    corporations_canada_summary,
    ingest_cordis_snapshot,
    ingest_corporations_canada_snapshot,
    insert_investment_canada_records,
    insert_source_snapshot,
    investment_canada_summary,
)
from .gleif_resolution import gleif_resolution_summary, resolve_cordis_targets
from .sources.cordis import (
    HORIZON_ARCHIVE_URL,
    SOURCE_BUCKET as CORDIS_SOURCE_BUCKET,
    SOURCE_NAME as CORDIS_SOURCE_NAME,
    download_horizon_archive,
    iter_participations,
    iter_projects,
)
from .sources.corporations_canada import (
    ACTIVE_BUSINESS_URL,
    SOURCE_BUCKET as CORPORATIONS_SOURCE_BUCKET,
    SOURCE_NAME as CORPORATIONS_SOURCE_NAME,
    download_active_business_csv,
    iter_active_business_csv,
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

    corp = subparsers.add_parser(
        "ingest-corporations-canada",
        help="Stream the daily Corporations Canada active-CBCA CSV into a baseline/diff store",
    )
    corp.add_argument("--db", required=True)
    corp.add_argument("--mode", required=True, choices=["baseline", "diff"])
    corp.add_argument("--source-url", default=ACTIVE_BUSINESS_URL)

    corp_summary = subparsers.add_parser(
        "summarize-corporations-canada",
        help="Emit current Corporations Canada coverage and event counts as JSON",
    )
    corp_summary.add_argument("--db", required=True)

    cordis = subparsers.add_parser(
        "ingest-cordis",
        help="Replace the local CORDIS Horizon project/participation snapshot",
    )
    cordis.add_argument("--db", required=True)
    cordis.add_argument("--source-url", default=HORIZON_ARCHIVE_URL)

    cordis_summary_parser = subparsers.add_parser(
        "summarize-cordis",
        help="Emit Canada-EU Horizon relationship coverage as JSON",
    )
    cordis_summary_parser.add_argument("--db", required=True)

    gleif = subparsers.add_parser(
        "resolve-cordis-gleif",
        help="Query GLEIF for candidate LEIs for EU CORDIS organizations on Canadian projects",
    )
    gleif.add_argument("--db", required=True)
    gleif.add_argument("--limit", type=int, default=50)
    gleif.add_argument("--offset", type=int, default=0)
    gleif.add_argument("--page-size", type=int, default=5)
    gleif.add_argument("--delay-seconds", type=float, default=0.1)

    gleif_summary_parser = subparsers.add_parser(
        "summarize-gleif",
        help="Emit GLEIF candidate-resolution coverage without auto-confirming identities",
    )
    gleif_summary_parser.add_argument("--db", required=True)

    return parser


def _ingest_investment_canada(db_path: str, buckets: list[str]) -> int:
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


def _ingest_corporations_canada(
    db_path: str,
    *,
    mode: str,
    source_url: str,
) -> int:
    retrieved_at = datetime.now(timezone.utc).isoformat()
    conn = connect(db_path)

    with tempfile.TemporaryDirectory(prefix="atlanticbridge-corp-") as temp_dir:
        csv_path = Path(temp_dir) / "corporations-active-cbca-en.csv"
        download = download_active_business_csv(
            csv_path,
            source_url=source_url,
        )
        result = ingest_corporations_canada_snapshot(
            conn,
            iter_active_business_csv(download.path, source_url=source_url),
            observed_at=retrieved_at,
            mode=mode,
        )
        insert_source_snapshot(
            conn,
            source_name=CORPORATIONS_SOURCE_NAME,
            source_url=source_url,
            source_bucket=CORPORATIONS_SOURCE_BUCKET,
            retrieved_at=retrieved_at,
            sha256=download.sha256,
            record_count=result["records_staged"],
        )

    print(
        json.dumps(
            {
                "source": CORPORATIONS_SOURCE_NAME,
                "mode": mode,
                "retrieved_at": retrieved_at,
                "source_bytes": download.byte_count,
                "source_sha256": download.sha256,
                **result,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _ingest_cordis(
    db_path: str,
    *,
    source_url: str,
) -> int:
    retrieved_at = datetime.now(timezone.utc).isoformat()
    conn = connect(db_path)

    with tempfile.TemporaryDirectory(prefix="atlanticbridge-cordis-") as temp_dir:
        archive_path = Path(temp_dir) / "cordis-HORIZONprojects-csv.zip"
        download = download_horizon_archive(
            archive_path,
            source_url=source_url,
        )
        result = ingest_cordis_snapshot(
            conn,
            iter_projects(download.path, source_url=source_url),
            iter_participations(download.path, source_url=source_url),
            observed_at=retrieved_at,
        )
        insert_source_snapshot(
            conn,
            source_name=CORDIS_SOURCE_NAME,
            source_url=source_url,
            source_bucket=CORDIS_SOURCE_BUCKET,
            retrieved_at=retrieved_at,
            sha256=download.sha256,
            record_count=result["projects"] + result["participations"],
        )

    print(
        json.dumps(
            {
                "source": CORDIS_SOURCE_NAME,
                "retrieved_at": retrieved_at,
                "source_bytes": download.byte_count,
                "source_sha256": download.sha256,
                **result,
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
            return _ingest_investment_canada(args.db, args.buckets)
        except Exception as exc:
            print(f"Investment Canada ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-investment-canada":
        conn = connect(args.db)
        print(json.dumps(investment_canada_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "ingest-corporations-canada":
        try:
            return _ingest_corporations_canada(
                args.db,
                mode=args.mode,
                source_url=args.source_url,
            )
        except Exception as exc:
            print(f"Corporations Canada ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-corporations-canada":
        conn = connect(args.db)
        print(json.dumps(corporations_canada_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "ingest-cordis":
        try:
            return _ingest_cordis(args.db, source_url=args.source_url)
        except Exception as exc:
            print(f"CORDIS ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-cordis":
        conn = connect(args.db)
        print(json.dumps(cordis_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "resolve-cordis-gleif":
        try:
            conn = connect(args.db)
            result = resolve_cordis_targets(
                conn,
                limit=args.limit,
                offset=args.offset,
                page_size=args.page_size,
                delay_seconds=args.delay_seconds,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            print(f"GLEIF resolution failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-gleif":
        conn = connect(args.db)
        print(json.dumps(gleif_resolution_summary(conn), indent=2, sort_keys=True))
        return 0

    return 2
