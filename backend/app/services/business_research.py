"""Gathers the evidence a business summary is allowed to use.

Sources, each given a short ref ("S1", "S2", ...) the summary must cite:
  * crm      — what we already hold: name, industry, website, size fields
               (entered by people / synced from Bigin; marked as internal)
  * location — the geocoder-verified address, only when VERIFIED
  * website  — the company's own site: the homepage plus up to a few pages
               whose links look like about / services / locations / team,
               reduced to visible text + schema.org JSON-LD

Deliberately conservative: only the company's own domain is crawled, robots.txt
is honoured, every hop is checked against private/loopback addresses (no
SSRF into the backend's network), responses are size- and time-capped, and
nothing is inferred here — this module only collects and labels text.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings
from app.models.company import Company
from app.models.location import VerificationStatus

logger = logging.getLogger("app.research")

USER_AGENT = "MeetingsManagerResearch/1.0 (business overview for scheduled sales meetings)"
MAX_BYTES = 2_000_000
MAX_TEXT_PER_PAGE = 6000
MAX_REDIRECTS = 4

_PAGE_KEYWORDS = {
    "about": 6, "who-we-are": 6, "our-story": 5, "company": 3, "services": 5, "solutions": 4,
    "what-we-do": 5, "locations": 6, "offices": 5, "find-us": 4, "team": 3, "providers": 4,
    "physicians": 4, "doctors": 4, "staff": 3, "leadership": 3, "careers": 2, "industries": 3,
    "specialties": 4, "practice": 3, "contact": 2,
}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}
_JSONLD_KEYS = (
    "@type", "name", "legalName", "description", "url", "telephone", "address", "numberOfEmployees",
    "areaServed", "foundingDate", "medicalSpecialty", "department", "location", "sameAs",
)


class ResearchFetchError(Exception):
    pass


@dataclass
class Source:
    ref: str
    source_type: str  # "crm" | "location" | "website"
    title: str | None
    url: str | None
    content: dict
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.content, sort_keys=True, default=str).encode()).hexdigest()

    def as_prompt_dict(self) -> dict:
        return {"ref": self.ref, "type": self.source_type, "title": self.title, "url": self.url, **self.content}


@dataclass
class ResearchBundle:
    company_name: str
    sources: list[Source]
    website_status: str  # "fetched" | "no_website" | "failed:<reason>" | "blocked_by_robots"

    @property
    def has_public_sources(self) -> bool:
        return any(s.source_type == "website" for s in self.sources)

    def to_json(self) -> dict:
        return {
            "company_name": self.company_name,
            "website_status": self.website_status,
            "sources": [s.as_prompt_dict() for s in self.sources],
        }


# ------------------------------------------------------------------ HTML
class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self.links: list[tuple[str, str]] = []
        self.jsonld: list[str] = []
        self._text: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_jsonld = False
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self.jsonld.append("")
            return
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("description", "og:description") and a.get("content") and not self.description:
                self.description = a["content"].strip()
        elif tag == "a" and a.get("href"):
            self._link_href = a["href"]
            self._link_text = []
        elif tag in ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "section", "tr", "address"):
            self._text.append("\n")

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            return
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._link_href is not None:
            self.links.append((self._link_href, " ".join(self._link_text).strip()))
            self._link_href = None

    def handle_data(self, data):
        if self._in_jsonld:
            self.jsonld[-1] += data
            return
        if self._skip:
            return
        if self._in_title:
            self.title = (self.title or "") + data.strip()
            return
        self._text.append(data)
        if self._link_href is not None:
            self._link_text.append(data.strip())

    @property
    def text(self) -> str:
        raw = "".join(self._text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.split("\n")]
        return "\n".join(line for line in lines if len(line) > 1)


def _structured_data(blobs: list[str]) -> list[dict]:
    """schema.org Organization/LocalBusiness-style objects, trimmed to the
    fields useful for a business overview."""
    found: list[dict] = []

    def visit(node):
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            if "@graph" in node:
                visit(node["@graph"])
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(isinstance(t, str) and t not in ("WebSite", "WebPage", "BreadcrumbList", "ImageObject",
                                                     "SearchAction", "ReadAction", "ListItem") for t in types):
                trimmed = {k: node[k] for k in _JSONLD_KEYS if k in node}
                if len(trimmed) > 1:
                    found.append(trimmed)

    for blob in blobs:
        try:
            visit(json.loads(blob))
        except (ValueError, TypeError):
            continue
    return found[:5]


# ---------------------------------------------------------------- fetching
def _check_public_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ResearchFetchError("unsupported URL")
    if parsed.port not in (None, 80, 443):
        raise ResearchFetchError("non-standard port")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ResearchFetchError("domain does not resolve") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ResearchFetchError("domain resolves to a private address")


class WebsiteFetcher:
    def __init__(self, http: httpx.Client | None = None, *, check_host=_check_public_host) -> None:
        settings = get_settings()
        self.http = http or httpx.Client(
            timeout=settings.research_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        self.check_host = check_host
        self._robots: dict[str, RobotFileParser | None] = {}

    def get(self, url: str) -> tuple[str, str]:
        """Fetch an HTML page, following redirects with each hop re-checked.
        Returns (final_url, html)."""
        for _ in range(MAX_REDIRECTS + 1):
            self.check_host(url)
            try:
                with self.http.stream("GET", url) as res:
                    if res.status_code in (301, 302, 303, 307, 308) and res.headers.get("location"):
                        url = urljoin(url, res.headers["location"])
                        continue
                    if res.status_code != 200:
                        raise ResearchFetchError(f"HTTP {res.status_code}")
                    ctype = res.headers.get("content-type", "")
                    if "html" not in ctype and "xml" not in ctype:
                        raise ResearchFetchError("not an HTML page")
                    body = b""
                    for chunk in res.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return url, body.decode(res.encoding or "utf-8", errors="replace")
            except httpx.HTTPError as exc:
                raise ResearchFetchError(type(exc).__name__) from exc
        raise ResearchFetchError("too many redirects")

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                self.check_host(origin + "/robots.txt")
                res = self.http.get(origin + "/robots.txt")
                if res.status_code == 200:
                    parser.parse(res.text.splitlines())
                elif res.status_code in (401, 403):
                    parser.disallow_all = True
                else:
                    parser = None  # no robots.txt — everything allowed
            except (httpx.HTTPError, ResearchFetchError):
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(USER_AGENT, url)


def normalize_website(website: str | None) -> str | None:
    if not website or not website.strip():
        return None
    url = website.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.hostname or "." not in parsed.hostname:
        return None
    return url


def _same_site(host_a: str | None, host_b: str | None) -> bool:
    if not host_a or not host_b:
        return False
    a, b = host_a.lower().removeprefix("www."), host_b.lower().removeprefix("www.")
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _candidate_pages(base_url: str, links: list[tuple[str, str]], limit: int) -> list[str]:
    base_host = urlparse(base_url).hostname
    scored: dict[str, int] = {}
    for href, label in links:
        url = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not _same_site(parsed.hostname, base_host):
            continue
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|zip|docx?|xlsx?)$", parsed.path, re.IGNORECASE):
            continue
        # Match on the page's own slug and its link label — not on parent
        # folders (".../city-services/all-departments/trash-pickup" is not a
        # services overview) — and prefer shallow, site-level pages.
        segments = [s for s in parsed.path.lower().split("/") if s]
        haystack = f"{segments[-1] if segments else ''} {label.lower().replace(' ', '-')}"
        score = max((w for k, w in _PAGE_KEYWORDS.items() if k in haystack), default=0)
        score -= max(len(segments) - 1, 0) * 2
        if score > 0 and url.rstrip("/") != base_url.rstrip("/"):
            scored[url] = max(scored.get(url, 0), score)
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])][:limit]


# ----------------------------------------------------------------- gather
def gather_research(company: Company, fetcher: WebsiteFetcher | None = None) -> ResearchBundle:
    settings = get_settings()
    sources: list[Source] = []

    def add(source_type, title, url, content) -> None:
        sources.append(Source(ref=f"S{len(sources) + 1}", source_type=source_type, title=title, url=url, content=content))

    crm = {
        "note": "Internal CRM record (entered by staff or synced from Bigin) — not independently verified.",
        "name": company.name,
        "industry": company.industry,
        "website": company.website,
        "employee_count": company.employee_count,
        "location_count": company.location_count,
        "parent_company": company.parent_company,
    }
    add("crm", "CRM record", None, {k: v for k, v in crm.items() if v not in (None, "")})

    primary = next((loc for loc in company.locations if loc.is_primary), None)
    if primary and primary.verification_status == VerificationStatus.VERIFIED and primary.formatted_address:
        add("location", "Verified business address", None, {
            "address": primary.formatted_address,
            "geocoder": primary.provider,
        })

    website = normalize_website(company.website)
    if website is None:
        return ResearchBundle(company.name, sources, "no_website")

    fetcher = fetcher or WebsiteFetcher()
    try:
        if not fetcher.allowed(website):
            return ResearchBundle(company.name, sources, "blocked_by_robots")
        final_url, html = fetcher.get(website)
    except ResearchFetchError as exc:
        logger.info("Research: website for %s not fetched: %s", company.name, exc)
        return ResearchBundle(company.name, sources, f"failed:{exc}")

    pages = [(final_url, html)]
    home = _PageParser()
    home.feed(html)
    for url in _candidate_pages(final_url, home.links, max(settings.research_max_pages - 1, 0)):
        try:
            if fetcher.allowed(url):
                pages.append(fetcher.get(url))
        except ResearchFetchError:
            continue

    for url, page_html in pages:
        parser = home if url == final_url else _PageParser()
        if parser is not home:
            parser.feed(page_html)
        content = {
            "description": parser.description,
            "structured_data": _structured_data(parser.jsonld) or None,
            "text": parser.text[:MAX_TEXT_PER_PAGE],
        }
        add("website", (parser.title or url)[:300], url, {k: v for k, v in content.items() if v})

    return ResearchBundle(company.name, sources, "fetched")
