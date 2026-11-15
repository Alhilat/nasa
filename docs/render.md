# Render deployment

The repository includes a Render Blueprint at [`render.yaml`](../render.yaml).
It creates:

- `firescope-db`: a PostGIS-backed Render Postgres database.
- `firescope-api`: the FastAPI container, with migrations run during startup.
- `firescope-web`: the Vite static site, configured to call the API service.

## Deploy

1. In Render, choose **New → Blueprint** and connect this repository.
2. Select the `main` branch and apply the Blueprint.
3. Enter `MAP_KEY` and `GEMINI_API_KEY` when Render prompts for secret values.
4. Wait for the database, API, and frontend services to finish deploying.
5. Open `https://firescope-web.onrender.com`.

The API health endpoint is `https://firescope-api.onrender.com/api/v1/health/ready`.

The Blueprint uses Render’s Free plan for a low-cost preview. Free Postgres databases
expire after 30 days and have a 1 GB storage limit; use a paid database plan for a
persistent deployment. If you rename either service, update `CORS_ORIGINS` and
`VITE_API_BASE_URL` in `render.yaml` to match the resulting `onrender.com` URLs.
