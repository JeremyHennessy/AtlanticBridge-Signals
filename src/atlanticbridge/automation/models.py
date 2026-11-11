"""Strict, bounded input contracts; all inputs remain local context-only evidence."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

ORIGINS = frozenset({"INVENTED_FIXTURE", "LOCAL_REVIEW_PACKET"})
_MAX_BODY = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, name, limit=512):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError(f"Invalid {name}")
    return value


def timestamp(value):
    text(value, "timestamp", 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp needs an explicit UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def day(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Date must be YYYY-MM-DD or null")
    return date.fromisoformat(value).isoformat()


def source_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_:-]{0,99}", value):
        raise ValueError("Invalid source ID")
    return value


def url(value):
    if value is None:
        return None
    text(value, "URL", 2048)
    try:
        p = urlsplit(value)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            raise ValueError("Invalid HTTPS evidence URL")
        if p.fragment or any(ord(c) < 33 for c in value):
            raise ValueError("Invalid HTTPS evidence URL")
    except ValueError as error:
        raise ValueError("Invalid HTTPS evidence URL") from error
    return value


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {name}")
    return value


@dataclass(frozen=True)
class SourceContract:
    source_id: str
    title: str
    parser_version: str
    allowed_fields: tuple[str, ...]
    license_name: str
    license_url: str
    attribution: str
    coverage: str
    origin: str = "LOCAL_REVIEW_PACKET"
    access_method: str = "LOCAL_FILE_ONLY"
    cadence_seconds: int = 86400
    lease_seconds: int = 120
    retry_seconds: int = 300
    max_retry_seconds: int = 86400
    max_failures: int = 5
    max_records: int = 10000
    max_bytes: int = _MAX_BODY
    production_enabled: bool = False

    def __post_init__(self):
        source_id(self.source_id)
        for name in ("title", "parser_version", "license_name", "attribution", "coverage"):
            text(getattr(self, name), name, 4096)
        url(self.license_url)
        if self.license_url is None:
            raise ValueError("A declared licence URL is required; this does not verify rights")
        if self.access_method != "LOCAL_FILE_ONLY" or self.production_enabled is not False:
            raise ValueError("Production and network transports are not implemented or enabled")
        if self.origin not in ORIGINS:
            raise ValueError("Only local packets and invented fixtures are accepted")
        if not isinstance(self.allowed_fields, tuple) or not 1 <= len(self.allowed_fields) <= 100:
            raise ValueError("Allowed fields must be a nonempty tuple")
        for field in self.allowed_fields:
            text(field, "allowed field", 100)
        if len(set(self.allowed_fields)) != len(self.allowed_fields):
            raise ValueError("Duplicate allowed fields")
        for name, low, high in (
            ("cadence_seconds", 60, 2592000), ("lease_seconds", 1, 3600),
            ("retry_seconds", 1, 86400), ("max_retry_seconds", 1, 604800),
            ("max_failures", 1, 20), ("max_records", 1, 10000), ("max_bytes", 1, _MAX_BODY),
        ):
            integer(getattr(self, name), name, low, high)
        if self.max_retry_seconds < self.retry_seconds:
            raise ValueError("Retry cap is below initial retry")

    @property
    def contract_id(self):
        return digest(asdict(self))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Contract must be an object")
        data = dict(data)
        fields = data.get("allowed_fields")
        if isinstance(fields, list):
            data["allowed_fields"] = tuple(fields)
        try:
            return cls(**data)
        except TypeError as error:
            raise ValueError("Unknown or missing source contract fields") from error


@dataclass(frozen=True)
class Record:
    record_id: str
    facts: dict
    source_url: str | None = None
    event_date: str | None = None
    published_date: str | None = None
    source_observed_at: str | None = None

    def validate(self, contract):
        text(self.record_id, "record ID", 512)
        url(self.source_url)
        day(self.event_date)
        day(self.published_date)
        if self.source_observed_at is not None:
            timestamp(self.source_observed_at)
        if not isinstance(self.facts, dict) or not set(self.facts) <= set(contract.allowed_fields):
            raise ValueError("Record contains fields outside the source allowlist")
        # Evidence facts are deliberately scalar: no hidden unbounded subtrees.
        for key, value in self.facts.items():
            if value is not None and type(value) not in (str, int, float, bool):
                raise ValueError("Evidence facts must be JSON scalars")
            if isinstance(value, str) and (len(value) > 16000 or "\x00" in value):
                raise ValueError("Evidence fact too long or invalid")
        canonical(self.facts)  # Reject NaN and infinity.
        return self

    def content(self):
        # Retrieval/import clocks do not constitute a content change.
        return {k: v for k, v in asdict(self).items() if k != "source_observed_at"}


@dataclass(frozen=True)
class Batch:
    source_id: str
    origin: str
    records: tuple[Record, ...]
    coverage: str
    input_sha256: str
    input_bytes: bytes
    input_kind: str = "LOCAL_NORMALIZED_PACKET_NOT_RAW_SOURCE_RESPONSE"

    def validate(self, contract):
        if self.source_id != contract.source_id or self.origin != contract.origin:
            raise ValueError("Source or origin does not match pinned contract")
        if self.coverage != contract.coverage:
            raise ValueError("Coverage must match the pinned contract")
        if self.input_kind != "LOCAL_NORMALIZED_PACKET_NOT_RAW_SOURCE_RESPONSE":
            raise ValueError("Only locally normalized input evidence is accepted")
        if type(self.input_bytes) is not bytes or len(self.input_bytes) > contract.max_bytes:
            raise ValueError("Input bytes exceed the bounded source contract")
        if hashlib.sha256(self.input_bytes).hexdigest() != self.input_sha256:
            raise ValueError("Input evidence hash mismatch")
        if not isinstance(self.records, tuple) or len(self.records) > contract.max_records:
            raise ValueError("Record count exceeds the bounded source contract")
        ids = set()
        for row in self.records:
            if not isinstance(row, Record):
                raise ValueError("Invalid record")
            row.validate(contract)
            if row.record_id in ids:
                raise ValueError("Duplicate source record ID")
            ids.add(row.record_id)
        # Bind normalized fields to retained bytes, not a caller-supplied label/hash alone.
        decoded = decode_batch(self.input_bytes, contract)
        if canonical([asdict(r) for r in self.records]) != canonical([asdict(r) for r in decoded.records]):
            raise ValueError("Normalized records differ from retained input")
        return self


def decode_batch(body, contract):
    if type(body) is not bytes or len(body) > contract.max_bytes:
        raise ValueError("Input exceeds source byte limit")
    def strict_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError("Nonfinite JSON number")
    try:
        data = json.loads(body, object_pairs_hook=strict_pairs, parse_constant=nonfinite)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Invalid input JSON") from error
    required = {"format_version", "source_id", "origin", "coverage", "records"}
    if not isinstance(data, dict) or set(data) != required or type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ValueError("Unsupported local input envelope")
    if data["source_id"] != contract.source_id or data["origin"] != contract.origin or data["coverage"] != contract.coverage:
        raise ValueError("Input source, origin or coverage differs from contract")
    rows = data["records"]
    if not isinstance(rows, list) or len(rows) > contract.max_records:
        raise ValueError("Invalid or excessive records")
    records = []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid record object")
        try:
            record = Record(**row).validate(contract)
        except TypeError as error:
            raise ValueError("Unknown or missing record fields") from error
        if record.record_id in ids:
            raise ValueError("Duplicate source record ID")
        ids.add(record.record_id)
        records.append(record)
    from .protected_sources import validate_protected_input
    validate_protected_input(contract, records)
    return Batch(contract.source_id, contract.origin, tuple(records), contract.coverage,
                 hashlib.sha256(body).hexdigest(), body)
