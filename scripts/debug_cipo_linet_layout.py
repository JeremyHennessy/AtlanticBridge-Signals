from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from atlanticbridge.sources.cipo_journal import (
    JournalIssue,
    extract_advertised_application_blocks,
    pdf_issue_text,
)


CASES = [
    {
        "application_number": "1336563",
        "publication_date": date(2008, 2, 13),
        "pdf_url": (
            "https://cipo.ic.gc.ca/opic-cipo/tmj/eng/"
            "13fevrier2008.pdf?year=2008&edition=02-13"
        ),
    },
    {
        "application_number": "1336566",
        "publication_date": date(2008, 2, 20),
        "pdf_url": (
            "https://cipo.ic.gc.ca/opic-cipo/tmj/eng/"
            "20fevrier2008.pdf?year=2008&edition=02-20"
        ),
    },
]


def html_url(published: date) -> str:
    return (
        "https://cipo.ic.gc.ca/opic-cipo/tmj/eng/view.html"
        f"?edition={published:%m-%d}&file=Journal_en.html&year={published.year}"
    )


def main() -> int:
    output = []
    for case in CASES:
        issue = JournalIssue(
            publication_date=case["publication_date"],
            pdf_url=case["pdf_url"],
            html_url=html_url(case["publication_date"]),
        )
        text = pdf_issue_text(issue)
        parser_mode, applications = extract_advertised_application_blocks(text)
        target = next(
            (
                row
                for row in applications
                if row["application_number"] == case["application_number"]
            ),
            None,
        )
        if target is None:
            raise RuntimeError(
                f"application not parsed: {case['application_number']}"
            )
        output.append(
            {
                "application_number": case["application_number"],
                "publication_date": case["publication_date"].isoformat(),
                "parser_mode": parser_mode,
                "parsed_applicant": target["applicant"],
                "raw_block": target["raw_block"][:12000],
            }
        )

    path = Path("debug-output/linet-layout.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
