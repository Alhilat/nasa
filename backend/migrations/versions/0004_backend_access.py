"""Keep application tables accessible through the trusted backend only.

No browser Data API access is required. Table owners retain direct access;
non-owner service roles must be explicitly provisioned in a separate change.
Extension-owned PostGIS tables and functions are deliberately out of scope.
"""

from alembic import op

from app.migration_locks import acquire_release_locks

revision = "0004_backend_access"
down_revision = "0003_calibration"
branch_labels = None
depends_on = None

TABLES = (
    "alembic_version",
    "sensors",
    "source_files",
    "raw_observations",
    "processing_jobs",
    "harmonized_aggregates",
    "aggregate_sources",
    "analytical_results",
    "raw_records",
    "normalized_observations",
    "observation_records",
    "data_quality_reports",
    "import_checkpoints",
    "calibration_models",
)


def upgrade():
    if op.get_context().as_sql:
        names = ", ".join(f'"{table}"' for table in TABLES)
        op.execute(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE NOWAIT")
    else:
        acquire_release_locks(op.get_bind(), TABLES)
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')
        # These roles exist on Supabase, but not on ordinary local PostgreSQL.
        op.execute(f"""DO $$
        DECLARE browser_role text;
        BEGIN
            FOR browser_role IN SELECT rolname FROM pg_roles
                WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON TABLE %I FROM %I', '{table}', browser_role);
            END LOOP;
        END $$""")
    # Resolve names only in the owning application schema and pg_catalog.
    op.execute("""DO $$ BEGIN
        EXECUTE format('ALTER FUNCTION reject_source_mutation() SET search_path TO %I, pg_catalog',
                       current_schema());
        EXECUTE format('ALTER FUNCTION set_raw_record_hash() SET search_path TO %I, pg_catalog',
                       current_schema());
    END $$""")


def downgrade():
    raise RuntimeError(
        "Do not reopen browser access; restore reviewed grants and policies explicitly"
    )
