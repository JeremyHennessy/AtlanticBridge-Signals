from __future__ import annotations

import csv
import hashlib
import http.cookiejar
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from ..constants import EU27, normalize_country

PAGE_URL = "https://canadabuys.canada.ca/en/procurement-and-contracting-data"
CURRENT_AWARDS_URL = (
    "https://canadabuys.canada.ca/opendata/pub/"
    "2026-2027-awardNotice-avisAttribution.csv"
)
SOURCE_NAME = "canadabuys_award_notices"
SOURCE_BUCKET = "2026-2027"

EU27_ISO2_TO_NAME = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "HR": "Croatia",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DK": "Denmark",
    "EE": "Estonia",
    "FI": "Finland",
    "FR": "France",
    "DE": "Germany",
    "GR": "Greece",
    "HU": "Hungary",
    "IE": "Ireland",
    "IT": "Italy",
    "LV": "Latvia",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MT": "Malta",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "ES": "Spain",
    "SE": "Sweden",
}

EXPECTED_HEADER = [
    "title-titre-eng",
    "title-titre-fra",
    "referenceNumber-numeroReference",
    "amendmentNumber-numeroModification",
    "solicitationNumber-numeroSollicitation",
    "contractNumber-numeroContrat",
    "publicationDate-datePublication",
    "contractAwardDate-dateAttributionContrat",
    "amendmentDate-dateModification",
    "contractStartDate-contratDateDebut",
    "contractEndDate-dateFinContrat",
    "contractAmount-montantContrat",
    "totalContractValue-valeurTotaleContrat",
    "contractCurrency-contratMonnaie",
    "awardStatus-attributionStatut-eng",
    "awardStatus-attributionStatut-fra",
    "instrumentType-typeInstrument-eng",
    "instrumentType-typeInstrument-fra",
    "amendmentType-typeModification-eng",
    "amendmentType-typeModification-fra",
    "gsin-nibs",
    "gsinDescription-nibsDescription-eng",
    "gsinDescription-nibsDescription-fra",
    "unspsc",
    "unspscDescription-eng",
    "unspscDescription-fra",
    "procurementCategory-categorieApprovisionnement",
    "noticeType-avisType-eng",
    "noticeType-avisType-fra",
    "procurementMethod-methodeApprovisionnement-eng",
    "procurementMethod-methodeApprovisionnement-fra",
    "selectionCriteria-criteresSelection-eng",
    "selectionCriteria-criteresSelection-fra",
    "limitedTenderingReason-raisonAppelOffresLimite-eng",
    "limitedTenderingReason-raisonAppelOffresLimite-fra",
    "tradeAgreements-accordsCommerciaux-eng",
    "tradeAgreements-accordsCommerciaux-fra",
    "regionsOfDelivery-regionsLivraison-eng",
    "regionsOfDelivery-regionsLivraison-fra",
    "supplierLegalName-nomLegalFournisseur-eng",
    "supplierAddressLine-ligneAdresseFournisseur-eng",
    "supplierAddressCity-fournisseurAdresseVille-eng",
    "supplierAddressProvince-fournisseurAdresseProvince-eng",
    "supplierAddressPostalCode-fournisseurAdresseCodePostal",
    "supplierAddressCountry-fournisseurAdressePays-eng",
    "supplierLegalName-nomLegalFournisseur-fra",
    "supplierAddressLine-ligneAdresseFournisseur-fra",
    "supplierAddressCity-fournisseurAdresseVille-fra",
    "supplierAddressProvince-fournisseurAdresseProvince-fra",
    "supplierAddressCountry-fournisseurAdressePays-fra",
    "contractingEntityName-nomEntitContractante-eng",
    "contractingEntityAddressLine-ligneAdresseEntiteContractante-eng",
    "contractingEntityAddressCity-entiteContractanteAdresseVille-eng",
    "contractingEntityAddressProvince-entiteContractanteAdresseProvince-eng",
    "contractingEntityAddressPostalCode-entiteContractanteAdresseCodePostal",
    "contractingEntityAddressCountry-entiteContractanteAdressePays-eng",
    "contractingEntityName-nomEntitContractante-fra",
    "contractingEntityAddressLine-ligneAdresseEntiteContractante-fra",
    "contractingEntityAddressCity-entiteContractanteAdresseVille-fra",
    "contractingEntityAddressProvince-entiteContractanteAdresseProvince-fra",
    "contractingEntityAddressCountry-entiteContractanteAdressePays-fra",
    "endUserEntitiesName-nomEntitesUtilisateurFinal-eng",
    "endUserEntitiesAddress-adresseEntitesUtilisateurFinal-eng",
    "endUserEntitiesName-nomEntitesUtilisateurFinal-fra",
    "endUserEntitiesAddress-adresseEntitesUtilisateurFinal-fra",
    "contactInfoName-informationsContactNom",
    "contactInfoEmail-informationsContactCourriel",
    "contactInfoPhone-contactInfoTelephone",
    "contactInfoFax",
    "contactInfoAddressLine-contactInfoAdresseLigne-eng",
    "contactInfoCity-contacterInfoVille-eng",
    "contactInfoProvince-contacterInfoProvince-eng",
    "contactInfoPostalcode",
    "contactInfoCountry-contactInfoPays-eng",
    "contactInfoAddressLine-contactInfoAdresseLigne-fra",
    "contactInfoCity-contacterInfoVille-fra",
    "contactInfoProvince-contacterInfoProvince-fra",
    "contactInfoCountry-contactInfoPays-fra",
    "awardDescription-descriptionAttribution-eng",
    "awardDescription-descriptionAttribution-fra",
]


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def normalize_supplier_country(value: str) -> str:
    cleaned = _clean(value)
    upper = cleaned.upper()
    if upper in EU27_ISO2_TO_NAME:
        return EU27_ISO2_TO_NAME[upper]
    if upper in {"CA", "CAN"} or cleaned.casefold() == "canada":
        return "Canada"
    if upper in {"US", "USA"} or cleaned.casefold() in {
        "united states",
        "united states of america",
    }:
        return "United States"
    if upper in {"GB", "UK"} or cleaned.casefold() == "united kingdom":
        return "United Kingdom"
    normalized = normalize_country(cleaned)
    return normalized


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    sha256: str
    byte_count: int
    source_url: str


@dataclass(frozen=True, slots=True)
class CanadaBuysAwardRecord:
    title: str
    reference_number: str
    amendment_number: str
    solicitation_number: str
    contract_number: str
    publication_date: str
    contract_award_date: str
    amendment_date: str
    contract_start_date: str
    contract_end_date: str
    contract_amount: str
    total_contract_value: str
    contract_currency: str
    award_status: str
    instrument_type: str
    amendment_type: str
    gsin: str
    gsin_description: str
    unspsc: str
    unspsc_description: str
    procurement_category: str
    notice_type: str
    procurement_method: str
    selection_criteria: str
    limited_tendering_reason: str
    trade_agreements: str
    regions_of_delivery: str
    supplier_legal_name: str
    supplier_address_line: str
    supplier_city: str
    supplier_province: str
    supplier_postal_code: str
    supplier_country_raw: str
    supplier_country: str
    contracting_entity_name: str
    contracting_entity_city: str
    contracting_entity_province: str
    award_description: str
    raw_json: str
    source_url: str

    @property
    def record_id(self) -> str:
        material = "\x1f".join([self.reference_number, self.amendment_number])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @property
    def raw_hash(self) -> str:
        return hashlib.sha256(self.raw_json.encode("utf-8")).hexdigest()

    @property
    def is_eu27_supplier(self) -> bool:
        return self.supplier_country in EU27


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 "
            "AtlanticBridge-Signals/0.1"
        ),
        "Accept-Language": "en-CA,en;q=0.9",
    }


def download_awards_csv(
    destination: str | Path,
    *,
    source_url: str = CURRENT_AWARDS_URL,
    timeout: int = 120,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> DownloadResult:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cookie_jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    headers = _browser_headers()

    def open_with_retry(request: Request):
        for attempt in range(1, attempts + 1):
            try:
                return opener.open(request, timeout=timeout)
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt >= attempts:
                    raise
            except (TimeoutError, URLError):
                if attempt >= attempts:
                    raise
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    # The public file endpoint currently rejects cold requests from standard
    # GitHub runners. Establish the same public session used by the data page.
    with open_with_retry(Request(PAGE_URL, headers=headers)) as response:
        response.read(1)

    request = Request(
        source_url,
        headers={
            **headers,
            "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
            "Referer": PAGE_URL,
        },
    )

    digest = hashlib.sha256()
    byte_count = 0
    temp_path = destination.with_suffix(destination.suffix + ".part")
    try:
        with open_with_retry(request) as response, temp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                byte_count += len(chunk)
                handle.write(chunk)
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return DownloadResult(
        path=destination,
        sha256=digest.hexdigest(),
        byte_count=byte_count,
        source_url=source_url,
    )


def iter_awards_csv(
    path: str | Path,
    *,
    source_url: str = CURRENT_AWARDS_URL,
):
    seen_keys: set[tuple[str, str]] = set()

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_HEADER:
            raise ValueError(
                "CanadaBuys award schema changed. "
                f"Expected {EXPECTED_HEADER!r}, received {reader.fieldnames!r}"
            )

        for row in reader:
            reference = _clean(row["referenceNumber-numeroReference"])
            amendment = _clean(row["amendmentNumber-numeroModification"])
            if not reference:
                raise ValueError("CanadaBuys award row missing reference number")

            key = (reference, amendment)
            if key in seen_keys:
                raise ValueError(
                    "CanadaBuys award file contains duplicate "
                    f"(reference, amendment) key {key!r}"
                )
            seen_keys.add(key)

            raw_json = json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            country_raw = _clean(
                row["supplierAddressCountry-fournisseurAdressePays-eng"]
            )

            yield CanadaBuysAwardRecord(
                title=_clean(row["title-titre-eng"]),
                reference_number=reference,
                amendment_number=amendment,
                solicitation_number=_clean(
                    row["solicitationNumber-numeroSollicitation"]
                ),
                contract_number=_clean(row["contractNumber-numeroContrat"]),
                publication_date=_clean(row["publicationDate-datePublication"]),
                contract_award_date=_clean(
                    row["contractAwardDate-dateAttributionContrat"]
                ),
                amendment_date=_clean(row["amendmentDate-dateModification"]),
                contract_start_date=_clean(row["contractStartDate-contratDateDebut"]),
                contract_end_date=_clean(row["contractEndDate-dateFinContrat"]),
                contract_amount=_clean(row["contractAmount-montantContrat"]),
                total_contract_value=_clean(
                    row["totalContractValue-valeurTotaleContrat"]
                ),
                contract_currency=_clean(row["contractCurrency-contratMonnaie"]),
                award_status=_clean(row["awardStatus-attributionStatut-eng"]),
                instrument_type=_clean(row["instrumentType-typeInstrument-eng"]),
                amendment_type=_clean(row["amendmentType-typeModification-eng"]),
                gsin=_clean(row["gsin-nibs"]),
                gsin_description=_clean(
                    row["gsinDescription-nibsDescription-eng"]
                ),
                unspsc=_clean(row["unspsc"]),
                unspsc_description=_clean(row["unspscDescription-eng"]),
                procurement_category=_clean(
                    row["procurementCategory-categorieApprovisionnement"]
                ),
                notice_type=_clean(row["noticeType-avisType-eng"]),
                procurement_method=_clean(
                    row["procurementMethod-methodeApprovisionnement-eng"]
                ),
                selection_criteria=_clean(
                    row["selectionCriteria-criteresSelection-eng"]
                ),
                limited_tendering_reason=_clean(
                    row["limitedTenderingReason-raisonAppelOffresLimite-eng"]
                ),
                trade_agreements=_clean(
                    row["tradeAgreements-accordsCommerciaux-eng"]
                ),
                regions_of_delivery=_clean(
                    row["regionsOfDelivery-regionsLivraison-eng"]
                ),
                supplier_legal_name=_clean(
                    row["supplierLegalName-nomLegalFournisseur-eng"]
                ),
                supplier_address_line=_clean(
                    row["supplierAddressLine-ligneAdresseFournisseur-eng"]
                ),
                supplier_city=_clean(
                    row["supplierAddressCity-fournisseurAdresseVille-eng"]
                ),
                supplier_province=_clean(
                    row["supplierAddressProvince-fournisseurAdresseProvince-eng"]
                ),
                supplier_postal_code=_clean(
                    row["supplierAddressPostalCode-fournisseurAdresseCodePostal"]
                ),
                supplier_country_raw=country_raw,
                supplier_country=normalize_supplier_country(country_raw),
                contracting_entity_name=_clean(
                    row["contractingEntityName-nomEntitContractante-eng"]
                ),
                contracting_entity_city=_clean(
                    row[
                        "contractingEntityAddressCity-entiteContractanteAdresseVille-eng"
                    ]
                ),
                contracting_entity_province=_clean(
                    row[
                        "contractingEntityAddressProvince-entiteContractanteAdresseProvince-eng"
                    ]
                ),
                award_description=_clean(
                    row["awardDescription-descriptionAttribution-eng"]
                ),
                raw_json=raw_json,
                source_url=source_url,
            )
