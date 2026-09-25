from platemap.layout import build_layout, capacity, n_plates
from platemap.samples import Sample


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
