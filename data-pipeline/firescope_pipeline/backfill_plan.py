"""Pure date/availability planning. No database, filesystem or network access."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Product:
    product: str
    sensor: str
    first_day: date
    standard: str
    nrt: str


PRODUCTS = (
    Product("modis", "MODIS", date(2000, 11, 1), "MODIS_SP", "MODIS_NRT"),
    Product("viirs-snpp", "VIIRS_SNPP", date(2012, 1, 20), "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
)


def subtract_intervals(start, end, covered):
    """Return disjoint half-open uncovered date intervals, never inferred zeros."""
    cursor, gaps = start, []
    for lo, hi in sorted(covered):
        lo, hi = max(start, lo), min(end, hi)
        if lo >= hi:
            continue
        if cursor < lo:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def plan_backfill(*, start, through, as_of, catalog, availability):
    """Annual country files first; standard API next; NRT only for the remaining tail.

    API availability bounds are inclusive. Plans and checkpoints use exclusive ends.
    Current-day data are provisional, even when the API publishes that day.
    """
    if not date(2000, 1, 1) <= start <= through <= as_of:
        raise ValueError("Use ordered dates from 2000 through today (UTC)")
    end = through + timedelta(days=1)
    tasks, gaps = [], []
    for product in PRODUCTS:
        active_start = max(start, product.first_day)
        if start < min(end, product.first_day):
            gaps.append(
                {
                    "sensor": product.sensor,
                    "start": start.isoformat(),
                    "end": min(end, product.first_day).isoformat(),
                    "reason": "pre_operational_sensor",
                }
            )
        if active_start >= end:
            continue
        covered = []
        for year in range(active_start.year, through.year + 1):
            name = f"{product.product}_{year}_Jordan.csv"
            # A current-year summary does not establish a complete annual archive.
            if year >= as_of.year or name not in catalog:
                continue
            lo, hi = max(active_start, date(year, 1, 1)), min(end, date(year + 1, 1, 1))
            tasks.append(
                {
                    "kind": "annual",
                    "sensor": product.sensor,
                    "name": name,
                    "product": product.product,
                    "year": year,
                    "catalog_signature": catalog[name],
                    "start": lo.isoformat(),
                    "end": hi.isoformat(),
                }
            )
            covered.append((lo, hi))
        remaining = subtract_intervals(active_start, end, covered)
        for source in (product.standard, product.nrt):
            dates = availability.get(source)
            if dates is None:
                continue
            first, last = dates
            if first > last:
                raise ValueError("NASA availability dates must be ordered")
            next_remaining = []
            for lo, hi in remaining:
                begin, stop = max(lo, first), min(hi, last + timedelta(days=1))
                if begin < stop:
                    tasks.append(
                        {
                            "kind": "api",
                            "sensor": product.sensor,
                            "source": source,
                            "start": begin.isoformat(),
                            "end": stop.isoformat(),
                        }
                    )
                    next_remaining.extend(subtract_intervals(lo, hi, [(begin, stop)]))
                else:
                    next_remaining.append((lo, hi))
            remaining = next_remaining
        gaps.extend(
            {
                "sensor": product.sensor,
                "start": lo.isoformat(),
                "end": hi.isoformat(),
                "reason": "outside_published_availability",
            }
            for lo, hi in remaining
        )
    return {
        "region": "jordan",
        "start": start.isoformat(),
        "through": through.isoformat(),
        "end_exclusive": end.isoformat(),
        "as_of": as_of.isoformat(),
        "tasks": tasks,
        "gaps": gaps,
        "current_day_provisional": through == as_of,
    }
