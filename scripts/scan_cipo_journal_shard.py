from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from atlanticbridge.sources.cipo_journal import (
    ARCHIVE_URL,
    fetch,
    issue_text_for_scan,
    normalize_name,
    parse_archive,
    pdf_issue_text,
    scan_issue_aliases,
)


BACKTEST_END_DATE = date(2023, 5, 31)


def load_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_alias_contract(
    *,
    entities_payload: dict[str, object],
    journal_identity_payload: dict[str, object],
) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("backtest entities payload requires entities list")

    by_entity: dict[str, dict[str, object]] = {}
    alias_rows: dict[tuple[str, str], dict[str, str]] = {}

    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity rows must be objects")
        entity_id = str(entity["entity_id"])
        by_entity[entity_id] = entity
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks exact_aliases: {entity_id}")

        for alias in aliases:
            alias_text = str(alias).strip()
            normalized = normalize_name(alias_text)
            if not normalized:
                continue
            alias_rows[(entity_id, normalized)] = {
                "entity_id": entity_id,
                "alias": alias_text,
                "alias_kind": "CURRENT_REVIEWED_ALIAS",
                "provenance": "BACKTEST_ENTITY_EXACT_ALIAS",
            }

    cases = journal_identity_payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("CIPO Journal identity payload requires cases")

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Journal identity cases must be objects")
        entity_id = str(case["entity_id"])
        if entity_id not in by_entity:
            raise ValueError(f"Journal identity case references unknown entity: {entity_id}")

        relation = str(case.get("relation") or "")
        accepted = case.get("accepted_applicant_aliases") or []
        if not isinstance(accepted, list):
            raise ValueError("accepted_applicant_aliases must be a list")

        alias_kind = (
            "HISTORICAL_LEGAL_NAME"
            if relation == "SOURCE_BACKED_LEGAL_NAME_PREDECESSOR_SAME_COMPANY"
            else "JOURNAL_REVIEWED_ALIAS"
        )
        for alias in accepted:
            alias_text = str(alias).strip()
            normalized = normalize_name(alias_text)
            if not normalized:
                continue
            existing = alias_rows.get((entity_id, normalized))
            row = {
                "entity_id": entity_id,
                "alias": alias_text,
                "alias_kind": alias_kind,
                "provenance": f"JOURNAL_IDENTITY_CASE:{case['case_id']}",
            }
            if (
                existing is None
                or alias_kind == "HISTORICAL_LEGAL_NAME"
            ):
                alias_rows[(entity_id, normalized)] = row

        if alias_kind == "HISTORICAL_LEGAL_NAME":
            expected = str(case.get("expected_applicant") or "").strip()
            normalized = normalize_name(expected)
            if expected and normalized:
                alias_rows[(entity_id, normalized)] = {
                    "entity_id": entity_id,
                    "alias": expected,
                    "alias_kind": "HISTORICAL_LEGAL_NAME",
                    "provenance": f"JOURNAL_IDENTITY_CASE:{case['case_id']}",
                }

    aliases = sorted(
        alias_rows.values(),
        key=lambda row: (
            row["entity_id"],
            normalize_name(row["alias"]),
            row["alias_kind"],
        ),
    )
    return aliases, by_entity


def inventory_range(
    *,
    start_year: int,
    end_year: int,
    end_date: date,
):
    if end_year < start_year:
        raise ValueError("end_year must be >= start_year")
    issues = []
    years = []
    for year in range(start_year, end_year + 1):
        if year > end_date.year:
            break
        source_url = ARCHIVE_URL.format(year=year)
        page = str(fetch(source_url))
        parsed = [
            issue
            for issue in parse_archive(page, year=year, source_url=source_url)
            if issue.publication_date <= end_date
        ]
        if not parsed:
            raise ValueError(f"no in-scope CIPO Journal issues for {year}")
        issues.extend(parsed)
        years.append(
            {
                "year": year,
                "archive_url": source_url,
                "issue_count": len(parsed),
                "first_issue": parsed[0].publication_date.isoformat(),
                "last_issue": parsed[-1].publication_date.isoformat(),
            }
        )
    issues.sort(key=lambda item: item.publication_date)
    return issues, years


def scan_one_issue(issue, aliases):
    fallback_reason = None
    method, source_url, text = issue_text_for_scan(issue)
    try:
        scanned = scan_issue_aliases(text, aliases=aliases)
    except Exception as exc:
        if method != "OFFICIAL_JOURNAL_HTML":
            raise
        fallback_reason = (
            f"HTML_SCAN_FAILED:{type(exc).__name__}:{str(exc)[:240]}"
        )
        method = "OFFICIAL_JOURNAL_PDF_PDFTOTEXT"
        source_url = issue.pdf_url
        text = pdf_issue_text(issue)
        scanned = scan_issue_aliases(text, aliases=aliases)

    issue_proof = {
        "publication_date": issue.publication_date.isoformat(),
        "pdf_url": issue.pdf_url,
        "html_url": issue.html_url,
        "retrieval_method": method,
        "source_url": source_url,
        "fallback_reason": fallback_reason,
        "parser_mode": scanned["parser_mode"],
        "application_count": scanned["application_count"],
        "advertised_section_sha256": scanned["advertised_section_sha256"],
        "applications_canonical_sha256":
            scanned["applications_canonical_sha256"],
        "alias_occurrence_count": scanned["alias_occurrence_count"],
        "exact_match_count": len(scanned["matches"]),
        "unresolved_alias_occurrence_count": len(
            scanned["unresolved_alias_occurrences"]
        ),
        "complete_for_exact_alias_absence":
            scanned["complete_for_exact_alias_absence"],
    }

    records = []
    for row in scanned["matches"]:
        material = "\x1f".join(
            [
                str(row["entity_id"]),
                str(row["application_number"]),
                issue.publication_date.isoformat(),
                normalize_name(str(row["applicant"])),
            ]
        )
        records.append(
            {
                "evidence_id": hashlib.sha256(
                    material.encode("utf-8")
                ).hexdigest(),
                "entity_id": row["entity_id"],
                "signal_family": "CIPO_CANADIAN_TRADEMARK",
                "application_number": row["application_number"],
                "matched_alias": row["alias"],
                "alias_kind": row["alias_kind"],
                "matched_applicant_text": str(row["applicant"])[:1000],
                "publicly_available_date":
                    issue.publication_date.isoformat(),
                "publicly_available_date_precision": "DAY",
                "publicly_available_date_basis":
                    "Official CIPO Trademarks Journal publication date; "
                    "exact reviewed applicant alias in the Advertised "
                    "Applications section.",
                "source_url": source_url,
                "match_method":
                    "OFFICIAL_JOURNAL_EXACT_REVIEWED_ALIAS_APPLICANT",
            }
        )

    unresolved = []
    for row in scanned["unresolved_alias_occurrences"]:
        unresolved.append(
            {
                **row,
                "publication_date": issue.publication_date.isoformat(),
                "source_url": source_url,
            }
        )
    return issue_proof, records, unresolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument(
        "--journal-identities",
        default="reviews/backtests/2026-09-21-cipo-journal-identities.json",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    entities_payload = load_json(args.entities)
    journal_identity_payload = load_json(args.journal_identities)
    aliases, entities_by_id = build_alias_contract(
        entities_payload=entities_payload,
        journal_identity_payload=journal_identity_payload,
    )

    issues, years = inventory_range(
        start_year=args.start_year,
        end_year=args.end_year,
        end_date=BACKTEST_END_DATE,
    )

    issue_proof = []
    records = []
    unresolved = []
    failures = []

    for issue in issues:
        try:
            proof, issue_records, issue_unresolved = scan_one_issue(
                issue,
                aliases,
            )
            issue_proof.append(proof)
            records.extend(issue_records)
            unresolved.extend(issue_unresolved)
        except Exception as exc:
            failures.append(
                {
                    "publication_date": issue.publication_date.isoformat(),
                    "pdf_url": issue.pdf_url,
                    "html_url": issue.html_url,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            )

    dedup_records: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in records:
        key = (
            str(row["entity_id"]),
            str(row["application_number"]),
            str(row["publicly_available_date"]),
        )
        existing = dedup_records.get(key)
        if existing is None:
            dedup_records[key] = row
        elif (
            row["alias_kind"] == "HISTORICAL_LEGAL_NAME"
            and existing["alias_kind"] != "HISTORICAL_LEGAL_NAME"
        ):
            dedup_records[key] = row

    records = sorted(
        dedup_records.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["application_number"]),
        ),
    )
    issue_proof.sort(key=lambda row: str(row["publication_date"]))
    unresolved.sort(
        key=lambda row: (
            str(row["publication_date"]),
            str(row["entity_id"]),
            str(row["alias"]),
        )
    )
    failures.sort(key=lambda row: str(row["publication_date"]))

    methods = Counter(
        str(row["retrieval_method"]) for row in issue_proof
    )
    parser_modes = Counter(
        str(row["parser_mode"]) for row in issue_proof
    )
    material = "\n".join(
        f"{issue.publication_date.isoformat()}|{issue.pdf_url}"
        for issue in issues
    ) + "\n"

    payload = {
        "schema_version": 1,
        "design": "CIPO_JOURNAL_FULL_SCAN_SHARD",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "shard": {
            "start_year": args.start_year,
            "end_year": args.end_year,
            "requested_end_date": BACKTEST_END_DATE.isoformat(),
        },
        "alias_contract": {
            "entity_count": len(entities_by_id),
            "alias_count": len(aliases),
            "aliases": aliases,
        },
        "inventory": {
            "issue_count": len(issues),
            "canonical_issue_sha256": hashlib.sha256(
                material.encode("utf-8")
            ).hexdigest(),
            "years": years,
        },
        "summary": {
            "issues_in_inventory": len(issues),
            "issues_scanned": len(issue_proof),
            "issue_failures": len(failures),
            "complete_issues": sum(
                row["complete_for_exact_alias_absence"] is True
                for row in issue_proof
            ),
            "application_rows_scanned": sum(
                int(row["application_count"]) for row in issue_proof
            ),
            "exact_match_records": len(records),
            "unresolved_alias_occurrences": len(unresolved),
            "retrieval_methods": dict(sorted(methods.items())),
            "parser_modes": dict(sorted(parser_modes.items())),
        },
        "issue_proof": issue_proof,
        "records": records,
        "unresolved_alias_occurrences": unresolved,
        "failures": failures,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    if failures:
        print(
            json.dumps(
                {"first_failures": failures[:20]},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    if unresolved:
        print(
            json.dumps(
                {"first_unresolved": unresolved[:20]},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
