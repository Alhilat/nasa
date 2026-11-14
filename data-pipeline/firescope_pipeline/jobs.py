import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.models import DataQualityReport, ProcessingJob


def run_job(factory, kind: str, version: str, parameters: dict, operation: Callable):
    """Commit job status separately so a rolled-back import still has an audit trail."""
    job_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(ProcessingJob(
            id=job_id, kind=kind, status="running", algorithm_version=version,
            parameters=parameters, output_metadata={},
        ))
    try:
        with factory.begin() as session:
            output = operation(session, job_id)
            job = session.get(ProcessingJob, job_id)
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            job.output_metadata = output
        return {"job_id": str(job_id), **output}
    except Exception as exc:
        with factory.begin() as session:
            job = session.get(ProcessingJob, job_id)
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            # Do not persist credentials, row data or database connection errors.
            job.error_message = f"{type(exc).__name__}: processing failed; inspect local CLI output"
            if hasattr(exc, "report"):
                job.output_metadata = {"report": exc.report}
                session.add(DataQualityReport(job_id=job_id, report=exc.report))
        logging.getLogger(__name__).error("Processing job %s failed (%s)", job_id, type(exc).__name__)
        raise
