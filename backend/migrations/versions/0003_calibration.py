"""Immutable statistical calibration artifacts, scope validation and input provenance."""
from alembic import op

revision = "0003_calibration"
down_revision = "0002_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE calibration_models (
        model_version text PRIMARY KEY CHECK (model_version ~ '^[a-f0-9]{64}$'),
        job_id uuid NOT NULL REFERENCES processing_jobs(id),
        method text NOT NULL CHECK (method IN ('baseline','regression','quantile_mapping')),
        algorithm_version text NOT NULL,
        metric text NOT NULL,
        status text NOT NULL CHECK (status IN ('candidate_only','supported_for_scope')),
        artifact jsonb NOT NULL,
        validation jsonb NOT NULL,
        input_manifest jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TRIGGER immutable_calibration_models
        BEFORE UPDATE OR DELETE ON calibration_models
        FOR EACH ROW EXECUTE FUNCTION reject_source_mutation()""")
    op.execute("""CREATE TRIGGER immutable_truncate_calibration_models
        BEFORE TRUNCATE ON calibration_models
        FOR EACH STATEMENT EXECUTE FUNCTION reject_source_mutation()""")


def downgrade():
    raise RuntimeError("Calibration model history must be preserved; restore a verified backup")
