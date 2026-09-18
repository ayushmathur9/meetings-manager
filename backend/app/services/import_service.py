"""Excel/CSV import pipeline: parse -> map -> validate -> dedupe -> verify -> persist.

Raw uploaded values are always preserved in ImportRow.raw_data, even after
column mapping and normalization, so nothing the admin uploaded is ever lost
(spec: "do not destroy original raw values").
"""

import io
import re
import uuid
from datetime import datetime, timezone

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.company import Company, CompanyStatus
from app.models.contact import Contact
from app.models.import_job import Import, ImportRow, ImportRowStatus, ImportStatus
from app.models.location import Location
from app.providers.location.base import LocationProvider
from app.services.activity_service import ActivityService
from app.services.location_service import LocationService
from app.services.normalization import (
    extract_domain,
    normalize_company_name,
    normalize_phone,
    parse_combined_address,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^(https?://)?([\w-]+\.)+[\w-]+(/.*)?$", re.IGNORECASE)

MAPPABLE_FIELDS = [
    "company_name",
    "legal_name",
    "industry",
    "website",
    "phone",
    "email",
    "employee_count",
    "address_line_1",
    "city",
    "state",
    "postal_code",
    "country",
    "contact_first_name",
    "contact_last_name",
    "contact_full_name",
    "contact_title",
    "contact_email",
    "contact_phone",
    "contact_linkedin",
]

_AUTO_MAP_HINTS: dict[str, list[str]] = {
    "company_name": ["company name", "company", "business name", "account name"],
    "legal_name": ["legal name", "dba", "registered name"],
    "industry": ["industry", "vertical", "sector"],
    "website": ["website", "url", "domain"],
    "phone": ["phone", "company phone", "main phone", "telephone"],
    "email": ["email", "company email", "general email"],
    "employee_count": ["employees", "employee count", "headcount", "# employees"],
    "address_line_1": ["address", "street", "address line 1"],
    "city": ["city"],
    "state": ["state", "province"],
    "postal_code": ["zip", "zip code", "postal code"],
    "country": ["country"],
    "contact_first_name": ["first name", "contact first name"],
    "contact_last_name": ["last name", "contact last name"],
    "contact_full_name": ["contact name", "contact"],
    "contact_title": ["title", "job title", "position"],
    "contact_email": ["contact email", "personal email"],
    "contact_phone": ["contact phone", "mobile", "cell"],
    "contact_linkedin": ["linkedin", "linkedin url"],
}

DUPLICATE_NAME_THRESHOLD = 90


def suggest_column_mapping(columns: list[str]) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    used_columns: set[str] = set()
    for field, hints in _AUTO_MAP_HINTS.items():
        match = None
        for column in columns:
            if column in used_columns:
                continue
            normalized_column = column.strip().lower()
            if normalized_column in hints:
                match = column
                break
        if match is None:
            for column in columns:
                if column in used_columns:
                    continue
                normalized_column = column.strip().lower()
                if any(hint in normalized_column for hint in hints):
                    match = column
                    break
        if match:
            mapping[field] = match
            used_columns.add(match)
        else:
            mapping[field] = None
    return mapping


def parse_spreadsheet(filename: str, content: bytes) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    elif lower.endswith(".xlsx") or lower.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
        df = df.fillna("")
    else:
        raise ValueError("Unsupported file type. Please upload .xlsx, .xls, or .csv")
    df.columns = [str(c).strip() for c in df.columns]
    return df


class ImportService:
    def __init__(self, db: Session, location_provider: LocationProvider) -> None:
        self.db = db
        self.location_provider = location_provider

    def create_import(self, *, filename: str, imported_by_id: uuid.UUID, row_count: int) -> Import:
        import_job = Import(
            filename=filename,
            imported_by_id=imported_by_id,
            row_count=row_count,
            status=ImportStatus.PENDING,
        )
        self.db.add(import_job)
        self.db.flush()
        return import_job

    def store_raw_rows(self, import_job: Import, df: pd.DataFrame) -> None:
        for i, row in df.iterrows():
            self.db.add(
                ImportRow(
                    import_id=import_job.id,
                    row_number=int(i) + 1,
                    raw_data=row.to_dict(),
                    status=ImportRowStatus.VALID,
                )
            )
        self.db.flush()

    def apply_mapping_and_validate(self, import_job: Import, mapping: dict[str, str]) -> None:
        import_job.column_mapping = mapping
        rows = list(import_job.rows)

        seen_normalized_names: dict[str, int] = {}
        seen_phones: dict[str, int] = {}
        seen_domains: dict[str, int] = {}

        error_count = 0
        duplicate_count = 0
        valid_count = 0

        for row in rows:
            mapped = self._map_row(row.raw_data, mapping)
            row.mapped_data = mapped

            error = self._validate_row(mapped)
            if error:
                row.status = ImportRowStatus.ERROR
                row.error_reason = error
                error_count += 1
                continue

            dup_key = self._duplicate_signal(mapped, seen_normalized_names, seen_phones, seen_domains)
            if dup_key:
                row.status = ImportRowStatus.DUPLICATE
                row.error_reason = f"Possible duplicate: matches an earlier row on {dup_key}"
                duplicate_count += 1
                continue

            normalized_name = normalize_company_name(mapped["company_name"])
            phone_normalized = normalize_phone(mapped.get("phone"))
            domain = extract_domain(mapped.get("website"))

            fuzzy_match = None
            for existing_name in seen_normalized_names:
                if fuzz.token_sort_ratio(existing_name, normalized_name) >= DUPLICATE_NAME_THRESHOLD:
                    fuzzy_match = existing_name
                    break
            if fuzzy_match:
                row.status = ImportRowStatus.DUPLICATE
                row.error_reason = f"Possible duplicate: name closely matches '{fuzzy_match}'"
                duplicate_count += 1
                continue

            seen_normalized_names[normalized_name] = row.row_number
            if phone_normalized:
                seen_phones[phone_normalized] = row.row_number
            if domain:
                seen_domains[domain] = row.row_number

            row.status = ImportRowStatus.VALID
            row.error_reason = None
            valid_count += 1

        import_job.error_count = error_count
        import_job.duplicate_count = duplicate_count
        import_job.success_count = valid_count
        self.db.flush()

    def _map_row(self, raw: dict, mapping: dict[str, str]) -> dict:
        mapped = {}
        for field, column in mapping.items():
            if column and column in raw:
                value = raw[column]
                mapped[field] = value.strip() if isinstance(value, str) else value
        return mapped

    def _validate_row(self, mapped: dict) -> str | None:
        if not mapped.get("company_name"):
            return "Company name is missing"
        email = mapped.get("email") or mapped.get("contact_email")
        if email and not _EMAIL_RE.match(email):
            return f"Invalid email: {email}"
        website = mapped.get("website")
        if website and not _URL_RE.match(website):
            return f"Invalid website URL: {website}"
        return None

    def _duplicate_signal(
        self,
        mapped: dict,
        seen_names: dict[str, int],
        seen_phones: dict[str, int],
        seen_domains: dict[str, int],
    ) -> str | None:
        normalized_name = normalize_company_name(mapped["company_name"])
        if normalized_name in seen_names:
            return "company name"
        phone_normalized = normalize_phone(mapped.get("phone"))
        if phone_normalized and phone_normalized in seen_phones:
            return "phone number"
        domain = extract_domain(mapped.get("website"))
        if domain and domain in seen_domains:
            return "website domain"
        return None

    def check_existing_company_duplicates(self, import_job: Import) -> None:
        for row in import_job.rows:
            if row.status != ImportRowStatus.VALID or not row.mapped_data:
                continue
            mapped = row.mapped_data
            normalized_name = normalize_company_name(mapped["company_name"])
            phone_normalized = normalize_phone(mapped.get("phone"))
            domain = extract_domain(mapped.get("website"))

            existing = (
                self.db.query(Company).filter(Company.normalized_name == normalized_name).first()
            )
            if existing is None and phone_normalized:
                existing = (
                    self.db.query(Company)
                    .filter(Company.phone_normalized == phone_normalized)
                    .first()
                )
            if existing is None and domain:
                existing = self.db.query(Company).filter(Company.domain == domain).first()

            if existing is not None:
                row.status = ImportRowStatus.DUPLICATE
                row.error_reason = f"Matches existing company: {existing.name}"
                row.duplicate_of_company_id = existing.id

        import_job.duplicate_count = sum(
            1 for r in import_job.rows if r.status == ImportRowStatus.DUPLICATE
        )
        import_job.success_count = sum(
            1 for r in import_job.rows if r.status == ImportRowStatus.VALID
        )
        self.db.flush()

    def confirm_import(self, import_job: Import, *, verify_locations: bool = True) -> Import:
        import_job.status = ImportStatus.PROCESSING
        import_job.started_at = datetime.now(timezone.utc)
        self.db.flush()

        location_service = LocationService(self.db, self.location_provider)
        activity_service = ActivityService(self.db)

        for row in import_job.rows:
            if row.status != ImportRowStatus.VALID:
                continue
            mapped = row.mapped_data

            # Re-check for a same-named company right before creating one.
            # The mapping-step duplicate check (check_existing_company_duplicates)
            # can go stale if another import is confirmed concurrently — a
            # second import's mapping check can run before the first import's
            # confirm has finished inserting its companies. This catches that
            # race instead of silently creating a duplicate company.
            normalized_name = normalize_company_name(mapped["company_name"])
            existing = (
                self.db.query(Company).filter(Company.normalized_name == normalized_name).first()
            )
            if existing is not None:
                row.status = ImportRowStatus.DUPLICATE
                row.error_reason = f"Matches existing company: {existing.name}"
                row.duplicate_of_company_id = existing.id
                continue

            company = Company(
                name=mapped["company_name"],
                legal_name=mapped.get("legal_name"),
                normalized_name=normalize_company_name(mapped["company_name"]),
                industry=mapped.get("industry"),
                website=mapped.get("website"),
                domain=extract_domain(mapped.get("website")),
                phone=mapped.get("phone"),
                phone_normalized=normalize_phone(mapped.get("phone")),
                email=mapped.get("email"),
                employee_count=self._safe_int(mapped.get("employee_count")),
                status=CompanyStatus.NEW,
                is_demo=False,
                source_import_id=import_job.id,
            )
            self.db.add(company)
            self.db.flush()
            row.created_company_id = company.id
            row.status = ImportRowStatus.IMPORTED

            raw_address = mapped.get("address_line_1")
            city = mapped.get("city")
            state = mapped.get("state")
            postal_code = mapped.get("postal_code")
            country = mapped.get("country")

            # A single combined "Address" column (no dedicated City/State/ZIP
            # columns) is common in real spreadsheets. Split city/state/zip out
            # of it so the geographic sanity check in verify_company_location
            # has something to compare the geocoder's result against — without
            # this, a wrong-city match can't be caught for these rows.
            if raw_address and not (city or state):
                parsed = parse_combined_address(raw_address)
                if parsed["city"] and parsed["state"]:
                    raw_address = parsed["street"]
                    city = parsed["city"]
                    state = parsed["state"]
                    postal_code = postal_code or parsed["postal_code"]

            if verify_locations and (raw_address or city or state):
                try:
                    location, candidates, reason = location_service.verify_company_location(
                        company_id=company.id,
                        company_name=company.name,
                        raw_address=raw_address,
                        city=city,
                        state=state,
                        postal_code=postal_code,
                        country=country,
                    )
                    if location is None:
                        if not reason:
                            reason = (
                                f"{len(candidates)} possible match(es) found — none confident enough"
                                if candidates
                                else "No matching location found"
                            )
                        location_service.mark_needs_verification(
                            company_id=company.id,
                            raw_address=raw_address,
                            notes=reason,
                            city=city,
                            state=state,
                            postal_code=postal_code,
                            country=country,
                        )
                except Exception as exc:
                    location_service.mark_failed(
                        company_id=company.id,
                        raw_address=raw_address,
                        notes=f"Location lookup failed: {exc}",
                        city=city,
                        state=state,
                        postal_code=postal_code,
                        country=country,
                    )
            elif raw_address or city or state:
                self.db.add(
                    Location(
                        company_id=company.id,
                        is_primary=True,
                        address_line_1=raw_address,
                        city=city,
                        state=state,
                        postal_code=mapped.get("postal_code"),
                        country=mapped.get("country") or "USA",
                    )
                )

            if mapped.get("contact_full_name") or mapped.get("contact_first_name"):
                self.db.add(
                    Contact(
                        company_id=company.id,
                        first_name=mapped.get("contact_first_name"),
                        last_name=mapped.get("contact_last_name"),
                        full_name=mapped.get("contact_full_name")
                        or " ".join(
                            filter(
                                None,
                                [mapped.get("contact_first_name"), mapped.get("contact_last_name")],
                            )
                        ),
                        title=mapped.get("contact_title"),
                        email=mapped.get("contact_email"),
                        phone=mapped.get("contact_phone"),
                        linkedin_url=mapped.get("contact_linkedin"),
                        source="import",
                    )
                )

            activity_service.log(
                user_id=import_job.imported_by_id,
                entity_type="company",
                entity_id=company.id,
                action="imported",
                metadata={"import_id": str(import_job.id), "filename": import_job.filename},
            )

        import_job.status = ImportStatus.COMPLETED
        import_job.completed_at = datetime.now(timezone.utc)
        import_job.success_count = sum(
            1 for r in import_job.rows if r.status == ImportRowStatus.IMPORTED
        )
        import_job.duplicate_count = sum(
            1 for r in import_job.rows if r.status == ImportRowStatus.DUPLICATE
        )
        self.db.flush()
        return import_job

    @staticmethod
    def _safe_int(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
