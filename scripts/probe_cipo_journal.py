from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path

from atlanticbridge.sources.cipo_journal import (
    inventory,
    inventory_sha256,
    recover_known_case,
)


BACKTEST_END_DATE = date(2023, 5, 31)


def load_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove the CIPO Journal archive inventory and known historical cases."
    )
    parser.add_argument(
        "--identities",
        default="reviews/backtests/2026-09-21-cipo-journal-identities.json",
    )
    parser.add_argument(
        "--output",
        default="control-output/cipo-journal-known-case-proof.json",
    )
    args = parser.parse_args()

    identity_payload = load_json(args.identities)
    cases = identity_payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("CIPO Journal identities require cases list")

    issues, years = inventory(
        start_year=2000,
        end_date=BACKTEST_END_DATE,
    )
    by_date = {issue.publication_date.isoformat(): issue for issue in issues}

    required_dates = {
        str(case["journal_date"])
        for case in cases
        if isinstance(case, dict) and case.get("required") is True
    }
    missing_dates = sorted(required_dates - set(by_date))
    if missing_dates:
        raise ValueError(
            f"required Journal dates absent from official archive inventory: {missing_dates}"
        )

    recovered = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CIPO Journal identity cases must be objects")
        issue_date = str(case["journal_date"])
        issue = by_date.get(issue_date)
        if issue is None:
            if case.get("required") is True:
                raise ValueError(f"required Journal issue missing: {issue_date}")
            continue

        result = recover_known_case(
            issue,
            application_number=str(case["application_number"]),
            expected_applicant=str(case["expected_applicant"]),
        )
        recovered.append(
            {
                "case_id": case["case_id"],
                "entity_id": case["entity_id"],
                "required": bool(case.get("required")),
                "relation": case["relation"],
                "publication_date": result["publication_date"],
                "application_number": result["application_number"],
                "expected_applicant": result["expected_applicant"],
                "extracted_applicant": result["extracted_applicant"],
                "retrieval_method": result["retrieval_method"],
                "source_url": result["source_url"],
                "legal_name_history": case.get("legal_name_history"),
            }
        )

    recovered_by_id = {str(row["case_id"]): row for row in recovered}
    required_ids = {
        str(case["case_id"])
        for case in cases
        if isinstance(case, dict) and case.get("required") is True
    }
    missing_ids = sorted(required_ids - set(recovered_by_id))
    if missing_ids:
        raise ValueError(f"required known cases not recovered: {missing_ids}")

    methods = Counter(str(row["retrieval_method"]) for row in recovered)
    payload = {
        "schema_version": 1,
        "design": "CIPO_JOURNAL_ARCHIVE_KNOWN_CASE_PROOF",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_boundary": (
            "Authoritative CIPO Trademarks Journal publication archive. This probe "
            "establishes archive inventory and known-case recoverability only; "
            "it does not yet authorize absence inference."
        ),
        "inventory": {
            "start_date": issues[0].publication_date.isoformat(),
            "end_date": issues[-1].publication_date.isoformat(),
            "requested_end_date": BACKTEST_END_DATE.isoformat(),
            "year_count": len(years),
            "issue_count": len(issues),
            "canonical_issue_sha256": inventory_sha256(issues),
            "years": years,
        },
        "summary": {
            "required_case_count": len(required_ids),
            "required_cases_recovered": sum(
                case_id in recovered_by_id for case_id in required_ids
            ),
            "total_case_count": len(cases),
            "total_cases_recovered": len(recovered),
            "retrieval_methods": dict(sorted(methods.items())),
            "absence_inference_allowed": False,
        },
        "known_cases": recovered,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["inventory"], indent=2, sort_keys=True))
    for row in recovered:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
