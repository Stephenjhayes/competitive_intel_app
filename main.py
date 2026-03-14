"""
Competitive Intelligence Agent
===============================

Works for any company — configure your company and competitors in company.yaml.

Quick start
-----------
  cp company.example.yaml company.yaml   # fill in your company + competitors
  cp .env.example .env                   # add API keys
  pip install -r requirements.txt

  python main.py --setup      # interactive first-run wizard
  python main.py --bootstrap  # create Firehose tap + sync rules
  python main.py --run-now    # run the full pipeline immediately
  python main.py --schedule   # start daily scheduler (06:00 UTC)

Flags
-----
  --setup          Interactive wizard to generate company.yaml from scratch
  --bootstrap      One-time Firehose tap + rule setup (run after --setup)
  --run-now        Full pipeline: collect → analyse → report
  --schedule       Daily cron (default 06:00 UTC, override via DAILY_RUN_HOUR/MINUTE)
  --report-only    Skip data collection, regenerate report from existing DB
  --news-days N    Days of news/SEC data to pull (default 1; use 30 on first run)
  --skip-firehose  Skip Firehose pull
  --skip-firecrawl Skip Firecrawl deep scraping
"""

import argparse
import logging
import sys
import textwrap
from datetime import date
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Config loads company.yaml — must exist before importing anything else.
# --setup flag is special: it runs before config loads.
_SETUP_FLAG = "--setup" in sys.argv

if not _SETUP_FLAG:
    from config import (
        COMPANY_NAME,
        COMPETITORS,
        DAILY_RUN_HOUR,
        DAILY_RUN_MINUTE,
        FIREHOSE_MGMT_KEY,
        FIREHOSE_TAP_TOKEN,
        FIREHOSE_TAP_NAME,
        FIREHOSE_SINCE,
        FIREHOSE_MAX_EVENTS,
        FIRECRAWL_API_KEY,
        RETENTION_MONTHS,
    )
    from storage.database import init_db, purge_old_records
    from scrapers.firehose_scraper import bootstrap as firehose_bootstrap, pull_and_store_events
    from scrapers.firecrawl_scraper import scrape_all_competitors, scrape_job_postings
    from scrapers.news_scraper import fetch_all_competitor_news, fetch_all_sec_filings
    from analysis.analyzer import build_all_daily_snapshots, build_comparison_report
    from reports.report_generator import generate_html_report, generate_daily_digest_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("competitive_intel.log"),
    ],
)
log = logging.getLogger("main")


# ── Interactive setup wizard ──────────────────────────────────────────────────

def run_setup() -> None:
    """
    Interactively generate company.yaml from scratch.
    Guides the user through entering their company details and competitors.
    """
    here = Path(__file__).parent
    target = here / "company.yaml"

    print("\n" + "=" * 60)
    print("  Competitive Intelligence Agent — Setup Wizard")
    print("=" * 60)

    if target.exists():
        overwrite = input(
            f"\ncompany.yaml already exists at {target}.\nOverwrite? [y/N]: "
        ).strip().lower()
        if overwrite != "y":
            print("Keeping existing company.yaml. Run `python main.py --bootstrap` next.")
            return

    print("\n── Step 1: Your company ──────────────────────────────────\n")
    company_name = input("Your company name: ").strip()
    if not company_name:
        print("Company name is required.")
        sys.exit(1)

    industry = input("Industry / market (e.g. 'Insurance technology'): ").strip()
    description = input(
        "1-2 sentence description of what your company does\n(press Enter to skip): "
    ).strip()

    print("\n── Step 2: Competitors ───────────────────────────────────\n")
    print("Enter each competitor. Leave the name blank when done.\n")

    competitors: dict[str, dict] = {}
    idx = 1
    while True:
        name = input(f"Competitor {idx} name (or press Enter to finish): ").strip()
        if not name:
            break

        # Auto-generate a slug ID
        cid = name.lower().replace(" ", "_").replace("-", "_")
        cid = "".join(c for c in cid if c.isalnum() or c == "_")

        press_room = input(f"  Press room / news URL (optional): ").strip()
        blog       = input(f"  Blog URL (optional): ").strip()
        products   = input(f"  Products/solutions URL (optional): ").strip()
        careers    = input(f"  Careers URL (optional): ").strip()
        ticker     = input(f"  Stock ticker for SEC filings (optional, e.g. HUBS): ").strip()
        news_query = input(
            f"  Custom news search string (optional, defaults to '{name}'): "
        ).strip()

        entry: dict = {"name": name}
        if press_room: entry["press_room"] = press_room
        if blog:       entry["blog"] = blog
        if products:   entry["products"] = products
        if careers:    entry["careers"] = careers
        if ticker:     entry["ticker"] = ticker
        if news_query: entry["news_query"] = news_query

        competitors[cid] = entry
        idx += 1
        print()

    if not competitors:
        print("No competitors entered. Add them manually to company.yaml.")

    # Build YAML string manually (avoids pyyaml anchor noise)
    lines = [
        "company:",
        f'  name: "{company_name}"',
        f'  industry: "{industry}"',
    ]
    if description:
        lines.append(f"  description: >")
        for chunk in textwrap.wrap(description, 72):
            lines.append(f"    {chunk}")

    lines.append("")
    lines.append("competitors:")

    for cid, cfg in competitors.items():
        lines.append(f"  {cid}:")
        for k, v in cfg.items():
            lines.append(f'    {k}: "{v}"')
        lines.append("")

    yaml_content = "\n".join(lines) + "\n"

    with open(target, "w", encoding="utf-8") as fh:
        fh.write(yaml_content)

    print(f"\n✓ company.yaml written to {target}")
    print("\nNext steps:")
    print("  1. Review/edit company.yaml if needed")
    print("  2. Add your API keys to .env  (copy from .env.example)")
    print("  3. python main.py --bootstrap   (create Firehose tap + rules)")
    print("  4. python main.py --run-now --news-days 30  (first data pull)")
    print("  5. python main.py --schedule    (start daily runs)\n")


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def run_bootstrap() -> None:
    if not FIREHOSE_MGMT_KEY:
        log.error(
            "FIREHOSE_MGMT_KEY not set. Sign up at https://firehose.com "
            "and add your fhm_... key to .env"
        )
        sys.exit(1)

    n_competitors = len(COMPETITORS)
    log.info(
        "Bootstrapping Firehose tap '%s' for %s (%d competitors)…",
        FIREHOSE_TAP_NAME, COMPANY_NAME, n_competitors,
    )
    tap_token = firehose_bootstrap(FIREHOSE_MGMT_KEY, FIREHOSE_TAP_NAME)

    print("\n" + "=" * 60)
    print(f"TAP TOKEN — save this to .env as FIREHOSE_TAP_TOKEN:\n\n  {tap_token}\n")
    print("=" * 60)
    print("\nFirehose is now buffering mentions. Run the pipeline next:\n")
    print(f"  python main.py --run-now --news-days 30\n")


# ── Daily pipeline ─────────────────────────────────────────────────────────────

def run_daily_pipeline(
    *,
    news_days: int = 1,
    skip_firehose: bool = False,
    skip_firecrawl: bool = False,
    report_only: bool = False,
) -> None:
    today = date.today().isoformat()
    log.info("=" * 60)
    log.info("CI Daily Run — %s  ·  tracking %d competitors for %s",
             today, len(COMPETITORS), COMPANY_NAME)
    log.info("=" * 60)

    init_db()
    purge_old_records()

    if not report_only:
        # ── Phase 1: Firehose (primary) ───────────────────────────
        if not skip_firehose:
            if FIREHOSE_TAP_TOKEN:
                log.info("Phase 1: Firehose SSE pull (since=%s)", FIREHOSE_SINCE)
                try:
                    fh_counts = pull_and_store_events(
                        FIREHOSE_TAP_TOKEN,
                        since=FIREHOSE_SINCE,
                        max_events=FIREHOSE_MAX_EVENTS,
                    )
                    log.info("Firehose: %s", fh_counts)
                except Exception as exc:
                    log.error("Firehose pull failed: %s", exc)
            else:
                log.warning(
                    "FIREHOSE_TAP_TOKEN not set — run `python main.py --bootstrap` first"
                )

        # ── Phase 2: Firecrawl (supplemental deep scraping) ───────
        if not skip_firecrawl and FIRECRAWL_API_KEY:
            log.info("Phase 2: Firecrawl deep scraping")
            try:
                log.info("Firecrawl web: %s", scrape_all_competitors())
                log.info("Firecrawl careers: %s", scrape_job_postings())
            except Exception as exc:
                log.error("Firecrawl failed: %s", exc)
        else:
            log.info("Phase 2: Firecrawl skipped (%s)",
                     "FIRECRAWL_API_KEY not set" if not FIRECRAWL_API_KEY else "flag set")

        # ── Phase 3: News + SEC ───────────────────────────────────
        log.info("Phase 3: News & SEC filings (last %d days)", news_days)
        try:
            log.info("News: %s", fetch_all_competitor_news(days_back=news_days))
            log.info("SEC: %s", fetch_all_sec_filings(days_back=max(news_days, 7)))
        except Exception as exc:
            log.error("News/SEC failed: %s", exc)

        # ── Phase 4: Daily snapshots ──────────────────────────────
        log.info("Phase 4: Claude Opus 4.6 — daily snapshots")
        snapshots = {}
        try:
            snapshots = build_all_daily_snapshots(
                snapshot_date=today,
                lookback_days=news_days,
            )
            log.info("Snapshots: %d competitors", len(snapshots))
        except Exception as exc:
            log.error("Snapshot phase failed: %s", exc)

        if snapshots:
            try:
                md = generate_daily_digest_markdown(snapshots, digest_date=today)
                log.info("Daily digest → %s", md)
            except Exception as exc:
                log.error("Digest failed: %s", exc)

    # ── Phase 5: Comparison report ────────────────────────────────
    log.info("Phase 5: Claude Opus 4.6 — %d-month comparison report", RETENTION_MONTHS)
    try:
        comparison = build_comparison_report(
            report_date=today,
            period_months=RETENTION_MONTHS,
        )
        if comparison:
            html = generate_html_report(
                comparison, report_date=today, period_months=RETENTION_MONTHS,
            )
            log.info("HTML report → %s", html)

            from storage.database import upsert_comparison
            upsert_comparison(
                report_date=today,
                period_months=RETENTION_MONTHS,
                narrative=comparison.get("executive_narrative", ""),
                insights=comparison.get("strategic_insights", []),
                html_path=html,
            )
    except Exception as exc:
        log.error("Comparison report failed: %s", exc)

    log.info("Pipeline complete — %s", today)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="Competitive Intelligence Agent — configure via company.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Getting started:
          python main.py --setup           # interactive wizard → creates company.yaml
          python main.py --bootstrap       # Firehose tap + rules setup
          python main.py --run-now --news-days 30   # first full run
          python main.py --schedule        # start daily cron
        """),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--setup",     action="store_true", help="Interactive setup wizard")
    mode.add_argument("--bootstrap", action="store_true", help="Create Firehose tap + sync rules")
    mode.add_argument("--run-now",   action="store_true", help="Run the full pipeline now")
    mode.add_argument("--schedule",  action="store_true", help="Start the daily scheduler")

    p.add_argument("--report-only",    action="store_true", help="Regenerate report only (no collection)")
    p.add_argument("--news-days",      type=int, default=1,  help="Days of news/SEC to pull (default 1)")
    p.add_argument("--skip-firehose",  action="store_true",  help="Skip Firehose pull")
    p.add_argument("--skip-firecrawl", action="store_true",  help="Skip Firecrawl scraping")
    return p.parse_args()


def main():
    args = _parse_args()

    if args.setup:
        run_setup()
        return

    if args.bootstrap:
        run_bootstrap()
        return

    if args.run_now:
        run_daily_pipeline(
            news_days=args.news_days,
            skip_firehose=args.skip_firehose,
            skip_firecrawl=args.skip_firecrawl,
            report_only=args.report_only,
        )
        return

    if args.schedule:
        log.info("Starting scheduler — daily at %02d:%02d UTC for %s",
                 DAILY_RUN_HOUR, DAILY_RUN_MINUTE, COMPANY_NAME)
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            run_daily_pipeline,
            CronTrigger(hour=DAILY_RUN_HOUR, minute=DAILY_RUN_MINUTE),
            kwargs={"news_days": 1},
            id="daily_ci_pipeline",
            name=f"CI Daily — {COMPANY_NAME}",
            replace_existing=True,
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped.")
        return

    print("No action specified. Run `python main.py --help` for usage.")


if __name__ == "__main__":
    main()
