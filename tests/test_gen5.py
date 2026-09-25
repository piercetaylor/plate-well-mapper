import math
from pathlib import Path

import pytest

from platemap.gen5 import parse_gen5
from platemap.samples import PlatemapError

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_basic_block():
    data = parse_gen5(str(FIXTURES / "gen5_example.csv"))
    assert data["A1"] == 0.101
    assert data["A12"] == 0.112
    assert data["H12"] == 0.812


def test_parse_ovrflw_and_bad_value_are_nan():
    data = parse_gen5(str(FIXTURES / "gen5_example.csv"))
    assert math.isnan(data["B4"])
    assert math.isnan(data["E6"])


def test_two_blocks_default_is_first():
    data = parse_gen5(str(FIXTURES / "gen5_two_blocks.csv"))
    assert data["A1"] == 1.101


def test_two_blocks_wavelength_selects_second():
    data = parse_gen5(str(FIXTURES / "gen5_two_blocks.csv"), wavelength=660)
    assert data["A1"] == 2.101


def test_two_blocks_block_index():
    data = parse_gen5(str(FIXTURES / "gen5_two_blocks.csv"), block_index=1)
    assert data["A1"] == 2.101


def test_wavelength_not_found_raises():
    with pytest.raises(PlatemapError):
        parse_gen5(str(FIXTURES / "gen5_two_blocks.csv"), wavelength=999)


def test_block_index_out_of_range_raises():
    with pytest.raises(PlatemapError):
        parse_gen5(str(FIXTURES / "gen5_two_blocks.csv"), block_index=5)


def test_long_format():
    data = parse_gen5(str(FIXTURES / "gen5_long_format.csv"))
    assert data["A1"] == 0.111
    assert data["B7"] == 0.301


def test_long_format_wavelength_selects_column():
    data = parse_gen5(str(FIXTURES / "gen5_long_format.csv"), wavelength=660)
    assert data["A1"] == 0.211
    assert data["H12"] == 0.888


def test_no_data_raises(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("just,some,random,text\n", encoding="utf-8")
    with pytest.raises(PlatemapError):
        parse_gen5(str(path))


def test_wavelength_matches_read_label(tmp_path):
    header = "," + ",".join(str(c) for c in range(1, 13))
    body = "\n".join(r + "," + ",".join(["0.5"] * 12) for r in "ABCDEFGH")
    p = tmp_path / "g.csv"
    p.write_text(f"Read 1:562\n{header}\n{body}\n", encoding="utf-8")
    assert parse_gen5(p, wavelength="562")["H12"] == 0.5
