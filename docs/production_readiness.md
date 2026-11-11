# Production readiness gaps

This document tracks work required before SupportPilot AI can serve real customer traffic. The current application is a local portfolio prototype using synthetic data. Items marked **Open** are not implemented or have not been verified; they are not claims that the control is partially effective.

## Release decision

**Public production launch: blocked.** Keep the current Compose stack private and use synthetic data until the P0 controls below are implemented and verified. Completing this checklist is necessary but does not by itself constitute a security certification.

## P0 — identity, tenant boundaries, and exposure

| Gap | Current state | Work required | Closure evidence |
|---|---|---|---|
| Authentication | Open | Add a supported identity provider or API authentication scheme for the API and UI. Define session/token expiry and account recovery behavior. | Unauthorized requests are rejected; authenticated UI and API flows pass integration checks. |
| Authorization and tenant isolation | Open | Derive tenant scope from verified identity. Do not trust caller-supplied `tenant_id` as authorization. Apply tenant checks to documents, retrieval, records, approvals, workflow status, and checkpoints. | Cross-tenant access tests cover every tenant-owned endpoint and prove access is denied. |
| Public network exposure | Open | Keep internal services on private networks. Add a reviewed HTTPS gateway for any public entry point; do not expose PostgreSQL or Qdrant publicly. | External scan shows only intended HTTPS entry points; direct data-service access is blocked. |
| Secrets and credentials | Open | Remove local development credentials from deployment configuration. Store provider/database credentials in a secret manager, restrict access, and define rotation/revocation. | Deployment uses managed secrets; rotation and revoked-key behavior are documented and exercised. |
| Request abuse controls | Open | Add authentication-aware rate limits, request-size and timeout limits, and protection against repeated expensive model calls. | Limits are configured and tested for upload, answer, and agent endpoints. |

## P1 — data lifecycle and operations

| Gap | Current state | Work required | Closure evidence |
|---|---|---|---|
| Backups and recovery | Open | Define backup schedules and retention for PostgreSQL, Qdrant, uploaded/source data if introduced, and workflow checkpoints. Document recovery objectives. | Restore exercise recovers a consistent usable service from backups and records recovery time/data loss. |
| Retention and deletion | Open | Define retention, deletion, and export behavior for messages, documents, vectors, approvals, and checkpoints. Implement coordinated deletion across PostgreSQL and Qdrant. | Automated deletion tests show records and vectors are removed or retained according to policy. |
| Monitoring and alerting | Open | Add structured operational metrics, dependency checks, error/latency dashboards, and alerts with an incident owner/runbook. Avoid logging secrets or unnecessary personal data. | Staging alert exercise demonstrates detection and response for API, database, vector store, and provider failures. |
| Capacity and resilience | Open | Set resource limits, concurrency controls, provider timeout/retry budgets, and deployment scaling assumptions. | Load tests establish expected throughput and failure behavior within agreed limits. |
| Durable workflow verification | Open | Exercise PostgreSQL-backed pause/resume and human decisions end to end in the deployed-like environment. | Integration scenario pauses, survives API restart, resumes once, and rejects duplicate decisions. |

## P2 — quality and release confidence

| Gap | Current state | Work required | Closure evidence |
|---|---|---|---|
| Answer and agent quality | Open | Build a larger independently reviewed dataset covering evidence support, citations, abstention, tool errors, and escalations. Measure model answers separately from deterministic routing. | Versioned evaluation report includes sample size, review method, quality metrics, failures, and acceptance thresholds. |
| End-to-end UI verification | Open | Walk through upload, grounded answer/citations, record lookup, approval pause/decision, and evaluation results using the browser. | Recorded checklist or automated browser flow passes against the release candidate. |
| Security and dependency review | Open | Review threat model, dependency vulnerabilities, container configuration, data access, and provider terms for the intended deployment. | Findings are resolved or explicitly accepted by the project owner before release. |
| Release regression suite | Open | Run the full unit/integration suite and add deployment smoke checks to the release process. | CI or release checklist records a clean full-suite run and healthy service checks for the exact release revision. |

## Suggested execution order

1. Choose the hosting environment and identity provider; record the data classification and tenancy model.
2. Implement authentication, authorization, and tenant isolation before connecting real customer data.
3. Add secret handling, private networking, HTTPS, request limits, and deployment controls.
4. Define retention and backup/recovery; implement and exercise deletion and restore.
5. Add monitoring, runbooks, capacity limits, and failure handling.
6. Complete realistic quality, security, load, durable-workflow, and browser verification.
7. Review all evidence and make an explicit release decision.

For local operation and the current deployment boundary, see [deployment and operations](deployment.md). The implementation and measurement scope are summarized in the [portfolio case study](portfolio_case_study.md).
