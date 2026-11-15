"""Read-only archive reconciliation. Counts describe storage, not satellite coverage."""

import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import get_engine

CHECKS = {
    "source_hash_mismatch": """SELECT count(*) FROM source_files
        WHERE encode(sha256(original_bytes),'hex') <> sha256""",
    "source_row_count_mismatch": """SELECT count(*) FROM source_files s
        WHERE row_count <> (SELECT count(*) FROM raw_records r WHERE r.source_id=s.id)""",
    "missing_provenance": """SELECT count(*) FROM normalized_observations o WHERE NOT EXISTS
        (SELECT 1 FROM observation_records r WHERE r.observation_id=o.id)""",
    "provenance_hash_mismatch": """SELECT count(*) FROM observation_records l
        JOIN raw_records r ON r.id=l.raw_record_id
        JOIN normalized_observations o ON o.id=l.observation_id
        WHERE r.record_hash<>o.record_hash""",
    "duplicate_normalized_hashes": """SELECT count(*) FROM
        (SELECT record_hash FROM normalized_observations GROUP BY record_hash HAVING count(*)>1) t""",
}


def main():
    with get_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout='30s'"))
        results = {name: connection.scalar(text(query)) for name, query in CHECKS.items()}
        counts = {}
        for table in (
            "source_files",
            "raw_records",
            "normalized_observations",
            "observation_records",
            "data_quality_reports",
        ):
            counts[table] = connection.scalar(text(f"SELECT count(*) FROM {table}"))
        coverage = [
            dict(row)
            for row in connection.execute(
                text("""SELECT sensor_code,
            extract(year FROM acquired_at AT TIME ZONE 'UTC')::int AS year,
            extract(month FROM acquired_at AT TIME ZONE 'UTC')::int AS month,
            count(*) AS stored_observations FROM normalized_observations
            GROUP BY 1,2,3 ORDER BY 1,2,3""")
            ).mappings()
        ]
        unlinked = connection.scalar(
            text("""SELECT count(*) FROM raw_records r WHERE NOT EXISTS
            (SELECT 1 FROM observation_records l WHERE l.raw_record_id=r.id)""")
        )
        connection.rollback()
    passed = all(value == 0 for value in results.values())
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "counts": counts,
                "zero_expected_checks": results,
                "raw_records_without_normalized_link": unlinked,
                "stored_months": coverage,
                "observation_opportunity": "unknown",
                "notice": "Unlinked raw rows may be intentionally excluded by import filters. "
                "Stored months do not prove complete or cloud-free observations.",
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
