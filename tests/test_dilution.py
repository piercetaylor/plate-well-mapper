import csv

import pytest

from platemap.dilution import (
    PLATE1_SAMPLE_CAPACITY,
    apply_dilution,
    build_dilution_layout,
    dilution_plate_count,
    make_plan,
    standard_prep_warnings,
    standard_remaining_ul,
    stock_volume_ul,
    write_dilution_csv,
    write_samples_csv,
)
from platemap.layout import build_layout
from platemap.pdf import write_dilution_pdf
from platemap.samples import PlatemapError, Sample


def _samples(n):
    return [Sample(sample_name=f"Samp{i}") for i in range(1, n + 1)]


def test_make_plan_default():
    plan = make_plan(factor=20, final_volume_ul=200)
    assert plan.sample_volume_ul == 10
    assert plan.diluent_volume_ul == 190


def test_make_plan_factor_must_exceed_1():
    with pytest.raises(PlatemapError):
        make_plan(factor=1, final_volume_ul=200)


def test_make_plan_final_volume_must_be_positive():
    with pytest.raises(PlatemapError):
        make_plan(factor=20, final_volume_ul=0)


def test_make_plan_tiny_sample_volume_errors():
    # factor 200 -> sample volume 1 uL, below the 2 uL floor
    with pytest.raises(PlatemapError):
        make_plan(factor=200, final_volume_ul=200)


def test_make_plan_final_volume_over_capacity_errors():
    with pytest.raises(PlatemapError):
        make_plan(factor=20, final_volume_ul=301)


def test_plate1_sample_capacity_is_78():
    # 96 wells - 9 standard/blank groups x 2 replicate wells = 78
    assert PLATE1_SAMPLE_CAPACITY == 78


def test_standard_remaining_ul_matches_scheme():
    expected = {
        2000: 200.0,
        1500: 100.0,
        1000: 100.0,
        750: 200.0,
        500: 100.0,
        250: 100.0,
        125: 160.0,
        25: 200.0,
        0: 200.0,
    }
    for conc, remaining in expected.items():
        assert standard_remaining_ul(conc) == remaining


def test_stock_volume_ul_is_900():
    assert stock_volume_ul() == 900


def test_dilution_plate_count():
    assert dilution_plate_count(65) == 1
    assert dilution_plate_count(78) == 1
    assert dilution_plate_count(79) == 2
    assert dilution_plate_count(78 + 96) == 2
    assert dilution_plate_count(78 + 96 + 1) == 3


def test_build_dilution_layout_65_samples_plate1_samples_start_at_b7():
    samples = _samples(65)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    sample_wells = [w for w in wells if w.role == "sample"]

    assert {w.plate for w in wells} == {1}
    assert sample_wells[0].well == "B7"
    # samples 1-6 -> B7-B12, 7-18 -> row C, 19-30 -> D, 31-42 -> E, 43-54 -> F, 55-66 -> G
    assert sample_wells[64].well == "G11"  # 65th sample


def test_build_dilution_layout_79_samples_two_plates_plate2_starts_a1():
    samples = _samples(79)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    sample_wells = [w for w in wells if w.role == "sample"]

    plate2 = [w for w in sample_wells if w.plate == 2]
    assert plate2[0].well == "A1"
    assert {w.plate for w in wells} == {1, 2}
    # 78th sample is the last of plate 1, 79th is the first of plate 2
    assert sample_wells[77].plate == 1
    assert sample_wells[78].plate == 2


def test_build_dilution_layout_standards_mirror_assay_positions():
    samples = _samples(5)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    by_well = {w.well: w for w in wells}

    assert by_well["A1"].role == "standard" and by_well["A1"].conc_ugml == 2000
    assert by_well["A2"].role == "standard" and by_well["A2"].conc_ugml == 2000
    assert by_well["A3"].conc_ugml == 1500
    assert by_well["A5"].conc_ugml == 1000
    assert by_well["A7"].conc_ugml == 750
    assert by_well["A9"].conc_ugml == 500
    assert by_well["A11"].conc_ugml == 250
    assert by_well["B1"].conc_ugml == 125
    assert by_well["B3"].conc_ugml == 25
    assert by_well["B5"].role == "blank" and by_well["B6"].role == "blank"


def test_build_dilution_layout_source_tracks_same_replicate():
    samples = _samples(1)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    by_well = {w.well: w for w in wells}

    # 750 (A7/A8) is drawn from the 1500 wells (A3/A4), same replicate.
    assert by_well["A7"].source == "A3"
    assert by_well["A8"].source == "A4"
    # 2000/1500/1000 come from stock.
    assert by_well["A1"].source == "BSA stock"
    assert by_well["B5"].source == "diluent"


def test_short_id_matches_build_layout_short_id():
    samples = _samples(30)
    plan = make_plan()
    dilution_wells = build_dilution_layout(samples, plan)
    dilution_ids = {w.label: w.short_id for w in dilution_wells if w.role == "sample"}

    layout_rows = build_layout(samples, avoid_edges=False)
    layout_ids = {r.sample_name: r.short_id for r in layout_rows if r.role == "sample"}

    assert dilution_ids == layout_ids


def test_apply_dilution_multiplies_existing_factor():
    samples = [Sample(sample_name="A", dilution_factor=2.0, notes="n")]
    diluted = apply_dilution(samples, 20)
    assert diluted[0].dilution_factor == 40.0
    assert diluted[0].notes == "n"
    assert diluted[0].sample_name == "A"


def test_write_samples_csv(tmp_path):
    samples = apply_dilution(_samples(2), 20)
    path = tmp_path / "samples.csv"
    write_samples_csv(samples, str(path))
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["dilution_factor"] == "20"


def test_write_dilution_csv_includes_standards_and_samples(tmp_path):
    samples = _samples(2)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    path = tmp_path / "dilution.csv"
    write_dilution_csv(wells, str(path))
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["well"] == "A1"
    assert rows[0]["role"] == "standard"
    assert rows[0]["source"] == "BSA stock"
    sample_row = next(r for r in rows if r["role"] == "sample")
    assert sample_row["source_ul"] == "10.0"


def test_standard_prep_warnings_none_at_3_assay_plates():
    assert standard_prep_warnings(3) == []


def test_standard_prep_warnings_at_5_assay_plates():
    warnings = standard_prep_warnings(5)
    ids = {w.split()[0] for w in warnings}
    assert ids == {"STD1500", "STD1000", "STD500", "STD250"}


def test_write_dilution_pdf_page_count_one_plate(tmp_path):
    samples = _samples(65)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    path = tmp_path / "dilution.pdf"
    n_pages = write_dilution_pdf(
        wells, plan, str(path), n_assay_plates=3, experiment="Exp1", date="2026-01-01"
    )
    assert n_pages == 1
    assert path.exists()


def test_write_dilution_pdf_page_count_two_plates(tmp_path):
    samples = _samples(97)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    path = tmp_path / "dilution.pdf"
    n_pages = write_dilution_pdf(wells, plan, str(path), n_assay_plates=4)
    assert n_pages == 2


def test_write_dilution_pdf_with_low_remaining_warnings(tmp_path):
    # 105 samples -> 5 assay plates -> standard_prep_warnings(5) is non-empty.
    samples = _samples(105)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    path = tmp_path / "dilution.pdf"
    n_pages = write_dilution_pdf(wells, plan, str(path), n_assay_plates=5)
    assert n_pages == 2
    assert path.exists()
