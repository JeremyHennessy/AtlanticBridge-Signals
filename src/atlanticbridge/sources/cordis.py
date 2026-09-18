from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

HORIZON_ARCHIVE_URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"
SOURCE_NAME = "cordis_horizon_projects"
SOURCE_BUCKET = "horizon-projects-csv"

EU27_ISO2 = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
}

PROJECT_HEADER = [
    "id",
    "acronym",
    "status",
    "title",
    "startDate",
    "endDate",
    "totalCost",
    "ecMaxContribution",
    "topics",
    "ecSignatureDate",
    "frameworkProgramme",
    "masterCall",
    "subCall",
    "fundingScheme",
    "nature",
    "objective",
    "contentUpdateDate",
    "rcn",
    "grantDoi",
    "keywords",
    "Human-validated",
    "legalBasis",
]

ORGANIZATION_HEADER = [
    "projectID",
    "projectAcronym",
    "organisationID",
    "vatNumber",
    "name",
    "shortName",
    "SME",
    "activityType",
    "street",
    "postCode",
    "city",
    "country",
    "nutsCode",
    "geolocation",
    "organizationURL",
    "contactForm",
    "contentUpdateDate",
    "rcn",
    "order",
    "role",
    "ecContribution",
    "netEcContribution",
    "totalCost",
    "endOfParticipation",
    "active",
]


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    sha256: str
    byte_count: int
    source_url: str


@dataclass(frozen=True, slots=True)
class CordisProjectRecord:
    project_id: str
    acronym: str
    status: str
    title: str
    start_date: str
    end_date: str
    total_cost: str
    ec_max_contribution: str
    topics: str
    ec_signature_date: str
    framework_programme: str
    master_call: str
    sub_call: str
    funding_scheme: str
    nature: str
    objective: str
    content_update_date: str
    rcn: str
    grant_doi: str
    keywords: str
    human_validated: str
    legal_basis: str
    source_url: str = HORIZON_ARCHIVE_URL

    def db_tuple(self) -> tuple[str, ...]:
        return (
            self.project_id,
            self.acronym,
            self.status,
            self.title,
            self.start_date,
            self.end_date,
            self.total_cost,
            self.ec_max_contribution,
            self.topics,
            self.ec_signature_date,
            self.framework_programme,
            self.master_call,
            self.sub_call,
            self.funding_scheme,
            self.nature,
            self.objective,
            self.content_update_date,
            self.rcn,
            self.grant_doi,
            self.keywords,
            self.human_validated,
            self.legal_basis,
            self.source_url,
        )


@dataclass(frozen=True, slots=True)
class CordisParticipationRecord:
    project_id: str
    project_acronym: str
    organisation_id: str
    vat_number: str
    name: str
    short_name: str
    sme: str
    activity_type: str
    street: str
    post_code: str
    city: str
    country: str
    nuts_code: str
    geolocation: str
    organization_url: str
    contact_form: str
    content_update_date: str
    rcn: str
    source_order: str
    role: str
    ec_contribution: str
    net_ec_contribution: str
    total_cost: str
    end_of_participation: str
    active: str
    source_url: str = HORIZON_ARCHIVE_URL

    @property
    def record_json(self) -> str:
        return json.dumps(
            {
                "project_id": self.project_id,
                "project_acronym": self.project_acronym,
                "organisation_id": self.organisation_id,
                "vat_number": self.vat_number,
                "name": self.name,
                "short_name": self.short_name,
                "sme": self.sme,
                "activity_type": self.activity_type,
                "street": self.street,
                "post_code": self.post_code,
                "city": self.city,
                "country": self.country,
                "nuts_code": self.nuts_code,
                "geolocation": self.geolocation,
                "organization_url": self.organization_url,
                "contact_form": self.contact_form,
                "content_update_date": self.content_update_date,
                "rcn": self.rcn,
                "source_order": self.source_order,
                "role": self.role,
                "ec_contribution": self.ec_contribution,
                "net_ec_contribution": self.net_ec_contribution,
                "total_cost": self.total_cost,
                "end_of_participation": self.end_of_participation,
                "active": self.active,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def record_hash(self) -> str:
        return hashlib.sha256(self.record_json.encode("utf-8")).hexdigest()

    @property
    def participation_id(self) -> str:
        # Source-local row identity. Do not treat CORDIS organisationID as a
        # global legal-entity identifier; GLEIF/entity-resolution is separate.
        material = "\x1f".join(
            [
                self.project_id,
                self.organisation_id,
                self.rcn,
                self.source_order,
                self.name,
                self.country,
                self.role,
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def db_tuple(self) -> tuple[str, ...]:
        return (
            self.participation_id,
            self.project_id,
            self.project_acronym,
            self.organisation_id,
            self.vat_number,
            self.name,
            self.short_name,
            self.sme,
            self.activity_type,
            self.street,
            self.post_code,
            self.city,
            self.country,
            self.nuts_code,
            self.geolocation,
            self.organization_url,
            self.contact_form,
            self.content_update_date,
            self.rcn,
            self.source_order,
            self.role,
            self.ec_contribution,
            self.net_ec_contribution,
            self.total_cost,
            self.end_of_participation,
            self.active,
            self.record_hash,
            self.record_json,
            self.source_url,
        )


def download_horizon_archive(
    destination: str | Path,
    *,
    source_url: str = HORIZON_ARCHIVE_URL,
    timeout: int = 120,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> DownloadResult:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            )
        },
    )

    for attempt in range(1, attempts + 1):
        try:
            digest = hashlib.sha256()
            byte_count = 0
            temp_path = destination.with_suffix(destination.suffix + ".part")
            with urlopen(request, timeout=timeout) as response, temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
                    handle.write(chunk)
            temp_path.replace(destination)
            return DownloadResult(
                path=destination,
                sha256=digest.hexdigest(),
                byte_count=byte_count,
                source_url=source_url,
            )
        except (TimeoutError, URLError):
            destination.with_suffix(destination.suffix + ".part").unlink(missing_ok=True)
            if attempt >= attempts:
                raise
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise AssertionError("unreachable")


def _iter_archive_rows(
    archive_path: str | Path,
    *,
    member: str,
    expected_header: list[str],
):
    with zipfile.ZipFile(archive_path) as archive:
        if member not in archive.namelist():
            raise ValueError(f"CORDIS archive missing required member: {member}")
        with archive.open(member) as raw:
            handle = io.TextIOWrapper(
                raw,
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            )
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames != expected_header:
                raise ValueError(
                    f"CORDIS {member} schema changed. "
                    f"Expected {expected_header!r}, received {reader.fieldnames!r}"
                )
            yield from reader


def iter_projects(
    archive_path: str | Path,
    *,
    source_url: str = HORIZON_ARCHIVE_URL,
):
    for row in _iter_archive_rows(
        archive_path,
        member="project.csv",
        expected_header=PROJECT_HEADER,
    ):
        project_id = _clean(row["id"])
        if not project_id:
            continue
        yield CordisProjectRecord(
            project_id=project_id,
            acronym=_clean(row["acronym"]),
            status=_clean(row["status"]),
            title=_clean(row["title"]),
            start_date=_clean(row["startDate"]),
            end_date=_clean(row["endDate"]),
            total_cost=_clean(row["totalCost"]),
            ec_max_contribution=_clean(row["ecMaxContribution"]),
            topics=_clean(row["topics"]),
            ec_signature_date=_clean(row["ecSignatureDate"]),
            framework_programme=_clean(row["frameworkProgramme"]),
            master_call=_clean(row["masterCall"]),
            sub_call=_clean(row["subCall"]),
            funding_scheme=_clean(row["fundingScheme"]),
            nature=_clean(row["nature"]),
            objective=_clean(row["objective"]),
            content_update_date=_clean(row["contentUpdateDate"]),
            rcn=_clean(row["rcn"]),
            grant_doi=_clean(row["grantDoi"]),
            keywords=_clean(row["keywords"]),
            human_validated=_clean(row["Human-validated"]),
            legal_basis=_clean(row["legalBasis"]),
            source_url=source_url,
        )


def iter_participations(
    archive_path: str | Path,
    *,
    source_url: str = HORIZON_ARCHIVE_URL,
):
    for row in _iter_archive_rows(
        archive_path,
        member="organization.csv",
        expected_header=ORGANIZATION_HEADER,
    ):
        project_id = _clean(row["projectID"])
        if not project_id:
            continue
        yield CordisParticipationRecord(
            project_id=project_id,
            project_acronym=_clean(row["projectAcronym"]),
            organisation_id=_clean(row["organisationID"]),
            vat_number=_clean(row["vatNumber"]),
            name=_clean(row["name"]),
            short_name=_clean(row["shortName"]),
            sme=_clean(row["SME"]),
            activity_type=_clean(row["activityType"]),
            street=_clean(row["street"]),
            post_code=_clean(row["postCode"]),
            city=_clean(row["city"]),
            country=_clean(row["country"]),
            nuts_code=_clean(row["nutsCode"]),
            geolocation=_clean(row["geolocation"]),
            organization_url=_clean(row["organizationURL"]),
            contact_form=_clean(row["contactForm"]),
            content_update_date=_clean(row["contentUpdateDate"]),
            rcn=_clean(row["rcn"]),
            source_order=_clean(row["order"]),
            role=_clean(row["role"]),
            ec_contribution=_clean(row["ecContribution"]),
            net_ec_contribution=_clean(row["netEcContribution"]),
            total_cost=_clean(row["totalCost"]),
            end_of_participation=_clean(row["endOfParticipation"]),
            active=_clean(row["active"]),
            source_url=source_url,
        )
