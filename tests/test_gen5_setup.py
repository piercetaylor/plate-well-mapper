from pathlib import Path

from platemap.gen5 import check_gen5_layout
from platemap.gen5_setup import (
    gen5_assignments,
    gen5_protocol_layout,
    replicate_orientation,
    write_gen5_layout_csv,
    write_gen5_sample_ids,
    write_gen5_setup_pdf,
)
from platemap.layout import build_layout, read_layout_csv, write_layout_csv
from platemap.samples import Sample


def _samples(n):
    return [Sample(sample_name=f"S{i}") for i in range(1, n + 1)]


def _by_plate_well(assignments):
    return {(a["plate"], a["well"]): a for a in assignments}


def _rows_12ch_60():
    return build_layout(_samples(60), channels=12, replicates=2)


def _rows_12ch_60_wr2():
    return build_layout(_samples(60), channels=12, replicates=2, wr_only_blank_cols=2)


def test_gen5_assignments_standards_and_blanks():
    rows = _rows_12ch_60()
    a = _by_plate_well(gen5_assignments(rows))

    assert a[(1, "A1")]["gen5_type"] == "Standard"
    assert a[(1, "A1")]["gen5_id"] == "BCA:1"
    assert a[(1, "A1")]["conc"] == 2000.0

    assert a[(1, "A8")]["gen5_id"] == "BCA:8"
    assert a[(1, "A8")]["conc"] == 25.0

    assert a[(1, "B1")]["gen5_id"] == "BCA:1"

    for well in ("A9", "A10", "A11", "A12", "B9", "B10", "B11", "B12"):
        assert a[(1, well)]["gen5_type"] == "Blank"
        assert a[(1, well)]["gen5_id"] == "BLK"


def test_gen5_assignments_samples_plate1():
    rows = _rows_12ch_60()
    a = _by_plate_well(gen5_assignments(rows))

    assert a[(1, "C1")]["gen5_id"] == "SPL1"
    assert a[(1, "D1")]["gen5_id"] == "SPL1"
    assert a[(1, "C12")]["gen5_id"] == "SPL12"
    assert a[(1, "E1")]["gen5_id"] == "SPL13"
    assert a[(1, "F1")]["gen5_id"] == "SPL13"
    assert a[(1, "H12")]["gen5_id"] == "SPL36"


def test_gen5_assignments_samples_plate2_restarts_at_spl1():
    rows = _rows_12ch_60()
    a = _by_plate_well(gen5_assignments(rows))

    entry = a[(2, "C1")]
    assert entry["gen5_id"] == "SPL1"
    assert entry["short_id"] == "S37"
    assert entry["sample_name"] == "S37"


def test_replicate_orientation_vertical_12ch():
    rows = _rows_12ch_60()
    sample_rows = [r for r in rows if r.role == "sample"]
    standard_rows = [r for r in rows if r.role == "standard"]
    assert replicate_orientation(sample_rows) == "vertical"
    assert replicate_orientation(standard_rows) == "vertical"


def test_replicate_orientation_horizontal_row_wise_triplicate():
    rows = build_layout(_samples(27), avoid_edges=False, replicates=3)
    sample_rows = [r for r in rows if r.role == "sample"]
    standard_rows = [r for r in rows if r.role == "standard"]
    assert replicate_orientation(sample_rows) == "horizontal"
    assert replicate_orientation(standard_rows) == "horizontal"


def test_gen5_protocol_layout_has_36_spl_and_uses_plate1():
    rows = _rows_12ch_60()
    protocol = gen5_protocol_layout(rows)
    assert all(a["plate"] == 1 for a in protocol)
    spl_ids = {a["gen5_id"] for a in protocol if a["gen5_type"] == "Sample"}
    assert len(spl_ids) == 36


def test_gen5_assignments_reagent_blank_is_ctl1():
    rows = _rows_12ch_60_wr2()
    a = _by_plate_well(gen5_assignments(rows))

    for plate in (1, 2):
        for well in ("A11", "A12", "B11", "B12"):
            entry = a[(plate, well)]
            assert entry["gen5_type"] == "Assay Control"
            assert entry["gen5_id"] == "CTL1"
        for well in ("A9", "A10", "B9", "B10"):
            assert a[(plate, well)]["gen5_type"] == "Blank"
            assert a[(plate, well)]["gen5_id"] == "BLK"


def test_gen5_setup_pdf_and_layout_csv_wr_only(tmp_path):
    rows = _rows_12ch_60_wr2()
    pdf_path = tmp_path / "demo_gen5_setup.pdf"
    n_pages = write_gen5_setup_pdf(rows, str(pdf_path), experiment="Exp", date="2026-01-01")
    assert pdf_path.exists()
    assert n_pages == 3

    csv_path = tmp_path / "demo_gen5_layout.csv"
    write_gen5_layout_csv(rows, str(csv_path))
    content = csv_path.read_text(encoding="utf-8")
    assert "Assay Control,CTL1" in content


def test_gen5_setup_from_layout_csv_round_trip_wr_only(tmp_path):
    rows = _rows_12ch_60_wr2()
    csv_path = tmp_path / "demo_layout.csv"
    write_layout_csv(rows, str(csv_path))

    read_rows = read_layout_csv(str(csv_path))
    assert len(read_rows) == len(rows)

    for plate in (1, 2):
        plate_rows = [r for r in read_rows if r.plate == plate]
        layout = {a["well"]: (a["gen5_id"], "" if a["conc"] is None else str(a["conc"]))
                  for a in gen5_assignments(read_rows) if a["plate"] == plate}
        errors, warnings = check_gen5_layout(plate_rows, layout)
        assert errors == []
        assert warnings == []


def test_protocol_missing_wells_plate2():
    from platemap.gen5_setup import _protocol_missing_wells

    rows = _rows_12ch_60()
    missing = _protocol_missing_wells(rows)
    expected = [f"{r}{c}" for r in ("G", "H") for c in range(1, 13)]
    assert missing[2] == expected


def test_round_trip_check_gen5_layout_zero_errors_per_plate():
    rows = _rows_12ch_60()
    assignments = gen5_assignments(rows)
    for plate in (1, 2):
        plate_assignments = [a for a in assignments if a["plate"] == plate]
        layout = {
            a["well"]: (a["gen5_id"], "" if a["conc"] is None else str(int(a["conc"])))
            for a in plate_assignments
        }
        our_rows = [r for r in rows if r.plate == plate]
        errors, warnings = check_gen5_layout(our_rows, layout)
        assert errors == []
        assert warnings == []


def test_round_trip_protocol_layout_on_plate2_only_warnings():
    rows = _rows_12ch_60()
    protocol = gen5_protocol_layout(rows)
    proto_layout = {
        a["well"]: (a["gen5_id"], "" if a["conc"] is None else str(int(a["conc"])))
        for a in protocol
    }
    our_rows = [r for r in rows if r.plate == 2]
    errors, warnings = check_gen5_layout(our_rows, proto_layout)
    assert errors == []
    expected_wells = {f"{r}{c}" for r in ("G", "H") for c in range(1, 13)}
    warned_wells = {w.split(":")[0] for w in warnings}
    assert warned_wells == expected_wells


def test_write_gen5_sample_ids(tmp_path):
    rows = _rows_12ch_60()
    combined, per_plate = write_gen5_sample_ids(rows, tmp_path / "demo")

    with open(combined, "rb") as fh:
        data = fh.read()
    assert b"\r\n" in data
    lines = data.decode("utf-8").split("\r\n")
    lines = lines[:-1] if lines[-1] == "" else lines
    assert len(lines) == 60
    assert lines[36] == "S37"

    for plate, expected_n in ((1, 36), (2, 24)):
        with open(per_plate[plate], "rb") as fh:
            plate_lines = fh.read().decode("utf-8").split("\r\n")
        plate_lines = plate_lines[:-1] if plate_lines[-1] == "" else plate_lines
        assert len(plate_lines) == expected_n


def test_write_gen5_layout_csv(tmp_path):
    rows = _rows_12ch_60()
    path = tmp_path / "demo_gen5_layout.csv"
    write_gen5_layout_csv(rows, str(path))

    import csv

    with open(path, newline="", encoding="utf-8") as fh:
        reader = list(csv.DictReader(fh))
    assert reader[0]["plate"] == "1"
    assert reader[0]["well"] == "A1"
    assert reader[0]["gen5_type"] == "Standard"
    assert reader[0]["gen5_id"] == "BCA:1"
    assert reader[0]["conc_ugml"] == "2000.0"


def test_write_gen5_setup_pdf(tmp_path):
    rows = _rows_12ch_60()
    path = tmp_path / "demo_gen5_setup.pdf"
    n_pages = write_gen5_setup_pdf(rows, str(path), experiment="Exp", date="2026-01-01")
    assert path.exists()
    # page 1 (protocol) + one page per plate (2 plates)
    assert n_pages == 3


def test_gen5_setup_from_layout_csv_round_trip(tmp_path):
    rows = _rows_12ch_60()
    csv_path = tmp_path / "demo_layout.csv"
    write_layout_csv(rows, str(csv_path))

    read_rows = read_layout_csv(str(csv_path))
    assert len(read_rows) == len(rows)
    assert read_rows[0].plate == rows[0].plate
    assert read_rows[0].well == rows[0].well
    assert read_rows[0].conc_ugml == rows[0].conc_ugml
