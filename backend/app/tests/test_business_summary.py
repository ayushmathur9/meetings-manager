"""Business research + summaries: website gathering, citation enforcement,
no-website / failure paths, and the API. Network and LLM are faked."""

import json

import httpx
import pytest

from app.models.company import Company
from app.models.company_research import CompanyResearch, ResearchStatus
from app.services import background
from app.services.business_research import ResearchFetchError, WebsiteFetcher, _check_public_host, gather_research
from app.services.business_summary import BusinessSummaryService, SummaryError, SummaryResult, validate_summary

HOME = """<html><head><title>Eastern Dermatology | Wilson NC</title>
<meta name="description" content="Board-certified dermatology care in eastern North Carolina.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"MedicalBusiness",
 "name":"Eastern Dermatology","telephone":"252-555-0100","medicalSpecialty":"Dermatology"}</script>
<script>var tracking = "ignore me";</script></head>
<body><nav><a href="/about-us">About Us</a> <a href="/locations">Our Locations</a>
<a href="https://facebook.com/x">FB</a> <a href="/brochure.pdf">PDF</a></nav>
<h1>Expert skin care</h1><p>Medical, surgical and cosmetic dermatology.</p></body></html>"""
ABOUT = "<html><head><title>About</title></head><body><p>Founded in 1998, we serve patients at three clinics.</p></body></html>"
LOCATIONS = "<html><body><p>Wilson, Greenville and Rocky Mount offices. Online patient portal available.</p></body></html>"


def site_fetcher(pages=None, robots="User-agent: *\nAllow: /", status=200):
    pages = pages or {"/": HOME, "/about-us": ABOUT, "/locations": LOCATIONS}

    def handler(request: httpx.Request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if status != 200:
            return httpx.Response(status)
        body = pages.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return WebsiteFetcher(http, check_host=lambda url: None)


class FakeSummarizer:
    name = "fake"
    model = "fake-model"

    def __init__(self, data=None, error=None, configured=True):
        self.data = data
        self.error = error
        self.configured = configured
        self.calls = []

    @property
    def is_configured(self):
        return self.configured

    def summarize(self, research):
        self.calls.append(research)
        if self.error:
            raise self.error
        return SummaryResult(data=self.data, provider=self.name, model=self.model)


GOOD_SUMMARY = {
    "what_they_do": {"text": "Dermatology practice offering medical, surgical and cosmetic skin care.", "source_refs": ["S2"]},
    "industry": {"text": "Dermatology practice", "source_refs": ["S2"]},
    "footprint": [
        {"text": "Three clinics: Wilson, Greenville and Rocky Mount, NC.", "source_refs": ["S3", "S4"]},
        {"text": "About 400 employees.", "source_refs": []},  # uncited -> dropped
    ],
    "it_relevance": [
        {"signal": "Multiple locations", "why_it_matters": "Three sites to network and support.", "source_refs": ["S4"]},
        {"signal": "Uses Epic EHR", "why_it_matters": "Invented.", "source_refs": ["S99"]},  # unknown ref -> dropped
    ],
    "confidence": "high",
    "insufficient_information": False,
    "caveats": "",
}


@pytest.fixture
def derm(db):
    company = Company(name="Eastern Dermatology", normalized_name="eastern dermatology", website="easternderm.example",
                      industry="Healthcare")
    db.add(company)
    db.flush()
    return company


def _run(db, company, summarizer, fetcher=None):
    service = BusinessSummaryService(db, provider=summarizer, fetcher=fetcher or site_fetcher())
    research = service.request(company)
    db.commit()
    return service.run(research)


def test_company_with_website_summarized_from_cited_sources(db, derm):
    summarizer = FakeSummarizer(GOOD_SUMMARY)
    research = _run(db, derm, summarizer)

    assert research.status == ResearchStatus.COMPLETED
    sent = summarizer.calls[0]
    types = [s["type"] for s in sent["sources"]]
    assert types == ["crm", "website", "website", "website"]  # homepage + about + locations; no PDF/off-site
    home = sent["sources"][1]
    assert home["structured_data"][0]["medicalSpecialty"] == "Dermatology"
    assert "ignore me" not in home["text"]  # scripts stripped
    assert research.summary.startswith("Dermatology practice")
    assert [f["text"] for f in research.summary_data["footprint"]] == ["Three clinics: Wilson, Greenville and Rocky Mount, NC."]
    assert research.sam_it_relevance == "Multiple locations: Three sites to network and support."
    assert [s.url for s in research.sources if s.source_type == "website"][0] == "https://easternderm.example"
    assert research.generated_at and research.model == "fake-model"


def test_company_without_website_makes_no_llm_call(db):
    company = Company(name="Mystery LLC", normalized_name="mystery llc")
    db.add(company)
    db.flush()
    summarizer = FakeSummarizer(GOOD_SUMMARY)
    research = _run(db, company, summarizer)
    assert summarizer.calls == []
    assert research.status == ResearchStatus.COMPLETED and research.summary is None
    assert research.summary_data["insufficient_information"] is True
    assert "No website" in research.summary_data["caveats"]


def test_unreachable_website_is_reported_not_invented(db, derm):
    summarizer = FakeSummarizer(GOOD_SUMMARY)
    research = _run(db, derm, summarizer, site_fetcher(status=503))
    assert summarizer.calls == []
    assert research.summary is None and "HTTP 503" in research.summary_data["caveats"]


def test_robots_disallow_is_honoured(db, derm):
    summarizer = FakeSummarizer(GOOD_SUMMARY)
    research = _run(db, derm, summarizer, site_fetcher(robots="User-agent: *\nDisallow: /"))
    assert summarizer.calls == [] and "robots.txt" in research.summary_data["caveats"]


def test_ai_failure_keeps_sources_and_reports_error(db, derm):
    research = _run(db, derm, FakeSummarizer(error=SummaryError("The AI provider is rate-limiting requests — try again shortly.")))
    assert research.status == ResearchStatus.FAILED and "rate-limiting" in research.error
    assert len(research.sources) == 4 and research.research_data["website_status"] == "fetched"


def test_ai_not_configured(db, derm):
    research = _run(db, derm, FakeSummarizer(configured=False))
    assert research.status == ResearchStatus.FAILED and "not configured" in research.error


def test_missing_research_data_yields_insufficient(db):
    data = validate_summary({"what_they_do": {"text": "Guess", "source_refs": []}, "footprint": [], "it_relevance": [],
                             "confidence": "bogus"}, {"S1"})
    assert data["what_they_do"] is None and data["insufficient_information"] is True and data["confidence"] == "low"


def test_ssrf_guard_blocks_private_hosts():
    for url in ("http://127.0.0.1/", "http://localhost/admin", "http://169.254.169.254/latest", "ftp://example.com"):
        with pytest.raises(ResearchFetchError):
            _check_public_host(url)


def test_research_api_auto_generates_and_refresh_keeps_previous_summary(db, derm, sales_client, monkeypatch):
    queued = []
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: queued.append(a[0]))

    first = sales_client.get(f"/companies/{derm.id}/research").json()
    assert first["status"] == "pending" and len(queued) == 1

    research = db.query(CompanyResearch).filter(CompanyResearch.company_id == derm.id).one()
    BusinessSummaryService(db, provider=FakeSummarizer(GOOD_SUMMARY), fetcher=site_fetcher()).run(research)
    done = sales_client.get(f"/companies/{derm.id}/research").json()
    assert done["status"] == "completed" and len(queued) == 1  # no regeneration on every view
    assert {s["ref"] for s in done["sources"]} == {"S1", "S2", "S3", "S4"}

    refreshed = sales_client.post(f"/companies/{derm.id}/research/refresh")
    assert refreshed.status_code == 202
    body = refreshed.json()
    assert body["status"] == "pending" and body["summary"] == done["summary"] and len(queued) == 2


def test_research_api_requires_auth_and_existing_company(anon_client, sales_client):
    import uuid

    assert anon_client.get(f"/companies/{uuid.uuid4()}/research").status_code == 401
    assert sales_client.get(f"/companies/{uuid.uuid4()}/research").status_code == 404


def test_stale_summary_regenerates_on_view(db, derm, sales_client, monkeypatch):
    from datetime import datetime, timedelta, timezone

    queued = []
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: queued.append(a[0]))
    research = CompanyResearch(company_id=derm.id, status=ResearchStatus.COMPLETED, summary="Old",
                               generated_at=datetime.now(timezone.utc) - timedelta(days=400))
    db.add(research)
    db.commit()
    body = sales_client.get(f"/companies/{derm.id}/research").json()
    assert body["status"] == "pending" and body["summary"] == "Old" and len(queued) == 1


def test_anthropic_provider_request_shape(monkeypatch):
    """The real provider: structured output schema + refusal fallback, and a
    refusal is reported, not stored as a summary."""
    import anthropic

    from app.services.business_summary import AnthropicSummaryProvider

    captured = {}

    def handler(request: httpx.Request):
        captured["body"] = json.loads(request.content)
        captured["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
            "content": [{"type": "text", "text": json.dumps(GOOD_SUMMARY)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        })

    real_client = anthropic.Anthropic

    def fake_client(**kwargs):
        import httpx2

        return real_client(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(
            lambda req: httpx2.Response(**_to_httpx2(handler(httpx.Request(req.method, str(req.url), headers=dict(req.headers), content=req.content))))
        )))

    monkeypatch.setattr(anthropic, "Anthropic", fake_client)
    provider = AnthropicSummaryProvider()
    provider.api_key = "test-key"
    provider.model = "claude-opus-5"
    result = provider.summarize({"sources": []})

    assert result.data["confidence"] == "high"
    body = captured["body"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["thinking"] == {"type": "adaptive"} and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in captured["beta"]


def _to_httpx2(res: httpx.Response) -> dict:
    return {"status_code": res.status_code, "content": res.content, "headers": dict(res.headers)}
