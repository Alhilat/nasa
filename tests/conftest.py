"""Synthetic fixtures exercise software only; never served as scientific observations."""

import pytest


@pytest.fixture
def csv_bytes():
    return (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp,version,daynight,custom\n"
        "0,0,2024-01-01,0030,Terra,MODIS,80,12.5,6.1,D,test-only\n"
        "0.1,0.1,2024-01-01,1300,Terra,MODIS,20,,6.1,N,preserved\n"
    ).encode()
