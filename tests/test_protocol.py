from platemap.dilution import build_dilution_layout, make_plan, standard_prep_warnings
from platemap.layout import build_layout
from platemap.protocol import build_protocol, write_protocol_md, write_protocol_pdf
from platemap.samples import Sample


def _samples(n):
    return [Sample(sample_name=f"Samp{i}") for i in range(1, n + 1)]


def test_build_protocol_layout_only_row_wise(tmp_path):
    samples = _samples(5)
    rows = build_layout(samples, avoid_edges=False)
    doc = build_protocol(
        experiment="Exp1",
        date="2026-01-01",
        samples=samples,
        layout_rows=rows,
        file_names={"plate_map_pdf": "platemap_platemap.pdf", "workbook": "platemap_plates.xlsx"},
    )
    md_path = tmp_path / "protocol.md"
    pdf_path = tmp_path / "protocol.pdf"
    write_protocol_md(doc, str(md_path))
    n_pages = write_protocol_pdf(doc, str(pdf_path))

    assert md_path.exists()
    assert pdf_path.exists()
    assert n_pages >= 1
    text = md_path.read_text(encoding="utf-8")
    assert "row-wise" in text
    assert "Samples | 5" in text


def test_build_protocol_dilute_row_wise_wr_volume(tmp_path):
    samples = _samples(2)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan)
    rows = build_layout(samples, avoid_edges=False)
    doc = build_protocol(
        experiment="Exp1",
        date="2026-01-01",
        samples=samples,
        layout_rows=rows,
        plan=plan,
        dilution_wells=wells,
        n_assay_plates=1,
        standards_warnings=standard_prep_warnings(1),
        file_names={"prefix": "demo", "workbook": "demo_plates.xlsx"},
    )
    md_path = tmp_path / "protocol.md"
    write_protocol_md(doc, str(md_path))
    text = md_path.read_text(encoding="utf-8")

    n_wells = len(rows)
    expected_wr_ul = n_wells * 200 * 1.10
    assert f"{expected_wr_ul:.0f} µL total" in text


def test_build_protocol_multichannel_transfer_lines(tmp_path):
    samples = _samples(60)
    plan = make_plan()
    wells = build_dilution_layout(samples, plan, multichannel=True)
    rows = build_layout(samples, multichannel=True)
    doc = build_protocol(
        experiment="MC",
        date="2026-01-01",
        samples=samples,
        layout_rows=rows,
        multichannel=True,
        plan=plan,
        dilution_wells=wells,
        n_assay_plates=3,
        standards_warnings=standard_prep_warnings(3),
        file_names={"prefix": "mc", "workbook": "mc_plates.xlsx"},
    )
    md_path = tmp_path / "protocol.md"
    pdf_path = tmp_path / "protocol.pdf"
    write_protocol_md(doc, str(md_path))
    n_pages = write_protocol_pdf(doc, str(pdf_path))
    assert n_pages >= 1

    text = md_path.read_text(encoding="utf-8")
    assert "dilution plate 1 col 7 (S25-S32) -> assay col(s) 4, 5, 6" in text
    assert "8-channel column-wise" in text


def test_build_protocol_multichannel_layout_only(tmp_path):
    samples = _samples(60)
    rows = build_layout(samples, multichannel=True)
    doc = build_protocol(
        experiment="MC layout-only",
        date="2026-01-01",
        samples=samples,
        layout_rows=rows,
        multichannel=True,
        n_assay_plates=3,
        file_names={"prefix": "mc", "workbook": "mc_plates.xlsx"},
    )
    md_path = tmp_path / "protocol.md"
    pdf_path = tmp_path / "protocol.pdf"
    write_protocol_md(doc, str(md_path))
    n_pages = write_protocol_pdf(doc, str(pdf_path))
    assert n_pages >= 1
    assert md_path.exists()


def test_build_protocol_12ch_wr_only_blank_cols(tmp_path):
    samples = _samples(60)
    plan = make_plan(factor=5, final_volume_ul=100)
    wells = build_dilution_layout(samples, plan, channels=12, wr_only_blank_cols=2)
    rows = build_layout(samples, channels=12, replicates=2, wr_only_blank_cols=2)
    doc = build_protocol(
        experiment="WR",
        date="2026-01-01",
        samples=samples,
        layout_rows=rows,
        multichannel=True,
        channels=12,
        replicates=2,
        plan=plan,
        dilution_wells=wells,
        n_assay_plates=2,
        standards_warnings=standard_prep_warnings(2),
        file_names={"prefix": "wr", "workbook": "wr_plates.xlsx"},
    )
    md_path = tmp_path / "protocol.md"
    pdf_path = tmp_path / "protocol.pdf"
    write_protocol_md(doc, str(md_path))
    n_pages = write_protocol_pdf(doc, str(pdf_path))
    assert n_pages >= 1

    text = md_path.read_text(encoding="utf-8")
    assert "WR-only wells (A11, A12, B11, B12)" in text
    assert "buffer blank wells (A9, A10, B9, B10)" in text
    assert "you may remove tips 11–12 for this transfer" in text
    assert "including the WR-only wells A11, A12, B11, B12" in text
    assert "imidazole" in text
    assert "At dilution factor 5, a sample buffer with 250 mM imidazole gives 50 mM" in text
    assert "At dilution factor 5, a sample buffer with 300 mM imidazole gives 60 mM" in text
    assert "above the tolerated limit" in text
    assert "wr_blank_qc.csv" in text and "<prefix>" not in text


def test_build_protocol_no_wr_only_matches_baseline_wording(tmp_path):
    samples = _samples(60)
    plan = make_plan(factor=5, final_volume_ul=100)
    wells = build_dilution_layout(samples, plan, channels=12, wr_only_blank_cols=0)
    rows = build_layout(samples, channels=12, replicates=2, wr_only_blank_cols=0)
    doc = build_protocol(
        experiment="NoWR",
        date="2026-01-01",
        samples=samples,
        layout_rows=rows,
        multichannel=True,
        channels=12,
        replicates=2,
        plan=plan,
        dilution_wells=wells,
        n_assay_plates=2,
        standards_warnings=standard_prep_warnings(2),
        file_names={"prefix": "nowr", "workbook": "nowr_plates.xlsx"},
    )
    md_path = tmp_path / "protocol.md"
    write_protocol_md(doc, str(md_path))
    text = md_path.read_text(encoding="utf-8")

    assert "The blank must be diluent + Working Reagent, not Working Reagent alone." in text
    assert "WR-only wells" not in text
    assert "remove tips" not in text


def test_pdf_text_renders_code_spans_in_courier():
    from platemap.protocol import _pdf_text

    out = _pdf_text("run `platemap read a.xlsx` & check")
    assert out == 'run <font name="Courier">platemap read a.xlsx</font> &amp; check'
    assert _pdf_text("`x` & y", markup=False) == "x & y"
