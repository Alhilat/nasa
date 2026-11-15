# Render deployment

The repository includes a Render Blueprint at [`render.yaml`](../render.yaml).
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
