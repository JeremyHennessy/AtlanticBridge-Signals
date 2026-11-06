"""Offline parser for NL's government assessment table. No HTTP or activation.

Only invented fixtures can be converted to review collections until the
conditional reuse terms have been reviewed and authorized.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from html.parser import HTMLParser
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

SOURCE = "nl_environmental_assessments"
INDEX_URL = "https://www.gov.nl.ca/eccc/env-assessment/projects-list/"
TERMS_URL = "https://www.gov.nl.ca/disclaimer/"
SYNTHETIC_FIXTURE_SHA256 = "d9ba5e58262bd8aa47b8fde21fef895715a4087c455baa4d925d46eb234b162f"
_SYNTHETIC_RECORDS_SHA256 = "76a7f45e7fbfe40d7aa61fa2a716f6217b8c025611a1c925f6d5dcded4cffaba"
RIGHTS_STATUS = "SYNTHETIC_ONLY_REAL_REUSE_NOT_AUTHORIZED"
RIGHTS_NOTE = (
    "NL permits use of government-owned information subject to an indemnity/"
    "hold-harmless condition. That condition has not been accepted for this "
    "integration. Third-party content is outside this pilot. Real-data reuse "
    "and activation remain blocked; this packet contains invented fixtures."
)
ATTRIBUTION = "Source structure: Government of Newfoundland and Labrador environmental assessments. Values in this pilot are invented."
LIMIT = (
    "An assessment registration or release does not prove construction, "
    "commissioning, completed investment, Canadian first entry or expansion intent. "
    "Active means active assessment, not an operating facility. No European "
    "ownership, corporate group, capacity, spending or location is inferred."
)
MAX_HTML_BYTES = 2_000_000
MAX_ROWS = 5_000
HEADERS = ("Reg. #", "Title/Proponent", "Date Registered", "Status", "Release Date")
STAGES = {
    "Active": ("ASSESSMENT_ACTIVE", "Active assessment; not operational status"),
    "Released": ("RELEASED_FROM_ASSESSMENT", "Released from environmental assessment; not construction completion"),
    "Withdrawn": ("ASSESSMENT_WITHDRAWN", "Assessment registration withdrawn; not a company closure"),
    "Expired": ("ASSESSMENT_EXPIRED", "Assessment expired; not a company closure"),
    "Rejected": ("ASSESSMENT_REJECTED", "Assessment rejected; not an inferred business outcome"),
    "Not to Proceed": ("ASSESSMENT_NOT_TO_PROCEED", "Assessment status: Not to Proceed"),
}

def _text(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())

def parse_source_date(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Unexpected NL assessment date format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid NL assessment calendar date") from None
    if parsed.year < 1900:
        raise ValueError("NL assessment date predates supported source range")
    return value

def approved_project_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError:
        return None
    if (u.scheme != "https" or u.hostname != "www.gov.nl.ca" or u.username or u.password
            or port not in (None, 443) or u.query or u.fragment
            or not re.fullmatch(r"/eccc/projects/[A-Za-z0-9_-]+/", u.path)):
        return None
    return value

class _TableParser(HTMLParser):
    """Treat each new td as a cell boundary, including omitted closing td tags."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.table_count = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.in_em = 0
        self.link = None
        self.synthetic = False

    def _close_cell(self):
        if self.cell is not None:
            self.row.append(self.cell)
        self.cell = None
        self.in_em = 0
        self.link = None

    def _close_row(self):
        self._close_cell()
        if self.row:
            self.rows.append(self.row)
            if len(self.rows) > MAX_ROWS + 1:
                raise ValueError("NL table exceeds row bound")
        self.row = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "atlantic-fixture":
            self.synthetic = attrs.get("content") == "SYNTHETIC_NOT_REAL_SOURCE"
        if tag == "table":
            if self.active:
                raise ValueError("Nested NL project table is unsupported")
            if "dataTable" in attrs.get("class", "").split():
                self.table_count += 1
                self.active = True
            return
        if not self.active:
            return
        if tag == "tr":
            self._close_row()
            self.row = []
        elif tag in ("td", "th"):
            if self.row is None:
                raise ValueError("NL table cell outside a row")
            self._close_cell()
            self.cell = {"tag": tag, "text": [], "em": [], "links": [], "em_count": 0}
        elif self.cell is not None:
            if tag in ("script", "style", "iframe", "table"):
                raise ValueError("Unexpected active content in NL table cell")
            if tag == "br":
                self.handle_data(" ")
            elif tag == "em":
                self.in_em += 1
                self.cell["em_count"] += 1
            elif tag == "a":
                self.link = {"url": attrs.get("href"), "text": []}
                self.cell["links"].append(self.link)

    def handle_endtag(self, tag):
        if not self.active:
            return
        if tag == "table":
            self._close_row()
            self.active = False
        elif tag == "tr":
            self._close_row()
        elif tag in ("td", "th"):
            self._close_cell()
        elif tag == "em":
            self.in_em = max(0, self.in_em - 1)
        elif tag == "a":
            self.link = None

    def handle_data(self, data):
        if self.active and self.cell is not None:
            self.cell["text"].append(data)
            if self.in_em:
                self.cell["em"].append(data)
            if self.link is not None:
                self.link["text"].append(data)

def parse_project_list(raw: bytes) -> dict:
    """Inspect a supplied snapshot; reading is not a data-use or activation grant."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_HTML_BYTES:
        raise ValueError("NL snapshot must be nonempty bytes within 2 MB")
    try:
        html = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("NL snapshot must be UTF-8 HTML") from None
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    if parser.active:
        raise ValueError("NL project table did not close")
    if parser.table_count != 1 or not parser.rows:
        raise ValueError("Expected exactly one NL project table, not an empty/error page")
    if tuple(_text(c["text"]) for c in parser.rows[0]) != HEADERS:
        raise ValueError("NL project table headers changed")
    records = []
    keys = set()
    for number, cells in enumerate(parser.rows[1:], start=1):
        if len(cells) != 5 or any(c["tag"] != "td" for c in cells):
            raise ValueError("NL project table column structure changed")
        reg = _text(cells[0]["text"])
        if not re.fullmatch(r"[0-9]{1,8}", reg):
            raise ValueError("Invalid NL registration number; preserve it as a string")
        links = cells[1]["links"]
        if len(links) != 1 or cells[1]["em_count"] != 1:
            raise ValueError("NL title cell must contain one observed project link and one proponent em element")
        title = _text(links[0]["text"])
        proponent = re.sub(r"^Proponent:\s*", "", _text(cells[1]["em"])).strip() or None
        status = _text(cells[3]["text"])
        if not title or not status or any(len(x) > 4000 for x in [title, proponent or "", status]):
            raise ValueError("Missing or oversized NL title/proponent/status")
        url = approved_project_url(links[0]["url"])
        if url is None:
            raise ValueError("Unsupported NL project link; do not synthesize a replacement")
        key = url
        if key in keys:
            raise ValueError("Duplicate NL observed project URL identity")
        keys.add(key)
        registered, released = parse_source_date(_text(cells[2]["text"])), parse_source_date(_text(cells[4]["text"]))
        stage, label = STAGES.get(status, ("UNRECOGNIZED_ASSESSMENT_STATUS", "Unrecognized assessment status; review required"))
        issues = []
        if registered is None:
            issues.append("REGISTRATION_DATE_MISSING")
        if proponent is None:
            issues.append("PROPONENT_NOT_STATED")
        if status not in STAGES:
            issues.append("UNKNOWN_STATUS_PRESERVED")
        if status == "Released" and released is None:
            issues.append("RELEASE_DATE_MISSING")
        if released and registered and released < registered:
            issues.append("RELEASE_PRECEDES_REGISTRATION_REVIEW_REQUIRED")
        record = {
            "record_id": key, "registration_number": reg, "project_url": url,
            "title": title, "proponent_as_published": proponent,
            "registration_date": registered, "release_date": released,
            "status_as_published": status, "stage_code": stage, "stage_label": label,
            "source_row_number": number, "publication_date": None,
            "supersedes_registration_number": None, "issues": issues,
        }
        record["normalized_record_sha256"] = hashlib.sha256(
            json.dumps({k: record[k] for k in ("registration_number", "project_url", "title", "proponent_as_published", "registration_date", "release_date", "status_as_published")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        records.append(record)
    if not records:
        raise ValueError("NL table has no project records; completeness is not established")
    counts = Counter(r["registration_number"] for r in records)
    for record in records:
        if counts[record["registration_number"]] > 1:
            record["issues"].append("REGISTRATION_NUMBER_COLLISION_USE_OBSERVED_URL")
    return {
        "source": SOURCE, "source_url": INDEX_URL,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw), "rows_parsed": len(records),
        "synthetic_marker_reported": parser.synthetic,
        "duplicate_registration_numbers": sorted(k for k, n in counts.items() if n > 1),
        "records": records,
    }

def build_fixture_collection(raw: bytes, registration_numbers: list[str]) -> dict:
    """Build only an invented demonstration, never an authorized real-data feed."""
    if (not isinstance(registration_numbers, list) or not 1 <= len(registration_numbers) <= 20
            or any(not isinstance(x, str) or not re.fullmatch(r"[0-9]{1,8}", x) for x in registration_numbers)
            or len(set(registration_numbers)) != len(registration_numbers)):
        raise ValueError("Select 1–20 unique registration-number strings")
    parsed = parse_project_list(raw)
    if parsed["synthetic_marker_reported"] is not True or parsed["response_sha256"] != SYNTHETIC_FIXTURE_SHA256:
        raise ValueError("Real NL data reuse is gated pending review of the indemnity condition; only invented fixtures are enabled")
    wanted = set(registration_numbers)
    records = [r for r in parsed["records"] if r["registration_number"] in wanted]
    if len(records) > 50:
        raise ValueError("Selected NL fixture records exceed the review bound")
    collection = _fixture_envelope(records, registration_numbers)
    validate_fixture_collection(collection)
    return collection

def _fixture_envelope(records: list[dict], registration_numbers: list[str]) -> dict:
    return {
        "schema_version": 1, "source": SOURCE, "dataset_url": INDEX_URL,
        "collection_execution": "INJECTED_FETCHER_FIXTURE_OR_REPLAY",
        "fixture_only": True, "rights_status": RIGHTS_STATUS,
        "rights_note": RIGHTS_NOTE, "retrieved_at": None,
        "response_sha256": SYNTHETIC_FIXTURE_SHA256,
        "requested_registration_numbers": registration_numbers,
        "requested_limit": 50, "records_returned_by_api": None,
        "records_matching_exact_registration": len(records),
        "page_may_be_truncated": None,
        "source_update_frequency": None,
        "freshness_note": "Invented fixture. Registration/release dates are not publication dates; no live observation or complete coverage is claimed.",
        "coverage": "SYNTHETIC_SELECTED_REGISTRATIONS_ONLY; NO_ABSENCE_PROOF; NO_CORPORATE_IDENTITY_JOIN",
        "source_license": "NL conditional copyright permission; real-data reuse not authorized",
        "source_license_url": TERMS_URL, "source_attribution": ATTRIBUTION,
        "records": records,
    }


def _pinned_records() -> list[dict]:
    raw = Path(__file__).with_name("nl_assessment_fixture_records.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != _SYNTHETIC_RECORDS_SHA256:
        raise ValueError("Pinned NL invented records changed; review is required")
    return json.loads(raw)

def validate_fixture_collection(collection: dict) -> None:
    ids = collection.get("requested_registration_numbers")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 20
            or any(not isinstance(x, str) or not re.fullmatch(r"[0-9]{1,8}", x) for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Invalid NL fixture registration selection")
    expected = _fixture_envelope([r for r in _pinned_records() if r["registration_number"] in ids], ids)
    if collection != expected:
        raise ValueError("NL collection differs from the pinned invented records or rights/coverage metadata")


def has_nl_provenance(collection: dict) -> bool:
    def known(value):
        if not isinstance(value, str):
            return False
        try:
            u = urlsplit(value)
        except ValueError:
            return False
        return u.hostname == "www.gov.nl.ca" and (
            u.path.startswith("/eccc/projects/") or
            u.path in ("/eccc/env-assessment/projects-list/", "/disclaimer/"))
    if collection.get("response_sha256") == SYNTHETIC_FIXTURE_SHA256:
        return True
    if any(known(collection.get(k)) for k in ("dataset_url", "api_url", "source_license_url")):
        return True
    rows = collection.get("records")
    return isinstance(rows, list) and any(isinstance(row, dict) and
        any(known(row.get(k)) for k in ("record_id", "project_url")) for row in rows)
