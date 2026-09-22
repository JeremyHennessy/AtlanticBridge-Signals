from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from atlanticbridge.sources.cipo_journal import (
    inventory,
    inventory_sha256,
    issue_text_for_scan,
    pdf_issue_text,
    scan_issue_aliases,
)


ACCEPTED_END_DATE = date(2023, 5, 31)
EXTENDED_END_DATE = date(2024, 5, 31)
ACCEPTED_PREFIX_ISSUE_COUNT = 1221
ACCEPTED_PREFIX_SHA256 = (
    "8a89eccf0c368e82de4fcd62bea62481930210b7ddf2c182b18e7f45e7521a2d"
)


def scan_issue_without_aliases(issue):
    fallback_reason = None
    method, source_url, text = issue_text_for_scan(issue)
    try:
        scanned = scan_issue_aliases(text, aliases=[])
    except Exception as exc:
        if method != "OFFICIAL_JOURNAL_HTML":
            raise
        fallback_reason = (
            f"HTML_SCAN_FAILED:{type(exc).__name__}:{str(exc)[:240]}"
        )
        method = "OFFICIAL_JOURNAL_PDF_PDFTOTEXT"
        source_url = issue.pdf_url
        text = pdf_issue_text(issue)
        scanned = scan_issue_aliases(text, aliases=[])

    return {
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
        "complete_for_source_parse": bool(
            scanned["complete_for_exact_alias_absence"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prove the official CIPO Journal archive and Advertised "
            "Applications parser from 2023-06-01 through 2024-05-31 "
            "without enabling identity-specific absence inference."
        )
    )
    parser.add_argument(
        "--output",
        default="journal-extension-output/cipo-journal-extension-proof.json",
    )
    args = parser.parse_args()

    issues, years = inventory(
        start_year=2000,
        end_date=EXTENDED_END_DATE,
    )
    prefix = [
        issue
        for issue in issues
        if issue.publication_date <= ACCEPTED_END_DATE
    ]
    extension = [
        issue
        for issue in issues
        if ACCEPTED_END_DATE < issue.publication_date <= EXTENDED_END_DATE
    ]

    prefix_hash = inventory_sha256(prefix)
    full_hash = inventory_sha256(issues)

    failures = []
    issue_proof = []
    for issue in extension:
        try:
            issue_proof.append(scan_issue_without_aliases(issue))
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

    methods = Counter(
        str(row["retrieval_method"])
        for row in issue_proof
    )
    parser_modes = Counter(
        str(row["parser_mode"])
        for row in issue_proof
    )

    audit_material = "\n".join(
        "\x1f".join(
            [
                str(row["publication_date"]),
                str(row["retrieval_method"]),
                str(row["parser_mode"]),
                str(row["application_count"]),
                str(row["advertised_section_sha256"]),
                str(row["applications_canonical_sha256"]),
            ]
        )
        for row in issue_proof
    ) + ("\n" if issue_proof else "")

    structural_errors = []
    if len(prefix) != ACCEPTED_PREFIX_ISSUE_COUNT:
        structural_errors.append(
            "accepted prefix issue count changed: "
            f"{len(prefix)} != {ACCEPTED_PREFIX_ISSUE_COUNT}"
        )
    if prefix_hash != ACCEPTED_PREFIX_SHA256:
        structural_errors.append(
            "accepted prefix inventory hash changed: "
            f"{prefix_hash} != {ACCEPTED_PREFIX_SHA256}"
        )
    if not extension:
        structural_errors.append("extension inventory is empty")
    if extension and extension[0].publication_date <= ACCEPTED_END_DATE:
        structural_errors.append("extension overlaps accepted prefix")
    if extension and extension[-1].publication_date > EXTENDED_END_DATE:
        structural_errors.append("extension exceeds requested end date")
    if len(issue_proof) + len(failures) != len(extension):
        structural_errors.append(
            "extension scan accounting does not equal inventory"
        )
    incomplete = [
        row
        for row in issue_proof
        if row["complete_for_source_parse"] is not True
    ]
    if incomplete:
        structural_errors.append(
            f"{len(incomplete)} extension issues were not completely parsed"
        )

    gate_passed = not structural_errors and not failures

    payload = {
        "schema_version": 1,
        "design": "CIPO_JOURNAL_SOURCE_EXTENSION_PARSE_PROOF",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_boundary": (
            "Source completeness and Advertised Applications parser proof "
            "only. No reviewed entity aliases are evaluated, so this proof "
            "does not authorize identity-specific absence inference."
        ),
        "accepted_prefix": {
            "start_date": prefix[0].publication_date.isoformat(),
            "end_date": ACCEPTED_END_DATE.isoformat(),
            "issue_count": len(prefix),
            "canonical_issue_sha256": prefix_hash,
            "expected_issue_count": ACCEPTED_PREFIX_ISSUE_COUNT,
            "expected_canonical_issue_sha256": ACCEPTED_PREFIX_SHA256,
        },
        "extension": {
            "start_exclusive": ACCEPTED_END_DATE.isoformat(),
            "requested_end_date": EXTENDED_END_DATE.isoformat(),
            "first_issue": (
                extension[0].publication_date.isoformat()
                if extension else None
            ),
            "last_issue": (
                extension[-1].publication_date.isoformat()
                if extension else None
            ),
            "issue_count": len(extension),
            "application_rows_scanned": sum(
                int(row["application_count"])
                for row in issue_proof
            ),
            "retrieval_methods": dict(sorted(methods.items())),
            "parser_modes": dict(sorted(parser_modes.items())),
            "issue_audit_canonical_sha256": hashlib.sha256(
                audit_material.encode("utf-8")
            ).hexdigest(),
        },
        "extended_inventory": {
            "start_date": issues[0].publication_date.isoformat(),
            "end_date": issues[-1].publication_date.isoformat(),
            "year_count": len(years),
            "issue_count": len(issues),
            "canonical_issue_sha256": full_hash,
        },
        "gate": {
            "passed": gate_passed,
            "structural_errors": structural_errors,
            "issue_failures": failures,
        },
        "identity_absence_inference_allowed": False,
        "issue_audit": issue_proof,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload["accepted_prefix"], indent=2, sort_keys=True))
    print(json.dumps(payload["extension"], indent=2, sort_keys=True))
    print(json.dumps(payload["gate"], indent=2, sort_keys=True))
    return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
