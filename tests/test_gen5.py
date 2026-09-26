import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from platemap.gen5 import (
    check_gen5_layout,
    parse_gen5,
    parse_gen5_layout,
    parse_gen5_metadata,
    parse_gen5_reads,
)
from platemap.samples import PlatemapError

FIXTURES = Path(__file__).parent / "fixtures"


def _row(well, role, short_id, conc_ugml=None):
    return SimpleNamespace(well=well, role=role, short_id=short_id, conc_ugml=conc_ugml)


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


def test_real_format_default_is_raw_read():
    data = parse_gen5(str(FIXTURES / "gen5_real_format.txt"))
    assert data["A1"] == pytest.approx(0.100)
    assert data["H12"] == pytest.approx(1.890)


def test_real_format_read_label_selects_blank():
    data = parse_gen5(str(FIXTURES / "gen5_real_format.txt"), read_label="Blank Read 562nm:562")
    assert data["A1"] == pytest.approx(0.220)
    assert data["H12"] == pytest.approx(2.010)


def test_real_format_wavelength_562_matches_raw():
    data = parse_gen5(str(FIXTURES / "gen5_real_format.txt"), wavelength=562)
    assert data["A1"] == pytest.approx(0.100)


def test_real_format_layout():
    layout = parse_gen5_layout(str(FIXTURES / "gen5_real_format.txt"))
    assert layout["A1"] == ("BCA:1", "2000")
    assert layout["B5"] == ("BLK", "")
    assert layout["B7"] == ("SPL1", "")


def test_real_format_metadata():
    metadata = parse_gen5_metadata(str(FIXTURES / "gen5_real_format.txt"))
    assert metadata["Plate Number"] == "Plate 2"


def test_real_format_stdcurve_section_ignored():
    reads = parse_gen5_reads(str(FIXTURES / "gen5_real_format.txt"))
    assert set(reads.keys()) == {"Read 562nm:562", "Blank Read 562nm:562"}


def test_check_gen5_layout_standard_ok():
    rows = [_row("A1", "standard", "STD2000", 2000.0)]
    layout = {"A1": ("BCA:1", "2000")}
    errors, warnings = check_gen5_layout(rows, layout)
    assert errors == []
    assert warnings == []


def test_check_gen5_layout_standard_conc_mismatch():
    rows = [_row("A1", "standard", "STD2000", 2000.0)]
    layout = {"A1": ("BCA:1", "1500")}
    errors, warnings = check_gen5_layout(rows, layout)
    assert len(errors) == 1
    assert "A1" in errors[0]


def test_check_gen5_layout_blank_wrong_id():
    rows = [_row("B5", "blank", "BLK")]
    layout = {"B5": ("SPL1", "")}
    errors, warnings = check_gen5_layout(rows, layout)
    assert len(errors) == 1
    assert "B5" in errors[0]


def test_check_gen5_layout_sample_rank():
    rows = [
        _row("B7", "sample", "S27"),
        _row("B8", "sample", "S27"),
        _row("B9", "sample", "S27"),
        _row("B10", "sample", "S28"),
        _row("B11", "sample", "S28"),
        _row("B12", "sample", "S28"),
    ]
    layout = {
        "B7": ("SPL1", ""),
        "B8": ("SPL1", ""),
        "B9": ("SPL1", ""),
        "B10": ("SPL2", ""),
        "B11": ("SPL2", ""),
        "B12": ("SPL2", ""),
    }
    errors, warnings = check_gen5_layout(rows, layout)
    assert errors == []


def test_check_gen5_layout_sample_rank_is_by_short_id_not_well_order():
    # A7 = S9 (well order first), B4 = S2 (well order second): rank must follow the
    # S-number, not well order, so this is mode-independent (e.g. multichannel).
    rows = [
        _row("A7", "sample", "S9"),
        _row("A8", "sample", "S9"),
        _row("A9", "sample", "S9"),
        _row("B4", "sample", "S2"),
        _row("B5", "sample", "S2"),
        _row("B6", "sample", "S2"),
    ]
    layout = {
        # Rank by S-number: S2 -> SPL1, S9 -> SPL2 (not well order, which would be reversed).
        "A7": ("SPL2", ""),
        "A8": ("SPL2", ""),
        "A9": ("SPL2", ""),
        "B4": ("SPL1", ""),
        "B5": ("SPL1", ""),
        "B6": ("SPL1", ""),
    }
    errors, warnings = check_gen5_layout(rows, layout)
    assert errors == []


def test_check_gen5_layout_missing_in_gen5_is_error():
    rows = [_row("A1", "standard", "STD2000", 2000.0)]
    layout = {}
    errors, warnings = check_gen5_layout(rows, layout)
    assert len(errors) == 1


def test_check_gen5_layout_extra_in_gen5_is_warning():
    rows = []
    layout = {"A1": ("BCA:1", "2000")}
    errors, warnings = check_gen5_layout(rows, layout)
    assert errors == []
    assert len(warnings) == 1


def test_wavelength_matches_read_label(tmp_path):
    header = "," + ",".join(str(c) for c in range(1, 13))
    body = "\n".join(r + "," + ",".join(["0.5"] * 12) for r in "ABCDEFGH")
    p = tmp_path / "g.csv"
    p.write_text(f"Read 1:562\n{header}\n{body}\n", encoding="utf-8")
    assert parse_gen5(p, wavelength="562")["H12"] == 0.5
