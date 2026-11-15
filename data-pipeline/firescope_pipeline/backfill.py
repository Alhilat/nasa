"""Resumable official FIRMS backfill, with atomic cache writes and DB checkpoints."""

import hashlib
import json
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from app.models import ImportCheckpoint

from firescope_pipeline.backfill_plan import PRODUCTS, plan_backfill
from firescope_pipeline.calibration.prepare import COUNTRY_ROOT, _download
from firescope_pipeline.firms_api import FIRMSAPIError
from firescope_pipeline.selection import JORDAN_BBOX, Selection
from firescope_pipeline.service import import_source
from firescope_pipeline.sync import sync_api

VERSION = "firms-backfill-v1"
CATALOG_URL = COUNTRY_ROOT + "/yearly_summary_files.txt"


def _atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".partial", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _json(path, payload):
    _atomic_write(
        path, (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    )


def parse_catalog(content):
    """Only exact official demo-country filenames can enter local paths or URLs."""
    catalog = {}
    for line in content.decode("utf-8-sig").splitlines():
        name = line.split(",")[0]
        if re.fullmatch(r"(?:modis|viirs-snpp)_\d{4}_Jordan\.csv", name):
            catalog[name] = hashlib.sha256(line.encode()).hexdigest()
    if not catalog:
        raise ValueError("NASA's catalog contains no supported Jordan country files")
    return catalog


def backfill(
    factory,
    api_client,
    *,
    output,
    start,
    through,
    as_of,
    polygon,
    window_days=5,
    lookback_days=2,
    plan_only=False,
    public_client=None,
    progress=None,
):
    """A repeated command resumes automatically; each import/checkpoint is one transaction.

    The filesystem ledger is a download cache and report, never proof of DB import.
    Actual committed checkpoints decide whether annual imports may be skipped.
    """
    if not 1 <= window_days <= 5 or not 0 <= lookback_days <= 30:
        raise ValueError("Use window days 1–5 and lookback days 0–30")
    if not date(2000, 1, 1) <= start <= through <= as_of:
        raise ValueError("Use ordered dates from 2000 through today (UTC)")
    selection = Selection(bbox=JORDAN_BBOX, polygon=polygon)
    output = Path(output)
    ledger_path = output / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    if ledger and ledger.get("version") != VERSION:
        raise ValueError("Use a separate cache directory for this backfill version")
    ledger.setdefault("version", VERSION)
    ledger.setdefault("files", {})
    owns_public = public_client is None
    public_client = public_client or httpx.Client(timeout=60, follow_redirects=False)
    report = {
        "version": VERSION,
        "status": "planning",
        "imports": [],
        "annual_skipped": 0,
        "selection": selection.as_dict(),
        "observation_coverage": "unknown",
    }

    def save():
        _json(output / "report.json", report)

    try:
        catalog_bytes = _download(public_client, CATALOG_URL)
        catalog = parse_catalog(catalog_bytes)
        retrieved = datetime.now(UTC).isoformat()
        ledger["catalog"] = {
            "source_url": CATALOG_URL,
            "retrieved_at": retrieved,
            "sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        }
        _atomic_write(output / "yearly_summary_files.txt", catalog_bytes)
        _json(ledger_path, ledger)
        availability, availability_errors = {}, {}
        for product in PRODUCTS:
            for source in (product.standard, product.nrt):
                if api_client is None:
                    availability_errors[source] = "MAP_KEY is not configured; API tail unavailable"
                    continue
                try:
                    availability[source] = api_client.availability(source)
                except FIRMSAPIError as exc:
                    availability_errors[source] = str(exc)
        plan = plan_backfill(
            start=start, through=through, as_of=as_of, catalog=catalog, availability=availability
        )
        report.update(
            plan=plan,
            availability={s: [d.isoformat() for d in bounds] for s, bounds in availability.items()},
            availability_errors=availability_errors,
            catalog=ledger["catalog"],
            status="planned" if plan_only else "running",
        )
        save()
        if plan_only:
            return report

        def api_progress(source, following, result):
            report["last_committed_api_window"] = {
                "source": source,
                "next_date": following.isoformat(),
                "job_id": result["job_id"],
            }
            save()
            if progress:
                progress(f"Committed {source} through {following} (end exclusive)")

        for task in plan["tasks"]:
            if task["kind"] == "api":
                result = sync_api(
                    factory,
                    api_client,
                    source=task["source"],
                    selection=selection,
                    start=date.fromisoformat(task["start"]),
                    end=date.fromisoformat(task["end"]),
                    resume=True,
                    window_days=window_days,
                    lookback_days=lookback_days,
                    progress=api_progress,
                )
                report["imports"].append({"kind": "api", "source": task["source"], **result})
            else:
                name = task["name"]
                url = f"{COUNTRY_ROOT}/{task['product']}/{task['year']}/{name}"
                cached = ledger["files"].get(name, {})
                path = output / name
                if (
                    cached.get("catalog_signature") == task["catalog_signature"]
                    and cached.get("source_url") == url
                    and path.exists()
                ):
                    content = path.read_bytes()
                    if hashlib.sha256(content).hexdigest() != cached.get("sha256"):
                        raise ValueError(f"Cached original checksum mismatch: {name}")
                    fetched = datetime.fromisoformat(cached["retrieved_at"])
                else:
                    content = _download(public_client, url)
                    fetched = datetime.now(UTC)
                    _atomic_write(path, content)
                    cached = {
                        "source_url": url,
                        "retrieved_at": fetched.isoformat(),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "catalog_signature": task["catalog_signature"],
                    }
                    ledger["files"][name] = cached
                    _json(ledger_path, ledger)
                # The same start/scope is stable when --through grows. File revisions
                # change the checkpoint key and force validation/import again.
                parameters = {
                    "version": VERSION,
                    "url": url,
                    "sha256": cached["sha256"],
                    "selection": selection.as_dict(),
                    "anchor_start": task["start"],
                }
                stream_key = hashlib.sha256(
                    json.dumps(parameters, sort_keys=True).encode()
                ).hexdigest()
                stop = date.fromisoformat(task["end"])
                with factory() as session:
                    checkpoint = session.get(ImportCheckpoint, stream_key)
                    complete = checkpoint is not None and checkpoint.next_date >= stop
                if complete:
                    report["annual_skipped"] += 1
                else:
                    window = Selection(
                        bbox=selection.bbox,
                        polygon=selection.polygon,
                        start=datetime.fromisoformat(task["start"]).replace(tzinfo=UTC),
                        end=datetime.fromisoformat(task["end"]).replace(tzinfo=UTC),
                    )
                    result = import_source(
                        factory,
                        content,
                        filename=name,
                        sensor=task["sensor"],
                        product_version="native",
                        processing_level="standard",
                        source_url=url,
                        retrieved_at=fetched,
                        selection=window,
                        metadata={
                            "backfill_version": VERSION,
                            "catalog_signature": task["catalog_signature"],
                        },
                        checkpoint={
                            "stream_key": stream_key,
                            "next_date": stop,
                            "parameters": parameters,
                        },
                    )
                    report["imports"].append({"kind": "annual", "name": name, **result})
            if progress:
                progress(
                    f"Completed {task.get('name', task.get('source'))}: "
                    f"{task['start']} through {task['end']} (end exclusive)"
                )
            save()
        unavailable = any(g["reason"] == "outside_published_availability" for g in plan["gaps"])
        report["status"] = "completed_with_gaps" if unavailable else "completed"
        save()
        return report
    except BaseException as exc:
        report["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        # Persist safe error classes, never raw transport URLs or credentials.
        report["error_type"] = type(exc).__name__
        save()
        raise
    finally:
        if owns_public:
            public_client.close()
