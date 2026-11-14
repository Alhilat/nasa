# Operations

## Environment

Copy the root `.env.example` to `.env`. The default credentials are for a loopback-only development database. The Compose file explicitly binds PostgreSQL, API and frontend ports to `127.0.0.1`. Use simple URL-safe local credentials in Compose, or supply correctly URL-encoded database credentials through a managed deployment configuration. Changing `.env` credentials does not change users/passwords in an existing PostgreSQL volume; update the database deliberately.

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | Host-run API/pipeline SQLAlchemy `postgresql+psycopg` URL; Compose constructs its own internal `db` URL |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose database initialization and container connection configuration |
| `APP_ENV` | Public environment name (`development` by default) |
| `CORS_ORIGINS` | JSON array of allowed browser origins; defaults to localhost and 127.0.0.1 on ports 5173 and 8080 |
| `MAX_QUERY_RESULTS` | Server result cap (up to the public hard limit of 5,000) |
| `VITE_API_BASE_URL` | Public browser API URL; set before frontend build |
| `VITE_MAP_STYLE_URL` | Public MapLibre style URL; defaults to CARTO dark basemap |
| `MAP_KEY` | Optional server-only NASA FIRMS API key; passed only to the pipeline container |
| `TEST_DATABASE_URL` | Integration database; enables real PostGIS tests in an isolated schema |

`.env` files are ignored. Public `VITE_*` variables are embedded in browser bundles and must contain no secrets. Rebuild the frontend after changing them. The default basemap sends browser requests to CARTO and its referenced providers; configure self-hosted map styles/assets for offline or private environments. An unavailable basemap does not synthesize scientific data.

## Migrations and archives

`alembic -c backend/alembic.ini upgrade head` applies the explicit versioned initial migration. The migration enables PostGIS, creates indexed tables, installs source mutation guards and seeds sensor **metadata only**. A database principal with extension/schema privileges must perform initial provisioning. The API never creates tables automatically.

Back up the database, including source `bytea` content, with PostgreSQL tooling. Hashes without original bytes are insufficient for source preservation. Derived outputs can be regenerated from archived inputs and versioned jobs. Schema downgrade drops archive tables and is destructive; do not run it on an archive you intend to retain. Do not remove Compose volumes to troubleshoot a startup error.

## Jobs and limits

Operator CLI ingestion uses an atomic transaction; a separately committed job records success/failure. Ingestion limits are 50 MiB and 250,000 records; aggregation is capped at 1 million input observations per interval. Run non-overlapping bounded jobs for larger archives. A process kill can leave a job in `running`: confirm the process has stopped, inspect the transaction/output state, and reconcile that specific job through an operator database session. No automatic timeout marks an active job as failed.

Read-only queries are bounded in returned records; full-query summaries are not yet backed by tiles, caches or database statement budgets. The current daily series is suitable for challenge-scale history, not unrestricted public multi-decade queries on billions of rows. Add authentication, authorization, API rate/query limits, dedicated least-privilege database roles, TLS, monitoring and workload isolation before publishing the service.

## Dependency reproducibility

`requirements.lock` pins the resolved Python environment. Install it first and then install local packages with `--no-deps`, as documented. `frontend/pnpm-lock.yaml` pins the frontend graph and `pnpm-workspace.yaml` explicitly allows esbuild’s required install step. The backend supports Python 3.12+, and Docker/CI use 3.12. Frontend Docker/CI use Node 22. Container image minor tags are fixed; pin tested image digests for a production release. Dependency upgrades require rerunning unit, PostGIS and frontend checks.

Migration `0002_ingestion` separates raw/normalized records, backfills canonical identities, preserves the legacy table and adds quality reports and API checkpoints. Back up before migrating populated archives. It deliberately refuses downgrade to avoid deleting archive/provenance data. See [ingestion operations](ingestion.md) for MAP_KEY handling, retries, quota limits, resumable imports and the Jordan starter.
