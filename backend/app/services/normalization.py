"""Shared normalization helpers for company matching/deduplication.

These never mutate or discard the original raw values a caller holds onto —
they only derive comparison keys (normalized_name, phone_normalized, domain)
that get stored alongside the raw fields.
"""

import re
import urllib.parse

_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|plc|pllc|pc|p\.c)\.?\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Two-letter code -> full name, used to compare a geocoder's returned state
# against whatever form the spreadsheet used (either is common in real data).
US_STATE_ABBREVIATIONS: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
_STATE_NAME_TO_ABBR = {name.lower(): abbr for abbr, name in US_STATE_ABBREVIATIONS.items()}


def normalize_company_name(name: str) -> str:
    cleaned = _COMPANY_SUFFIXES.sub("", name.lower())
    cleaned = _NON_ALNUM.sub(" ", cleaned).strip()
    return re.sub(r"\s+", " ", cleaned)


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def normalize_state(state: str | None) -> str | None:
    """Return a 2-letter US state code regardless of whether the input was
    already an abbreviation ("NC") or a full name ("North Carolina")."""
    if not state:
        return None
    cleaned = state.strip()
    if not cleaned:
        return None
    if len(cleaned) == 2:
        return cleaned.upper()
    return _STATE_NAME_TO_ABBR.get(cleaned.lower())


def normalize_city(city: str | None) -> str | None:
    if not city:
        return None
    cleaned = re.sub(r"\s+", " ", city.strip().lower())
    return cleaned or None


def build_address_string(
    *,
    address_line_1: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
) -> str | None:
    """Join address parts into one normalized string for geocoding.

    Whitespace/punctuation is normalized but individual parts are trusted as
    given (no reformatting of the street itself) — this just assembles them
    into a consistent "Street, City, State ZIP, Country" shape so a provider
    sees the same structure regardless of which spreadsheet columns existed.
    """
    parts: list[str] = []
    if address_line_1:
        parts.append(re.sub(r"\s+", " ", address_line_1.strip().rstrip(",")))
    locality = ", ".join(filter(None, [city.strip() if city else None, state.strip() if state else None]))
    if postal_code:
        locality = f"{locality} {postal_code.strip()}".strip()
    if locality:
        parts.append(locality)
    if country:
        parts.append(country.strip())
    if not parts:
        return None
    return ", ".join(parts)


_TRAILING_CITY_STATE_ZIP = re.compile(
    r"^(?P<street>.+?),\s*"
    r"(?P<city>[A-Za-z][A-Za-z .'-]*?),\s*"
    r"(?P<state>[A-Za-z]{2}|[A-Za-z][A-Za-z ]+[A-Za-z])"
    r"(?:\s+(?P<zip>\d{5}(?:-\d{4})?))?\s*$"
)


def parse_combined_address(address: str) -> dict[str, str | None]:
    """Split a single "Street, City, State ZIP" style address string (the
    common shape when a spreadsheet has one Address column instead of
    separate Street/City/State/ZIP columns) into its parts.

    Only ever used to fill in city/state/zip that weren't already given by
    a dedicated column — never overwrites a value the importer already has.
    Returns the original string unchanged as `street` if it doesn't match
    the expected shape (e.g. a street-only address with no city/state).
    """
    match = _TRAILING_CITY_STATE_ZIP.match(address.strip())
    if not match:
        return {"street": address.strip(), "city": None, "state": None, "postal_code": None}
    return {
        "street": match.group("street").strip(),
        "city": match.group("city").strip(),
        "state": match.group("state").strip(),
        "postal_code": match.group("zip"),
    }


def extract_domain(website: str | None) -> str | None:
    if not website:
        return None
    candidate = website.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"http://{candidate}"
    try:
        netloc = urllib.parse.urlparse(candidate).netloc.lower()
    except ValueError:
        return None
    netloc = netloc.split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None
