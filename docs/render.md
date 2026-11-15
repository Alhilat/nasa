# Render deployment

## Fix an existing API-only deployment

The backend can now serve the built PIRX frontend at `/`, including direct visits
to `/explorer`, `/history`, `/sources`, and `/methodology`. API requests use
`/api/v1` on the same origin; public basemap tiles use the backend's fixed provider
proxy. No separate frontend or CORS configuration is needed for this setup.

For the existing `https://pirx-nasa.onrender.com` **Python** web service, configure:

| Setting | Value |
| --- | --- |
| Branch | `main` |
| Root Directory | Leave blank (repository root) |
| Build Command | `bash infrastructure/render-build.sh` |
| Start Command | `alembic -c backend/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/v1/health/live` |
| `NODE_VERSION` | `22.12.0` |

Keep the existing Supabase `DATABASE_URL`, `MAP_KEY`, and `GEMINI_API_KEY` in
Render's secret environment variables. Use **Deploy latest commit** after saving
the build/start settings. A restart alone does not rebuild the frontend.

For a **Docker** web service, keep the repository root as its build context and
`infrastructure/backend.Dockerfile` as its Dockerfile. It now builds and includes
the frontend automatically. Redeploy the latest commit.

Verify `/` returns HTML, `/assets/...` returns the compiled JavaScript/CSS,
`/history` works after a refresh, and `/api/v1/health/ready` reports the database
connected. If `/` still returns `{"detail":"Not Found"}`, check that the deployed
commit includes this change and its build log contains `vite build`.

## Optional separate-service Blueprint

The repository also includes a Render Blueprint at [`render.yaml`](../render.yaml).
It creates:

- `firescope-api`: the FastAPI container, with migrations run during startup.
- `firescope-web`: the Vite static site, configured to call the API service.

The database is hosted by Supabase rather than Render.

## Deploy

1. In Render, choose **New → Blueprint** and connect this repository.
2. Select the `main` branch and apply the Blueprint.
3. In Supabase, enable the PostGIS extension and copy the **Session pooler** connection
   string from **Connect**. Add it to the Render API service as the secret
   `DATABASE_URL`. The session pooler is the IPv4-compatible option for Render.
4. Enter `MAP_KEY` and `GEMINI_API_KEY` when Render prompts for secret values.
5. Wait for the API and frontend services to finish deploying.
6. Open `https://firescope-web.onrender.com`.

The API health endpoint is `https://firescope-api.onrender.com/api/v1/health/ready`.

The static site routes `/basemap/imagery/*` and `/basemap/reference/*` to the
existing Esri tile services before applying the SPA fallback. These routes
provide the tile forwarding used by the local Vite server and the Docker Nginx
configuration. Static sites use Render's CDN and omit the service `region` field.

Supabase stores the application data persistently. The API runs the Alembic migrations
on startup. If you rename either Render service, update `CORS_ORIGINS` and
`VITE_API_BASE_URL` in `render.yaml` to match the resulting `onrender.com` URLs.

The Supabase connection string is never committed to the repository. For a fresh
Supabase database, the first API deployment creates the application schema; existing
Render Postgres data requires a separate dump/restore migration.
