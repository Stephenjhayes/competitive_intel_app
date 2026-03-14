"""
Seed the database with realistic sample competitive intelligence events
so the analysis + report phases have data to work with.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from storage.database import init_db, insert_raw_event
from datetime import datetime, timedelta
import random

random.seed(42)

SAMPLE_EVENTS = {
    "duck_creek": [
        ("press_room", "Duck Creek Technologies Closes $200M Series D Funding Round",
         "Duck Creek Technologies announced today it has raised $200 million in a Series D "
         "funding round led by Vista Equity Partners. The funds will be used to accelerate "
         "cloud migration of its policy administration and claims management platforms. CEO "
         "Mike Jackowski stated the investment validates their cloud-first strategy for P&C insurers."),
        ("news", "Duck Creek Wins 7 New Tier-1 Carrier Contracts in Q1",
         "Duck Creek Technologies has signed agreements with seven major property and casualty "
         "insurers this quarter, including two Fortune 500 carriers. The wins are concentrated "
         "in their cloud-based Duck Creek OnDemand platform. Analysts note this accelerates "
         "their pace versus prior year and puts pressure on Guidewire's renewal pipeline."),
        ("blog", "Introducing Duck Creek Automated Underwriting — AI at the Core",
         "We're excited to announce Duck Creek Automated Underwriting, our new AI-powered "
         "underwriting engine that integrates directly with Duck Creek Policy. Built on "
         "large language models, it can process complex commercial submissions in under "
         "2 minutes versus the industry average of 3-5 days. Early beta customers report "
         "40% reduction in underwriting time and 15% improvement in loss ratios."),
        ("careers", "Duck Creek Hiring 120 Cloud Engineers and ML Scientists",
         "Duck Creek Technologies has posted 120 new positions in Q1, heavily weighted toward "
         "cloud platform engineers (AWS, Azure), ML scientists, and data engineers. The hiring "
         "surge follows the Series D close and signals aggressive product expansion. "
         "Notable postings include a VP of AI Products and Head of LLM Engineering."),
        ("news", "Duck Creek Partners with Microsoft Azure for Global Cloud Expansion",
         "Duck Creek and Microsoft announced a strategic partnership making Azure the preferred "
         "cloud for Duck Creek OnDemand globally. The deal includes co-selling agreements and "
         "joint go-to-market for European and APAC markets where Duck Creek has historically "
         "had limited presence."),
    ],
    "sapiens": [
        ("press_room", "Sapiens Q4 Revenue Up 18% YoY; Raises Full-Year Guidance",
         "Sapiens International reported Q4 revenue of $132M, up 18% year-over-year, beating "
         "consensus estimates by $4M. Cloud ARR now represents 62% of total revenue. The company "
         "raised full-year 2025 guidance to $560-570M. CEO Roni Al-Dor highlighted momentum in "
         "North America enterprise deals as the key growth driver."),
        ("news", "Sapiens Launches CoreSuite AI — Next-Gen Policy Admin with Embedded Intelligence",
         "Sapiens unveiled CoreSuite AI at its annual customer conference in Orlando. The platform "
         "embeds generative AI throughout the policy lifecycle — from quoting to claims. The "
         "system includes a natural language policy search, automated endorsement processing, "
         "and an AI claims triage engine. Pricing starts at $2M annually for mid-market carriers."),
        ("sec", "Sapiens SPNS 10-K Filing: Cloud Migration Capex Up 45%, Headcount +380 YoY",
         "Sapiens International annual filing reveals R&D spending increased to $89M (up 32% YoY), "
         "with cloud infrastructure investment up 45%. Headcount grew by 380, with 60% of new hires "
         "in engineering roles. The filing notes four ongoing Tier-1 carrier implementations in "
         "North America, with go-live dates expected in H2 2025."),
        ("blog", "How We Built the Sapiens AI Underwriting Copilot in 6 Months",
         "Engineering blog post detailing the architecture of Sapiens' AI Underwriting Copilot. "
         "Built on Claude API with RAG over carrier-specific policy forms and rate manuals. "
         "The system achieved 94% accuracy on structured commercial lines in testing. The team "
         "processed 2.3M historical submissions to fine-tune the retrieval pipeline."),
    ],
    "majesco": [
        ("press_room", "Majesco Achieves AWS Insurance Competency — First P&C Platform Vendor",
         "Majesco has become the first P&C insurance platform vendor to achieve AWS Insurance "
         "Competency status. This recognition validates Majesco CloudInsurer's technical "
         "architecture and security posture. The designation opens preferred placement in AWS "
         "Marketplace and joint-selling opportunities with AWS enterprise teams."),
        ("news", "Majesco Cloud Revenue Surges 34% as Legacy Migrations Accelerate",
         "Majesco reported cloud subscription revenue grew 34% in Q3, driven by accelerated "
         "migrations from on-premise legacy systems. The company now has 47 active cloud "
         "implementations, up from 31 a year ago. Management cited regulatory pressure and "
         "talent scarcity as the two forces most accelerating carrier cloud adoption."),
        ("careers", "Majesco Opens New AI Center of Excellence in Hyderabad",
         "Majesco announced the opening of a 200-person AI Center of Excellence in Hyderabad, "
         "India, focused on insurance-specific AI development. The center will develop predictive "
         "pricing models, automated underwriting tools, and fraud detection algorithms. "
         "The facility represents a $15M investment over three years."),
    ],
    "insurity": [
        ("press_room", "Insurity Acquires ClaimVantage for $85M — Bolsters Claims Intelligence",
         "Insurity announced the acquisition of ClaimVantage, a claims management software "
         "provider, for $85M. The deal adds 140 carrier clients and a modern cloud-native "
         "claims platform to Insurity's portfolio. ClaimVantage's AI-powered claims triage "
         "and fraud detection capabilities were cited as the primary strategic rationale."),
        ("news", "Insurity Expands into Specialty Lines with New E&S Platform Launch",
         "Insurity launched a dedicated Excess & Surplus lines platform at RIMS 2025. The new "
         "offering targets the fast-growing E&S market with flexible rating, rapid product "
         "configuration, and real-time market pricing integrations. Three managing general agents "
         "have signed letters of intent for the platform."),
        ("blog", "Why We Rebuilt Our Entire API Layer — A Technical Deep Dive",
         "Insurity's CTO blog on the 18-month project to rebuild their entire integration layer "
         "as a RESTful API-first architecture. The new layer supports 400+ third-party integrations "
         "including all major reinsurance platforms, weather data providers, and claims data "
         "exchanges. The project reduced average integration time from 6 months to 3 weeks."),
    ],
    "applied_systems": [
        ("press_room", "Applied Systems Reaches 1,500 Agency Customers on Applied Epic Cloud",
         "Applied Systems announced that 1,500 insurance agencies have migrated to Applied Epic "
         "Cloud, its SaaS agency management system. The milestone represents 40% of their total "
         "customer base. CEO Taylor Rhodes credited a simplified migration program and competitive "
         "pricing as the drivers behind accelerating cloud adoption."),
        ("news", "Applied Systems Launches AI Agent for Commercial Lines Submissions",
         "Applied Systems unveiled Applied AI Agent, a new product that automates commercial "
         "lines submission workflows for independent agencies. The agent uses computer vision "
         "to extract data from applications, acord forms, and supplementals, then routes to "
         "the optimal carrier markets. Early adopters report 70% reduction in submission preparation time."),
        ("careers", "Applied Systems Doubling Engineering Team Following $100M Investment",
         "Following a $100M strategic investment from Hellman & Friedman, Applied Systems "
         "announced plans to double its engineering headcount to 1,200 over 18 months. "
         "Priority hiring areas include AI/ML engineering, cloud platform, and developer experience. "
         "The company also plans to open a new engineering hub in Austin, Texas."),
    ],
    "one_shield": [
        ("press_room", "OneShield Partners with EY to Deliver Pre-Configured Insurance Suites",
         "OneShield Software and EY announced a global implementation partnership to deliver "
         "pre-configured insurance solutions combining OneShield's platform with EY's insurance "
         "domain assets and implementation methodology. The partnership targets mid-market carriers "
         "seeking faster time-to-value versus traditional multi-year implementations."),
        ("news", "OneShield Raises $40M Series C to Accelerate SaaS Transition",
         "OneShield Software closed a $40M Series C round led by Warburg Pincus. The investment "
         "will fund the company's transition from on-premise perpetual licenses to a SaaS delivery "
         "model. CEO Dan Carmichael noted that 70% of new deals in 2024 were cloud subscriptions, "
         "versus just 20% in 2022."),
    ],
}

def seed():
    init_db()
    now = datetime.utcnow()
    total = 0
    for comp_id, events in SAMPLE_EVENTS.items():
        for i, (source_type, title, content) in enumerate(events):
            days_ago = random.randint(0, 14)
            published = (now - timedelta(days=days_ago, hours=random.randint(0, 23))).isoformat()
            insert_raw_event(
                competitor_id=comp_id,
                source_type=source_type,
                url=f"https://example.com/{comp_id}/{i}",
                title=title,
                content=content,
                published_at=published,
            )
            total += 1
    print(f"Seeded {total} sample events across {len(SAMPLE_EVENTS)} competitors.")

if __name__ == "__main__":
    seed()
