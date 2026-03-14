"""
News and SEC EDGAR scrapers for competitive intelligence signals.

Two sources:
  1. NewsAPI (https://newsapi.org) — press coverage and industry news
  2. SEC EDGAR full-text search — public-company financial filings (10-K, 10-Q, 8-K)

Both require no Firecrawl credits and complement the web scraper nicely.
"""

import logging
import requests
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import NEWS_API_KEY, COMPETITORS, SEC_EDGAR_BASE
from storage.database import insert_raw_event

log = logging.getLogger(__name__)

NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
SEC_SEARCH_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"


# ── NewsAPI ───────────────────────────────────────────────────────────────────

def fetch_news(
    competitor_id: str,
    query: str,
    *,
    days_back: int = 1,
    page_size: int = 20,
) -> list[int]:
    """
    Fetch recent news articles mentioning a competitor via NewsAPI.
    Returns list of inserted raw_event IDs.
    """
    if not NEWS_API_KEY:
        log.warning("NEWS_API_KEY not set; skipping NewsAPI fetch for %s", competitor_id)
        return []

    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "language": "en",
        "apiKey": NEWS_API_KEY,
    }

    inserted: list[int] = []
    try:
        resp = requests.get(NEWSAPI_ENDPOINT, params=params, timeout=20)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])

        for art in articles:
            content = "\n\n".join(filter(None, [
                art.get("title", ""),
                art.get("description", ""),
                art.get("content", ""),
            ]))
            if len(content) < 50:
                continue

            event_id = insert_raw_event(
                competitor_id=competitor_id,
                source_type="news",
                url=art.get("url"),
                title=art.get("title", "")[:200],
                content=content,
                published_at=art.get("publishedAt"),
                metadata={
                    "source": art.get("source", {}).get("name"),
                    "author": art.get("author"),
                },
            )
            inserted.append(event_id)

    except Exception as exc:
        log.error("NewsAPI error for %s: %s", competitor_id, exc)

    return inserted


def fetch_all_competitor_news(days_back: int = 1) -> dict[str, int]:
    """Fetch news for all competitors. Returns {competitor_id: events_stored}."""
    counts = {}
    for cid, cfg in COMPETITORS.items():
        query = cfg.get("news_query", cfg["name"])
        ids = fetch_news(cid, query, days_back=days_back)
        counts[cid] = len(ids)
        log.info("News fetch %s: %d articles", cfg["name"], len(ids))
    return counts


# ── SEC EDGAR ─────────────────────────────────────────────────────────────────

def fetch_sec_filings(
    competitor_id: str,
    company_name: str,
    ticker: str | None,
    *,
    days_back: int = 7,
    form_types: tuple[str, ...] = ("10-K", "10-Q", "8-K"),
) -> list[int]:
    """
    Search SEC EDGAR for recent filings by public competitors.
    Skips private companies (no ticker).
    """
    if not ticker:
        return []

    start = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end = datetime.utcnow().strftime("%Y-%m-%d")
    forms_param = ",".join(form_types)

    params = {
        "q": f'"{company_name}"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "forms": forms_param,
    }

    inserted: list[int] = []
    try:
        resp = requests.get(
            SEC_SEARCH_ENDPOINT,
            params=params,
            headers={"User-Agent": "CompetitiveIntelAgent/1.0 research@example.com"},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])

        for hit in hits[:10]:
            src = hit.get("_source", {})
            file_date = src.get("file_date", "")
            form_type = src.get("form_type", "")
            entity = src.get("entity_name", company_name)
            filing_url = (
                f"{SEC_EDGAR_BASE}/Archives/edgar/data/"
                f"{src.get('entity_id', '')}/{src.get('file_num', '')}"
            )
            content_summary = (
                f"SEC Filing: {form_type} by {entity}\n"
                f"Filed: {file_date}\n"
                f"Period: {src.get('period_of_report', 'N/A')}\n\n"
                f"{src.get('period_of_report', '')} {form_type}"
            )

            event_id = insert_raw_event(
                competitor_id=competitor_id,
                source_type="sec",
                url=filing_url,
                title=f"{form_type} - {entity} ({file_date})",
                content=content_summary,
                published_at=file_date + "T00:00:00Z" if file_date else None,
                metadata={
                    "form_type": form_type,
                    "ticker": ticker,
                    "period": src.get("period_of_report"),
                },
            )
            inserted.append(event_id)

    except Exception as exc:
        log.error("SEC EDGAR error for %s: %s", competitor_id, exc)

    return inserted


def fetch_all_sec_filings(days_back: int = 7) -> dict[str, int]:
    """Fetch SEC filings for public competitors only."""
    counts = {}
    for cid, cfg in COMPETITORS.items():
        ticker = cfg.get("ticker")
        if not ticker:
            counts[cid] = 0
            continue
        ids = fetch_sec_filings(
            cid,
            cfg["name"],
            ticker,
            days_back=days_back,
        )
        counts[cid] = len(ids)
        log.info("SEC filings %s (%s): %d filings", cfg["name"], ticker, len(ids))
    return counts
