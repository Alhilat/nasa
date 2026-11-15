# PIRX release verification

## Production path

The confirmed Render workspace is `عبدالرحمن's workspace`. The existing `Pirx-nasa`
service is a Python web service at `https://pirx-nasa.onrender.com`, using branch
`main` and the combined native build. No second static site is needed.

- Build: `bash infrastructure/render-build.sh`.
- Start: `alembic -c backend/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Set `APP_ENV=production` to enforce the startup artifact guard.
- Recommended HTTP health path: `/api/v1/health/live`. The service currently uses
  a TCP check; changing that field is a separate Dashboard/API setting.
- The optional two-service `render.yaml` is for a separately reviewed deployment;
  do not sync it over the existing Python service to fix a website problem.

## Release gates

1. Run backend/frontend checks and the disposable PostGIS integration suite in CI.
2. Run `python scripts/check_release.py --write-metadata` after building the
   frontend. This rejects missing HTML, missing/empty JavaScript or CSS referenced
   by that HTML, and asset paths escaping the build directory.
3. Review migrations and confirm backup/rollback compatibility before deploying.
4. Push the reviewed commit and monitor the specific Render deploy to `live`.
5. Verify the exact deployed commit and public behavior:

   ```powershell
   python scripts/smoke_release.py https://pirx-nasa.onrender.com --expect-commit COMMIT_SHA --require-data
   python scripts/audit_archive.py
   ```

The smoke check uses GET and HEAD for all pages, verifies referenced assets,
checks `/api/v1/health/build`, database readiness, a bounded source query, unknown
API route handling and a real basemap tile. CI skips only the external map provider;
production verification must include it. Neither command performs data imports.
`audit_archive.py` verifies archived source bytes, source row counts, canonical
hash uniqueness and provenance consistency in a read-only database transaction.

`/api/v1/health/build` reports API/frontend status and a public commit SHA only.
Native Render builds capture `RENDER_GIT_COMMIT`; CI uses `GITHUB_SHA`. A local or
Docker build without Git metadata may report a null SHA and cannot pass an exact
commit smoke check until its builder supplies that metadata.

## Backend-only Supabase access

Migration `0004_backend_access` enables default-deny RLS on the 14 application
tables, including migration metadata, and revokes table grants from PUBLIC and
the Supabase `anon`/`authenticated` roles when they exist. There are intentionally
no browser policies: the React app accesses FastAPI, not the Supabase Data API.
Existing owner connections continue working. No broad BYPASSRLS grant is created.
The migration pins the two application trigger functions to their owning schema.
It acquires all application table locks before changing permissions, using NOWAIT
inside a savepoint. A busy archive retries up to 30 times, releasing partial locks
between attempts. Exhaustion aborts the transaction and keeps the old release;
it never terminates readers or applies a partial access change.

The database owner currently supplies backend and pipeline access. A dedicated
read-only API identity and separately scoped ingestion role remain follow-up work;
provision and test their explicit policies before changing `DATABASE_URL`.
PostGIS extension-owned objects are untouched and require a separate review.

CI tests a fresh migrated schema, owner access, and a disposable non-login role
with deliberately broad grants to prove RLS still blocks reads/inserts/updates/
deletes. The role/grants and synthetic writes roll back; no production fixtures
are inserted. Existing importer integration tests verify owner imports still work.

## Application rollback

Rollback the application through Render only to a version compatible with the
current database revision. A rollback does not reverse migrations, imports or
external effects. Older code that hardcodes `0003_calibration` will fail database
readiness against `0004_backend_access`; prepare a compatible corrective release
instead of disabling RLS or restoring anonymous grants.

The access migration refuses automatic downgrade. An emergency access adjustment
must explicitly preserve the backend-only architecture and be tested against the
real service role. No archive table or source bytes need to be deleted.

A backup/restore drill, credential rotation verification, dedicated runtime role,
and a real production rollback rehearsal are not established by a passing smoke
check. Record those as separate operational evidence before claiming the entire
site-improvement roadmap is complete.
