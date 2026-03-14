"""
Configuration loader for the competitive intelligence agent.

Company identity and competitor definitions come from company.yaml (gitignored).
Copy company.example.yaml → company.yaml and fill it in before running.

All API secrets come from environment variables / .env — never from yaml.
"""

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# ── Locate company.yaml ───────────────────────────────────────────────────────
_HERE = Path(__file__).parent
COMPANY_CONFIG_PATH = os.getenv("COMPANY_CONFIG", str(_HERE / "company.yaml"))

def _load_company_config() -> dict:
    path = Path(COMPANY_CONFIG_PATH)
    if not path.exists():
        example = _HERE / "company.example.yaml"
        print(
            f"\n[config] company.yaml not found at {path}\n"
            f"         Copy the example and fill it in:\n\n"
            f"         cp {example} {path}\n"
            f"         # then edit company.yaml with your company + competitors\n",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)

_cfg = _load_company_config()

# ── Company identity ──────────────────────────────────────────────────────────
COMPANY: dict = _cfg.get("company", {})
COMPANY_NAME: str        = COMPANY.get("name", "Your Company")
COMPANY_INDUSTRY: str    = COMPANY.get("industry", "")
COMPANY_DESCRIPTION: str = COMPANY.get("description", "")

# ── Competitors ───────────────────────────────────────────────────────────────
# Dict of {competitor_id: {name, press_room, blog, products, careers, ticker, ...}}
COMPETITORS: dict[str, dict] = _cfg.get("competitors", {})

if not COMPETITORS:
    print(
        "[config] No competitors defined in company.yaml. "
        "Add at least one competitor under the 'competitors:' key.",
        file=sys.stderr,
    )
    sys.exit(1)

# ── API keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Firehose (https://firehose.com) — primary real-time web mentions (free)
FIREHOSE_MGMT_KEY  = os.getenv("FIREHOSE_MGMT_KEY", "")
FIREHOSE_TAP_TOKEN = os.getenv("FIREHOSE_TAP_TOKEN", "")
FIREHOSE_TAP_NAME  = os.getenv("FIREHOSE_TAP_NAME", "competitive-intel")

# Firecrawl — deep page scraping (optional, supplemental)
FIRECRAWL_API_KEY  = os.getenv("FIRECRAWL_API_KEY", "")

# NewsAPI — additional press coverage (optional)
NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "")

# ── Model ─────────────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-opus-4-6"

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH           = os.getenv("INTEL_DB_PATH", "competitive_intel.db")
REPORTS_DIR       = os.getenv("REPORTS_DIR", "reports")
RETENTION_MONTHS  = int(os.getenv("RETENTION_MONTHS", "24"))

# ── Firehose pull ─────────────────────────────────────────────────────────────
FIREHOSE_SINCE      = os.getenv("FIREHOSE_SINCE", "24h")
FIREHOSE_MAX_EVENTS = int(os.getenv("FIREHOSE_MAX_EVENTS", "5000"))

# ── Firecrawl scraping targets (ordered by priority) ─────────────────────────
SCRAPE_TARGETS = ["press_room", "blog", "products"]

# ── SEC EDGAR ─────────────────────────────────────────────────────────────────
SEC_EDGAR_BASE     = "https://www.sec.gov"
SEC_SEARCH_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"

# ── Scheduling ────────────────────────────────────────────────────────────────
DAILY_RUN_HOUR   = int(os.getenv("DAILY_RUN_HOUR", "6"))
DAILY_RUN_MINUTE = int(os.getenv("DAILY_RUN_MINUTE", "0"))
