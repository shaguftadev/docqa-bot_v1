# Deployment and operations

## Intended deployment level

The checked-in Compose stack is for local development and a private portfolio demo. It starts FastAPI, PostgreSQL, Qdrant, and Streamlit. Host ports are bound to loopback; PostgreSQL is only reachable on the internal Compose network. Compose waits for PostgreSQL health before starting the API, and the UI waits for the API health check. Docker documents that `service_healthy` dependencies wait for a passing health check, and recommends an additional Compose file for environment-specific production changes ([startup ordering](https://docs.docker.com/compose/how-tos/startup-order/), [Compose in production](https://docs.docker.com/compose/how-tos/production/)).

This is not ready for public customer traffic. It has no authentication or authorization, tenant IDs are supplied by the caller, and the included database password is a local development value. Keep the UI/API private until those controls and operational requirements are implemented and reviewed.

## Local setup

1. Install Docker Desktop and make sure its Linux container engine is running.
2. Copy `.env.example` to `.env`; set `GEMINI_API_KEY` locally if you want answer generation. Never commit `.env`.
3. From the repository root, start the full stack:

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

4. Open the Streamlit console at `http://127.0.0.1:8501`. FastAPI is available at `http://127.0.0.1:8000` and its OpenAPI page is `/docs`.
5. Seed synthetic order and ticket records if you want to demo lookup tools:

   ```powershell
   docker compose exec api python -m scripts.seed_demo_records
   ```

6. Upload `data/sample_docs/return_policy.md` through the UI, then ask: “What should I do if my item arrived damaged?”

The API startup command applies Alembic migrations before serving. On the first knowledge query, FastEmbed may download its model into the named `embedding_model_cache` volume. Allow enough disk space and initial startup time.

## Operations

```powershell
docker compose ps
docker compose logs --tail 100 api ui postgres qdrant
docker compose restart api
docker compose down
```

The named volumes retain PostgreSQL, Qdrant, and embedding cache data when the containers stop. `docker compose down -v` deletes those volumes; use it only when intentionally resetting local demo data. There is no automated backup job in this repository. Before any real deployment, define and test database and vector-data backup and restore procedures.

To update images after pulling code:

```powershell
git pull
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

## Private single-VM demo

A small Linux VM with Docker Engine and the Compose plugin can run this stack for a private demo. Clone the repository onto the VM, store runtime secrets outside Git, then use the same Compose commands. Use a VPN or a restricted SSH tunnel to access the loopback-bound UI. Do not expose ports 8000, 8501, 5432, or 6333 directly to the public internet.

For an internet-facing deployment, use a separate production design and review at least these items first:

- Authenticate API and UI users and derive tenant scope from verified identity, not request fields.
- Replace local credentials with a secret manager and rotate all credentials.
- Use managed PostgreSQL and Qdrant (or secure self-hosted services) with private networking, TLS, access policies, backups, and tested restores.
- Put a maintained TLS reverse proxy or gateway in front of the application; add rate limits and request-size limits at the edge.
- Define retention and deletion behavior for customer messages and LangGraph checkpoints.
- Add monitoring, alerting, dependency health checks, capacity limits, and an incident/recovery procedure.
- Run security review and load tests with the intended data and model-provider agreements.

The demo uses synthetic records and should remain an isolated demonstration until these controls are implemented.
