"""python -m app.history_export --request request.json --output reports/history"""

import argparse
import json
from pathlib import Path

from app.history import HistoryQuery, analyze, calendar_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reproducible historical activity analysis")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--request", type=Path, help="Query JSON; read the local archive")
    selection.add_argument("--replay", type=Path, help="Replay a saved input-snapshot.json offline")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.replay:
        snapshot = json.loads(args.replay.read_text(encoding="utf-8"))
        query = HistoryQuery.model_validate(snapshot["query"])
        records, sources = snapshot["records"], snapshot["sources"]
        calibration_models = snapshot.get("calibration_models")
    else:
        from app.db import session_factory
        from app.history_routes import load_calibration_models, load_inputs

        query = HistoryQuery.model_validate_json(args.request.read_text(encoding="utf-8"))
        factory = session_factory()
        with factory() as session:
            records, sources = load_inputs(session, query)
            calibration_models = load_calibration_models(session)
    result = analyze(query, records, sources, calibration_models=calibration_models)
    snapshot = {
        "query": query.model_dump(mode="json"),
        "records": records,
        "sources": result["sources"],
        **(
            {"calibration_models": calibration_models}
            if calibration_models
            else {}
        ),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, payload in [("analysis.json", result), ("input-snapshot.json", snapshot)]:
        (args.output / filename).write_text(
            json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    (args.output / "calendar.csv").write_text(calendar_csv(result), encoding="utf-8", newline="")
    print(result["analysis_id"])


if __name__ == "__main__":
    main()
