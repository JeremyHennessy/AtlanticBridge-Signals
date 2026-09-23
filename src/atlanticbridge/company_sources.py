"""Public company-source parsing and a persistent, baseline-safe observation ledger.

Records are source-local evidence, never automatic legal-entity joins or expansion
predictions. A new observation is not necessarily a newly published event.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
import re
import sqlite3
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

VERSION = 2
CANADA = re.compile(r"\b(canada|canadian|canadien(?:ne)?|montr[eé]al|toronto|ottawa|calgary|edmonton|winnipeg|halifax|saskatoon|regina)\b", re.I)
MILITARY = re.compile(r"\b(military|munitions|weapon(?:s)?|armed forces|defen[cs]e|militaire)\b", re.I)
TRACKING = {"gclid", "fbclid", "msclkid"}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Expected text, not a coerced object")
    return " ".join(BeautifulSoup(html.unescape(value), "html.parser").get_text(" ", strip=True).split())


def url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("URL must be text")
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Only credential-free HTTPS URLs are accepted")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return urlunsplit(("https", p.netloc.lower(), p.path or "/", urlencode(sorted(query)), ""))


def instant(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("A timestamp is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        result = parsedate_to_datetime(value)
    if result.tzinfo is None:
        # A date alone is retained elsewhere as day-granular publication evidence.
        raise ValueError("Timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def publication(value: object) -> tuple[str | None, str]:
    if value in (None, ""):
        return None, "UNKNOWN"
    if not isinstance(value, str):
        raise ValueError("Invalid publication date type")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        datetime.strptime(value, "%Y-%m-%d")
        return value, "DAY"
    return instant(value).isoformat(), "TIMESTAMP"


def record(source: dict, key: str, title: str, link: str, *, body: str = "",
           location: str = "", published: object = None, clock: str = "UNKNOWN",
           updated: object = None, remote: bool | None = None) -> dict:
    title, body, location = text(title), text(body), text(location)
    if not title or not str(key).strip():
        raise ValueError("Missing source identifier or title")
    if max(len(title), len(location)) > 3000 or len(body) > 200000:
        raise ValueError("Record exceeds bounded text size")
    date, precision = publication(published)
    # Careers geography uses location/title only, never global-company boilerplate.
    geography_text = f"{location} {title}" if source["kind"] == "careers" else f"{title} {body}"
    canada = bool(CANADA.search(geography_text))
    if re.search(r"\bvancouver\b", geography_text, re.I):
        canada = canada or not re.search(r"\b(washington|wa|united states|usa)\b", geography_text, re.I)
    excluded = bool(MILITARY.search(f"{title} {body}"))
    return {"id": digest([source["id"], str(key)]), "source_id": source["id"],
            "source_record_id": str(key), "company_candidate": source.get("company"),
            "identity_scope": "SOURCE_LOCAL_NO_AUTOMATIC_LEGAL_OR_PARENT_JOIN",
            "title": title, "source_url": url(link), "evidence_text": body,
            "location_text": location, "remote": remote,
            "source_publication_date": date, "publication_precision": precision,
            "publication_clock": clock, "source_updated_at": updated,
            "canada_relevance": "CANDIDATE_REQUIRES_REVIEW" if canada else "NOT_ESTABLISHED",
            "scope_exclusion": "MILITARY_REVIEW_HOLD" if excluded else None,
            "backtest_eligible": False, "public_alert_allowed": False,
            "interpretation": "Observed public evidence; not proof of first entry, a new office, or expansion probability."}


def unique(records: list[dict]) -> list[dict]:
    seen = set()
    for item in records:
        if item["id"] in seen:
            raise ValueError("Duplicate source key; completeness is not established")
        seen.add(item["id"])
    return records


def parse_greenhouse(payload: dict, source: dict) -> list[dict]:
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or type(payload.get("meta", {}).get("total")) is not int:
        raise ValueError("Greenhouse jobs/total schema missing")
    if payload["meta"]["total"] != len(jobs) or len(jobs) > 10000:
        raise ValueError("Incomplete or excessive Greenhouse response")
    out, all_ids = [], set()
    for job in jobs:
        key = job.get("id")
        if type(key) is not int or key <= 0 or key in all_ids:
            raise ValueError("Invalid or duplicate Greenhouse posting id")
        all_ids.add(key)
        if job.get("internal_job_id") is None:
            continue  # General prospect posts are not open positions.
        location = job.get("location")
        if not isinstance(location, dict) or not isinstance(location.get("name"), str):
            raise ValueError("Missing structured Greenhouse location")
        out.append(record(source, str(key), job["title"], job["absolute_url"],
                          body=job.get("content", ""), location=location["name"],
                          # updated_at is expressly NOT a publication date.
                          updated=job.get("updated_at"), clock="NO_PUBLICATION_DATE_IN_LIST"))
    return unique(out)


def parse_ashby(payload: dict, source: dict) -> list[dict]:
    if payload.get("apiVersion") != "1" or not isinstance(payload.get("jobs"), list):
        raise ValueError("Unknown Ashby schema/version")
    if len(payload["jobs"]) > 10000:
        raise ValueError("Excessive Ashby response")
    out = []
    for job in payload["jobs"]:
        if type(job.get("isListed")) is not bool:
            raise ValueError("Missing Ashby listing visibility")
        if not job["isListed"]:
            continue  # Direct-link-only postings must not be surfaced.
        locations = [job.get("location", "")]
        address = job.get("address") or {}
        postal = address.get("postalAddress") or {}
        locations.append(postal.get("addressCountry", ""))
        for secondary in job.get("secondaryLocations") or []:
            locations.extend([secondary.get("location", ""),
                              (secondary.get("address") or {}).get("addressCountry", "")])
        locations = ["Canada" if value in {"CAN", "CA"} else value for value in locations if value]
        link = url(job["jobUrl"])
        out.append(record(source, link, job["title"], link,
                          body=job.get("descriptionPlain") or job.get("descriptionHtml", ""),
                          location=" | ".join(locations), published=job.get("publishedAt"),
                          clock="LAST_PUBLISHED_NOT_ORIGINAL_PUBLICATION", remote=job.get("isRemote")))
    return unique(out)


def discover_ats(body: bytes, page_url: str) -> list[tuple[str, str]]:
    """Only follow actual links/embeds on the reviewed official careers page."""
    soup = BeautifulSoup(body, "html.parser")
    found = set()
    for tag in soup.find_all(["a", "iframe", "script"]):
        value = tag.get("href") or tag.get("src")
        if not value:
            continue
        p = urlsplit(urljoin(page_url, value))
        parts = [x for x in p.path.split("/") if x]
        if p.scheme != "https":
            continue
        if p.hostname == "jobs.ashbyhq.com" and parts:
            found.add(("ashby", parts[0]))
        if p.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io"}:
            token = dict(parse_qsl(p.query)).get("for") if parts and parts[0] == "embed" else (parts[0] if parts else None)
            if token and p.hostname != "boards.eu.greenhouse.io":
                found.add(("greenhouse", token))
    return sorted(found)


def parse_index(body: bytes, source: dict) -> list[dict]:
    """One reviewed index page, not a historical archive or absence proof."""
    soup = BeautifulSoup(body, "html.parser")
    out = {}
    base = urlsplit(source["url"])
    prefix = source["article_path_prefix"]
    for tag in soup.find_all("a", href=True):
        href = urljoin(source["url"], tag["href"])
        p = urlsplit(href)
        if p.hostname != base.hostname or not p.path.startswith(prefix) or p.path.rstrip("/") == base.path.rstrip("/"):
            continue
        if p.query or re.search(r"/(?:page|category|tag|subject)/", p.path):
            continue
        title = tag.get_text(" ", strip=True)
        if len(title) < 12:
            continue
        canonical = url(href)
        if canonical not in out or len(title) > len(out[canonical]["title"]):
            out[canonical] = record(source, canonical, title, canonical, clock="INDEX_LINK_UNDATED")
    if not out:
        raise ValueError("No article links: unsupported page or schema drift, not zero news")
    if len(out) > 1000:
        raise ValueError("Index exceeds reviewed bound")
    return list(out.values())


def parse_article(body: bytes, source: dict) -> list[dict]:
    soup = BeautifulSoup(body, "html.parser")
    meta = soup.find("meta", property="og:title")
    heading = soup.find("h1") or soup.find("title")
    title = meta.get("content", "") if meta else (heading.get_text(" ", strip=True) if heading else "")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    selector = source.get("reviewed_content_selector")
    if selector is not None:
        # Content scoping is source-contract data, not a generic fallback. Add each
        # selector explicitly in code review so a layout change fails closed.
        if selector not in {"main"}:
            raise ValueError("Unreviewed article content selector")
        matches = soup.select(selector)
        if len(matches) != 1:
            raise ValueError("Reviewed article content selector is missing or ambiguous")
        content = matches[0]
    else:
        content = soup.find("article") or soup.find("main") or soup
    plain = content.get_text(" ", strip=True)
    for required in source.get("required_text", []):
        if required.casefold() not in " ".join(plain.split()).casefold():
            raise ValueError("Reviewed article anchor no longer present: " + required)
    # A curator-specified date is accepted only with a literal date anchor on the page.
    date = source.get("reviewed_publication_date")
    if date and source.get("publication_date_text", "__MISSING__").casefold() not in plain.casefold():
        raise ValueError("Reviewed publication date not found on source page")
    return [record(source, source["url"], title, source["url"], body=plain,
                   published=date, clock="REVIEWED_ON_PAGE_DATE_NOT_HISTORICAL_AVAILABILITY")]


def parse_feed(body: bytes, source: dict) -> list[dict]:
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("XML entity declarations are forbidden")
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    if root.tag == "rss":
        entries, atom = root.findall("./channel/item"), False
    elif root.tag == "{http://www.w3.org/2005/Atom}feed":
        entries, atom = root.findall("a:entry", ns), True
    else:
        raise ValueError("Not an RSS/Atom feed")
    out = []
    for item in entries:
        if atom:
            links = [x for x in item.findall("a:link", ns) if x.get("rel", "alternate") == "alternate"]
            if len(links) != 1:
                raise ValueError("Ambiguous Atom article URL")
            link = urljoin(source["url"], links[0].get("href", ""))
            title = item.findtext("a:title", namespaces=ns)
            summary = item.findtext("a:summary", default="", namespaces=ns)
            published = item.findtext("a:published", namespaces=ns)
        else:
            link = item.findtext("link")
            title = item.findtext("title")
            summary = item.findtext("description", default="")
            published = item.findtext("pubDate")
        canonical = url(link)
        out.append(record(source, canonical, title, canonical, body=summary,
                          published=published, clock="FEED_PUBLISHED_NOT_HISTORICAL_AVAILABILITY"))
    return unique(out)


class Ledger:
    """Append-only identities survive empty pages/outages. Each source commits atomically."""
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS company_source_state (
          id TEXT PRIMARY KEY, contract TEXT NOT NULL, last_success TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_observations (
          id TEXT PRIMARY KEY, source_id TEXT NOT NULL, first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_observation_events (
          id TEXT PRIMARY KEY, source_id TEXT NOT NULL, observed_at TEXT NOT NULL,
          kind TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def apply(self, source: dict, records: list[dict], observed_at: str,
              raw_sha256: str, *, complete: bool = True) -> list[dict]:
        now = instant(observed_at)
        if not complete or not re.fullmatch(r"[a-f0-9]{64}", raw_sha256):
            raise ValueError("Incomplete source or missing raw provenance")
        unique(records)
        if any(r["source_id"] != source["id"] for r in records):
            raise ValueError("Mixed source identities")
        contract = digest({"parser_version": VERSION, "source": source})
        prior = self.db.execute("SELECT contract,last_success FROM company_source_state WHERE id=?", (source["id"],)).fetchone()
        if prior and prior[0] != contract:
            raise ValueError("Source contract changed: explicit migration/review required")
        if prior and now < instant(prior[1]):
            raise ValueError("Observation clock moved backwards")
        # Validate the whole response before opening the update transaction.
        for r in records:
            date = r["source_publication_date"]
            if date and ((r["publication_precision"] == "DAY" and date > now.date().isoformat()) or
                         (r["publication_precision"] == "TIMESTAMP" and instant(date) > now)):
                raise ValueError("Future-dated source record")
        events = []
        with self.db:
            for r in records:
                stable = {k: v for k, v in r.items() if k not in {"source_updated_at"}}
                fingerprint = digest(stable)
                old = self.db.execute("SELECT first_seen,fingerprint FROM company_observations WHERE id=?", (r["id"],)).fetchone()
                kind = None
                if prior and old is None:
                    # Never call Ashby's last-published clock an original first posting.
                    kind = "NEWLY_OBSERVED_RECORD"
                elif old and old[1] != fingerprint:
                    kind = "RECORD_CHANGED"
                stored = dict(r, first_observed_at=old[0] if old else observed_at,
                              last_observed_at=observed_at, raw_sha256=raw_sha256)
                if kind:
                    event = {"id": digest([r["id"], fingerprint, observed_at]),
                             "kind": kind, "observed_at": observed_at, "record": stored,
                             "public_alert_allowed": False, "review_required": True}
                    events.append(event)
                    self.db.execute("INSERT INTO company_observation_events VALUES (?,?,?,?,?)",
                                    (event["id"], source["id"], observed_at, kind, json.dumps(event, ensure_ascii=False)))
                self.db.execute("INSERT INTO company_observations VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,fingerprint=excluded.fingerprint,payload=excluded.payload",
                                (r["id"], source["id"], stored["first_observed_at"], observed_at,
                                 fingerprint, json.dumps(stored, ensure_ascii=False)))
            self.db.execute("INSERT INTO company_source_state VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET last_success=excluded.last_success",
                            (source["id"], contract, observed_at))
        return events
