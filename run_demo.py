"""
Demo: bypasses the Claude API call and feeds pre-generated, realistic
analysis directly into the DB and report generators, showing exactly
what real outputs look like.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta
from storage.database import init_db, upsert_daily_snapshot
from reports.report_generator import generate_html_report, generate_daily_digest_markdown

TODAY = date.today().isoformat()

# ── Realistic per-competitor daily snapshots ──────────────────────────────────

SNAPSHOTS = {
    "duck_creek": {
        "summary": (
            "Duck Creek had a highly active week, closing a landmark $200M Series D and signing "
            "seven new Tier-1 carrier contracts — both the strongest signals of momentum seen from "
            "this competitor in over two years. The Azure strategic partnership broadens their "
            "distribution into European and APAC markets where Guidewire has historically had the advantage."
        ),
        "key_signals": [
            "$200M Series D led by Vista Equity — validates cloud-first P&C strategy",
            "7 new Tier-1 carrier contract signings in Q1 — accelerating vs. prior year",
            "AI Automated Underwriting launch: LLM-powered, sub-2-minute commercial submissions",
            "Microsoft Azure strategic partnership — co-sell into Europe and APAC",
            "120 new engineering and ML hires posted — aggressive product expansion signal",
        ],
        "sentiment_score": -0.65,
        "watch_items": [
            "Monitor Duck Creek's pipeline in APAC — Azure partnership could accelerate deals",
            "AI Underwriting Copilot in beta: request early-access briefing if possible",
        ],
    },
    "sapiens": {
        "summary": (
            "Sapiens reported Q4 results well above expectations with 18% YoY revenue growth and "
            "cloud ARR now at 62% of total — a meaningful inflection point. The CoreSuite AI launch "
            "positions them as the first competitor to embed generative AI throughout the entire "
            "policy lifecycle, not just as a bolt-on. Their SEC filing reveals four active Tier-1 "
            "North American implementations set for H2 2025 go-live, which could generate significant "
            "case study and reference selling momentum."
        ),
        "key_signals": [
            "Q4 revenue $132M (+18% YoY) — beat consensus by $4M; guidance raised to $560-570M",
            "Cloud ARR now 62% of total — accelerating SaaS transition",
            "CoreSuite AI: generative AI embedded across quote, policy, claims lifecycle",
            "4 active Tier-1 North American implementations due go-live H2 2025",
            "R&D spend up 32% YoY ($89M); 380 net new hires, 60% in engineering",
        ],
        "sentiment_score": -0.55,
        "watch_items": [
            "H2 2025 North American go-lives will create new reference customers — watch for press releases",
            "CoreSuite AI pricing ($2M+ for mid-market) may pressure Guidewire's mid-market positioning",
        ],
    },
    "majesco": {
        "summary": (
            "Majesco's cloud revenue surged 34% this quarter, driven by legacy system migration "
            "acceleration. The AWS Insurance Competency — a first for P&C platform vendors — "
            "opens meaningful co-selling opportunities with AWS enterprise teams. Their new "
            "AI Center of Excellence in Hyderabad ($15M investment) signals a serious long-term "
            "commitment to AI-native insurance products, though execution risk remains elevated "
            "for a company of their size."
        ),
        "key_signals": [
            "Cloud subscription revenue +34% QoQ — 47 active cloud implementations (vs 31 a year ago)",
            "First P&C vendor to achieve AWS Insurance Competency — preferred Marketplace placement",
            "AI Center of Excellence: 200 engineers, $15M, focused on predictive pricing and fraud detection",
            "Regulatory pressure and talent scarcity cited as top drivers of customer cloud adoption",
        ],
        "sentiment_score": -0.30,
        "watch_items": [
            "AWS co-sell motion could bring Majesco into enterprise deals previously outside their reach",
        ],
    },
    "insurity": {
        "summary": (
            "Insurity made its most significant strategic move in years with the $85M acquisition "
            "of ClaimVantage, adding 140 carrier clients and AI-powered claims triage capabilities. "
            "The simultaneous E&S platform launch is well-timed given the explosive growth in "
            "the Excess & Surplus market. The API-first architecture rebuild (400+ integrations, "
            "3-week go-live vs. 6 months previously) removes a key Guidewire competitive advantage."
        ),
        "key_signals": [
            "ClaimVantage acquisition ($85M) — adds 140 carriers, AI claims triage, fraud detection",
            "E&S platform launch at RIMS 2025 — 3 MGAs already signed LOIs",
            "API layer rebuild: 400+ integrations, reduced integration time from 6 months → 3 weeks",
        ],
        "sentiment_score": -0.40,
        "watch_items": [
            "ClaimVantage clients are potential cross-sell targets for Guidewire claims products",
            "Monitor E&S platform traction — this is an underserved segment Guidewire does not own",
        ],
    },
    "applied_systems": {
        "summary": (
            "Applied Systems hit 1,500 agency customers on Applied Epic Cloud (40% of total base) — "
            "a significant milestone in their SaaS transition. The Applied AI Agent launch, automating "
            "commercial lines submissions with 70% time savings, represents a real threat to submission "
            "workflow products in Guidewire's distribution management portfolio. The $100M H&F "
            "investment and plans to double engineering headcount to 1,200 signal serious scale ambitions."
        ),
        "key_signals": [
            "1,500 agencies on Epic Cloud — 40% of customer base migrated to SaaS",
            "Applied AI Agent: 70% reduction in commercial lines submission prep time",
            "$100M Hellman & Friedman investment — doubling engineering to 1,200 over 18 months",
            "New Austin engineering hub; Computer vision for ACORD form extraction",
        ],
        "sentiment_score": -0.25,
        "watch_items": [
            "AI Agent submission automation could threaten Guidewire's agency distribution products",
        ],
    },
    "one_shield": {
        "summary": (
            "OneShield's EY partnership and $40M Series C reflect a pragmatic pivot toward SaaS "
            "and implementation efficiency. With 70% of 2024 new deals as cloud subscriptions (vs 20% in 2022), "
            "they are rapidly repositioning from a legacy on-prem vendor to a credible SaaS player. "
            "Their pre-configured solution bundles with EY target exactly the mid-market carriers "
            "who struggle with the cost and complexity of full-scale implementations."
        ),
        "key_signals": [
            "EY global implementation partnership — pre-configured insurance suites, faster time-to-value",
            "$40M Series C (Warburg Pincus) — funding SaaS transition",
            "70% of 2024 new deals are cloud subscriptions (vs 20% in 2022)",
        ],
        "sentiment_score": -0.15,
        "watch_items": [
            "EY co-delivery model may lower deal cost threshold — watch mid-market displacement deals",
        ],
    },
}

# ── Realistic comparison report (what Claude Opus would generate) ─────────────

COMPARISON_REPORT = {
    "executive_narrative": (
        "The P&C insurance technology landscape has undergone a fundamental acceleration in the past quarter. "
        "Three simultaneous forces are converging: AI is moving from pilot to production across all major competitors, "
        "cloud migration has passed the inflection point from optional to urgent, and consolidation (Insurity/ClaimVantage) "
        "is creating more capable platform players. Guidewire faces its most complex competitive environment in five years.\n\n"
        "Duck Creek's $200M raise and Sapiens' beat-and-raise quarter represent the two most significant competitive "
        "threats in the near term. Duck Creek is executing aggressively on both the enterprise segment (7 Tier-1 wins) "
        "and AI (Automated Underwriting Copilot), while Sapiens is transitioning to a genuine SaaS business with 62% "
        "cloud ARR and a generative AI product suite that predates most competitors'. Both companies are now better "
        "funded, better positioned in AI, and more globally capable than at any previous point.\n\n"
        "The mid-market is the most contested battleground. OneShield/EY's pre-configured bundles, Majesco's AWS "
        "co-sell, and Insurity's rebuilt API layer all target carriers who have historically been underserved by "
        "enterprise platforms. This segment represents a meaningful growth opportunity for Guidewire but requires "
        "a more streamlined implementation path than the current offering provides.\n\n"
        "Applied Systems' trajectory in the agency distribution channel deserves elevated monitoring. Their AI "
        "submission automation and $100M investment in engineering represent a credible build-out in a distribution "
        "workflow category that Guidewire has ambitions in. A competitive collision in digital distribution is "
        "increasingly likely within 12-18 months.\n\n"
        "The collective hiring signals across all six competitors — an estimated 1,500+ net new engineering and AI "
        "roles in this quarter alone — indicate that R&D investment is accelerating industry-wide. Guidewire's "
        "ability to attract and retain AI talent will be as important a competitive variable as product strategy "
        "over the next 24 months."
    ),
    "competitor_rankings": [
        {
            "competitor": "Duck Creek Technologies",
            "threat_level": "critical",
            "momentum": "accelerating",
            "headline": "$200M raise + 7 enterprise wins + AI Underwriting Copilot = highest competitive velocity in 3 years",
        },
        {
            "competitor": "Sapiens International",
            "threat_level": "high",
            "momentum": "accelerating",
            "headline": "Beat-and-raise quarter, 62% cloud ARR, full-lifecycle generative AI — North American momentum building",
        },
        {
            "competitor": "Insurity",
            "threat_level": "high",
            "momentum": "growing",
            "headline": "ClaimVantage acquisition adds 140 carriers and AI claims triage; E&S platform targets an uncontested segment",
        },
        {
            "competitor": "Applied Systems",
            "threat_level": "medium",
            "momentum": "growing",
            "headline": "AI submission agent + $100M investment signals a move into Guidewire's distribution workflow territory",
        },
        {
            "competitor": "Majesco",
            "threat_level": "medium",
            "momentum": "growing",
            "headline": "AWS co-sell + AI CoE could bring Majesco into enterprise deals previously outside their reach",
        },
        {
            "competitor": "OneShield Software",
            "threat_level": "low",
            "momentum": "stable",
            "headline": "SaaS pivot progressing; EY partnership improves mid-market credibility but scale remains limited",
        },
    ],
    "market_themes": [
        {
            "theme": "Generative AI in Core Insurance Workflows",
            "description": (
                "Every major competitor has moved from AI pilots to production AI embedded in underwriting, "
                "claims, and policy administration. The race is now about accuracy, insurance-domain specificity, "
                "and seamless workflow integration rather than novelty."
            ),
            "competitors_driving": ["Duck Creek Technologies", "Sapiens International", "Applied Systems"],
            "implication_for_guidewire": (
                "Guidewire must accelerate the roadmap for AI-native underwriting and claims products. "
                "The window to ship before competitors establish reference customers is closing rapidly."
            ),
        },
        {
            "theme": "Mid-Market Cloud Acceleration",
            "description": (
                "Regulatory pressure, talent scarcity, and simplified SaaS offerings are driving mid-market "
                "carriers to cloud faster than anticipated. Pre-configured bundles (OneShield/EY, Majesco/AWS) "
                "are removing the complexity barrier that historically protected enterprise platform incumbents."
            ),
            "competitors_driving": ["Majesco", "OneShield Software", "Insurity"],
            "implication_for_guidewire": (
                "Guidewire should evaluate a simplified, pre-configured cloud offering for carriers under "
                "$500M DWP to defend against low-cost, fast-implementation alternatives."
            ),
        },
        {
            "theme": "Distribution Workflow Automation",
            "description": (
                "Applied Systems' AI submission agent and Duck Creek's agency integration work signal "
                "a convergence of policy administration and distribution management platforms. "
                "The traditional boundary between carrier systems and agency systems is blurring."
            ),
            "competitors_driving": ["Applied Systems", "Duck Creek Technologies"],
            "implication_for_guidewire": (
                "Guidewire's digital distribution and agent portal roadmap needs acceleration to defend "
                "against encroachment from the agency management system side."
            ),
        },
        {
            "theme": "M&A-Driven Portfolio Expansion",
            "description": (
                "Insurity's ClaimVantage acquisition is the latest in a series of bolt-on deals that "
                "expand competitor capabilities faster than organic development allows. "
                "Better-funded competitors will continue to acquire to fill product gaps."
            ),
            "competitors_driving": ["Insurity", "Duck Creek Technologies"],
            "implication_for_guidewire": (
                "Monitor M&A activity in claims analytics and specialty lines — these are segments "
                "where targeted acquisitions could rapidly close capability gaps."
            ),
        },
    ],
    "strategic_insights": [
        {
            "insight": "Launch an AI Underwriting Copilot before Duck Creek's Reaches GA",
            "evidence": (
                "Duck Creek's AI Automated Underwriting (currently in beta) targets sub-2-minute "
                "commercial submissions — a capability that resonates strongly with commercial lines "
                "underwriters and could become a key renewal-cycle differentiator."
            ),
            "recommendation": (
                "Fast-track the Guidewire AI Underwriting product to GA and develop a competitive "
                "displacement narrative specifically targeting carriers evaluating Duck Creek."
            ),
        },
        {
            "insight": "Develop a Pre-Configured Mid-Market Cloud Bundle",
            "evidence": (
                "Three competitors (Majesco, OneShield/EY, Insurity) are actively targeting mid-market "
                "carriers with simplified, faster-to-deploy solutions. Majesco has 47 active cloud "
                "implementations; Majesco and AWS now co-sell into enterprise accounts."
            ),
            "recommendation": (
                "Create a Guidewire Cloud Essentials tier with pre-configured product templates "
                "for standard personal and commercial lines carriers under $500M DWP, with a "
                "target implementation timeline of 6 months or less."
            ),
        },
        {
            "insight": "Establish a Competitive Counter-Narrative on Sapiens AI",
            "evidence": (
                "Sapiens CoreSuite AI is generating significant analyst attention and is being "
                "positioned as the first 'full-lifecycle AI' insurance platform. Their $2M+ pricing "
                "targets the same enterprise segment as Guidewire."
            ),
            "recommendation": (
                "Prepare a detailed competitive battlecard for Sapiens that highlights "
                "Guidewire's enterprise scale, ecosystem depth, and implementation track record "
                "at Tier-1 carriers — areas where Sapiens lacks equivalent reference customers."
            ),
        },
        {
            "insight": "Protect the E&S Market Before Insurity Gains Traction",
            "evidence": (
                "Insurity's new E&S platform has signed 3 MGA LOIs at launch. Excess & Surplus "
                "is among the fastest-growing segments in P&C insurance and has historically been "
                "underserved by enterprise platform vendors including Guidewire."
            ),
            "recommendation": (
                "Accelerate the Guidewire Specialty Lines product roadmap and establish "
                "2-3 MGA reference customers in the E&S market before Insurity's LOIs "
                "convert to signed contracts."
            ),
        },
    ],
    "hiring_signals": (
        "Competitor hiring in Q1 is the strongest indicator of near-term product investment. "
        "Duck Creek is hiring 120 cloud and ML engineers, including a VP of AI Products and Head of LLM Engineering — "
        "a clear signal of a major AI product cycle. Sapiens added 380 net new hires (60% engineering) and is "
        "running 4 concurrent Tier-1 implementations. Applied Systems is doubling engineering headcount to 1,200 "
        "over 18 months on the back of a $100M investment. Majesco's new 200-person AI CoE in Hyderabad represents "
        "a $15M multi-year commitment. Collectively, this represents an estimated $150M+ in annualised engineering "
        "payroll being added to the competitive field in a single quarter — the highest rate of competitor R&D "
        "expansion observed in the 24-month dataset."
    ),
    "deal_activity": (
        "Deal activity this quarter favoured competitors in enterprise and mid-market segments. "
        "Duck Creek's 7 Tier-1 carrier signings represent the single largest quarterly win total across "
        "all tracked competitors and directly threatens Guidewire's renewal pipeline for 2025-2026. "
        "Insurity's ClaimVantage acquisition adds 140 carrier client relationships that are potential "
        "cross-sell targets for Insurity's broader platform. Sapiens' 4 active North American Tier-1 "
        "implementations (H2 2025 go-live) will generate new reference selling capacity in Guidewire's "
        "core market. OneShield's EY partnership targets mid-market RFPs with a combined delivery offering "
        "that reduces implementation risk — historically one of Guidewire's strongest selling points."
    ),
    "product_moves": (
        "The most significant product moves this quarter were concentrated in AI. Duck Creek launched AI "
        "Automated Underwriting (beta) using LLMs for commercial submission processing; Sapiens unveiled "
        "CoreSuite AI with natural language policy search, automated endorsements, and AI claims triage; "
        "Applied Systems launched Applied AI Agent using computer vision for ACORD form extraction and "
        "carrier routing with 70% reported time savings. On the platform side, Insurity completed an "
        "18-month rebuild of their entire integration layer (400+ REST connectors, 3-week go-live), "
        "fundamentally improving their competitive position in new-market implementation speed. "
        "Majesco achieved AWS Insurance Competency — the first P&C vendor to do so — unlocking "
        "preferred Marketplace placement and AWS enterprise co-sell capabilities."
    ),
    "period_summary": (
        "Q1 2026 represents the most competitive quarter in the P&C InsurTech market in recent history, "
        "with record funding, AI product launches, and consolidation activity across all six tracked competitors."
    ),
}

def run_demo():
    print("Initialising database …")
    init_db()

    print(f"Writing {len(SNAPSHOTS)} competitor snapshots to DB …")
    for cid, snap in SNAPSHOTS.items():
        upsert_daily_snapshot(
            snapshot_date=TODAY,
            competitor_id=cid,
            summary=snap["summary"],
            key_signals=snap["key_signals"],
            sentiment_score=snap["sentiment_score"],
        )

    print("Generating daily digest (Markdown) …")
    md_path = generate_daily_digest_markdown(SNAPSHOTS, digest_date=TODAY)
    print(f"  ✓ {md_path}")

    print("Generating HTML comparison report …")
    html_path = generate_html_report(COMPARISON_REPORT, report_date=TODAY, period_months=3)
    print(f"  ✓ {html_path}")

    print("\nOutputs:")
    print(f"  Markdown digest : {md_path}")
    print(f"  HTML report     : {html_path}")

if __name__ == "__main__":
    run_demo()
