# Two-minute SupportPilot AI demo

Use only the synthetic sample policy, orders, tickets, and customer messages in this walkthrough. Start Compose first and seed demo records with `docker compose exec api python -m scripts.seed_demo_records`.

## 0:00–0:15 — Set context

“SupportPilot AI is a portfolio prototype for policy-grounded support. It can search a business policy, look up synthetic records, and pause sensitive requests for a human. It does not send customer messages or issue refunds.”

## 0:15–0:40 — Ground an answer

In **Knowledge Documents**, upload `data/sample_docs/return_policy.md`. In **Ask SupportPilot**, ask: “What should I do if my item arrived damaged?”

Show the damaged-items citation and point out the seven-day contact window. Explain that the answer is generated from retrieved policy chunks and citations are checked against those chunks.

## 0:40–0:55 — Look up an order

In **Orders & Tickets**, look up `ORD-1001`. Show its synthetic shipment status and tracking number. Mention that the tool performs a read-only exact lookup scoped by tenant.

## 0:55–1:25 — Pause for a human

In **Ask SupportPilot**, submit: “I want to complain about an unsafe product.” Open **Human Review**, load the pending workflow, inspect the customer message and draft, then reject it for triage (or approve the edited draft). Show that the workflow records the decision and that no message is sent.

## 1:25–1:45 — Show evaluation and engineering limits

Briefly show `reports/evaluation/agent_baseline.json` and `reports/evaluation/retrieval_baseline.json`. State that these are small synthetic baselines: 19 routing examples and three queries over one policy, not production accuracy or customer-impact claims.

## 1:45–2:00 — Close with boundaries

“The demo is containerized and reproducible. Before connecting real customer systems, I would add identity-based tenant enforcement, authentication, operational backup/restore, privacy controls, and a customer-reviewed evaluation set.”
