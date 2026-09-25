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


def test_notebook_writes_file(tmp_path):
    out_path = tmp_path / "analysis.ipynb"
    rc = main(["notebook", "-o", str(out_path)])
    assert rc == 0
    assert out_path.exists()


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
