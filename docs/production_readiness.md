# Production readiness gaps

This document tracks work required before SupportPilot AI can serve real customer traffic. The current application is a local portfolio prototype using synthetic data. Items marked **Open** are not implemented or have not been verified; they are not claims that the control is partially effective.

## Release decision

**Public production launch: blocked.** Keep the current Compose stack private and use synthetic data until the P0 controls below are implemented and verified. Completing this checklist is necessary but does not by itself constitute a security certification.

The initial Cognito verifier and tenant-claim enforcement are implemented behind `AUTH_ENABLED`. Seventeen focused token/configuration and cross-tenant API checks and the complete 64-test suite pass. These tests use generated signing keys; no AWS Cognito user pool, real token, pre-token-generation trigger, or hosted sign-in flow has been configured or exercised.

## P0 — identity, tenant boundaries, and exposure

| Gap | Current state | Work required | Closure evidence |
|---|---|---|---|
| Authentication | In progress | The API can validate Cognito RS256 access tokens when enabled. Configure a user pool/app client, integrate UI sign-in or a managed auth proxy, and define short token lifetime, revocation, and account recovery behavior. | Unauthorized API requests are rejected; real Cognito-issued access tokens pass; ID tokens, wrong issuer/client, expired tokens, and missing-tenant tokens fail; UI sign-in and session handling are reviewed. |
| Authorization and tenant isolation | In progress | Tenant-bearing API routes compare the requested tenant to the verified access-token `tenant_id` claim. Configure a Cognito pre-token-generation trigger to add this trusted claim, then check all document, retrieval, record, approval, workflow status, and checkpoint flows. Add role/scope checks for approval decisions. | Cross-tenant tests cover every tenant-owned endpoint and prove access is denied. Approval permissions are tested separately from tenant membership. |
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

1. Choose the hosting environment; configure Cognito user-pool/app-client settings and document the data classification and tenancy model.
2. Configure and test the signed tenant claim and approval scopes before connecting real customer data.
3. Add secret handling, private networking, HTTPS, request limits, and deployment controls.
4. Define retention and backup/recovery; implement and exercise deletion and restore.
5. Add monitoring, runbooks, capacity limits, and failure handling.
6. Complete realistic quality, security, load, durable-workflow, and browser verification.
7. Review all evidence and make an explicit release decision.

For local operation and the current deployment boundary, see [deployment and operations](deployment.md). The implementation and measurement scope are summarized in the [portfolio case study](portfolio_case_study.md).
