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
    starts = [
        folded.find("advertised applications"),
        folded.find("applications advertised"),
    ]
    starts = [value for value in starts if value >= 0]
    if not starts:
        return text
    start = min(starts)

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
        applicant_match = re.search(
            r"(?is)\bApplicant\b\s*(.{1,800}?)(?="
            r"\b(?:Representative|Agent|Trademark|Trade-mark|Goods|Services|Claims)\b"
            r"|\n\s*Application\s+Number\b|$)",
            after,
        )
        applicant_text = (
            " ".join(applicant_match.group(1).split())
            if applicant_match
            else expected_applicant
        )
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
