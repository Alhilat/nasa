from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.history import HistoryQuery


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scope(StrictModel):
    region_id: str = Field(default="selected", max_length=80)
    start_year: int | None = Field(default=None, ge=1900, le=2099)
    end_year: int | None = Field(default=None, ge=1900, le=2099)
    sensors: list[str] | None = Field(default=None, max_length=5)
    start_date: date | None = Field(
        default=None, description="Inclusive UTC date; supply with end_date for exact-day selection"
    )
    end_date: date | None = Field(
        default=None, description="Inclusive UTC date; partial months cannot be declared complete"
    )


class DateWindow(StrictModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def ordered(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must not follow end_date")
        return self


class CompareSeasons(StrictModel):
    region_id: str = Field(default="selected", max_length=80)
    other_region_id: str | None = Field(default=None, max_length=80)
    first_year: int = Field(ge=1900, le=2099)
    second_year: int = Field(ge=1900, le=2099)
    months: list[int] = Field(min_length=1, max_length=12)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=3000)
    context: HistoryQuery
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{40,60}$")
    refresh: bool = False
    date_window: DateWindow | None = None

    @model_validator(mode="after")
    def window_in_context(self):
        if self.date_window and not (
            self.context.start_year
            <= self.date_window.start_date.year
            <= self.date_window.end_date.year
            <= self.context.end_year
        ):
            raise ValueError("Selected date window must belong to the context years")
        return self


class Statement(StrictModel):
    text: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=6)


class Interpretation(StrictModel):
    executive_summary: list[Statement] = Field(min_length=1, max_length=4)
    interpretations: list[Statement] = Field(max_length=6)
    data_limitations: list[Statement] = Field(min_length=1, max_length=6)
    recommendations: list[Statement] = Field(min_length=1, max_length=6)


class Evidence(StrictModel):
    id: str
    tool: str
    status: Literal["available", "unavailable"]
    scope: dict[str, Any]
    analysis_ids: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    source_count: int = 0
    source_list_truncated: bool = False
    facts: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    retrieved_at: str
    cache_hit: bool = False


class AgentReply(StrictModel):
    conversation_id: str
    report_id: str
    model: str
    created_at: str
    status: Literal["interpreted", "evidence_only"]
    interpretation: Interpretation | None
    evidence: list[Evidence]
    tool_calls: list[dict[str, Any]]
    notices: list[str]
    forecasting: Literal[False] = False


class ExportRequest(StrictModel):
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{40,60}$")
    report_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    format: Literal["markdown", "json"] = "markdown"


class ResetRequest(StrictModel):
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{40,60}$")
