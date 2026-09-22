"""Canadian investment references: discovery candidates, not validated entry labels.

Reuse the accepted company-source record and ledger contracts. No existing
collector, model label, publication gate, or UI behavior is changed.
"""
from __future__ import annotations

from collections import Counter
import json
import re

from bs4 import BeautifulSoup

from .company_sources import Ledger, record, unique

SOURCE_URL = "https://www.investcanada.ca/news"


def parse_investment_cards(body: bytes, source: dict) -> list[dict]:
    """Reconcile one current page's controls/cards, not a historical corpus."""
    if source.get("url") != SOURCE_URL or source.get("kind") != "investment_cards":
        raise ValueError("Unreviewed investment-card source contract")
    if not isinstance(body, bytes) or len(body) > 16 * 1024 * 1024:
        raise ValueError("Invalid or oversized investment page")
    soup = BeautifulSoup(body, "html.parser")
    cards = soup.select("article.investment-announcement[id]")
    ids = [card["id"] for card in cards]
    controls = {tag.get("data-controls") for tag in soup.select("a.investment-announcement[data-controls]")}
    # The desktop and mobile controls repeat the same IDs; card identities must not.
    if not cards or len(cards) > 1000 or len(ids) != len(set(ids)) or set(ids) != controls:
        raise ValueError("Missing, duplicate or incomplete investment-card collection")
    rows = []
    for card in cards:
        def field(name: str) -> str:
            nodes = card.select(f".field--name-field-{name} .field--item")
            if len(nodes) > 1:
                raise ValueError("Ambiguous investment-card field: " + name)
            return nodes[0].get_text(" ", strip=True) if nodes else ""
        headings = card.select("h3.slide-title")
        name = headings[0].get_text(" ", strip=True) if len(headings) == 1 else ""
        kind, country, location = field("investment-type"), field("country"), field("location")
        if not all((name, kind, country, location)) or not re.fullmatch(r"investment-\d+", card["id"]):
            raise ValueError("Investment card lacks required source identity/context")
        row = record(source, card["id"], name + " — " + kind, source["url"],
                     body=card.get_text(" ", strip=True), location=location,
                     clock="UNDATED_AGENCY_INVESTMENT_REFERENCE")
        row.update(company_candidate=name, source_fragment=card["id"],
                   source_country_as_published=country, investment_type_as_published=kind,
                   amount_as_published=field("total-invested") or None,
                   jobs_as_published=field("total-jobs") or None,
                   canada_relevance="CANDIDATE_REQUIRES_REVIEW",
                   legal_identity_confirmed=False, first_entry_confirmed=False,
                   operational_opening_date=None, outcome_date=None,
                   outcome_review_status="UNREVIEWED_DISCOVERY_CANDIDATE",
                   sector_scope_review_status="REQUIRED_BEFORE_QUALIFICATION",
                   independent_holdout=False,
                   interpretation="Agency-published investment reference. Country, amount and job labels are retained as published, not verified legal control, realized expenditure, created jobs or dated first entry.")
        rows.append(row)
    return unique(rows)


def discovery_summary(rows: list[dict]) -> dict:
    unique(rows)
    if any(row.get("outcome_review_status") != "UNREVIEWED_DISCOVERY_CANDIDATE"
           or row.get("first_entry_confirmed") is not False
           or row.get("backtest_eligible") is not False for row in rows):
        raise ValueError("Discovery evidence must not be promoted into outcome labels")
    return {"candidate_records": len(rows),
            "country_labels_as_published": dict(sorted(Counter(r["source_country_as_published"] for r in rows).items())),
            "dated_first_entry_labels": 0, "independent_holdout_rows": 0,
            "scope_review_required": len(rows), "absence_inference_allowed": False,
            "expansion_score_publication_allowed": False}


def retained_review_records(ledger: Ledger, rows: list[dict]) -> list[dict]:
    """Export persisted first/last observations; never replace first-seen with rebuild time."""
    retained = []
    for row in rows:
        saved = ledger.db.execute("SELECT payload FROM company_observations WHERE id=?", (row["id"],)).fetchone()
        if saved is None:
            raise ValueError("Review export requires a committed ledger observation")
        item = json.loads(saved[0])
        if item["source_id"] != row["source_id"]:
            raise ValueError("Review export source mismatch")
        retained.append(item)
    return retained
