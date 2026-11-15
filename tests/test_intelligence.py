"""AI tests use synthetic archive fixtures and a mocked provider; no paid requests."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.db import get_session
from app.history import HistoryQuery, analyze
from app.intelligence.agent import AgentService, GoogleProvider, validate_interpretation
from app.intelligence.routes import get_agent, markdown_report
from app.intelligence.schemas import ChatRequest, DateWindow, Scope
from app.intelligence.tools import CACHE, ToolRegistry
from app.main import app
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.genai import errors, types

SNAPSHOT = json.loads(
    (Path(__file__).parent / "fixtures/history-synthetic-snapshot.json").read_text()
)


class Session:
    def execute(self, *_args):
        return SimpleNamespace(all=lambda: [])

    def rollback(self):
        pass


@pytest.fixture
def context():
    return HistoryQuery.model_validate(SNAPSHOT["query"])


@pytest.fixture(autouse=True)
def analytical_archive(monkeypatch):
    CACHE.entries.clear()
    calls = []

    def historical(_session, query, max_records=None):
        calls.append((query, max_records))
        return analyze(
            query, copy.deepcopy(SNAPSHOT["records"]), copy.deepcopy(SNAPSHOT["sources"])
        )

    monkeypatch.setattr("app.intelligence.tools.load_history", historical)
    yield calls
    CACHE.entries.clear()


def prose(
    evidence_id,
    text="Interpret the archived pattern alongside the disclosed completeness limitations.",
):
    statement = {"text": text, "evidence_ids": [evidence_id]}
    return {
        "executive_summary": [statement],
        "interpretations": [],
        "data_limitations": [statement],
        "recommendations": [statement],
    }


class Provider:
    def __init__(self, _settings):
        self.round = 0
        self.calls = []
        self.content = None
        self.closed = False

    def choose(self, contents, declarations, force):
        self.calls.append(contents)
        self.round += 1
        if self.round == 1:
            assert force
            name = (
                "generate_activity_report" if len(declarations) == 1 else "get_historical_activity"
            )
            call = types.FunctionCall(name=name, args={}, id="test-call-id")
            self.content = types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=call,
                        thought_signature=b"opaque-test-signature",
                    )
                ],
            )
            return self.content, [call]
        assert contents[1] is self.content
        assert contents[1].parts[0].thought_signature == b"opaque-test-signature"
        assert contents[-1].role == "user"
        assert contents[-1].parts[0].function_response.id == "test-call-id"
        return types.Content(role="model", parts=[types.Part.from_text(text="Ready")]), []

    def interpret(self, prompt):
        self.final_prompt = json.loads(prompt)
        return prose(self.final_prompt["evidence"][0]["id"])

    def close(self):
        self.closed = True


def settings(**changes):
    return Settings(gemini_api_key="synthetic-test-credential-never-leak", **changes)


def test_tools_use_validated_python_counts_and_source_identity(context):
    registry = ToolRegistry(Session(), context)
    historical = registry.execute("get_historical_activity", {})
    assert historical.status == "available"
    assert historical.facts[-1]["value"] == 8
    assert historical.analysis_ids
    assert historical.sources[0]["sha256"] == "0" * 64
    assert historical.scope["query"]["bbox"] == context.model_dump(mode="json")["bbox"]
    assert historical.charts[0]["series"][0]["values"][1] is None
    anomalies = registry.execute("detect_activity_anomalies", {})
    assert anomalies.data["anomalies"]["flagged_count"] == 1
    assert anomalies.facts[0]["historical_median"] == 2
    assert anomalies.facts[0]["upper_threshold"] == 2.9
    assert anomalies.facts[0]["period"] == "2016-01"
    spatial = registry.execute("analyze_spatial_hotspots", {})
    assert spatial.data["concentration"][0]["herfindahl_index"] == 1
    assert "not an area-normalized" in spatial.data["grid_note"]


def test_equivalent_season_comparison_is_computed_in_python(context):
    evidence = ToolRegistry(Session(), context).execute(
        "compare_fire_seasons",
        {
            "first_year": 2013,
            "second_year": 2016,
            "months": [1],
        },
    )
    comparison = evidence.data["comparisons"][0]
    assert comparison["percent_change"] == 700
    assert comparison["matched_complete_months"] == [1]
    assert comparison["equivalent_area"] is True


def test_other_regions_do_not_inherit_coverage_or_count_ratios(context):
    registry = ToolRegistry(Session(), context)
    other = registry.resolve(Scope(region_id="JOR_northwest"))
    assert other.complete_months == []
    assert other.polygon is not None and other.bbox is None
    evidence = registry.execute(
        "compare_fire_seasons",
        {
            "region_id": "selected",
            "other_region_id": "JOR_northwest",
            "first_year": 2013,
            "second_year": 2016,
            "months": [1],
        },
    )
    assert evidence.status == "available"
    assert evidence.data["comparisons"][0]["percent_change"] is None


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("run_sql", {"sql": "delete from anything"}),
        ("get_historical_activity", {"region_id": "../../.env"}),
        ("get_historical_activity", {"bbox": [0, 0, 1, 1]}),
        ("get_historical_activity", {"region_id": "unknown-city"}),
        ("get_historical_activity", {"end_year": 2099}),
        ("compare_fire_seasons", {"first_year": 2013, "second_year": 2016, "months": [1, 1]}),
    ],
)
def test_untrusted_tools_and_arguments_do_not_execute(context, analytical_archive, name, arguments):
    evidence = ToolRegistry(Session(), context).execute(name, arguments)
    assert evidence.status == "unavailable"
    assert evidence.facts == []
    assert not analytical_archive


def test_environmental_unavailability_is_explicit(context, analytical_archive):
    evidence = ToolRegistry(Session(), context).execute("get_environmental_conditions", {})
    assert evidence.status == "unavailable"
    assert "No environmental" in evidence.data["reason"]
    assert not evidence.facts and not evidence.charts and not analytical_archive


def test_cache_is_disclosed_bounded_and_refreshable(context, analytical_archive):
    first = ToolRegistry(Session(), context).execute("get_historical_activity", {})
    second = ToolRegistry(Session(), context).execute("get_historical_activity", {})
    assert first.cache_hit is False and second.cache_hit is True
    assert first.id == second.id
    assert len(analytical_archive) == 1
    assert analytical_archive[0][1] == 50000
    ToolRegistry(Session(), context, refresh=True).execute("get_historical_activity", {})
    assert len(analytical_archive) == 2


@pytest.mark.parametrize(
    "text",
    [
        "There are 999 fires.",
        "There are ٣ fires.",
        "See https://invented.example/data",
        "This was caused by drought.",
        "These are unique wildfires.",
        "There are one hundred detections.",
        "The archive contains zero detections.",
        "Activity increased twofold.",
    ],
)
def test_generated_measurements_urls_and_causal_claims_are_rejected(context, text):
    evidence = ToolRegistry(Session(), context).execute("get_historical_activity", {})
    with pytest.raises(ValueError):
        validate_interpretation(prose(evidence.id, text), [evidence])


def test_unknown_citations_are_rejected_and_scientific_caveats_are_allowed(context):
    evidence = ToolRegistry(Session(), context).execute("get_historical_activity", {})
    with pytest.raises(ValueError):
        validate_interpretation(prose("E-invented"), [evidence])
    assert validate_interpretation(
        prose(evidence.id, "Thermal detections are not unique wildfires."), [evidence]
    )


def test_manual_function_loop_preserves_signatures_ids_and_server_context(context):
    provider = Provider(settings())
    service = AgentService(settings(), lambda _settings: provider)
    reply = service.chat(
        ChatRequest(message="Explain the archive", context=context), Session(), "test"
    )
    assert reply.status == "interpreted"
    assert reply.evidence[0].facts[-1]["value"] == 8
    assert reply.forecasting is False and provider.closed
    assert "synthetic-test-credential-never-leak" not in json.dumps(provider.final_prompt)
    assert "charts" not in provider.final_prompt["evidence"][0]
    assert service.stored_report(reply.conversation_id, reply.report_id) == reply
    changed = context.model_copy(update={"bbox": (35, 30, 39, 33)})
    with pytest.raises(HTTPException) as exc:
        service.chat(
            ChatRequest(message="Again", context=changed, conversation_id=reply.conversation_id),
            Session(),
            "test",
        )
    assert exc.value.status_code == 409


def test_invalid_ai_output_becomes_evidence_only_instead_of_a_fabricated_result(context):
    class InvalidProvider(Provider):
        def interpret(self, prompt):
            data = json.loads(prompt)
            return prose(data["evidence"][0]["id"], "There were 999 unique fires.")

    service = AgentService(settings(), InvalidProvider)
    reply = service.chat(ChatRequest(message="Count", context=context), Session(), "test")
    assert reply.status == "evidence_only" and reply.interpretation is None
    assert "999 unique fires" not in reply.model_dump_json()
    assert reply.evidence[0].facts[-1]["value"] == 8


def test_report_forces_evidence_collection_and_export_has_all_sections(context):
    service = AgentService(settings(), Provider)
    reply = service.chat(
        ChatRequest(message="Report", context=context), Session(), "test", report=True
    )
    assert reply.tool_calls[0]["tool"] == "generate_activity_report"
    report = markdown_report(reply)
    for title in [
        "Executive summary",
        "Historical observations",
        "Statistical comparisons",
        "Anomalies",
        "Supporting evidence",
        "Data limitations",
        "Recommendations for further monitoring",
    ]:
        assert title in report
    assert "0" * 64 in report
    assert "synthetic-test-credential-never-leak" not in report


def test_quota_and_concurrency_are_bounded(context):
    service = AgentService(settings(ai_requests_per_minute=1), Provider)
    request = ChatRequest(message="Explain", context=context)
    service.chat(request, Session(), "client")
    with pytest.raises(HTTPException) as exc:
        service.chat(request, Session(), "client")
    assert exc.value.status_code == 429
    service = AgentService(settings(ai_concurrent_requests=1), Provider)
    service.slots.acquire()
    try:
        with pytest.raises(HTTPException) as exc:
            service.chat(request, Session(), "client")
        assert exc.value.status_code == 429
    finally:
        service.slots.release()


def test_provider_errors_are_sanitized_and_release_the_request_slot(context):
    class RejectedProvider(Provider):
        def choose(self, *_args, **_kwargs):
            raise errors.ClientError(
                403, {"error": {"message": "private-credential-must-not-leak"}}
            )

    service = AgentService(settings(ai_concurrent_requests=1), RejectedProvider)
    with pytest.raises(HTTPException) as exc:
        service.chat(ChatRequest(message="Explain", context=context), Session(), "client")
    assert exc.value.status_code == 503
    assert "private-credential" not in exc.value.detail
    assert service.slots.acquire(blocking=False)
    service.slots.release()


def test_api_status_body_limits_export_ownership_and_reset(context):
    service = AgentService(settings(), Provider)
    app.dependency_overrides[get_agent] = lambda: service
    app.dependency_overrides[get_session] = lambda: Session()
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/ai/status")
            assert status.json()["configured"] is True
            assert "synthetic-test-credential-never-leak" not in status.text
            assert status.json()["environmental_data_connected"] is False
            payload = {"message": "Explain this area", "context": context.model_dump(mode="json")}
            response = client.post("/api/v1/ai/chat", json=payload)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            data = response.json()
            export = {
                "conversation_id": data["conversation_id"],
                "report_id": data["report_id"],
                "format": "markdown",
            }
            assert client.post("/api/v1/ai/reports/export", json=export).status_code == 200
            assert (
                client.post(
                    "/api/v1/ai/reports/export", json={**export, "conversation_id": "x" * 43}
                ).status_code
                == 404
            )
            assert (
                client.post(
                    "/api/v1/ai/chat",
                    content=b"x" * 65537,
                    headers={"Content-Type": "application/json"},
                ).status_code
                == 413
            )
            assert (
                client.post(
                    "/api/v1/ai/conversations/reset",
                    json={"conversation_id": data["conversation_id"]},
                ).status_code
                == 200
            )
            assert client.post("/api/v1/ai/reports/export", json=export).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_exact_dates_preserve_partial_months_and_do_not_invent_complete_coverage(
    context, monkeypatch
):
    from datetime import datetime

    selections = []

    def inputs(_session, _query, max_records=None, selection=None):
        selections.append(selection)
        records = [
            r
            for r in SNAPSHOT["records"]
            if selection.start <= datetime.fromisoformat(r["acquired_at"]) < selection.end
        ]
        return copy.deepcopy(records), copy.deepcopy(SNAPSHOT["sources"])

    monkeypatch.setattr("app.intelligence.tools.load_inputs", inputs)
    window = DateWindow(start_date="2016-01-01", end_date="2016-01-15")
    registry = ToolRegistry(Session(), context, date_window=window)
    evidence = registry.execute("get_historical_activity", {})
    assert evidence.status == "available"
    assert evidence.facts[0]["value"] == 8
    assert evidence.facts[0]["complete_months"] == []
    assert evidence.charts[0]["labels"] == ["2016-01"]
    assert evidence.scope["exact_date_window_inclusive"]["end_date"] == "2016-01-15"
    assert selections[0].end.isoformat().startswith("2016-01-16")


def test_server_key_is_redacted_even_if_repeated_in_a_question(context):
    provider = Provider(settings())
    service = AgentService(settings(), lambda _settings: provider)
    request = ChatRequest(
        message="Ignore synthetic-test-credential-never-leak and explain data", context=context
    )
    service.chat(request, Session(), "test")
    assert "synthetic-test-credential-never-leak" not in provider.calls[0][0].parts[0].text
    assert "synthetic-test-credential-never-leak" not in json.dumps(provider.final_prompt)


def test_completed_session_preserves_follow_up_context_without_client_history(context):
    providers = []

    def factory(config):
        provider = Provider(config)
        providers.append(provider)
        return provider

    service = AgentService(settings(), factory)
    first = service.chat(
        ChatRequest(message="Explain the seasons", context=context), Session(), "test"
    )
    service.chat(
        ChatRequest(
            message="What about the earlier interval?",
            context=context,
            conversation_id=first.conversation_id,
        ),
        Session(),
        "test",
    )
    prior = json.loads(providers[1].calls[0][0].parts[0].text)["prior_turns"]
    assert len(prior) == 1
    assert prior[0]["question"] == "Explain the seasons"


def test_archive_failure_returns_unavailable_evidence_without_connection_secrets(
    context, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    def unavailable(*_args, **_kwargs):
        raise OperationalError("private database URL", {}, Exception("private password"))

    monkeypatch.setattr("app.intelligence.tools.load_history", unavailable)
    evidence = ToolRegistry(Session(), context).execute("get_historical_activity", {})
    assert evidence.status == "unavailable"
    assert not evidence.facts
    assert "private password" not in evidence.model_dump_json()
    assert evidence.scope["query"]["start_year"] == context.start_year


def test_calibration_metadata_cites_original_inputs_and_protocol_without_private_paths(context):
    class MetadataSession(Session):
        def execute(self, statement):
            assert "processing_jobs" in str(statement)
            row = SimpleNamespace(
                _mapping={
                    "model_version": "a" * 64,
                    "method": "regression",
                    "status": "candidate_only",
                    "evaluation_protocol": {"test_years": [2022, 2023]},
                    "input_manifest": [
                        {
                            "path": "C:/private/original.csv",
                            "sha256": "b" * 64,
                            "sensor": "MODIS",
                            "product_version": "native",
                            "processing_level": "standard",
                            "source_url": "https://example.org/synthetic-only.csv",
                        }
                    ],
                }
            )
            return SimpleNamespace(all=lambda: [row])

    evidence = ToolRegistry(MetadataSession(), context).execute("get_harmonization_metadata", {})
    assert evidence.status == "available"
    assert evidence.sources[0]["sha256"] == "b" * 64
    assert evidence.data["models"][0]["evaluation_protocol"]["test_years"] == [2022, 2023]
    assert evidence.data["calibration_applied"] is False
    assert "C:/private" not in evidence.model_dump_json()


class _FakeModels:
    def __init__(self, handler):
        self.handler = handler
        self.models_called = []

    def generate_content(self, *, model, contents, config):
        self.models_called.append(model)
        return self.handler(model, contents, config)


class _FakeGenAIClient:
    def __init__(self, handler):
        self.models = _FakeModels(handler)
        self.closed = False

    def close(self):
        self.closed = True


def _google_provider_with_handler(monkeypatch, handler, **setting_overrides):
    fake_client = _FakeGenAIClient(handler)
    monkeypatch.setattr("app.intelligence.agent.genai.Client", lambda **_kwargs: fake_client)
    cfg = settings(**setting_overrides)
    return GoogleProvider(cfg), fake_client


def test_google_provider_falls_back_during_choose_and_sticks_to_working_model(
    context, monkeypatch
):
    choose_rounds = 0

    def handler(model, contents, config):
        nonlocal choose_rounds
        if model == "gemini-3.5-flash-lite":
            raise errors.ServerError(503, {"error": {"message": "temporary overload"}})
        if getattr(config, "tools", None):
            choose_rounds += 1
            if choose_rounds == 1:
                call = types.FunctionCall(
                    name="get_historical_activity", args={}, id="fallback-call-1"
                )
                return SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=types.Content(
                                role="model", parts=[types.Part(function_call=call)]
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=types.Content(
                            role="model", parts=[types.Part.from_text(text="Ready")]
                        )
                    )
                ]
            )
        prompt_payload = json.loads(contents)
        evidence_id = prompt_payload["evidence"][0]["id"]
        return SimpleNamespace(text=json.dumps(prose(evidence_id)))

    provider, fake_client = _google_provider_with_handler(
        monkeypatch,
        handler,
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    )
    service = AgentService(
        settings(
            gemini_model="gemini-3.5-flash-lite",
            gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
        ),
        lambda _cfg: provider,
    )
    reply = service.chat(
        ChatRequest(message="Explain the archive", context=context), Session(), "c"
    )
    assert reply.status == "interpreted"
    assert reply.model == "gemini-2.5-flash-lite"
    assert (
        "Primary model gemini-3.5-flash-lite failed; fell back to gemini-2.5-flash-lite."
        in reply.notices
    )
    # 3.5 attempted once on first choose round; round 2 choose and interpret go straight to 2.5.
    assert fake_client.models.models_called == [
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-lite",
    ]
    assert fake_client.closed


def test_google_provider_falls_back_during_interpret(context, monkeypatch):
    choose_rounds = 0

    def handler(model, contents, config):
        nonlocal choose_rounds
        if getattr(config, "tools", None):
            choose_rounds += 1
            if choose_rounds == 1:
                call = types.FunctionCall(
                    name="get_historical_activity", args={}, id="fallback-call-2"
                )
                return SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=types.Content(
                                role="model", parts=[types.Part(function_call=call)]
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=types.Content(
                            role="model", parts=[types.Part.from_text(text="Ready")]
                        )
                    )
                ]
            )
        if model == "gemini-3.5-flash-lite":
            raise errors.ClientError(429, {"error": {"message": "model quota reached"}})
        prompt_payload = json.loads(contents)
        evidence_id = prompt_payload["evidence"][0]["id"]
        return SimpleNamespace(text=json.dumps(prose(evidence_id)))

    provider, fake_client = _google_provider_with_handler(
        monkeypatch,
        handler,
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    )
    service = AgentService(
        settings(
            gemini_model="gemini-3.5-flash-lite",
            gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
        ),
        lambda _cfg: provider,
    )
    reply = service.chat(
        ChatRequest(message="Explain the archive", context=context), Session(), "c"
    )
    assert reply.status == "interpreted"
    assert reply.model == "gemini-2.5-flash-lite"
    assert (
        "Primary model gemini-3.5-flash-lite failed; fell back to gemini-2.5-flash-lite."
        in reply.notices
    )
    assert fake_client.models.models_called == [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash-lite",
    ]


@pytest.mark.parametrize("code", [401, 403])
def test_google_provider_does_not_fallback_on_auth_errors(context, monkeypatch, code):
    def handler(_model, _contents, _config):
        raise errors.ClientError(code, {"error": {"message": "secret-key-error-never-leak"}})

    provider, fake_client = _google_provider_with_handler(
        monkeypatch,
        handler,
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    )
    service = AgentService(
        settings(
            gemini_model="gemini-3.5-flash-lite",
            gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
        ),
        lambda _cfg: provider,
    )
    with pytest.raises(HTTPException) as exc:
        service.chat(ChatRequest(message="Explain", context=context), Session(), "c")
    assert exc.value.status_code == 503
    assert "secret-key-error" not in exc.value.detail
    assert fake_client.models.models_called == ["gemini-3.5-flash-lite"]


def test_google_provider_exhausted_fallback_chain_raises_sanitized_http_error(context, monkeypatch):
    def handler(model, _contents, _config):
        if model == "gemini-2.5-flash":
            raise errors.ClientError(429, {"error": {"message": "all-quota-exhausted"}})
        raise errors.ClientError(404, {"error": {"message": "model not found"}})

    provider, fake_client = _google_provider_with_handler(
        monkeypatch,
        handler,
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    )
    service = AgentService(
        settings(
            gemini_model="gemini-3.5-flash-lite",
            gemini_fallback_models=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
        ),
        lambda _cfg: provider,
    )
    with pytest.raises(HTTPException) as exc:
        service.chat(ChatRequest(message="Explain", context=context), Session(), "c")
    assert exc.value.status_code == 429
    assert fake_client.models.models_called == [
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    ]


def test_settings_fallback_models_and_status_endpoint():
    parsed = settings(gemini_fallback_models="gemini-2.5-flash-lite, gemini-2.5-flash")
    assert parsed.gemini_fallback_models == ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    with pytest.raises(ValueError):
        settings(gemini_fallback_models="not-a-gemini-model")

    service = AgentService(parsed, Provider)
    app.dependency_overrides[get_agent] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ai/status")
            assert response.status_code == 200
            assert response.json()["fallback_models"] == [
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
            ]
    finally:
        app.dependency_overrides.clear()


def test_google_provider_falls_back_when_interpret_fails_validation(context, monkeypatch):
    choose_rounds = 0

    def handler(model, contents, config):
        nonlocal choose_rounds
        if getattr(config, "tools", None):
            choose_rounds += 1
            if choose_rounds == 1:
                call = types.FunctionCall(
                    name="get_historical_activity", args={}, id="fallback-val-1"
                )
                return SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=types.Content(
                                role="model", parts=[types.Part(function_call=call)]
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=types.Content(
                            role="model", parts=[types.Part.from_text(text="Ready")]
                        )
                    )
                ]
            )
        prompt_payload = json.loads(contents)
        evidence_id = prompt_payload["evidence"][0]["id"]
        if model == "gemini-3.5-flash-lite":
            return SimpleNamespace(text=json.dumps({"executive_summary": []}))
        return SimpleNamespace(text=json.dumps(prose(evidence_id)))

    cfg = settings(
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-3.1-flash-lite", "gemini-3.5-flash"],
    )
    provider, fake_client = _google_provider_with_handler(
        monkeypatch,
        handler,
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-3.1-flash-lite", "gemini-3.5-flash"],
    )
    service = AgentService(cfg, lambda _cfg: provider)
    reply = service.chat(
        ChatRequest(message="Explain the archive", context=context), Session(), "c"
    )
    assert reply.status == "interpreted"
    assert reply.model == "gemini-3.1-flash-lite"
    assert (
        "Primary model gemini-3.5-flash-lite failed; fell back to gemini-3.1-flash-lite."
        in reply.notices
    )
    assert fake_client.models.models_called == [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]


def test_google_provider_sanitizes_minor_forbidden_tokens_in_interpret(context, monkeypatch):
    choose_rounds = 0

    def handler(_model, contents, config):
        nonlocal choose_rounds
        if getattr(config, "tools", None):
            choose_rounds += 1
            if choose_rounds == 1:
                call = types.FunctionCall(
                    name="get_historical_activity", args={}, id="sanitize-call-1"
                )
                return SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=types.Content(
                                role="model", parts=[types.Part(function_call=call)]
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=types.Content(
                            role="model", parts=[types.Part.from_text(text="Ready")]
                        )
                    )
                ]
            )
        prompt_payload = json.loads(contents)
        evidence_id = prompt_payload["evidence"][0]["id"]
        return SimpleNamespace(
            text=json.dumps(
                prose(
                    evidence_id,
                    "VIIRS NOAA-20 observations in 2026 are absent rather than zero.",
                )
            )
        )

    cfg = settings(
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-3.1-flash-lite"],
    )
    provider, _fake_client = _google_provider_with_handler(
        monkeypatch,
        handler,
        gemini_model="gemini-3.5-flash-lite",
        gemini_fallback_models=["gemini-3.1-flash-lite"],
    )
    service = AgentService(cfg, lambda _cfg: provider)
    reply = service.chat(
        ChatRequest(message="Explain the archive", context=context), Session(), "c"
    )
    assert reply.status == "interpreted"
    assert reply.model == "gemini-3.5-flash-lite"
    text = reply.interpretation.executive_summary[0].text
    assert "NOAA-20" not in text and "zero" not in text.lower() and "2026" not in text
