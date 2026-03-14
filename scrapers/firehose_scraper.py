"""
Ahrefs Firehose scraper — real-time web mentions via SSE.

Firehose (https://firehose.com) is backed by Ahrefs' crawler infrastructure
and delivers matching pages via Server-Sent Events (SSE). It's free.

Rules are generated automatically from company.yaml — no hardcoding needed.

API overview
------------
- Management key (fhm_...) : create/list/delete taps and rules
- Tap token     (fh_...)   : stream events and query rules
- SSE endpoint             : GET https://api.firehose.com/v1/stream
- Buffer                   : up to 24h (`since=24h` replays the buffer)
- Rule syntax              : Lucene — field:, AND/OR/NOT, recent:Nh/Nd/Nmo
- Docs                     : https://firehose.com/api-docs
"""

import json
import logging
import time
from typing import Generator

import requests

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import COMPETITORS
from storage.database import insert_raw_event

log = logging.getLogger(__name__)

FIREHOSE_API_BASE = "https://api.firehose.com/v1"


# ── Rule generation ───────────────────────────────────────────────────────────

def _rules_for_competitor(competitor_id: str, cfg: dict) -> list[dict]:
    """
    Build Lucene Firehose rules for one competitor.

    Checks for an explicit `firehose_rules` list in the competitor config first.
    Falls back to auto-generating rules from the competitor name.
    """
    tag = competitor_id

    # Explicit rules in company.yaml take priority
    if explicit := cfg.get("firehose_rules"):
        return [{"value": r, "tag": tag} for r in explicit]

    name = cfg["name"]
    rules = []

    # Rule 1: exact phrase match anywhere in content
    rules.append({
        "value": f'"{name}" AND recent:24h',
        "tag": tag,
    })

    # Rule 2: title match (catches press releases, articles)
    # Use first two words of name to reduce noise for long names
    short = " ".join(name.split()[:2])
    if short != name:
        rules.append({
            "value": f'title:"{short}" AND recent:24h',
            "tag": tag,
        })

    # Rule 3: custom news_query from config (if provided and different from name)
    nq = cfg.get("news_query", "")
    if nq and nq.lower() != name.lower():
        rules.append({
            "value": f'"{nq}" AND recent:24h',
            "tag": tag,
        })

    return rules


def build_all_rules() -> dict[str, list[dict]]:
    """Return all Firehose rules keyed by competitor_id."""
    return {
        cid: _rules_for_competitor(cid, cfg)
        for cid, cfg in COMPETITORS.items()
    }


# Flat list for bootstrap + reverse tag→competitor_id map
def _flat_rules() -> list[dict]:
    return [
        rule
        for rules in build_all_rules().values()
        for rule in rules
    ]


def _tag_to_competitor() -> dict[str, str]:
    return {
        rule["tag"]: cid
        for cid, rules in build_all_rules().items()
        for rule in rules
    }


# ── Client helpers ────────────────────────────────────────────────────────────

def _mgmt_headers(mgmt_key: str) -> dict:
    return {"Authorization": f"Bearer {mgmt_key}", "Content-Type": "application/json"}


def _tap_headers(tap_token: str) -> dict:
    return {"Authorization": f"Bearer {tap_token}", "Content-Type": "application/json"}


# ── Tap management ─────────────────────────────────────────────────────────────

def list_taps(mgmt_key: str) -> list[dict]:
    resp = requests.get(
        f"{FIREHOSE_API_BASE}/taps",
        headers=_mgmt_headers(mgmt_key),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def create_tap(mgmt_key: str, name: str) -> dict:
    """Create a tap (idempotent — returns existing tap if name matches)."""
    for tap in list_taps(mgmt_key):
        if tap.get("name") == name:
            log.info("Tap '%s' already exists (uuid: %s)", name, tap.get("uuid"))
            return tap
    resp = requests.post(
        f"{FIREHOSE_API_BASE}/taps",
        headers=_mgmt_headers(mgmt_key),
        json={"name": name},
        timeout=15,
    )
    resp.raise_for_status()
    tap = resp.json().get("data", {})
    log.info("Created tap '%s' (uuid: %s)", name, tap.get("uuid"))
    return tap


# ── Rule management ───────────────────────────────────────────────────────────

def list_rules(tap_token: str) -> list[dict]:
    resp = requests.get(
        f"{FIREHOSE_API_BASE}/rules",
        headers=_tap_headers(tap_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def create_rule(tap_token: str, value: str, tag: str) -> dict:
    resp = requests.post(
        f"{FIREHOSE_API_BASE}/rules",
        headers=_tap_headers(tap_token),
        json={"value": value, "tag": tag},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def sync_rules(tap_token: str) -> tuple[int, int]:
    """
    Ensure all rules derived from company.yaml exist on the tap.
    Returns (created, already_existing).
    """
    existing_values = {r.get("value") for r in list_rules(tap_token)}
    created = 0
    skipped = 0

    for rule in _flat_rules():
        if rule["value"] in existing_values:
            log.debug("Rule exists: %s", rule["value"][:70])
            skipped += 1
            continue
        create_rule(tap_token, rule["value"], rule["tag"])
        log.info("Created rule [%s]: %s", rule["tag"], rule["value"][:80])
        created += 1
        time.sleep(0.3)

    return created, skipped


# ── SSE streaming ─────────────────────────────────────────────────────────────

def _parse_sse(response: requests.Response) -> Generator[dict, None, None]:
    event_lines: list[str] = []
    for raw in response.iter_lines(decode_unicode=True):
        if not raw:
            if event_lines:
                payload = "\n".join(event_lines)
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    log.warning("SSE parse error: %s", payload[:100])
                event_lines = []
            continue
        if raw.startswith("data:"):
            event_lines.append(raw[5:].lstrip())
        # skip SSE comments/heartbeats


def stream_events(
    tap_token: str,
    *,
    since: str = "24h",
    limit: int | None = None,
    timeout: int = 60,
) -> Generator[dict, None, None]:
    """Open SSE connection and yield raw Firehose event dicts."""
    params: dict = {"since": since}
    if limit is not None:
        params["limit"] = limit

    log.info("Opening Firehose SSE stream (since=%s, limit=%s)", since, limit)
    with requests.get(
        f"{FIREHOSE_API_BASE}/stream",
        headers={
            "Authorization": f"Bearer {tap_token}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        },
        params=params,
        stream=True,
        timeout=(10, timeout),
    ) as resp:
        resp.raise_for_status()
        yield from _parse_sse(resp)


# ── Daily pull ────────────────────────────────────────────────────────────────

def pull_and_store_events(
    tap_token: str,
    *,
    since: str = "24h",
    max_events: int = 5000,
) -> dict[str, int]:
    """
    Drain the Firehose buffer and store each event as a raw_event.
    Returns {competitor_id: events_stored}.
    """
    tag_map = _tag_to_competitor()
    counts: dict[str, int] = {cid: 0 for cid in COMPETITORS}
    total = 0

    for event in stream_events(tap_token, since=since, limit=max_events):
        tags = event.get("tags") or event.get("matching_rules", [])
        tag_strs = [
            t.get("tag", t) if isinstance(t, dict) else str(t)
            for t in (tags if isinstance(tags, list) else [])
        ]

        competitor_ids = {
            tag_map[tag] for tag in tag_strs if tag in tag_map
        }
        if not competitor_ids:
            continue

        url         = event.get("url", "")
        title       = event.get("title", url[:120])
        content     = event.get("content") or event.get("description") or event.get("text", "")
        published_at = event.get("published_at") or event.get("crawled_at")
        domain      = event.get("domain", "")

        for cid in competitor_ids:
            insert_raw_event(
                competitor_id=cid,
                source_type="firehose",
                url=url,
                title=title[:200],
                content=content,
                published_at=published_at,
                metadata={
                    "domain": domain,
                    "tags": tag_strs,
                    "language": event.get("language"),
                    "word_count": len(content.split()) if content else 0,
                },
            )
            counts[cid] = counts.get(cid, 0) + 1
            total += 1

    log.info("Firehose pull complete: %d events — %s", total, counts)
    return counts


# ── Bootstrap (one-time setup) ────────────────────────────────────────────────

def bootstrap(mgmt_key: str, tap_name: str = "competitive-intel") -> str:
    """
    Create the tap and sync all competitor rules from company.yaml.
    Returns the tap token — store as FIREHOSE_TAP_TOKEN in .env.
    """
    tap = create_tap(mgmt_key, tap_name)
    tap_token = (
        tap.get("token")
        or tap.get("tap_token")
        or tap.get("fh_token", "")
    )
    if not tap_token:
        raise ValueError(
            f"Could not extract tap token from Firehose response.\n"
            f"Full tap object: {tap}"
        )
    created, skipped = sync_rules(tap_token)
    log.info(
        "Bootstrap complete — %d rules created, %d already existed. Token: %s…",
        created, skipped, tap_token[:12],
    )
    return tap_token
