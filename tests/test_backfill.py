"""Synthetic orchestration fixtures; no scientific observations or live NASA requests."""

import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from firescope_pipeline import backfill as module
from firescope_pipeline.backfill_plan import plan_backfill, subtract_intervals


def test_plan_prefers_annual_then_standard_then_nrt_and_reports_unavailable_tail():
    plan = plan_backfill(
        start=date(2000, 1, 1),
        through=date(2026, 11, 15),
        as_of=date(2026, 11, 15),
        catalog={f"modis_{year}_Jordan.csv": f"signature-{year}" for year in range(2000, 2026)},
        availability={
            "MODIS_SP": (date(2000, 11, 1), date(2026, 8, 31)),
            "MODIS_NRT": (date(2026, 9, 1), date(2026, 11, 15)),
            "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 7, 31)),
            "VIIRS_SNPP_NRT": (date(2026, 8, 1), date(2026, 11, 2)),
        },
    )
    annual = [t for t in plan["tasks"] if t["kind"] == "annual"]
    assert len(annual) == 26
    assert annual[0]["start"] == "2000-11-01"
    modis_api = [t for t in plan["tasks"] if t.get("source", "").startswith("MODIS")]
    assert [(t["source"], t["start"], t["end"]) for t in modis_api] == [
        ("MODIS_SP", "2026-01-01", "2026-09-01"),
        ("MODIS_NRT", "2026-09-01", "2026-11-16"),
    ]
    assert {
        "sensor": "VIIRS_SNPP",
        "start": "2026-11-03",
        "end": "2026-11-16",
        "reason": "outside_published_availability",
    } in plan["gaps"]
    assert plan["current_day_provisional"] is True
    assert any(g["reason"] == "pre_operational_sensor" for g in plan["gaps"])


def test_catalog_holes_are_planned_from_actual_api_availability_not_skipped():
    plan = plan_backfill(
        start=date(2013, 1, 1),
        through=date(2015, 12, 31),
        as_of=date(2026, 11, 15),
        catalog={"modis_2013_Jordan.csv": "a", "modis_2015_Jordan.csv": "b"},
        availability={"MODIS_SP": (date(2014, 2, 1), date(2014, 11, 30))},
    )
    assert [t for t in plan["tasks"] if t["kind"] == "api"] == [
        {
            "kind": "api",
            "sensor": "MODIS",
            "source": "MODIS_SP",
            "start": "2014-02-01",
            "end": "2014-12-01",
        }
    ]
    gaps = [g for g in plan["gaps"] if g["sensor"] == "MODIS"]
    assert [(g["start"], g["end"]) for g in gaps] == [
        ("2014-01-01", "2014-02-01"),
        ("2014-12-01", "2015-01-01"),
    ]


def test_interval_subtraction_coalesces_overlap_and_clips_outside_coverage():
    def d(day):
        return date(2024, 1, day)

    assert subtract_intervals(d(2), d(20), [(d(1), d(4)), (d(3), d(8)), (d(10), d(30))]) == [
        (d(8), d(10))
    ]


@pytest.mark.parametrize(
    "start,through",
    [
        (date(1999, 1, 1), date(2000, 1, 1)),
        (date(2026, 1, 1), date(2027, 1, 1)),
        (date(2025, 1, 2), date(2025, 1, 1)),
    ],
)
def test_invalid_date_ranges_do_not_plan_sources(start, through):
    with pytest.raises(ValueError):
        plan_backfill(
            start=start, through=through, as_of=date(2026, 11, 15), catalog={}, availability={}
        )


class MemoryFactory:
    def __init__(self):
        self.checkpoints = {}

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def get(self, _model, key):
        return self.checkpoints.get(key)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    factory = MemoryFactory()
    state = {"imports": [], "downloads": [], "revision": "1", "interrupt": False}

    def transport(request):
        if request.url.path.endswith("yearly_summary_files.txt"):
            text = "\n".join(
                f"modis_{y}_Jordan.csv,100,revision-{state['revision']}" for y in (2013, 2014)
            )
            return httpx.Response(200, text=text)
        state["downloads"].append(request.url.path)
        return httpx.Response(200, content=f"synthetic transport {state['revision']}".encode())

    def importer(_factory, content, **kwargs):
        if state["interrupt"] and kwargs["filename"].startswith("modis_2014"):
            raise KeyboardInterrupt()
        state["imports"].append(kwargs)
        cp = kwargs["checkpoint"]
        factory.checkpoints[cp["stream_key"]] = SimpleNamespace(next_date=cp["next_date"])
        return {"job_id": "synthetic-job", "source_id": "synthetic-source"}

    monkeypatch.setattr(module, "import_source", importer)
    client = httpx.Client(transport=httpx.MockTransport(transport))

    def run(**changes):
        return module.backfill(
            factory,
            None,
            output=tmp_path,
            start=date(2013, 1, 1),
            through=date(2014, 12, 31),
            as_of=date(2026, 11, 15),
            polygon=None,
            public_client=client,
            **changes,
        )

    yield factory, state, run, tmp_path
    client.close()


def test_repeat_skips_committed_files_but_never_trusts_a_ledger_without_db_checkpoint(setup):
    factory, state, run, _path = setup
    first, second = run(), run()
    assert first["status"] == "completed_with_gaps"  # No fabricated VIIRS or API tail.
    assert second["annual_skipped"] == 2
    assert len(state["imports"]) == len(state["downloads"]) == 2
    factory.checkpoints.clear()
    run()
    assert len(state["imports"]) == 4
    assert len(state["downloads"]) == 2


def test_interruption_preserves_completed_files_and_resumes_the_uncommitted_file(setup):
    _factory, state, run, path = setup
    state["interrupt"] = True
    with pytest.raises(KeyboardInterrupt):
        run()
    assert json.loads((path / "report.json").read_text())["status"] == "interrupted"
    assert len(state["imports"]) == 1
    state["interrupt"] = False
    result = run()
    assert result["annual_skipped"] == 1
    assert len(state["imports"]) == 2
    assert len(state["downloads"]) == 2


def test_corrupt_cache_is_rejected_before_skip_and_catalog_revision_reimports(setup):
    _factory, state, run, path = setup
    run()
    (path / "modis_2013_Jordan.csv").write_bytes(b"corrupted cache")
    with pytest.raises(ValueError, match="checksum mismatch"):
        run()
    assert len(state["imports"]) == 2
    state["revision"] = "2"
    result = run()
    assert result["annual_skipped"] == 0
    assert len(state["imports"]) == 4


def test_plan_does_not_touch_database_or_download_observations(setup):
    _factory, state, run, _path = setup
    assert run(plan_only=True)["status"] == "planned"
    assert not state["imports"] and not state["downloads"]


def test_catalog_rejects_error_text_and_does_not_accept_paths():
    with pytest.raises(ValueError):
        module.parse_catalog(b"NASA temporarily unavailable")
    parsed = module.parse_catalog(
        b"../../modis_2013_Jordan.csv,100,bad\nmodis_2014_Jordan.csv,100,ok"
    )
    assert set(parsed) == {"modis_2014_Jordan.csv"}


def test_fully_covered_annual_history_does_not_require_an_api_key(tmp_path, monkeypatch):
    factory = MemoryFactory()

    def transport(request):
        if request.url.path.endswith("yearly_summary_files.txt"):
            return httpx.Response(
                200,
                text=(
                    "modis_2013_Jordan.csv,100,synthetic\nviirs-snpp_2013_Jordan.csv,100,synthetic"
                ),
            )
        return httpx.Response(200, content=b"synthetic transport; importer injected")

    monkeypatch.setattr(module, "import_source", lambda *_args, **_kwargs: {"job_id": "test-only"})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = module.backfill(
            factory,
            None,
            output=tmp_path,
            start=date(2013, 1, 1),
            through=date(2013, 12, 31),
            as_of=date(2026, 11, 15),
            polygon=None,
            public_client=client,
        )
    assert result["status"] == "completed"
    assert not result["plan"]["gaps"]
