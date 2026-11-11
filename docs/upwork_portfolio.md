# Upwork portfolio copy and service packages

## Portfolio title

**SupportPilot AI — Citation-Grounded Customer Support Automation Prototype**

## Short overview

I built an independently developed support automation prototype that searches company policy documents, drafts evidence-grounded answers with citations, looks up synthetic order/ticket records, and pauses sensitive cases for human review. It uses FastAPI, LangGraph, PostgreSQL, Qdrant, Gemini, Docker Compose, and Streamlit. The demo includes a labeled evaluation set and reports; it does not send replies or issue refunds.

## Portfolio description

Support teams often need fast answers from policy documents while keeping account-specific requests and sensitive complaints under human control. SupportPilot AI demonstrates one way to structure that workflow:

- Ingest FAQ, policy, and manual files and retrieve relevant chunks from Qdrant.
- Draft grounded answers, check returned citations against retrieved chunks, and abstain when evidence is insufficient.
- Route requests to tenant-scoped synthetic order/ticket tools or to human review.
- Persist workflow metadata and LangGraph checkpoints in PostgreSQL for pause/resume review.
- Explore the workflow through a Streamlit console and Docker Compose.

Evaluation is deliberately transparent: the current agent baseline covers 19 curated cases, and retrieval covers three queries against one synthetic policy. These are engineering checks, not claims of production accuracy or business savings.

## Suggested fixed-scope packages

These are starting examples in USD, not guaranteed market prices. Upwork's 2026 guidance gives directional hourly ranges of $35–$60 for AI engineers and $30–$150 for AI agent developers; actual fixed bids should be recalculated from scope, data condition, integrations, review time, and the freelancer's own target rate ([Upwork rate guide](https://www.upwork.com/resources/upwork-hourly-rates/)). Upwork currently states a freelancer service fee range of 0%–15% per contract, shown before accepting the offer ([Upwork fee help](https://support.upwork.com/hc/en-us/articles/211062538-Learn-about-the-Freelancer-Service-Fee)). Third-party model, hosting, vector database, and labeling costs are separate.

| Package | Example scope | Illustrative fixed price |
|---|---|---:|
| Policy Q&A pilot | One knowledge source (up to 10 documents), one upload/search/answer flow, citations and abstention, local run instructions, handoff session | $900–$1,800 |
| Support workflow prototype | Up to three intents, one or two read-only business tools, human-review pause, small labeled evaluation set, API and demo UI | $2,000–$4,500 |
| Evaluation and integration hardening | Review an existing prototype, add an integration or workflow path, expand test/evaluation coverage, document operational risks and handoff | $1,200–$3,200 |

Confirm document volume, formats, data access, identity/tenant needs, providers, environments, acceptance examples, and client-owned credentials before quoting. Exclude production security certification, unlimited documents, guaranteed answer accuracy, ongoing hosting, external system write actions, and third-party API usage unless separately scoped.

## Suggested scope boundary

Deliver a tested prototype against agreed synthetic or client-approved sample data, with explicit citations, abstention, read-only integrations, and human approval for consequential actions. Production access, authentication, authorization, retention/deletion, security review, backups, monitoring, service levels, and customer-system write access require a separate discovery and implementation scope.
