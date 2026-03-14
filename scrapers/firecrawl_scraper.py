"""
Firecrawl-powered scraper for competitor web properties.

Uses Firecrawl's /scrape endpoint to convert competitor press rooms, blogs,
and product pages into clean LLM-ready markdown, then stores each article as
a raw_event in the database.

Firecrawl docs: https://www.firecrawl.dev/use-cases/competitive-intelligence
"""

import re
import time
import logging
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FIRECRAWL_API_KEY, COMPETITORS, SCRAPE_TARGETS
from storage.database import insert_raw_event

try:
    from firecrawl import FirecrawlApp
    _firecrawl_available = True
except ImportError:
    _firecrawl_available = False

log = logging.getLogger(__name__)


def _get_client():
    if not _firecrawl_available:
        raise RuntimeError(
            "firecrawl-py is not installed. Run: pip install firecrawl-py"
        )
    return FirecrawlApp(api_key=FIRECRAWL_API_KEY)


def _extract_title(markdown: str) -> str:
    """Pull the first heading from markdown as the title."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return re.sub(r"^#+\s*", "", stripped)[:200]
    # Fallback: first non-empty line
    for line in markdown.splitlines():
        if line.strip():
            return line.strip()[:200]
    return "Untitled"


def scrape_competitor_page(
    competitor_id: str,
    source_type: str,
    url: str,
    *,
    crawl_subpages: bool = False,
    max_pages: int = 10,
) -> list[int]:
    """
    Scrape a single competitor URL (or crawl its subpages) via Firecrawl.
    Returns a list of newly inserted raw_event IDs.
    """
    client = _get_client()
    inserted_ids: list[int] = []

    try:
        if crawl_subpages:
            # Crawl up to max_pages subpages from this URL
            log.info("Crawling %s (max %d pages) for %s", url, max_pages, competitor_id)
            result = client.crawl_url(
                url,
                params={
                    "limit": max_pages,
                    "scrapeOptions": {
                        "formats": ["markdown"],
                        "onlyMainContent": True,
                    },
                },
            )
            pages = result.get("data", []) if isinstance(result, dict) else []
        else:
            # Single-page scrape
            log.info("Scraping %s for %s", url, competitor_id)
            result = client.scrape_url(
                url,
                params={
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                },
            )
            pages = [result] if result else []

        for page in pages:
            markdown = page.get("markdown", "")
            if not markdown or len(markdown) < 100:
                continue

            page_url = page.get("metadata", {}).get("url", url)
            title = (
                page.get("metadata", {}).get("title")
                or _extract_title(markdown)
            )
            published_at = page.get("metadata", {}).get("publishedTime")

            event_id = insert_raw_event(
                competitor_id=competitor_id,
                source_type=source_type,
                url=page_url,
                title=title,
                content=markdown,
                published_at=published_at,
                metadata={
                    "description": page.get("metadata", {}).get("description"),
                    "language": page.get("metadata", {}).get("language"),
                    "word_count": len(markdown.split()),
                },
            )
            inserted_ids.append(event_id)
            log.debug("Stored event %d: %s", event_id, title[:60])

    except Exception as exc:
        log.error("Firecrawl error scraping %s [%s]: %s", url, competitor_id, exc)

    return inserted_ids


def scrape_all_competitors(
    *,
    crawl_blogs: bool = True,
    press_room_pages: int = 15,
    blog_pages: int = 10,
) -> dict[str, int]:
    """
    Run Firecrawl scraping across all configured competitors.
    Returns a dict of {competitor_id: events_stored}.
    """
    counts: dict[str, int] = {}

    for cid, cfg in COMPETITORS.items():
        total = 0

        for target in SCRAPE_TARGETS:
            url = cfg.get(target)
            if not url:
                continue

            crawl = crawl_blogs and target in ("blog", "press_room")
            pages = press_room_pages if target == "press_room" else blog_pages

            ids = scrape_competitor_page(
                competitor_id=cid,
                source_type=target,
                url=url,
                crawl_subpages=crawl,
                max_pages=pages,
            )
            total += len(ids)

            # Polite delay between requests
            time.sleep(2)

        counts[cid] = total
        log.info("Scraped %s: %d new events", cfg["name"], total)

    return counts


def scrape_job_postings() -> dict[str, int]:
    """
    Scrape careers pages for each competitor to detect hiring signals
    (e.g., heavy ML/AI hiring may signal product roadmap direction).
    """
    client = _get_client()
    counts: dict[str, int] = {}

    for cid, cfg in COMPETITORS.items():
        url = cfg.get("careers")
        if not url:
            continue

        ids = scrape_competitor_page(
            competitor_id=cid,
            source_type="careers",
            url=url,
            crawl_subpages=True,
            max_pages=5,
        )
        counts[cid] = len(ids)
        time.sleep(2)

    return counts
