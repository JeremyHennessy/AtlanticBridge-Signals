from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ARCHIVE_URL = "https://cipo.ic.gc.ca/opic-cipo/tmj/eng/archive.html?year={year}"
HTML_URL = (
    "https://cipo.ic.gc.ca/opic-cipo/tmj/eng/view.html"
    "?edition={edition}&file=Journal_en.html&year={year}"
)
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(CIPO Journal historical completeness research; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)
_DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b")


@dataclass(frozen=True, slots=True)
class JournalIssue:
    publication_date: date
    pdf_url: str
    html_url: str

    @property
    def year(self) -> int:
        return self.publication_date.year

    @property
    def edition(self) -> str:
        return self.publication_date.strftime("%m-%d")

    @property
    def canonical_key(self) -> str:
        return f"{self.publication_date.isoformat()}|{self.pdf_url}"


def normalize_name(value: str) -> str:
    return "".join(char for char in (value or "").casefold() if char.isalnum())


def normalize_application_number(value: str) -> str:
    return "".join(char for char in (value or "") if char.isdigit())


def fetch(
    url: str,
    *,
    binary: bool = False,
    attempts: int = 4,
    timeout: int = 120,
) -> bytes | str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/pdf,*/*;q=0.8"
                if binary
                else "text/html,application/xhtml+xml,*/*;q=0.8"
            ),
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
            if binary:
                return payload
            return payload.decode("utf-8", errors="replace")
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == attempts:
                raise
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt == attempts:
                raise
        time.sleep(2 ** (attempt - 1))
    assert last_error is not None
    raise last_error


def parse_archive(html: str, *, year: int, source_url: str) -> list[JournalIssue]:
    soup = BeautifulSoup(html, "html.parser")
    issues: list[JournalIssue] = []
    seen_dates: set[date] = set()

    for row in soup.find_all("tr"):
        text = " ".join(row.stripped_strings)
        match = _DATE_RE.search(text)
        if not match:
            continue
        published = date.fromisoformat(match.group(0))
        if published.year != year or published in seen_dates:
            continue

        links = []
        for anchor in row.find_all("a", href=True):
            href = str(anchor["href"])
            if ".pdf" not in href.casefold():
                continue
            links.append(urljoin(source_url, href))
        if not links:
            continue

        english = next(
            (
                link
                for link in links
                if "/eng/" in link.casefold()
                or link.casefold().endswith("_en.pdf")
                or "_en.pdf?" in link.casefold()
            ),
            links[0],
        )
        issues.append(
            JournalIssue(
                publication_date=published,
                pdf_url=english,
                html_url=HTML_URL.format(
                    edition=published.strftime("%m-%d"),
                    year=published.year,
                ),
            )
        )
        seen_dates.add(published)

    # Older archive pages (notably 2000-era pages) do not use table
    # rows. Fall back to the publication-date text node followed by the next
    # PDF anchor. The archive order itself supplies the association; dates are
    # never inferred from a weekly calendar.
    for text_node in soup.find_all(string=True):
        raw = str(text_node).strip()
        match = _DATE_RE.fullmatch(raw)
        if not match:
            continue
        published = date.fromisoformat(match.group(0))
        if published.year != year or published in seen_dates:
            continue

        parent = text_node.parent
        if parent is None:
            continue
        anchor = parent.find_next(
            "a",
            href=lambda value: bool(
                value and ".pdf" in str(value).casefold()
            ),
        )
        if anchor is None:
            continue
        href = str(anchor.get("href") or "")
        if not href:
            continue
        pdf_url = urljoin(source_url, href)
        issues.append(
            JournalIssue(
                publication_date=published,
                pdf_url=pdf_url,
                html_url=HTML_URL.format(
                    edition=published.strftime("%m-%d"),
                    year=published.year,
                ),
            )
        )
        seen_dates.add(published)

    issues.sort(key=lambda issue: issue.publication_date)
    if not issues:
        raise ValueError(f"no CIPO Journal issues parsed for {year}")
    return issues


def inventory(
    *,
    start_year: int = 2000,
    end_date: date = date(2023, 5, 31),
) -> tuple[list[JournalIssue], list[dict[str, object]]]:
    issues: list[JournalIssue] = []
    years: list[dict[str, object]] = []
    for year in range(start_year, end_date.year + 1):
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

    issues.sort(key=lambda issue: issue.publication_date)
    dates = [issue.publication_date for issue in issues]
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate Journal publication dates in inventory")
    if dates[0] != date(2000, 1, 5):
        raise ValueError(f"unexpected first Journal date: {dates[0]}")
    if dates[-1] > end_date:
        raise ValueError("Journal inventory exceeded requested end date")
    return issues, years


def inventory_sha256(issues: list[JournalIssue]) -> str:
    material = "\n".join(issue.canonical_key for issue in issues) + "\n"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _application_pattern(application_number: str) -> re.Pattern[str]:
    digits = normalize_application_number(application_number)
    if not digits:
        raise ValueError("application number is empty")
    parts = []
    first = len(digits) % 3
    if first:
        parts.append(digits[:first])
    for offset in range(first, len(digits), 3):
        parts.append(digits[offset : offset + 3])
    return re.compile(r"[\s,]*".join(re.escape(part) for part in parts))


def _advertised_section(text: str) -> str:
    folded = text.casefold()
    starts: list[int] = []
    for label in ("advertised applications", "applications advertised"):
        offset = 0
        while True:
            value = folded.find(label, offset)
            if value < 0:
                break
            starts.append(value)
            offset = value + len(label)
    if not starts:
        return text

    # Modern HTML Journals repeat this label in the table of contents and at
    # the actual application section. The last occurrence is the section
    # heading; starting at the first would truncate at the next TOC item.
    start = max(starts)

    end_candidates = []
    for label in (
        "applications to extend",
        "registered trademarks",
        "registration of trademarks",
        "amendments to register",
        "public notices under section 9",
    ):
        pos = folded.find(label, start + 30)
        if pos > start:
            end_candidates.append(pos)
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


_OLD_APPLICATION_START_RE = re.compile(
    r"(?m)^\\s*(\\d{1,3}(?:,\\d{3}){1,2})\\.\\s+"
    r"(\\d{4}/\\d{2}/\\d{2})\\.\\s+"
)
_MODERN_APPLICATION_START_RE = re.compile(
    r"(?i)Application\\s+Number\\s+([\\d,\\s]+)"
)


def advertised_section(text: str) -> str:
    old_start = _OLD_APPLICATION_START_RE.search(text)
    if old_start:
        end_candidates = []
        for pattern in (
            r"(?im)^\\s*Enregistrements\\s*/?\\s*Registrations\\s*$",
            r"(?im)^\\s*Registrations\\s*$",
            r"(?im)^\\s*Registrations Amended\\s*$",
            r"(?im)^\\s*Enregistrements modifiés\\s*$",
        ):
            match = re.search(pattern, text[old_start.start() :])
            if match:
                end_candidates.append(old_start.start() + match.start())
        end = min(end_candidates) if end_candidates else len(text)
        return text[old_start.start() : end]

    folded = text.casefold()
    if not any(
        label in folded
        for label in ("advertised applications", "applications advertised")
    ):
        raise ValueError("Journal Advertised applications section heading not found")

    section = _advertised_section(text)
    if section == text:
        raise ValueError("Journal Advertised applications section was not isolated")
    return section


def _modern_applicant_text(block: str) -> str:
    lines = [line.strip() for line in block.splitlines()]
    for index, line in enumerate(lines):
        if line.casefold() != "applicant":
            continue
        applicant_lines = []
        for candidate in lines[index + 1 :]:
            if not candidate:
                continue
            folded = candidate.casefold()
            if folded in {
                "representative for service",
                "agent",
                "trademark",
                "trade-mark",
                "goods",
                "services",
                "claims",
            }:
                break
            if folded.startswith("application number"):
                break
            applicant_lines.append(candidate)
        return " ".join(applicant_lines)
    return ""


def _old_applicant_text(block: str, *, prefix_end: int) -> str:
    tail = block[prefix_end:]
    end = len(tail)
    for marker in (
        "Representative for Service",
        "Représentant pour Signification",
        "WARES:",
        "MARCHANDISES:",
        "SERVICES:",
        "TRADE-MARK:",
        "MARQUE DE COMMERCE:",
    ):
        value = tail.find(marker)
        if value >= 0:
            end = min(end, value)
    return " ".join(tail[:end].split())


def extract_advertised_application_blocks(
    text: str,
) -> tuple[str, list[dict[str, str]]]:
    section = advertised_section(text)

    modern = list(_MODERN_APPLICATION_START_RE.finditer(section))
    if modern:
        rows = []
        for index, match in enumerate(modern):
            end = modern[index + 1].start() if index + 1 < len(modern) else len(section)
            block = section[match.start() : end]
            application = normalize_application_number(match.group(1))
            applicant = _modern_applicant_text(block)
            rows.append(
                {
                    "application_number": application,
                    "applicant": applicant,
                    "raw_block": block,
                }
            )
        return "MODERN_APPLICATION_NUMBER_APPLICANT", rows

    old = list(_OLD_APPLICATION_START_RE.finditer(section))
    if old:
        rows = []
        for index, match in enumerate(old):
            end = old[index + 1].start() if index + 1 < len(old) else len(section)
            block = section[match.start() : end]
            application = normalize_application_number(match.group(1))
            applicant = _old_applicant_text(
                block,
                prefix_end=match.end() - match.start(),
            )
            rows.append(
                {
                    "application_number": application,
                    "applicant": applicant,
                    "raw_block": block,
                }
            )
        return "LEGACY_NUMBER_DATE_APPLICANT", rows

    raise ValueError("Journal Advertised applications section format not recognized")


def scan_issue_aliases(
    text: str,
    *,
    aliases: list[dict[str, str]],
) -> dict[str, object]:
    parser_mode, applications = extract_advertised_application_blocks(text)
    section = advertised_section(text)
    normalized_section = normalize_name(section)

    matches: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    occurrence_aliases: set[str] = set()

    for alias in aliases:
        entity_id = str(alias["entity_id"])
        alias_value = str(alias["alias"])
        normalized = normalize_name(alias_value)
        if not normalized or normalized not in normalized_section:
            continue
        occurrence_aliases.add(normalized)

        applicant_matches = []
        for application in applications:
            applicant = str(application["applicant"])
            applicant_normalized = normalize_name(applicant)
            if applicant_normalized.startswith(normalized):
                applicant_matches.append(
                    {
                        "entity_id": entity_id,
                        "alias": alias_value,
                        "alias_kind": str(alias.get("alias_kind") or ""),
                        "application_number": str(application["application_number"]),
                        "applicant": applicant,
                    }
                )

        if applicant_matches:
            matches.extend(applicant_matches)
        else:
            unresolved.append(
                {
                    "entity_id": entity_id,
                    "alias": alias_value,
                    "alias_kind": str(alias.get("alias_kind") or ""),
                    "reason": "ALIAS_OCCURS_IN_ADVERTISED_SECTION_BUT_NOT_VERIFIED_AS_APPLICANT",
                }
            )

    dedup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in matches:
        key = (
            row["entity_id"],
            row["application_number"],
            normalize_name(row["applicant"]),
        )
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = row
        elif row["alias_kind"] == "HISTORICAL_LEGAL_NAME":
            dedup[key] = row

    application_material = "\n".join(
        "\x1f".join(
            [
                str(row["application_number"]),
                normalize_name(str(row["applicant"])),
            ]
        )
        for row in applications
    ) + "\n"

    return {
        "parser_mode": parser_mode,
        "application_count": len(applications),
        "advertised_section_sha256": hashlib.sha256(
            section.encode("utf-8")
        ).hexdigest(),
        "applications_canonical_sha256": hashlib.sha256(
            application_material.encode("utf-8")
        ).hexdigest(),
        "alias_occurrence_count": len(occurrence_aliases),
        "matches": sorted(
            dedup.values(),
            key=lambda row: (
                row["entity_id"],
                row["application_number"],
                row["alias"],
            ),
        ),
        "unresolved_alias_occurrences": unresolved,
        "complete_for_exact_alias_absence": not unresolved,
    }


def issue_text_for_scan(
    issue: JournalIssue,
) -> tuple[str, str, str]:
    if issue.year >= 2013:
        html = html_issue_text(issue)
        if html:
            return "OFFICIAL_JOURNAL_HTML", issue.html_url, html

    return (
        "OFFICIAL_JOURNAL_PDF_PDFTOTEXT",
        issue.pdf_url,
        pdf_issue_text(issue),
    )


def locate_known_application(
    text: str,
    *,
    application_number: str,
    expected_applicant: str,
) -> dict[str, object] | None:
    section = _advertised_section(text)
    pattern = _application_pattern(application_number)
    expected = normalize_name(expected_applicant)

    for match in pattern.finditer(section):
        left = max(0, match.start() - 800)
        right = min(len(section), match.end() + 5000)
        window = section[left:right]
        if expected not in normalize_name(window):
            continue

        after = section[match.end() : right]
        applicant_text = expected_applicant
        lines = [line.strip() for line in after.splitlines()]
        for index, line in enumerate(lines):
            if line.casefold() != "applicant":
                continue
            applicant_lines = []
            for candidate in lines[index + 1 :]:
                if not candidate:
                    continue
                if candidate.casefold() in {
                    "representative for service",
                    "agent",
                    "trademark",
                    "trade-mark",
                    "goods",
                    "services",
                    "claims",
                }:
                    break
                applicant_lines.append(candidate)
                if expected in normalize_name(" ".join(applicant_lines)):
                    break
            if applicant_lines:
                applicant_text = " ".join(applicant_lines)
                break
        return {
            "application_number": normalize_application_number(application_number),
            "expected_applicant": expected_applicant,
            "extracted_applicant": applicant_text,
            "exact_expected_name_in_application_window": True,
        }
    return None


def html_issue_text(issue: JournalIssue) -> str | None:
    try:
        html = str(fetch(issue.html_url, attempts=2, timeout=90))
    except (HTTPError, URLError, TimeoutError):
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    if len(text) < 5_000:
        return None
    return text


def pdf_issue_text(issue: JournalIssue) -> str:
    payload = fetch(issue.pdf_url, binary=True, attempts=4, timeout=180)
    assert isinstance(payload, bytes)
    if not payload.startswith(b"%PDF"):
        raise ValueError(f"Journal issue is not a PDF: {issue.pdf_url}")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "journal.pdf"
        path.write_bytes(payload)
        process = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        text = process.stdout
    if len(text) < 5_000:
        raise ValueError(f"extracted Journal text unexpectedly small: {issue.pdf_url}")
    return text


def recover_known_case(
    issue: JournalIssue,
    *,
    application_number: str,
    expected_applicant: str,
) -> dict[str, object]:
    html = html_issue_text(issue)
    if html:
        found = locate_known_application(
            html,
            application_number=application_number,
            expected_applicant=expected_applicant,
        )
        if found:
            return {
                **found,
                "publication_date": issue.publication_date.isoformat(),
                "retrieval_method": "OFFICIAL_JOURNAL_HTML",
                "source_url": issue.html_url,
            }

    pdf_text = pdf_issue_text(issue)
    found = locate_known_application(
        pdf_text,
        application_number=application_number,
        expected_applicant=expected_applicant,
    )
    if not found:
        raise ValueError(
            "known Journal application not recovered: "
            f"{application_number} {expected_applicant} "
            f"{issue.publication_date.isoformat()}"
        )
    return {
        **found,
        "publication_date": issue.publication_date.isoformat(),
        "retrieval_method": "OFFICIAL_JOURNAL_PDF_PDFTOTEXT",
        "source_url": issue.pdf_url,
    }
