"""Mock network responses only; no MAP_KEY or external NASA requests are used."""
from datetime import UTC, date, datetime

import httpx
import pytest

from firescope_pipeline.firms_api import FIRMSAPIError, FIRMSClient, retry_delay

KEY = "testkeynotreal"
HEADER = b"latitude,longitude,acq_date,acq_time,satellite,confidence,version\n"


def make_client(handler, **kwargs):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FIRMSClient(KEY, client=http, sleep=kwargs.pop("sleep", lambda _delay: None), **kwargs)


def test_official_area_contract_and_header_only_zero_result():
    seen = []
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, content=HEADER)
    with make_client(handler) as client:
        assert client.area("MODIS_NRT", (34.8, 29, 39.4, 33.5), date(2026, 1, 1)) == HEADER
    assert seen == [f"/api/area/csv/{KEY}/MODIS_NRT/34.8,29,39.4,33.5/1/2026-01-01"]


def test_transient_error_retries_and_honors_retry_after():
    responses = [httpx.Response(503, headers={"Retry-After": "7"}),
                 httpx.Response(200, content=HEADER)]
    sleeps = []
    with make_client(lambda _r: responses.pop(0), sleep=sleeps.append) as client:
        assert client.area("VIIRS_SNPP_NRT", (0, 0, 1, 1), date(2026, 1, 1)) == HEADER
        assert client.requests == 2
    assert 7 in sleeps and 1 in sleeps


def test_rate_limit_without_retry_after_stops_for_quota_window():
    with make_client(lambda _r: httpx.Response(429)) as client:
        with pytest.raises(FIRMSAPIError, match="600 seconds") as error:
            client.area("MODIS_NRT", (0, 0, 1, 1), date(2026, 1, 1))
        assert client.requests == 1
        assert KEY not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 302])
def test_permanent_errors_are_not_retried_or_echoed(status):
    with make_client(lambda _r: httpx.Response(status, text=f"Invalid key: {KEY}")) as client:
        with pytest.raises(FIRMSAPIError) as error:
            client.area("MODIS_NRT", (0, 0, 1, 1), date(2026, 1, 1))
        assert KEY not in str(error.value)
        assert client.requests == 1


def test_http_200_error_text_is_not_an_empty_scientific_response():
    with make_client(lambda _r: httpx.Response(200, text=f"Invalid MAP_KEY {KEY}")) as client:
        with pytest.raises(FIRMSAPIError, match="not observations") as error:
            client.area("MODIS_NRT", (0, 0, 1, 1), date(2026, 1, 1))
        assert KEY not in str(error.value)


def test_network_failure_exhaustion_redacts_sensitive_exception():
    def handler(request):
        raise httpx.ConnectError(f"Could not connect to URL containing {KEY}", request=request)
    with make_client(handler, retries=2) as client:
        with pytest.raises(FIRMSAPIError, match="retry budget exhausted") as error:
            client.area("MODIS_NRT", (0, 0, 1, 1), date(2026, 1, 1))
        assert KEY not in str(error.value)
        assert client.requests == 3


def test_local_request_budget_includes_retry_attempts():
    with make_client(lambda _r: httpx.Response(503), max_requests=1) as client:
        with pytest.raises(FIRMSAPIError, match="budget exhausted"):
            client.area("MODIS_NRT", (0, 0, 1, 1), date(2026, 1, 1))
        assert client.requests == 1


def test_availability_is_parsed_without_assuming_sensor_end_dates():
    with make_client(lambda _r: httpx.Response(200, text=(
        "data_id,min_date,max_date\nVIIRS_SNPP_NRT,2026-09-01,2026-11-02\n"
    ))) as client:
        assert client.availability("VIIRS_SNPP_NRT") == (date(2026, 9, 1), date(2026, 11, 2))


@pytest.mark.parametrize("body", ["Invalid MAP_KEY", "<html>error</html>", "data_id,min_date,max_date\n"])
def test_bad_availability_does_not_invent_ranges(body):
    with make_client(lambda _r: httpx.Response(200, text=body)) as client:
        with pytest.raises(FIRMSAPIError):
            client.availability("MODIS_NRT")


def test_retry_after_http_date_and_invalid_header():
    assert retry_delay("Wed, 01 Jan 2025 00:00:10 GMT", 0,
                       now=datetime(2025, 1, 1, tzinfo=UTC)) == 10
    assert 2 <= retry_delay("nonsense", 1) <= 2.5
    assert 1 <= retry_delay("nan", 0) <= 1.5


def test_bad_request_parameters_fail_before_network():
    with make_client(lambda _r: pytest.fail("Must not request")) as client:
        for source, bbox, days in [("BAD", (0, 0, 1, 1), 1),
                                   ("MODIS_NRT", (170, 0, -170, 1), 1),
                                   ("MODIS_NRT", (0, 0, 1, 1), 6)]:
            with pytest.raises(ValueError):
                client.area(source, bbox, date(2026, 1, 1), days)
    with pytest.raises(ValueError, match="MAP_KEY"):
        FIRMSClient("")


def test_httpx_diagnostic_logging_redacts_map_key(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="httpx")
    with make_client(lambda _r: httpx.Response(200, content=HEADER)) as client:
        client.area("MODIS_NRT", (0, 0, 1, 1), date(2026, 1, 1))
    assert KEY not in caplog.text
    assert "[REDACTED]" in caplog.text
