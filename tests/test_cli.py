from pathlib import Path

import pytest

from platemap.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _write_samples(tmp_path, n=2):
    path = tmp_path / "samples.csv"
    lines = ["sample_name"] + [f"Samp{i}" for i in range(1, n + 1)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_layout_writes_files_and_prints_summary(tmp_path, capsys):
    samples_path = _write_samples(tmp_path, n=2)
    outdir = tmp_path / "out"
    rc = main(["layout", samples_path, "-o", str(outdir)])
    assert rc == 0

    assert (outdir / "platemap_layout.csv").exists()
    assert (outdir / "platemap_plates.xlsx").exists()
    assert (outdir / "platemap_platemap.pdf").exists()

    out = capsys.readouterr().out
    assert "samples=2" in out
    assert "capacity=26" in out


def test_layout_duplicate_sample_returns_2(tmp_path, capsys):
    path = tmp_path / "samples.csv"
    path.write_text("sample_name\nAlpha\nAlpha\n", encoding="utf-8")
    rc = main(["layout", str(path), "-o", str(tmp_path / "out")])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")


def test_main_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_layout_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["layout", "-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_read_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["read", "-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_notebook_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["notebook", "-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_analyze_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_read_writes_filled_and_mapped(tmp_path, capsys):
    samples_path = _write_samples(tmp_path, n=1)
    outdir = tmp_path / "out"
    main(["layout", samples_path, "-o", str(outdir)])
    workbook = outdir / "platemap_plates.xlsx"

    reader = FIXTURES / "gen5_example.csv"
    rc = main(["read", str(workbook), str(reader), "-o", str(outdir / "filled.xlsx")])
    assert rc == 0

    filled = outdir / "filled.xlsx"
    mapped_csv = outdir / "platemap_plates_mapped.csv"
    assert filled.exists()
    assert mapped_csv.exists()

    import csv

    with open(mapped_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    b7 = next(r for r in rows if r["well"] == "B7")
    assert b7["absorbance"] == "0.207"


def test_read_real_gen5_format_end_to_end(tmp_path, capsys):
    samples_path = _write_samples(tmp_path, n=52)
    outdir = tmp_path / "out"
    main(["layout", samples_path, "-o", str(outdir)])
    workbook = outdir / "platemap_plates.xlsx"

    reader = FIXTURES / "gen5_real_format.txt"
    rc = main(
        ["read", str(workbook), str(reader), "--plate", "2", "-o", str(outdir / "filled.xlsx")]
    )
    assert rc == 0

    mapped_csv = outdir / "platemap_plates_mapped.csv"
    gen5_reads_csv = outdir / "platemap_plates_gen5_reads.csv"
    assert gen5_reads_csv.exists()

    import csv

    with open(mapped_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    b7 = next(r for r in rows if r["well"] == "B7" and r["plate"] == "2")
    assert float(b7["absorbance"]) == pytest.approx(0.4)

    with open(gen5_reads_csv, newline="", encoding="utf-8") as fh:
        gen5_rows = list(csv.DictReader(fh))
    labels = {r["read_label"] for r in gen5_rows}
    assert labels == {"Read 562nm:562", "Blank Read 562nm:562"}
    b7_blank = next(
        r for r in gen5_rows if r["well"] == "B7" and r["read_label"] == "Blank Read 562nm:562"
    )
    assert b7_blank["gen5_well_id"] == "SPL1"
    assert b7_blank["plate_number"] == "Plate 2"


def _write_analyze_mapped_csv(path, blank_abs=0.1):
    import csv

    concs = [2000, 1500, 1000, 750, 500, 250, 125, 25]
    rows = []
    for conc in concs:
        for rep in (1, 2):
            rows.append(
                dict(
                    plate=1,
                    well=f"A{rep}",
                    role="standard",
                    short_id=f"STD{conc}",
                    label=f"STD{conc}",
                    conc_ugml=float(conc),
                    sample_name="",
                    dilution_factor="",
                    replicate=rep,
                    absorbance=0.6 + 0.001 * conc,
                )
            )
    for rep in (1, 2):
        rows.append(
            dict(
                plate=1,
                well=f"B{rep}",
                role="blank",
                short_id="BLK",
                label="Blank",
                conc_ugml=0.0,
                sample_name="",
                dilution_factor="",
                replicate=rep,
                absorbance=blank_abs,
            )
        )
    true_conc = 250.0
    for rep in (1, 2, 3):
        rows.append(
            dict(
                plate=1,
                well=f"C{rep}",
                role="sample",
                short_id="S1",
                label="Sample1",
                conc_ugml="",
                sample_name="Sample1",
                dilution_factor=1.0,
                replicate=rep,
                absorbance=0.6 + 0.001 * true_conc,
            )
        )
    columns = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return true_conc


def test_analyze_include_blank_vs_no_blank_in_fit(tmp_path):
    import csv

    mapped_csv = tmp_path / "demo_plates_mapped.csv"
    true_conc = _write_analyze_mapped_csv(mapped_csv, blank_abs=0.1)

    outdir_with = tmp_path / "with_blank"
    rc = main(["analyze", str(mapped_csv), "--model", "linear", "-o", str(outdir_with)])
    assert rc == 0
    with open(outdir_with / "demo_results.csv", newline="", encoding="utf-8") as fh:
        row_with = next(csv.DictReader(fh))
    err_with = abs(float(row_with["mean"]) - true_conc) / true_conc

    outdir_without = tmp_path / "without_blank"
    rc = main(
        [
            "analyze",
            str(mapped_csv),
            "--model",
            "linear",
            "--no-blank-in-fit",
            "-o",
            str(outdir_without),
        ]
    )
    assert rc == 0
    with open(outdir_without / "demo_results.csv", newline="", encoding="utf-8") as fh:
        row_without = next(csv.DictReader(fh))
    err_without = abs(float(row_without["mean"]) - true_conc) / true_conc

    assert err_without < 0.02
    assert err_with >= 0.02

    assert (outdir_without / "demo_results_wells.csv").exists()
    assert (outdir_without / "demo_curve_fits.csv").exists()
    assert (outdir_without / "demo_standard_curves.pdf").exists()


def test_read_plate_number_mismatch_is_error(tmp_path, capsys):
    samples_path = _write_samples(tmp_path, n=52)
    outdir = tmp_path / "out"
    main(["layout", samples_path, "-o", str(outdir)])
    workbook = outdir / "platemap_plates.xlsx"

    reader = FIXTURES / "gen5_real_format.txt"
    rc = main(
        ["read", str(workbook), str(reader), "--plate", "1", "-o", str(outdir / "filled.xlsx")]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "Plate Number" in err
    assert "Plate 2" in err


def test_read_no_layout_check_skips_plate_number_check(tmp_path):
    samples_path = _write_samples(tmp_path, n=52)
    outdir = tmp_path / "out"
    main(["layout", samples_path, "-o", str(outdir)])
    workbook = outdir / "platemap_plates.xlsx"

    reader = FIXTURES / "gen5_real_format.txt"
    rc = main(
        [
            "read",
            str(workbook),
            str(reader),
            "--plate",
            "1",
            "--no-layout-check",
            "-o",
            str(outdir / "filled.xlsx"),
        ]
    )
    assert rc == 0


def test_notebook_writes_file(tmp_path):
    out_path = tmp_path / "analysis.ipynb"
    rc = main(["notebook", "-o", str(out_path)])
    assert rc == 0
    assert out_path.exists()


def test_notebook_no_blank_in_fit_sets_parameter(tmp_path):
    out_path = tmp_path / "analysis.ipynb"
    rc = main(["notebook", "-o", str(out_path), "--no-blank-in-fit"])
    assert rc == 0

    import nbformat

    nb = nbformat.read(str(out_path), as_version=4)
    param_cells = [c for c in nb.cells if c.metadata.get("tags") == ["parameters"]]
    assert "INCLUDE_BLANK_IN_FIT = False" in param_cells[0].source


def test_dilute_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["dilute", "-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_dilute_writes_files_and_prints_summary(tmp_path, capsys):
    samples_path = _write_samples(tmp_path, n=2)
    outdir = tmp_path / "out"
    rc = main(["dilute", samples_path, "-o", str(outdir), "--prefix", "demo"])
    assert rc == 0

    expected = [
        "demo_samples_diluted.csv",
        "demo_dilution.csv",
        "demo_dilution.pdf",
        "demo_layout.csv",
        "demo_plates.xlsx",
        "demo_platemap.pdf",
        "demo_bca_analysis.ipynb",
    ]
    for name in expected:
        assert (outdir / name).exists(), name

    out = capsys.readouterr().out
    assert "samples=2 factor=20 sample_ul=10 diluent_ul=190" in out
    assert "dilution_plates=1" in out
    assert "assay_plates=1" in out


def test_dilute_warns_on_low_remaining_standard_volume(tmp_path, capsys):
    # 105 samples -> ceil(105/26) = 5 assay plates -> need 125 uL/well, several
    # standard wells only have 100 uL remaining after the serial dilution.
    samples_path = _write_samples(tmp_path, n=105)
    outdir = tmp_path / "out"
    rc = main(["dilute", samples_path, "-o", str(outdir), "--prefix", "demo"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "assay_plates=5" in out
    assert "WARNING: STD1500" in out


def test_dilute_layout_sheet_has_diluted_dilution_factor(tmp_path):
    from platemap.excel import read_layout

    samples_path = _write_samples(tmp_path, n=2)
    outdir = tmp_path / "out"
    main(["dilute", samples_path, "-o", str(outdir), "--prefix", "demo"])

    rows = read_layout(outdir / "demo_plates.xlsx")
    sample_row = next(r for r in rows if r.role == "sample")
    assert sample_row.dilution_factor == 20.0
