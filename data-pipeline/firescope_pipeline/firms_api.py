"""Bounded NASA FIRMS area client. MAP_KEY never enters exception messages/metadata."""
import csv
import io
import logging
import math
import random
import time
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.schemas import ObservationQuery
from firescope_pipeline.ingest import MAX_FILE_BYTES

BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
API_SOURCES = {
    "MODIS_NRT": "MODIS", "MODIS_SP": "MODIS",
    "VIIRS_SNPP_NRT": "VIIRS_SNPP", "VIIRS_SNPP_SP": "VIIRS_SNPP",
    "VIIRS_NOAA20_NRT": "VIIRS_NOAA20", "VIIRS_NOAA20_SP": "VIIRS_NOAA20",
    "VIIRS_NOAA21_NRT": "VIIRS_NOAA21", "VIIRS_NOAA21_SP": "VIIRS_NOAA21",
}


class FIRMSAPIError(RuntimeError):
    pass


class _RedactKey(logging.Filter):
    def __init__(self, key):
        super().__init__()
        self.key = key

    def filter(self, record):
        message = record.getMessage()
        if self.key in message:
            record.msg, record.args = message.replace(self.key, "[REDACTED]"), ()
        return True


def retry_delay(header: str | None, attempt: int, now=None) -> float:
    if header:
        try:
            delay = float(header)
            if math.isfinite(delay) and delay >= 0:
                return delay
        except ValueError:
            try:
                timestamp = parsedate_to_datetime(header)
                if timestamp.utcoffset() is not None:
                    return max(0, (timestamp - (now or datetime.now(UTC))).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return min(2 ** attempt + random.uniform(0, 0.5), 30)


class FIRMSClient:
    def __init__(self, map_key: str, *, client=None, sleep=time.sleep, retries=3,
                 min_interval=1.0, max_retry_wait=60.0, max_requests=200):
        if not map_key or not map_key.isascii() or not map_key.isalnum():
            raise ValueError("Set a valid MAP_KEY environment variable; never pass it as a CLI flag")
        if (not 0 <= retries <= 8 or not math.isfinite(min_interval) or min_interval < 1
                or not 1 <= max_requests <= 5000 or not math.isfinite(max_retry_wait)
                or not 0 <= max_retry_wait <= 60):
            raise ValueError("Invalid API retry/rate configuration")
        self._key = map_key
        self._client = client or httpx.Client(timeout=30, follow_redirects=False)
        self._owns_client = client is None
        self._sleep = sleep
        self.retries, self.min_interval = retries, min_interval
        self.max_retry_wait, self.max_requests = max_retry_wait, max_requests
        self.requests = 0
        self._log_filter = _RedactKey(map_key)
        self._loggers = [logging.getLogger(name) for name in (
            "httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2",
            "httpcore.proxy", "httpcore.socks",
        )]
        for logger in self._loggers:
            logger.addFilter(self._log_filter)

    def close(self):
        if self._owns_client:
            self._client.close()
        for logger in self._loggers:
            logger.removeFilter(self._log_filter)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _get(self, path: str) -> bytes:
        failure = None
        for attempt in range(self.retries + 1):
            if self.requests >= self.max_requests:
                raise FIRMSAPIError("Local request budget exhausted; resume later")
            if self.requests:
                self._sleep(self.min_interval)
            self.requests += 1
            try:
                with self._client.stream("GET", BASE_URL + path) as response:
                    status = response.status_code
                    retry_after = response.headers.get("Retry-After")
                    chunks, size = [], 0
                    if status == 200:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_FILE_BYTES:
                                raise FIRMSAPIError("API response exceeds 50 MiB; narrow the region")
                            chunks.append(chunk)
                        return b"".join(chunks)
                failure = f"NASA FIRMS returned HTTP {status}"
                if status not in {408, 429, 500, 502, 503, 504}:
                    raise FIRMSAPIError(failure)
                delay = retry_delay(retry_after, attempt)
                if status == 429 and not retry_after:
                    delay = 600  # NASA's documented 10-minute transaction window.
            except (httpx.TransportError, httpx.TimeoutException):
                failure = "NASA FIRMS network request failed"
                delay = retry_delay(None, attempt)
            if attempt == self.retries:
                break
            if delay > self.max_retry_wait:
                raise FIRMSAPIError(
                    f"{failure}; retry after at least {math.ceil(delay)} seconds and resume"
                ) from None
            self._sleep(delay)
        raise FIRMSAPIError(f"{failure}; retry budget exhausted") from None

    def availability(self, source: str) -> tuple[date, date]:
        if source not in API_SOURCES:
            raise ValueError("Unsupported FIRMS source")
        content = self._get(f"/api/data_availability/csv/{self._key}/{source}")
        try:
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
            row = next(row for row in rows if row.get("data_id", "").upper() == source)
            first, last = date.fromisoformat(row["min_date"]), date.fromisoformat(row["max_date"])
            if first > last:
                raise ValueError()
            return first, last
        except (UnicodeError, ValueError, KeyError, StopIteration, csv.Error):
            raise FIRMSAPIError("FIRMS availability response is not a supported CSV") from None

    def area(self, source: str, bbox, start: date, days: int = 1) -> bytes:
        if source not in API_SOURCES or not 1 <= days <= 5:
            raise ValueError("Use a supported source and a 1–5 day request")
        validated = ObservationQuery(bbox=bbox).bbox
        if validated is None or validated[0] >= validated[2]:
            raise ValueError("API area requires a non-wrapping bbox; split at the antimeridian")
        bounds = ",".join(format(value, ".8g") for value in validated)
        content = self._get(
            f"/api/area/csv/{self._key}/{source}/{bounds}/{days}/{start.isoformat()}"
        )
        try:
            header = next(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
            if not {"latitude", "longitude", "acq_date", "acq_time", "satellite"} <= set(header):
                raise ValueError()
        except (UnicodeError, StopIteration, ValueError, csv.Error):
            # FIRMS sometimes returns error text with HTTP 200. Do not echo it: it may contain key.
            raise FIRMSAPIError("FIRMS returned an error or unsupported CSV, not observations") from None
        return content
