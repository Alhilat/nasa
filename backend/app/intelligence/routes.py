import html
import json
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session

from .agent import AgentService
from .schemas import ChatRequest, ExportRequest, ResetRequest
from .tools import CATALOG, TOOL_SPECS

router = APIRouter(prefix="/api/v1/ai", tags=["scientific intelligence"])
SessionDep = Annotated[Session, Depends(get_session)]


@lru_cache
def get_agent():
    return AgentService(get_settings())


AgentDep = Annotated[AgentService, Depends(get_agent)]


class AIBodyLimit:
    """Reject oversized AI bodies before FastAPI JSON decoding, including chunked input."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not scope.get("path", "").startswith("/api/v1/ai/")
        ):
            await self.app(scope, receive, send)
            return
        chunks, total = [], 0
        while True:
            part = await receive()
            if part["type"] == "http.disconnect":
                return
            total += len(part.get("body", b""))
            if total > 65536:
                await JSONResponse(
                    {"detail": "AI request exceeds 64 KiB; simplify the region or message"},
                    status_code=413,
                )(scope, receive, send)
                return
            chunks.append(part.get("body", b""))
            if not part.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


@router.get("/status")
def status(agent: AgentDep):
    return {
        "configured": bool(agent.settings.gemini_api_key.get_secret_value()),
        "model": agent.settings.gemini_model,
        "fallback_models": list(getattr(agent.settings, "gemini_fallback_models", [])),
        "tools": list(TOOL_SPECS),
        "regions": CATALOG,
        "requests_per_minute": agent.settings.ai_requests_per_minute,
        "requests_per_day": agent.settings.ai_requests_per_day,
        "environmental_data_connected": False,
        "forecasting": False,
        "privacy": (
            "Questions, selected geometry and bounded analytical evidence"
            " are sent to Google Gemini when you submit. The API key and "
            "original source files are never sent in prompts."
        ),
    }


@router.post("/chat")
def chat(payload: ChatRequest, request: Request, session: SessionDep, agent: AgentDep):
    result = agent.chat(payload, session, request.client.host if request.client else "unknown")
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.post("/reports")
def report(payload: ChatRequest, request: Request, session: SessionDep, agent: AgentDep):
    result = agent.chat(
        payload, session, request.client.host if request.client else "unknown", report=True
    )
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


def markdown_report(reply):
    # Text is rendered inert; citations are assembled from server-owned source metadata.
    def text(value):
        value = html.escape(str(value)).replace("\n", " ")
        for character in "\\`*_{}[]|":
            value = value.replace(character, "\\" + character)
        return value

    lines = [
        "# PIRX scientific activity report",
        "",
        f"Model: {text(reply.model)}",
        f"Created (UTC): {text(reply.created_at)}",
        "",
        "AI prose is interpretation. Numeric results below are produced by Python, not Gemini.",
        "Thermal detections are not unique wildfires, burned area or risk forecasts.",
        "",
    ]
    interpretation = reply.interpretation
    lines.extend(["## Executive summary", ""])
    if interpretation:
        lines.extend(
            f"- {text(s.text)} ({', '.join(s.evidence_ids)})"
            for s in interpretation.executive_summary
        )
    else:
        lines.append("AI interpretation unavailable; the report contains retrieved evidence only.")
    for section, title in [
        ("historical_observations", "Historical observations"),
        ("statistical_comparisons", "Statistical comparisons"),
        ("anomalies", "Anomalies"),
    ]:
        lines.extend(["", f"## {title}", ""])
        facts = [(e, f) for e in reply.evidence for f in e.facts if f.get("section") == section]
        if not facts:
            lines.append(
                "No assessed result was returned for this section; absence is"
                " not a zero or proof of normal activity."
            )
        for evidence, fact in facts:
            lines.append(
                f"- {text(fact.get('label'))}: "
                f"{text(json.dumps(fact, ensure_ascii=False))} ({evidence.id})"
            )
    if interpretation:
        lines.extend(["", "## Scientific interpretations", ""])
        lines.extend(
            f"- {text(s.text)} ({', '.join(s.evidence_ids)})"
            for s in interpretation.interpretations
        )
    lines.extend(["", "## Supporting evidence", ""])
    for evidence in reply.evidence:
        lines.extend(
            [
                f"### {evidence.id} — {text(evidence.tool)}",
                "",
                f"Status: {evidence.status}; snapshot retrieved: "
                f"{text(evidence.retrieved_at)}; cache hit: {evidence.cache_hit}",
                f"Scope: {text(json.dumps(evidence.scope, ensure_ascii=False))}",
                f"Analysis IDs: {text(', '.join(evidence.analysis_ids))}",
            ]
        )
        for source in evidence.sources:
            url = source.get("source_url")
            citation = (
                f"[dataset]({quote(url, safe=':/?&=%.#_-')})" if url else "source URL unavailable"
            )
            lines.append(
                f"- {citation}; sensor {text(source.get('sensor_code'))}; "
                f"SHA-256 {text(source.get('sha256'))}; "
                f"product {text(source.get('product_version'))}"
            )
    lines.extend(["", "## Data limitations", ""])
    lines.extend(
        f"- {text(note)}"
        for note in dict.fromkeys(n for e in reply.evidence for n in e.limitations)
    )
    if interpretation:
        lines.extend(
            f"- {text(s.text)} ({', '.join(s.evidence_ids)})"
            for s in interpretation.data_limitations
        )
    lines.extend(["", "## Recommendations for further monitoring", ""])
    if interpretation:
        lines.extend(
            f"- {text(s.text)} ({', '.join(s.evidence_ids)})"
            for s in interpretation.recommendations
        )
    else:
        lines.append(
            "- Review data completeness and source provenance before draw"
            "ing scientific conclusions."
        )
    return "\n".join(lines) + "\n"


@router.post("/reports/export", response_class=Response)
def export(payload: ExportRequest, agent: AgentDep):
    reply = agent.stored_report(payload.conversation_id, payload.report_id)
    content = (
        reply.model_dump_json(indent=2) if payload.format == "json" else markdown_report(reply)
    )
    suffix = "json" if payload.format == "json" else "md"
    return Response(
        content,
        media_type="application/json" if suffix == "json" else "text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="pirx-ai-report.{suffix}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/conversations/reset")
def reset(payload: ResetRequest, agent: AgentDep):
    agent.reset(payload.conversation_id)
    return {"status": "cleared"}
