import csv
from pathlib import Path

import pytest

from canonical_audit_v2 import load_symbol, funding_map


def write_ohlcv(path: Path, times):
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['open_time','open','high','low','close','volume'])
        for t in times:
            w.writerow([t, 100, 101, 99, 100, 10])


def test_validator_rejects_duplicate_timestamps(tmp_path):
    p = tmp_path / 'BTCUSDT_15m.csv'
    write_ohlcv(p, [0, 900000, 900000])
    with pytest.raises(ValueError, match='duplicate|non-15m'):
        load_symbol(p, '1970-01-01T00:00:00Z', '1970-01-01T01:00:00Z')


def test_validator_rejects_gap(tmp_path):
    p = tmp_path / 'BTCUSDT_15m.csv'
    write_ohlcv(p, [0, 900000, 2700000])
    with pytest.raises(ValueError, match='non-15m gaps'):
        load_symbol(p, '1970-01-01T00:00:00Z', '1970-01-01T01:00:00Z')


def test_funding_map_accepts_standard_columns(tmp_path):
    p = tmp_path / 'funding.csv'
    p.write_text('fundingTime,fundingRate\n1000,0.0001\n2000,-0.0002\n')
    assert funding_map(p) == {1000: 0.0001, 2000: -0.0002}
