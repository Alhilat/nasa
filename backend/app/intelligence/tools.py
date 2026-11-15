"""Allowlisted Python-only analytical tools with bounded evidence and no generated code."""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.history import NOTES, HistoryQuery, analyze, change
from app.history_routes import load_history, load_inputs
from app.models import CalibrationModel, ProcessingJob

from .schemas import CompareSeasons, Evidence, Scope

REGION_FILE = Path(__file__).with_name("regions.geojson")
REGION_DATA = json.loads(REGION_FILE.read_text(encoding="utf-8"))
REGIONS = {f["properties"]["region_id"]: f for f in REGION_DATA["features"]}
REGION_HASH = hashlib.sha256(REGION_FILE.read_bytes()).hexdigest()
CATALOG = {
    "selected": "Current user-selected geometry",
    "jordan_envelope": "Jordan study envelope [34,29,40,34], not national boundary",
    **{key: f["properties"]["label"] for key, f in REGIONS.items()},
}
LIMITS = [
    NOTES["count"],
    NOTES["coverage"],
    NOTES["baseline"],
    NOTES["percentile"],
    NOTES["robust_z"],
    NOTES["year_over_year"],
    "Interpretations do not establish causation or provide forecasts or prediction accuracy.",
]
TOOL_SPECS = {
    "get_historical_activity": (
        Scope,
        "Retrieve archived monthly/yearly counts and seasonal profiles.",
    ),
    "compare_fire_seasons": (
        CompareSeasons,
        "Compare the same complete calendar months across years. "
        "Different regions are descriptive only, with no count ratio.",
    ),
    "detect_activity_anomalies": (
        Scope,
        "Retrieve Python percentile anomaly assessments and missing-data reasons.",
    ),
    "analyze_spatial_hotspots": (
        Scope,
        "Retrieve angular-grid detection concentration, not fire risk or physical density.",
    ),
    "get_harmonization_metadata": (
        Scope,
        "Read registered calibration status and versions. Never applies a calibration.",
    ),
    "get_environmental_conditions": (
        Scope,
        "Check environmental data availability. No environmental dataset is connected.",
    ),
    "generate_activity_report": (
        Scope,
        (
            "Collect historical, anomaly, spatial, calibration and enviro"
            "nmental evidence for a report."
        ),
    ),
}


class HistoryCache:
    """Short, disclosed snapshot cache; bounded by both entry count and serialized bytes."""

    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            row = self.entries.get(key)
            if row and time.monotonic() - row[0] < 30:
                self.entries.move_to_end(key)
                return json.loads(row[1])
            self.entries.pop(key, None)
        return None

    def put(self, key, value):
        payload = json.dumps(value, sort_keys=True, allow_nan=False)
        if len(payload.encode()) > 2_000_000:
            return
        with self.lock:
            self.entries[key] = (time.monotonic(), payload)
            while (
                len(self.entries) > 16 or sum(len(v[1]) for v in self.entries.values()) > 8_000_000
            ):
                self.entries.popitem(last=False)


CACHE = HistoryCache()


class ToolRegistry:
    def __init__(self, session, context: HistoryQuery, refresh=False, date_window=None):
        self.session, self.context, self.refresh = session, context, refresh
        self.memo = {}
        self.date_window = date_window

    def effective_scope(self, scope):
        if self.date_window and all(
            getattr(scope, k) is None for k in ("start_year", "end_year", "start_date", "end_date")
        ):
            return scope.model_copy(
                update={
                    "start_date": self.date_window.start_date,
                    "end_date": self.date_window.end_date,
                }
            )
        return scope

    def resolve(self, scope: Scope):
        scope = self.effective_scope(scope)
        if bool(scope.start_date) != bool(scope.end_date):
            raise ValueError("Supply both exact-date boundaries")
        if scope.start_date:
            if (
                scope.start_date > scope.end_date
                or scope.end_date > datetime.now(UTC).date()
                or scope.start_year not in (None, scope.start_date.year)
                or scope.end_year not in (None, scope.end_date.year)
            ):
                raise ValueError(
                    "Exact historical dates must be ordered, consistent and not in the future"
                )
        values = self.context.model_dump(mode="json")
        values["start_year"] = (
            scope.start_date.year
            if scope.start_date
            else (scope.start_year or self.context.start_year)
        )
        values["end_year"] = (
            scope.end_date.year if scope.end_date else (scope.end_year or self.context.end_year)
        )
        if values["end_year"] > datetime.now(UTC).year:
            raise ValueError("Historical tools cannot analyze future years")
        values["baseline_start_year"], values["baseline_end_year"] = (
            values["start_year"],
            values["end_year"],
        )
        values["sensors"] = scope.sensors or self.context.sensors
        if scope.region_id not in CATALOG:
            raise ValueError("Unknown region. Ask for a map selection or a supported region ID")
        if scope.region_id != "selected":
            values["bbox"] = [34, 29, 40, 34] if scope.region_id == "jordan_envelope" else None
            values["polygon"] = (
                REGIONS[scope.region_id]["geometry"] if scope.region_id in REGIONS else None
            )
            values["complete_months"] = []  # Never transfer an area's coverage claims to another.
        values["complete_months"] = [
            c
            for c in values["complete_months"]
            if c["sensor_code"] in values["sensors"]
            and values["start_year"] <= int(c["month"][:4]) <= values["end_year"]
        ]
        if scope.start_date:
            retained = []
            for declaration in values["complete_months"]:
                month = date.fromisoformat(declaration["month"] + "-01")
                next_month = (month + timedelta(days=32)).replace(day=1)
                if scope.start_date <= month and next_month <= scope.end_date + timedelta(days=1):
                    retained.append(declaration)
            values["complete_months"] = retained
        return HistoryQuery.model_validate(values)

    def history(self, query, scope=None):
        window = (
            {"start": scope.start_date.isoformat(), "end": scope.end_date.isoformat()}
            if scope and scope.start_date
            else None
        )
        key = query.model_dump_json() + json.dumps(window)
        if key in self.memo:
            return self.memo[key]
        cached = None if self.refresh else CACHE.get(key)
        if cached is not None:
            self.memo[key] = (cached, True)
        else:
            if window:
                start = datetime.combine(scope.start_date, day_time(), UTC)
                end = datetime.combine(scope.end_date + timedelta(days=1), day_time(), UTC)
                selection = query.observation_query().model_copy(
                    update={"start": start, "end": end}
                )
                records, sources = load_inputs(
                    self.session, query, max_records=50000, selection=selection
                )
                result = analyze(query, records, sources, audit_sources=False)
                result["monthly"] = [
                    r
                    for r in result["monthly"]
                    if r["month"] >= scope.start_date.strftime("%Y-%m")
                    and r["month"] <= scope.end_date.strftime("%Y-%m")
                ]
            else:
                result = load_history(self.session, query, max_records=50000)
            # Do not cache a potentially huge grid feature collection.
            result["top_cells"] = sorted(
                result.pop("spatial")["features"],
                key=lambda f: (
                    -f["properties"]["count"],
                    f["properties"]["sensor_code"],
                    f["properties"]["grid_x"],
                    f["properties"]["grid_y"],
                ),
            )[:50]
            result["retrieved_at"] = datetime.now(UTC).isoformat()
            CACHE.put(key, result)
            self.memo[key] = (result, False)
        return self.memo[key]

    def metadata(self):
        models = self.session.execute(
            select(
                CalibrationModel.model_version,
                CalibrationModel.method,
                CalibrationModel.status,
                CalibrationModel.metric,
                CalibrationModel.algorithm_version,
                CalibrationModel.validation["status"].label("validation_status"),
                CalibrationModel.validation["splits"]["test_years"].label("heldout_time_metrics"),
                CalibrationModel.artifact["context"].label("evaluated_context"),
                CalibrationModel.input_manifest,
                ProcessingJob.parameters["protocol"].label("evaluation_protocol"),
            )
            .join(ProcessingJob, ProcessingJob.id == CalibrationModel.job_id)
            .order_by(CalibrationModel.model_version)
            .limit(21)
        ).all()
        registered, citations = [], {}
        for row in models[:20]:
            entry = dict(row._mapping)
            manifest = entry.pop("input_manifest", []) or []
            entry["input_manifest_sha256"] = hashlib.sha256(
                json.dumps(manifest, sort_keys=True).encode()
            ).hexdigest()
            entry["input_source_count"] = len(manifest)
            registered.append(entry)
            for source in manifest:
                digest = source.get("sha256")
                if digest:
                    identity = f"{digest}:{source.get('sensor', '')}"
                    citations[identity] = {
                        "id": identity,
                        "sha256": digest,
                        "sensor_code": source.get("sensor"),
                        "source_url": source.get("source_url", ""),
                        "product_version": source.get("product_version"),
                        "processing_level": source.get("processing_level"),
                    }
        return {
            "models": registered,
            "dataset_citations": list(citations.values()),
            "truncated": len(models) > 20,
            "calibration_applied": False,
            "evaluation_scope_note": (
                "Metrics describe original registered evaluation scopes and s"
                "ensor-reference agreement, not physical fire truth or the cu"
                "rrent map selection."
            ),
            "note": (
                "Registered candidates are not operational approval; this agent never applies them."
            ),
        }

    def execute(self, name, raw_args):
        now = datetime.now(UTC).isoformat()
        scope = {}
        if name not in TOOL_SPECS:
            return self.unavailable(name, "Tool is not allowlisted", {}, now)
        try:
            args = TOOL_SPECS[name][0].model_validate(raw_args)
            if isinstance(args, CompareSeasons):
                return self.compare(args)
            args = self.effective_scope(args)
            query = self.resolve(args)
            scope = {
                "query": query.model_dump(mode="json"),
                "region_id": args.region_id,
                "region_label": CATALOG[args.region_id],
                "region_catalog_sha256": REGION_HASH,
                "period": (
                    f"{query.start_year}-01-01 to {query.end_year + 1}-01-01, end exclusive UTC"
                ),
            }
            if args.start_date:
                scope["exact_date_window_inclusive"] = {
                    "start_date": args.start_date.isoformat(),
                    "end_date": args.end_date.isoformat(),
                }
                scope["period"] = (
                    f"{args.start_date} to {args.end_date}, both inclusive UTC. "
                    "Partial months are incomplete; outside months are excluded."
                )
            if name == "get_environmental_conditions":
                return self.unavailable(
                    name,
                    "No environmental dataset/provider is configured. "
                    "No weather, vegetation, soil moisture or causal attribution can be inferred.",
                    scope,
                    now,
                )
            if name == "get_harmonization_metadata":
                metadata = self.metadata()
                sources = metadata.pop("dataset_citations")
                return self.wrap(name, scope, metadata, [], [], sources, now)
            result, cache_hit = self.history(query, args)
            facts, data, charts = self.summarize(name, result)
            if name == "generate_activity_report":
                try:
                    data["harmonization"] = self.metadata()
                except SQLAlchemyError:
                    self.session.rollback()
                    data["harmonization"] = {"status": "unavailable"}
                data["environmental_conditions"] = {
                    "status": "unavailable",
                    "reason": "No connected environmental dataset",
                }
            evidence = self.wrap(
                name,
                scope,
                data,
                facts,
                charts,
                result["sources"],
                result["retrieved_at"],
                [result["analysis_id"]],
            )
            evidence.cache_hit = cache_hit
            return evidence
        except (ValidationError, ValueError, TypeError, KeyError):
            return self.unavailable(
                name,
                (
                    "Invalid or unsupported tool arguments. Use the supplied regi"
                    "on catalog, years and sensors."
                ),
                scope,
                now,
            )
        except (SQLAlchemyError, HTTPException):
            self.session.rollback()
            return self.unavailable(
                name,
                (
                    "Archive unavailable or selection too large. No measurements "
                    "or statistics were inferred."
                ),
                scope,
                now,
            )

    def summarize(self, name, result):
        rows = result["monthly"]
        facts, charts, data = [], [], {}
        if name in {"get_historical_activity", "generate_activity_report"}:
            data.update(yearly=result["yearly"], seasonal_profiles=result["seasonal_profiles"])
            for year in result["yearly"]:
                facts.append(
                    {
                        "section": "historical_observations",
                        "label": "Observed archive total (may be incomplete)",
                        "sensor": year["sensor_code"],
                        "period": str(year["year"]),
                        "value": year["observed_count"],
                        "unit": "thermal detections",
                        "complete_months": year["complete_months"],
                    }
                )
                comparison = year["year_over_year"]
                if name == "generate_activity_report" and comparison["matched_months"]:
                    facts.append(
                        {
                            "section": "statistical_comparisons",
                            "label": "Adjacent-year matched complete-month change",
                            "sensor": year["sensor_code"],
                            "period": f"{year['year'] - 1} vs {year['year']}",
                            "value": comparison["percent_change"],
                            "unit": "percent change",
                            **comparison,
                        }
                    )
            for sensor in result["query"]["sensors"]:
                sensor_rows = [r for r in rows if r["sensor_code"] == sensor]
                charts.append(
                    {
                        "title": f"{sensor} monthly archived detections",
                        "labels": [r["month"] for r in sensor_rows],
                        "series": [
                            {
                                "name": sensor,
                                "values": [r["count"] for r in sensor_rows],
                                "color": "#F47A32",
                            }
                        ],
                    }
                )
        if name in {"detect_activity_anomalies", "generate_activity_report"}:
            flagged = [
                r for r in rows if r["anomaly_status"] in {"unusually_high", "unusually_low"}
            ]
            data["anomalies"] = {
                "flagged": flagged[:50],
                "flagged_count": len(flagged),
                "truncated": len(flagged) > 50,
                "unassessed_count": sum(
                    r["anomaly_status"] in {"incomplete_period", "insufficient_history"}
                    for r in rows
                ),
                "upper_percentile": result["query"]["percentile"],
            }
            for row in flagged[:30]:
                facts.append(
                    {
                        "section": "anomalies",
                        "label": row["anomaly_status"],
                        "sensor": row["sensor_code"],
                        "period": row["month"],
                        "value": row["count"],
                        "unit": "thermal detections",
                        "historical_median": row["historical_median"],
                        "lower_threshold": row["lower_threshold"],
                        "upper_threshold": row["upper_threshold"],
                        "baseline_years": row["baseline_years"],
                    }
                )
        if name in {"analyze_spatial_hotspots", "generate_activity_report"}:
            data.update(
                concentration=result["concentration"],
                top_cells=result["top_cells"],
                grid_note=NOTES["spatial"],
                top_cells_limit=50,
            )
            for row in result["concentration"]:
                facts.append(
                    {
                        "section": "historical_observations",
                        "label": "Angular-grid Herfindahl concentration index",
                        "sensor": row["sensor_code"],
                        "value": row["herfindahl_index"],
                        "unit": "dimensionless",
                    }
                )
        return facts, data, charts

    def compare(self, args):
        months = sorted(set(args.months))
        if len(months) != len(args.months) or any(m < 1 or m > 12 for m in months):
            raise ValueError("Supply distinct calendar months from 1 to 12")
        queries = [
            self.resolve(Scope(region_id=region, start_year=year, end_year=year))
            for region, year in [
                (args.region_id, args.first_year),
                (args.other_region_id or args.region_id, args.second_year),
            ]
        ]
        histories = [self.history(q)[0] for q in queries]
        equivalent_area = (
            queries[0].bbox == queries[1].bbox and queries[0].polygon == queries[1].polygon
        )
        rows, facts = [], []
        for sensor in self.context.sensors:
            selected = [
                [
                    r
                    for r in h["monthly"]
                    if r["sensor_code"] == sensor and r["calendar_month"] in months
                ]
                for h in histories
            ]
            matched = [
                m
                for m in months
                if all(
                    any(r["calendar_month"] == m and r["completeness"] == "complete" for r in rs)
                    for rs in selected
                )
            ]
            counts = (
                [sum(r["count"] for r in rs if r["calendar_month"] in matched) for rs in selected]
                if matched
                else [None, None]
            )
            comparison = (
                change(counts[1], counts[0])
                if matched and equivalent_area
                else {"difference": None, "percent_change": None}
            )
            item = {
                "sensor": sensor,
                "requested_months": months,
                "matched_complete_months": matched,
                "first_count": counts[0],
                "second_count": counts[1],
                "equivalent_area": equivalent_area,
                "first_observed_archive_count": sum(
                    r["count"] for r in selected[0] if r["count"] is not None
                )
                if any(r["count"] is not None for r in selected[0])
                else None,
                "second_observed_archive_count": sum(
                    r["count"] for r in selected[1] if r["count"] is not None
                )
                if any(r["count"] is not None for r in selected[1])
                else None,
                **comparison,
            }
            rows.append(item)
            facts.append(
                {
                    "section": "statistical_comparisons",
                    "label": "Matched complete-month comparison",
                    "sensor": sensor,
                    "period": f"{args.first_year} vs {args.second_year}",
                    "value": comparison["percent_change"],
                    "unit": "percent change; null if not comparable",
                    **item,
                }
            )
        sources = {s["id"]: s for h in histories for s in h["sources"]}
        return self.wrap(
            "compare_fire_seasons",
            {
                "first": queries[0].model_dump(mode="json"),
                "second": queries[1].model_dump(mode="json"),
                "months": months,
            },
            {
                "comparisons": rows,
                "note": (
                    "Only matched complete months. Different areas are descriptiv"
                    "e, with no count difference or ratio."
                ),
            },
            facts,
            [],
            list(sources.values()),
            datetime.now(UTC).isoformat(),
            [h["analysis_id"] for h in histories],
        )

    @staticmethod
    def wrap(name, scope, data, facts, charts, sources, retrieved_at, analysis_ids=None):
        safe_sources = [
            {
                k: s.get(k)
                for k in [
                    "id",
                    "sha256",
                    "sensor_code",
                    "product_version",
                    "processing_level",
                    "retrieved_at",
                ]
            }
            | {
                "source_url": s["source_url"]
                if (
                    isinstance(s.get("source_url"), str)
                    and len(s["source_url"]) <= 2048
                    and urlparse(s["source_url"]).scheme in {"http", "https"}
                )
                else None
            }
            for s in sources[:100]
        ]
        data = {**data, "fact_count": len(facts), "fact_list_truncated": len(facts) > 120}
        payload = {
            "tool": name,
            "scope": scope,
            "data": data,
            "facts": facts[:120],
            "analysis_ids": analysis_ids or [],
            "sources": safe_sources,
        }
        evidence_id = (
            "E-"
            + hashlib.sha256(
                json.dumps(payload, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()[:16]
        )
        return Evidence(
            id=evidence_id,
            tool=name,
            status="available",
            scope=scope,
            analysis_ids=analysis_ids or [],
            sources=safe_sources,
            source_count=len(sources),
            source_list_truncated=len(sources) > 100,
            facts=facts[:120],
            charts=charts[:5],
            data=data,
            limitations=LIMITS,
            retrieved_at=retrieved_at,
        )

    @staticmethod
    def unavailable(name, reason, scope, now):
        evidence = ToolRegistry.wrap(name, scope, {"reason": reason}, [], [], [], now)
        evidence.status = "unavailable"
        evidence.limitations = [reason, *LIMITS]
        return evidence
