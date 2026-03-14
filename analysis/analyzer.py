"""
Claude Opus 4.6 powered competitive intelligence analyzer.

Fully generic — driven entirely by company.yaml. No company names are
hardcoded here; all context comes from config at runtime.

Two analysis passes per daily run:
  1. Per-competitor daily snapshot  — summarises one competitor's events for the day
  2. Cross-competitor comparison    — synthesises N months of snapshots into an
                                      executive-grade insight report
"""

import json
import logging
from datetime import datetime, date, timedelta

import anthropic

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    COMPANY_NAME,
    COMPANY_INDUSTRY,
    COMPANY_DESCRIPTION,
    COMPETITORS,
    RETENTION_MONTHS,
)
from storage.database import (
    get_events_since,
    upsert_daily_snapshot,
    get_all_snapshots_range,
)

log = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Prompt builders ───────────────────────────────────────────────────────────

def _snapshot_system() -> str:
    return f"""You are a senior competitive intelligence analyst. Your client is **{COMPANY_NAME}**,
operating in the **{COMPANY_INDUSTRY}** industry.

{f'About {COMPANY_NAME}: {COMPANY_DESCRIPTION}' if COMPANY_DESCRIPTION else ''}

Your task: analyse the raw intelligence collected today about a single competitor
and produce a concise, actionable daily snapshot for the CI team.

Output ONLY valid JSON in this exact schema — no markdown fences, no prose outside the JSON:

{{
  "summary": "<2-3 sentence executive summary of today's notable signals>",
  "key_signals": [
    "<bullet signal 1>",
    "<bullet signal 2>"
  ],
  "sentiment_score": <float -1.0 to 1.0 where -1=very negative for {COMPANY_NAME}, 1=very positive>,
  "watch_items": ["<thing the CI team should monitor>"]
}}"""


def _comparison_system() -> str:
    competitor_names = ", ".join(
        cfg["name"] for cfg in COMPETITORS.values()
    )
    n_months = RETENTION_MONTHS

    return f"""You are a principal competitive intelligence analyst. Your client is **{COMPANY_NAME}**,
operating in the **{COMPANY_INDUSTRY}** industry.

{f'About {COMPANY_NAME}: {COMPANY_DESCRIPTION}' if COMPANY_DESCRIPTION else ''}

You have access to {n_months} months of daily intelligence snapshots covering
{COMPANY_NAME}'s competitors: {competitor_names}.

Your task: synthesise all available data into a strategic comparison report for
{COMPANY_NAME}'s executive and product leadership teams.

Output ONLY valid JSON in this exact schema:

{{
  "executive_narrative": "<4-6 paragraph strategic narrative covering competitive landscape, momentum shifts, and {COMPANY_NAME}'s positioning>",
  "competitor_rankings": [
    {{
      "competitor": "<name>",
      "threat_level": "<low|medium|high|critical>",
      "momentum": "<declining|stable|growing|accelerating>",
      "headline": "<one sentence competitive headline>"
    }}
  ],
  "market_themes": [
    {{
      "theme": "<theme title>",
      "description": "<2-3 sentences>",
      "competitors_driving": ["<name>"],
      "implication_for_{COMPANY_NAME.lower().replace(' ', '_')}": "<1-2 sentences on what this means for {COMPANY_NAME}>"
    }}
  ],
  "strategic_insights": [
    {{
      "insight": "<actionable insight title>",
      "evidence": "<supporting evidence from the data>",
      "recommendation": "<recommended action for {COMPANY_NAME}>"
    }}
  ],
  "hiring_signals": "<paragraph on what competitor hiring patterns reveal about their roadmaps>",
  "deal_activity": "<paragraph on notable customer wins/losses and partnership activity>",
  "product_moves": "<paragraph on product launches, releases, and R&D signals>",
  "period_summary": "<1-2 sentences summarising the data coverage period>"
}}"""


# ── Helper ────────────────────────────────────────────────────────────────────

def _stream_and_parse_json(system: str, user: str) -> dict:
    """
    Stream a Claude Opus 4.6 response with adaptive thinking and return
    the parsed JSON. Streaming avoids HTTP timeouts on large contexts.
    """
    full_text = ""
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                full_text += event.delta.text

    text = full_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    return json.loads(text.strip())


# ── Per-competitor daily snapshot ─────────────────────────────────────────────

def build_daily_snapshot(
    competitor_id: str,
    *,
    snapshot_date: str | None = None,
    lookback_days: int = 1,
) -> dict:
    """
    Fetch recent raw events for one competitor, ask Claude to summarise them,
    and upsert the result into daily_snapshots.
    """
    target_date = snapshot_date or date.today().isoformat()
    cfg = COMPETITORS[competitor_id]
    log.info("Building snapshot for %s on %s", cfg["name"], target_date)

    rows = get_events_since(competitor_id, days=lookback_days)
    if not rows:
        log.info("No new events for %s — skipping snapshot", cfg["name"])
        return {}

    # Condensed digest of events (cap at ~60K chars)
    digest_parts = []
    char_budget = 60_000
    for row in rows:
        entry = f"### [{row['source_type'].upper()}] {row['title']}\n{row['content'][:2000]}\n"
        if sum(len(p) for p in digest_parts) + len(entry) > char_budget:
            break
        digest_parts.append(entry)

    digest = "\n---\n".join(digest_parts)
    user_msg = (
        f"Competitor: **{cfg['name']}** (id: {competitor_id})\n"
        f"Snapshot date: {target_date}\n"
        f"Events collected ({len(rows)} total, showing {len(digest_parts)}):\n\n"
        f"{digest}"
    )

    try:
        result = _stream_and_parse_json(_snapshot_system(), user_msg)
    except json.JSONDecodeError as exc:
        log.error("JSON parse error for %s snapshot: %s", competitor_id, exc)
        return {}

    upsert_daily_snapshot(
        snapshot_date=target_date,
        competitor_id=competitor_id,
        summary=result.get("summary", ""),
        key_signals=result.get("key_signals", []),
        sentiment_score=result.get("sentiment_score"),
    )
    log.info("Snapshot stored for %s", cfg["name"])
    return result


def build_all_daily_snapshots(
    snapshot_date: str | None = None,
    lookback_days: int = 1,
) -> dict[str, dict]:
    results = {}
    for cid in COMPETITORS:
        results[cid] = build_daily_snapshot(
            cid,
            snapshot_date=snapshot_date,
            lookback_days=lookback_days,
        )
    return results


# ── Cross-competitor comparison report ────────────────────────────────────────

def build_comparison_report(
    *,
    report_date: str | None = None,
    period_months: int = RETENTION_MONTHS,
) -> dict:
    """
    Synthesise all snapshots across all competitors over `period_months` into
    a strategic comparison report.
    """
    target_date = report_date or date.today().isoformat()
    start_date = (
        datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=period_months * 30)
    ).strftime("%Y-%m-%d")

    log.info(
        "Building comparison report %s → %s (%d months)",
        start_date, target_date, period_months,
    )

    rows = get_all_snapshots_range(start_date, target_date)
    if not rows:
        log.warning("No snapshot data in range %s–%s", start_date, target_date)
        return {}

    # Organise by competitor, budget context evenly
    by_competitor: dict[str, list] = {cid: [] for cid in COMPETITORS}
    for row in rows:
        cid = row["competitor_id"]
        if cid in by_competitor:
            by_competitor[cid].append(row)

    char_budget_per = 80_000 // max(len(COMPETITORS), 1)
    context_parts = []

    for cid, snapshots in by_competitor.items():
        if not snapshots:
            continue
        cfg = COMPETITORS[cid]
        sections = [f"## {cfg['name']} ({len(snapshots)} daily snapshots)"]
        chars = 0
        for snap in reversed(snapshots):
            signals = json.loads(snap["key_signals"]) if snap["key_signals"] else []
            score = snap["sentiment_score"] or 0.0
            entry = (
                f"**{snap['snapshot_date']}** (sentiment: {score:.2f})\n"
                f"{snap['summary']}\n"
                + "\n".join(f"- {s}" for s in signals[:5])
                + "\n"
            )
            if chars + len(entry) > char_budget_per:
                break
            sections.append(entry)
            chars += len(entry)
        context_parts.append("\n".join(sections))

    user_msg = (
        f"Report date: {target_date}\n"
        f"Data period: {start_date} → {target_date} ({period_months} months)\n"
        f"Total snapshots analysed: {len(rows)}\n\n"
        "# Competitor Intelligence Data\n\n"
        + "\n\n---\n\n".join(context_parts)
    )

    try:
        result = _stream_and_parse_json(_comparison_system(), user_msg)
    except json.JSONDecodeError as exc:
        log.error("JSON parse error in comparison report: %s", exc)
        return {}

    log.info("Comparison report complete for %s", target_date)
    return result
