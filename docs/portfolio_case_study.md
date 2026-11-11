# SupportPilot AI — portfolio case study

## Summary

SupportPilot AI is an independently developed portfolio MVP for support teams. It indexes policy documents, answers supported questions with citations, looks up synthetic orders and tickets, classifies requests, and pauses sensitive cases for a human decision. It is not a client deployment and does not send customer replies or issue refunds.

## Problem and approach

Support teams need answers grounded in current policies and a clear way to route requests that need account data or human judgment. This demo uses a small FastAPI service with PostgreSQL metadata, Qdrant retrieval, Gemini structured answer generation, and a LangGraph workflow. Each external action is constrained: retrieval is tenant-filtered, record tools use exact tenant-and-ID lookups, sensitive complaints pause for a human, and approved replies remain unsent drafts.

## What is implemented

- PDF, Markdown, and UTF-8 text ingestion with chunk metadata and Qdrant search.
- Evidence-grounded answers, validated citations, and a fixed abstention when evidence is insufficient.
- Deterministic intent/priority classification and explicit graph routing.
- Typed synthetic order and ticket lookup tools.
- PostgreSQL workflow records, a PostgreSQL-backed LangGraph checkpointer, and pause/resume approval endpoints.
- Streamlit console for document upload, support requests, record lookup, and approval review.
- Docker Compose stack and repeatable agent/retrieval evaluation scripts.

## Measured demo results

The committed agent report evaluates 19 hand-authored examples: intent, priority, route, tool-selection, terminal-status, and human-review routing each matched the labels for all 19 cases. The recorded offline graph p50/p95 latency was 2.054/5.091 ms with stub tools and `InMemorySaver`; it excludes databases, Qdrant, embeddings, Gemini, and network time.

The committed retrieval report evaluates three queries against one synthetic return-policy document. Recall@5 and MRR were both 1.0. The recorded local API search p50/p95 latency was 53.87/55.63 ms over nine requests. This checks three known sections in one document; it does not establish general retrieval quality, customer impact, production latency, or answer correctness at scale.

See [`../reports/evaluation/`](../reports/evaluation/) for the generated reports and [`../data/eval/`](../data/eval/) for labeled cases.

## Architecture choices

- Deterministic routing keeps the demo predictable and makes its decisions inspectable; classification quality still needs a larger independently reviewed dataset.
- PostgreSQL stores metadata and workflow records; Qdrant stores vectors. LangGraph checkpoints let paused workflows resume using a stable workflow/thread ID.
- The model only drafts from retrieved evidence. Local validation checks citations against retrieved chunk IDs before an answer is returned.
- Synthetic business data avoids using real customer information in a public portfolio repository.

## Limits and next production work

The API has an optional Cognito RS256 access-token verifier and checks tenant-scoped requests against a signed tenant claim. The Streamlit UI and reference trigger implement Hosted UI PKCE sign-in, token refresh/logout, and a reviewer-group approval scope, but no Cognito user pool or real token has been configured or tested. Public deployment controls, rate limiting, comprehensive retention/deletion, operational backups, and load/security testing remain open. The local Compose credentials and loopback exposure are for development. A real client engagement would begin with identity/data boundaries, failure behavior, operational ownership, and a reviewed evaluation set before connecting customer systems.
