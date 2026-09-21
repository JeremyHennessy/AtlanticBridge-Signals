from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import re

from atlanticbridge.sources import cipo_journal
from atlanticbridge.sources.cipo_journal import (
    JournalIssue,
    advertised_section,
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
        digits = case["application_number"]
        parts = []
        first = len(digits) % 3
        if first:
            parts.append(digits[:first])
        for offset in range(first, len(digits), 3):
            parts.append(digits[offset : offset + 3])
        pattern = re.compile(
            r"[\\s,]*".join(re.escape(part) for part in parts)
        )
        match = pattern.search(text)
        if match is None:
            raise RuntimeError(
                f"application number not found in PDF text: {digits}"
            )

        section = advertised_section(text)
        old_matches = list(cipo_journal._OLD_APPLICATION_START_RE.finditer(section))
        modern_matches = list(cipo_journal._MODERN_APPLICATION_START_RE.finditer(section))
        parser_mode, applications = extract_advertised_application_blocks(text)
        target = next(
            (
                row
                for row in applications
                if row["application_number"] == digits
            ),
            None,
        )
        left = max(0, match.start() - 5000)
        right = min(len(text), match.end() + 12000)
        output.append(
            {
                "application_number": digits,
                "publication_date": case["publication_date"].isoformat(),
                "match_start": match.start(),
                "parser_mode": parser_mode,
                "parsed_target": target,
                "old_match_count": len(old_matches),
                "modern_match_count": len(modern_matches),
                "first_old_match_start": (
                    old_matches[0].start() if old_matches else None
                ),
                "first_modern_match_start": (
                    modern_matches[0].start() if modern_matches else None
                ),
                "nearby_parsed_applications": [
                    row["application_number"]
                    for row in applications
                    if abs(int(row["application_number"]) - int(digits)) < 300
                ][:50],
                "raw_context": text[left:right],
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
