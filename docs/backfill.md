# Resumable NASA FIRMS backfill

`pipeline backfill` imports real MODIS and S-NPP VIIRS data for the Jordan demo
region from 2000 through the current UTC date. It uses NASA's published annual
country-file catalog, then fills the remaining dates with standard-processing
and near-real-time API products according to their current published availability.
It never generates observations or assumes that an unavailable day means zero.

## Run and resume

Install the project as described in the README. The `pipeline` command is an
alias of `firescope-pipeline`. From the repository root on Windows:

```powershell
# Inspect the real source plan without importing observations.
.\.venv\Scripts\pipeline.exe backfill --region jordan --plan

# Import from 2000 through today. Repeating this command resumes automatically.
.\.venv\Scripts\pipeline.exe backfill --region jordan --report reports/backfill-jordan.json
```

The module form works too:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli backfill --region jordan
```

Use `--start YYYY-MM-DD` and `--through YYYY-MM-DD` for a bounded run.
`--through` is inclusive; internal intervals and checkpoint dates have exclusive
ends. Future dates are rejected. All boundaries are UTC. The current UTC day is
provisional and may contain only the overpasses already processed.

`MAP_KEY` is read from the server-side environment or root `.env`; it never
appears in flags, source URLs, reports or exception messages. Annual country
files can be imported without a key; unavailable API tails are then explicitly
reported. No additional API key is needed when the workstation's existing key
is configured. `DATABASE_URL` selects the migrated PostGIS archive.

## Source and spatial scope

### Docker execution

After building the Compose stack, create a reusable tools container. Its writable
container filesystem holds the cache; the PostGIS volume holds committed imports:

```sh
docker compose --env-file .env -f infrastructure/compose.yaml --profile tools run --name pirx-backfill pipeline backfill --region jordan --output /tmp/pirx-backfill
```

After stopping or completing that first run, resume that container with:

```sh
docker start --attach pirx-backfill
```

Do not add `--rm` if you want to retain that container's download cache. Database
checkpoints remain authoritative even if a cache/container is replaced. This
avoids writing to the pipeline's read-only `/data` mount or assuming a writable
host report bind mount. The host `.venv` command above remains the workstation's
verified execution path.

The demo uses the existing Jordan Natural Earth country polygon inside the
Jordan API envelope `[34.8, 29.0, 39.4, 33.5]`. The same point selection is applied
to annual and API imports. The region uses a simplified country boundary; it
does not represent a survey boundary or certify the larger dashboard study
rectangle. Every source's original bytes, checksum, native product version,
processing level, retrieval timestamp, request scope and quality report remain
in the existing archive/provenance tables.

The planner:

1. Starts each sensor at its operational availability; earlier dates are marked
   `pre_operational_sensor`, with no invented VIIRS observations before 2012.
2. Uses only catalog-listed completed-year MODIS and S-NPP country files.
3. Covers annual-file holes and the current year with available standard API data.
4. Uses NRT only for the remaining supported dates, retaining its processing label.
5. Lists unsupported intervals as `outside_published_availability`.

NASA's live API availability can differ between sensors. A completed command
can therefore report `completed_with_gaps`. That status means the available
source plan finished, not that every requested sensor/day was observed. Archive
completeness remains distinct from satellite exposure, cloud and smoke coverage.

Official interfaces: [annual country catalog](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt),
[area API](https://firms.modaps.eosdis.nasa.gov/api/area/),
[data availability API](https://firms.modaps.eosdis.nasa.gov/api/data_availability/).

## Interruption and idempotence

Stop the foreground command with **Ctrl+C**, then run the same command again.
Each source/window import and checkpoint advancement commit in one database
transaction. An interrupted current transaction rolls back; successful earlier
imports remain committed. Interrupted jobs are marked failed. A hard process or
machine termination can leave a running audit job, but cannot advance an
uncommitted checkpoint; rerunning remains safe.

Annual imports are skipped only when their database checkpoint proves the
requested dates were committed. A download ledger alone cannot cause a skip.
Extending `--through` reuses the same scope/start checkpoint and imports any
newly selected dates. Changed catalog revisions trigger a fresh download;
changed content checksums force a new checkpoint and strict import. Normalized
observations retain the existing exact
payload deduplication policy; changed measurements, product revisions and
NRT/standard versions remain distinct, not physical-fire deduplications.

API imports resume from committed windows and replay a two-day lookback by
default, so the current provisional tail can update. Use `--lookback-days 0`
to check a fully completed fixed snapshot without replaying its tail. Availability
changes or new annual products may replace an API portion of a later plan;
source-level idempotence still prevents exact repeated payloads from duplicating.

Availability gaps describe the current fetch plan. They do not erase observations
already archived from an earlier API window or another real source.

## Cache, progress and limits

Default output is `data/backfill/jordan/`, which is ignored by Git:

- `yearly_summary_files.txt`: the actual catalog snapshot.
- Annual CSV files: originals saved by atomic replacement.
- `ledger.json`: checksums, retrieval timestamps and catalog revision signatures.
- `report.json`: plan, explicit gaps, completed imports, and the last committed API window.

`--output` selects another cache directory. Completed cached files are verified
before reuse, including before a checkpoint skip. Corrupt originals fail explicitly.
Temporary partial files are never treated as complete downloads. Ctrl+C and errors
preserve a machine-readable progress report. `--report` writes an additional final
report; the cache's `report.json` is updated throughout a run.

API windows default to five days, within NASA's supported one-to-five-day range.
The existing transport applies retries, rate spacing and a request budget.
`--max-requests` defaults to 2000 API requests, counting availability checks and
retries; a budget/rate failure preserves committed progress for the next run.
Public country files retain the strict 50 MiB/file and row-validation limits.

## Code and verification

`backfill_plan.py` contains pure interval and source-priority functions.
`backfill.py` handles transport, cache, progress and orchestration.
`sync.py` and `service.py` retain transactional import/checkpoint ownership.
No migration or unauthenticated ingestion endpoint is added.

Unit tests cover source priority, annual holes, date boundaries, missing source
availability, corrupted caches, changed catalog revisions and interrupted resumes.
A disposable-schema PostGIS test interrupts an actual import, verifies that its
rows/checkpoint rolled back, resumes from the successful file, and verifies that
another run adds neither observations nor sources. Synthetic tests are never
loaded into the application archive.
