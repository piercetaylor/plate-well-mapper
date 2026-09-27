import pytest

from platemap.layout import build_layout, capacity, n_plates
from platemap.samples import PlatemapError, Sample


def _samples(n):
    return [Sample(sample_name=f"S{i}") for i in range(1, n + 1)]


def _by_well(rows, plate=1):
    return {r.well: r for r in rows if r.plate == plate}


def test_capacity():
    assert capacity(avoid_edges=False) == 26
    assert capacity(avoid_edges=True) == 12


def test_n_plates():
    assert n_plates(26, avoid_edges=False) == 1
    assert n_plates(27, avoid_edges=False) == 2
    assert n_plates(130, avoid_edges=False) == 5


def test_full_mode_standards_and_samples():
    rows = build_layout(_samples(27), avoid_edges=False)
    wells = _by_well(rows, plate=1)

    assert wells["A1"].conc_ugml == 2000.0 and wells["A2"].conc_ugml == 2000.0
    assert wells["A11"].conc_ugml == 250.0 and wells["A12"].conc_ugml == 250.0
    assert wells["B1"].conc_ugml == 125.0
    assert wells["B3"].conc_ugml == 25.0
    assert wells["B5"].role == "blank" and wells["B5"].short_id == "BLK"

    assert wells["B7"].short_id == "S1"
    assert wells["B8"].short_id == "S1"
    assert wells["B9"].short_id == "S1"
    assert wells["B10"].short_id == "S2"
    assert wells["C1"].short_id == "S3"

    plate2 = _by_well(rows, plate=2)
    assert plate2["A1"].role == "standard"
    assert plate2["B7"].short_id == "S27"


def test_edge_mode_standards_and_samples():
    rows = build_layout(_samples(12), avoid_edges=True)
    wells = _by_well(rows, plate=1)

    assert wells["B2"].conc_ugml == 2000.0
    assert wells["C9"].role == "blank"
    assert "C10" not in wells
    assert "C11" not in wells

    assert wells["D2"].short_id == "S1"
    assert wells["D3"].short_id == "S1"
    assert wells["D4"].short_id == "S1"


def test_standard_labels_and_roles():
    rows = build_layout(_samples(1), avoid_edges=False)
    wells = _by_well(rows, plate=1)
    assert wells["A1"].role == "standard"
    assert wells["A1"].short_id == "STD2000"
    assert wells["A1"].label == "BSA 2000 µg/mL"
    assert wells["B5"].label == "Blank"
    assert wells["B5"].conc_ugml == 0.0
    assert wells["A1"].sample_name is None
    assert wells["A1"].dilution_factor is None


def test_sample_fields():
    rows = build_layout(_samples(1), avoid_edges=False)
    sample_rows = [r for r in rows if r.role == "sample"]
    assert len(sample_rows) == 3
    for r in sample_rows:
        assert r.conc_ugml is None
        assert r.sample_name == "S1"
        assert r.dilution_factor == 1.0
    assert [r.replicate for r in sample_rows] == [1, 2, 3]


def test_multichannel_capacity_and_n_plates():
    assert capacity(multichannel=True) == 24
    assert n_plates(60, multichannel=True) == 3
    assert n_plates(24, multichannel=True) == 1
    assert n_plates(25, multichannel=True) == 2


def test_multichannel_avoid_edges_errors():
    with pytest.raises(PlatemapError):
        capacity(avoid_edges=True, multichannel=True)
    with pytest.raises(PlatemapError):
        build_layout(_samples(1), avoid_edges=True, multichannel=True)


def test_multichannel_standards_and_blank():
    rows = build_layout(_samples(1), multichannel=True)
    by_well = _by_well(rows, plate=1)
    assert by_well["A1"].role == "standard" and by_well["A1"].conc_ugml == 2000.0
    assert by_well["A1"].replicate == 1
    assert by_well["A2"].role == "standard" and by_well["A2"].conc_ugml == 2000.0
    assert by_well["A2"].replicate == 2
    assert by_well["H1"].conc_ugml == 25.0
    for row_letter in "ABCDEFGH":
        assert by_well[f"{row_letter}3"].role == "blank"
        assert by_well[f"{row_letter}3"].short_id == "BLK"


def test_multichannel_sample_placement_60_samples():
    rows = build_layout(_samples(60), multichannel=True)
    by_plate_well = {(r.plate, r.well): r for r in rows}

    assert by_plate_well[(1, "A4")].short_id == "S1"
    assert by_plate_well[(1, "A5")].short_id == "S1"
    assert by_plate_well[(1, "A6")].short_id == "S1"
    assert by_plate_well[(1, "A7")].short_id == "S9"
    assert by_plate_well[(1, "A8")].short_id == "S9"
    assert by_plate_well[(1, "A9")].short_id == "S9"
    assert by_plate_well[(2, "A4")].short_id == "S25"

    plates = {r.plate for r in rows}
    assert plates == {1, 2, 3}


def test_8ch_replicates2_capacity_is_32():
    assert capacity(channels=8, replicates=2) == 32


def test_row_wise_replicates2_capacity():
    # standards: 9 groups x 2 wells = 18 wells; then groups of 2 samples fit per row.
    cap = capacity(replicates=2)
    assert cap == 39


def test_12ch_capacity_and_n_plates():
    assert capacity(channels=12, replicates=2) == 36
    assert capacity(channels=12, replicates=3) == 24
    assert n_plates(60, channels=12, replicates=2) == 2


def test_12ch_avoid_edges_errors():
    with pytest.raises(PlatemapError):
        capacity(avoid_edges=True, channels=12)
    with pytest.raises(PlatemapError):
        build_layout(_samples(1), avoid_edges=True, channels=12)


def test_12ch_replicates2_60_samples():
    rows = build_layout(_samples(60), channels=12, replicates=2)
    plates = sorted({r.plate for r in rows})
    assert plates == [1, 2]

    def _n_sample_wells(plate):
        return len([r for r in rows if r.plate == plate and r.role == "sample"])

    assert _n_sample_wells(1) == 72  # 36 samples x 2 wells
    assert _n_sample_wells(2) == 48  # 24 samples x 2 wells

    by = {(r.plate, r.well): r for r in rows}

    # standards in both rows A and B on both plates
    for plate in plates:
        assert by[(plate, "A1")].role == "standard" and by[(plate, "A1")].conc_ugml == 2000.0
        assert by[(plate, "A8")].conc_ugml == 25.0
        assert by[(plate, "B1")].role == "standard" and by[(plate, "B1")].conc_ugml == 2000.0

    # 8 blank wells per plate
    for plate in plates:
        n_blanks = len({r.well for r in rows if r.plate == plate and r.role == "blank"})
        assert n_blanks == 8
    assert by[(1, "A9")].role == "blank"
    assert by[(1, "A12")].role == "blank"
    assert by[(1, "B9")].role == "blank"
    assert by[(1, "B12")].role == "blank"

    # S1 at dil C1 and assay C1+D1 (dilution-side placement is dilution.py's job;
    # here we check the assay layout replication).
    assert by[(1, "C1")].short_id == "S1" and by[(1, "D1")].short_id == "S1"
    assert by[(1, "C12")].short_id == "S12" and by[(1, "D12")].short_id == "S12"
    assert by[(1, "E1")].short_id == "S13" and by[(1, "F1")].short_id == "S13"

    # S37 on assay plate 2 at C1+D1 (from dil row F)
    assert by[(2, "C1")].short_id == "S37" and by[(2, "D1")].short_id == "S37"

    # S60 at plate 2 E12+F12
    assert by[(2, "E12")].short_id == "S60" and by[(2, "F12")].short_id == "S60"

    # plate 2 rows G-H empty
    assert (2, "G1") not in by
    assert (2, "H1") not in by

    # each sample exactly 2 wells
    from collections import Counter

    sample_counts = Counter(r.short_id for r in rows if r.role == "sample")
    assert all(c == 2 for c in sample_counts.values())
    assert len(sample_counts) == 60
