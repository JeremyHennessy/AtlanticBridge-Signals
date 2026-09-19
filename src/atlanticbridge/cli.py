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
    replace_investment_canada_history,
)
from .gleif_resolution import gleif_resolution_summary, resolve_cordis_targets
from .entry_identity import entry_identity_summary, run_entry_identity_resolution
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
    crawl_investment_canada_history,
    fetch_bucket,
    parse_index_html,
)
from .cipo_store import cipo_summary, run_owner_search
from .canadabuys_store import canadabuys_summary, ingest_awards
from .sources.canadabuys import (
    CURRENT_AWARDS_URL,
    SOURCE_BUCKET as CANADABUYS_SOURCE_BUCKET,
    SOURCE_NAME as CANADABUYS_SOURCE_NAME,
    download_awards_csv,
    iter_awards_csv,
)
from .sources.ted import search_awards
from .ted_store import ingest_ted_search_result, ted_summary
from .sources.statcan_trade import (
    ANNUAL_CONFIG as STATCAN_ANNUAL_CONFIG,
    MONTHLY_CONFIG as STATCAN_MONTHLY_CONFIG,
    download_table as download_statcan_table,
    iter_filtered_records as iter_statcan_records,
)
from .statcan_trade_store import ingest_statcan_snapshot, statcan_trade_summary


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
        help="Comma-separated first-page index buckets; default: all",
    )
    ingest.add_argument(
        "--history",
        action="store_true",
        help="Fetch the complete paginated historical index across all alphanumeric buckets",
    )
    ingest.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent bucket workers for --history; default: 4",
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

    ted = subparsers.add_parser(
        "ingest-ted-awards",
        help="Ingest TED contract-award notices for a publication-date window",
    )
    ted.add_argument("--db", required=True)
    ted.add_argument("--start-date", required=True)
    ted.add_argument("--end-date", required=True)
    ted.add_argument("--scope", choices=["ACTIVE", "ALL", "LATEST"], default="ALL")
    ted.add_argument("--page-size", type=int, default=250)
    ted.add_argument(
        "--only-latest-versions",
        action="store_true",
        help="Ask TED to return only the latest version of each notice",
    )

    ted_summary_parser = subparsers.add_parser(
        "summarize-ted",
        help="Emit TED award/winner coverage without assuming multi-winner alignment",
    )
    ted_summary_parser.add_argument("--db", required=True)

    cipo = subparsers.add_parser(
        "ingest-cipo-owner",
        help=(
            "Search the live CIPO database by current owner and optionally "
            "enrich a bounded subset with detail pages"
        ),
    )
    cipo.add_argument("--db", required=True)
    cipo.add_argument("--owner", required=True)
    cipo.add_argument("--detail-limit", type=int, default=10)
    cipo.add_argument("--detail-offset", type=int, default=0)
    cipo.add_argument("--detail-delay-seconds", type=float, default=0.2)

    cipo_summary_parser = subparsers.add_parser(
        "summarize-cipo",
        help="Emit CIPO owner-search and detail-enrichment coverage",
    )
    cipo_summary_parser.add_argument("--db", required=True)

    canadabuys = subparsers.add_parser(
        "ingest-canadabuys-awards",
        help="Ingest the current CanadaBuys fiscal-year award notice CSV",
    )
    canadabuys.add_argument("--db", required=True)
    canadabuys.add_argument("--source-url", default=CURRENT_AWARDS_URL)

    canadabuys_summary_parser = subparsers.add_parser(
        "summarize-canadabuys",
        help="Emit current CanadaBuys award coverage and EU-27 supplier evidence",
    )
    canadabuys_summary_parser.add_argument("--db", required=True)

    statcan = subparsers.add_parser(
        "ingest-statcan-trade",
        help=(
            "Ingest Statistics Canada Nova Scotia/Canada EU trade context "
            "from monthly major-market and annual full-EU tables"
        ),
    )
    statcan.add_argument("--db", required=True)
    statcan.add_argument(
        "--source",
        choices=["both", "monthly", "annual"],
        default="both",
    )

    statcan_summary_parser = subparsers.add_parser(
        "summarize-statcan-trade",
        help="Emit aggregate Nova Scotia EU trade context and year-over-year comparisons",
    )
    statcan_summary_parser.add_argument("--db", required=True)

    identity = subparsers.add_parser(
        "resolve-entry-identities",
        help=(
            "Resolve recent Investment Canada new-business outcomes to "
            "federal Canadian entry entities and certificate dates"
        ),
    )
    identity.add_argument("--db", required=True)
    identity.add_argument("--start-month", default="2019-01")
    identity.add_argument("--end-month", default="2025-12")
    identity.add_argument("--gold-limit", type=int, default=100)
    identity.add_argument("--detail-limit", type=int, default=140)
    identity.add_argument("--detail-delay-seconds", type=float, default=0.05)

    identity_summary = subparsers.add_parser(
        "summarize-entry-identities",
        help="Emit latest federal entry-entity gold cohort and timing coverage",
    )
    identity_summary.add_argument("--db", required=True)

    return parser


def _ingest_investment_canada(
    db_path: str,
    buckets: list[str],
    *,
    history: bool,
    workers: int,
) -> int:
    conn = connect(db_path)
    retrieved_at = datetime.now(timezone.utc).isoformat()

    if history:
        crawl = crawl_investment_canada_history(workers=workers)
        stored = replace_investment_canada_history(
            conn,
            crawl.records,
            crawl.page_snapshots,
            observed_at=retrieved_at,
        )
        print(
            json.dumps(
                {
                    "source": SOURCE_NAME,
                    "mode": "history",
                    "retrieved_at": retrieved_at,
                    "bucket_count": crawl.bucket_count,
                    "page_count": crawl.page_count,
                    "records_seen": crawl.appearances,
                    "duplicate_appearances": crawl.duplicate_appearances,
                    "unique_records": crawl.unique_records,
                    **stored,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

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
                "mode": "first-page",
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




def _ingest_canadabuys(
    db_path: str,
    *,
    source_url: str,
) -> int:
    retrieved_at = datetime.now(timezone.utc).isoformat()
    conn = connect(db_path)

    with tempfile.TemporaryDirectory(prefix="atlanticbridge-canadabuys-") as temp_dir:
        csv_path = Path(temp_dir) / "award-notices.csv"
        download = download_awards_csv(csv_path, source_url=source_url)
        result = ingest_awards(
            conn,
            iter_awards_csv(download.path, source_url=source_url),
            source_sha256=download.sha256,
            source_url=source_url,
            source_bytes=download.byte_count,
            observed_at=retrieved_at,
        )
        insert_source_snapshot(
            conn,
            source_name=CANADABUYS_SOURCE_NAME,
            source_url=source_url,
            source_bucket=CANADABUYS_SOURCE_BUCKET,
            retrieved_at=retrieved_at,
            sha256=download.sha256,
            record_count=int(result["records"]),
        )

    print(
        json.dumps(
            {
                "source": CANADABUYS_SOURCE_NAME,
                "source_bucket": CANADABUYS_SOURCE_BUCKET,
                "retrieved_at": retrieved_at,
                **result,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0



def _ingest_statcan(
    db_path: str,
    *,
    source: str,
) -> int:
    conn = connect(db_path)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    configs = []
    if source in {"both", "monthly"}:
        configs.append(STATCAN_MONTHLY_CONFIG)
    if source in {"both", "annual"}:
        configs.append(STATCAN_ANNUAL_CONFIG)

    results = []
    with tempfile.TemporaryDirectory(prefix="atlanticbridge-statcan-") as temp_dir:
        for config in configs:
            download = download_statcan_table(config, temp_dir)
            result = ingest_statcan_snapshot(
                conn,
                download,
                iter_statcan_records(download),
                observed_at=retrieved_at,
            )
            insert_source_snapshot(
                conn,
                source_name=config.source_name,
                source_url=download.download_url,
                source_bucket=config.source_bucket,
                retrieved_at=retrieved_at,
                sha256=download.archive_sha256,
                record_count=int(result["filtered_records"]),
            )
            results.append(result)

    print(
        json.dumps(
            {
                "source": "statistics_canada_trade_context",
                "retrieved_at": retrieved_at,
                "tables": results,
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
            return _ingest_investment_canada(
                args.db,
                args.buckets,
                history=args.history,
                workers=args.workers,
            )
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

    if args.command == "ingest-ted-awards":
        try:
            conn = connect(args.db)
            result = search_awards(
                args.start_date,
                args.end_date,
                page_size=args.page_size,
                scope=args.scope,
                only_latest_versions=args.only_latest_versions,
            )
            stored = ingest_ted_search_result(conn, result)
            print(
                json.dumps(
                    {
                        "source": "ted_search_api_v3",
                        "start_date": args.start_date,
                        "end_date": args.end_date,
                        "scope": args.scope,
                        **stored,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        except Exception as exc:
            print(f"TED award ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-ted":
        conn = connect(args.db)
        print(json.dumps(ted_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "ingest-cipo-owner":
        try:
            conn = connect(args.db)
            result = run_owner_search(
                conn,
                owner_name=args.owner,
                detail_limit=args.detail_limit,
                detail_offset=args.detail_offset,
                detail_delay_seconds=args.detail_delay_seconds,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            print(f"CIPO owner ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-cipo":
        conn = connect(args.db)
        print(json.dumps(cipo_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "ingest-canadabuys-awards":
        try:
            return _ingest_canadabuys(args.db, source_url=args.source_url)
        except Exception as exc:
            print(f"CanadaBuys award ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-canadabuys":
        conn = connect(args.db)
        print(json.dumps(canadabuys_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "ingest-statcan-trade":
        try:
            return _ingest_statcan(args.db, source=args.source)
        except Exception as exc:
            print(f"Statistics Canada trade ingestion failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-statcan-trade":
        conn = connect(args.db)
        print(json.dumps(statcan_trade_summary(conn), indent=2, sort_keys=True))
        return 0

    if args.command == "resolve-entry-identities":
        try:
            conn = connect(args.db)
            with tempfile.TemporaryDirectory(
                prefix="atlanticbridge-entry-identity-"
            ) as temp_dir:
                result = run_entry_identity_resolution(
                    conn,
                    workdir=temp_dir,
                    start_month=args.start_month,
                    end_month=args.end_month,
                    gold_limit=args.gold_limit,
                    detail_limit=args.detail_limit,
                    detail_delay_seconds=args.detail_delay_seconds,
                )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            print(f"Entry identity resolution failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "summarize-entry-identities":
        conn = connect(args.db)
        print(json.dumps(entry_identity_summary(conn), indent=2, sort_keys=True))
        return 0

    return 2
