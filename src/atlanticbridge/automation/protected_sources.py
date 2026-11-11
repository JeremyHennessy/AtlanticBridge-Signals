"""Revalidate protected pilots at every durable-ingestion boundary.

The canonical values come only from the existing hash-checked bundled source
pins and packet builder, never from caller-supplied normalized metadata. No
network access, test fixture path, caller secret or bypass flag is involved.
"""
from __future__ import annotations
from dataclasses import asdict
import json

from .models import canonical
from ..sources import halifax_building_permits as halifax
from ..sources import nl_environmental_assessments as nl

PROTECTED_IDS = frozenset({halifax.SOURCE, nl.SOURCE})


def _has_nl_provenance(value):
    if isinstance(value, dict):
        return any(_has_nl_provenance(k) or _has_nl_provenance(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_nl_provenance(v) for v in value)
    if isinstance(value, str):
        return any(token in value.lower() for token in (
            "nl_environmental_assessments", "www.gov.nl.ca/eccc/projects/",
            "www.gov.nl.ca/eccc/env-assessment/", "www.gov.nl.ca/disclaimer/",
            "newfoundland and labrador environmental assessments", "nl conditional copyright",
            "synthetic_only_real_reuse_not_authorized", nl.SYNTHETIC_FIXTURE_SHA256,
        ))
    return False


def _expected_variants(source):
    # Import lazily: the bridge calls decode_batch only from its public wrapper.
    from .review_bridge import _prepare_review_parts
    if source == halifax.SOURCE:
        collections = [halifax.build_pinned_collection(kind) for kind in ("ui_observed", "invented")]
    elif source == nl.SOURCE:
        rows = nl._pinned_records()  # Bundled package resource, verified by the existing source hash.
        ids = sorted({row["registration_number"] for row in rows})
        collection = nl._fixture_envelope(rows, ids)
        nl.validate_fixture_collection(collection)
        collections = [collection]
    else:
        return []
    variants = []
    for collection in collections:
        contract, body = _prepare_review_parts(collection, generated_at="2026-11-06T12:00:00Z")
        variants.append((contract, json.loads(body)["records"]))
    return variants


def validate_protected_contract(contract):
    """Reserve protected IDs and identifiable rights/provenance against relabeling."""
    metadata = asdict(contract)
    if contract.source_id not in PROTECTED_IDS:
        if halifax.has_halifax_provenance(metadata) or _has_nl_provenance(metadata):
            raise ValueError("Protected pilot provenance cannot be relabelled as another source")
        return
    if not any(canonical(metadata) == canonical(asdict(expected)) for expected, _ in _expected_variants(contract.source_id)):
        raise ValueError("Protected pilot contract differs from the bundled source, rights, origin or limits")


def validate_protected_input(contract, records):
    validate_protected_contract(contract)
    actual = [asdict(record) for record in records]
    if contract.source_id not in PROTECTED_IDS:
        if halifax.has_halifax_provenance(actual) or _has_nl_provenance(actual):
            raise ValueError("Protected pilot record provenance cannot be relabelled as another source")
        return
    matching = [(expected, rows) for expected, rows in _expected_variants(contract.source_id)
                if canonical(asdict(contract)) == canonical(asdict(expected))]
    if not matching or not records:
        raise ValueError("Protected pilot requires nonempty pinned records")
    allowed = {row["record_id"]: canonical(row) for row in matching[0][1]}
    if any(allowed.get(row["record_id"]) != canonical(row) for row in actual):
        raise ValueError("Protected pilot records differ from bundled facts, dates, provenance or interpretation")
    # Halifax has exactly one row per origin. NL supports pinned fixture subsets.
    if contract.source_id == halifax.SOURCE and len(actual) != len(allowed):
        raise ValueError("Protected Halifax sample must remain complete and pinned")
