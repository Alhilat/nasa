"""Public harmonized-calendar contract; TypeScript is generated from these models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CalendarContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MedianComparison(CalendarContract):
    historical_median: float | None
    departure: float | None
    departure_percent: float | None
    baseline_size: int
    baseline_years: list[int]
    status: Literal[
        "assessed",
        "missing_value",
        "incomplete_archive",
        "insufficient_history",
        "unapproved_mapping",
        "extrapolated",
        "unsupported_processing",
    ]
    reason: str


class CalendarMonth(CalendarContract):
    month: str
    value: float | None
    lower_95: float | None
    upper_95: float | None
    mapped_value: float | None = None
    mapped_lower_95: float | None = None
    mapped_upper_95: float | None = None
    mapped_extrapolated: bool | None = None
    sensor_code: str | None
    origin: Literal["modis_reference", "mapped_viirs", "missing"]
    validation_status: Literal["validated", "experimental", "unavailable"]
    completeness: str
    extrapolated: bool
    model_version: str | None
    source_ids: list[str]
    reason: str
    uncertainty_reason: str
    median_comparison: MedianComparison


class CalendarCandidate(CalendarContract):
    method: str
    available: bool
    validation_mae: float | None
    reason: str | None


class CalendarModel(CalendarContract):
    method: str
    model_version: str
    artifact: dict
    approval: Literal["supported_for_scope", "experimental"]
    training_months: list[str]
    selection_year: int | None
    selection_mae: float | None
    bootstrap_successes: int


class HarmonizedCalendar(CalendarContract):
    algorithm_version: str
    status: Literal["validated", "experimental", "unavailable"]
    reference_sensor: str | None
    source_sensor: str | None
    units: str
    selection_policy: str
    uncertainty_method: str
    reason: str
    limitations: list[str]
    candidates: list[CalendarCandidate]
    model: CalendarModel | None
    monthly: list[CalendarMonth]
