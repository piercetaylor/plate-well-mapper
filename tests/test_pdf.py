from platemap.layout import build_layout
from platemap.pdf import write_pdf
from platemap.samples import Sample


def _samples(n):
    return [Sample(sample_name=f"Samp{i}") for i in range(1, n + 1)]


def test_write_pdf_page_count(tmp_path):
    rows = build_layout(_samples(1), avoid_edges=False)
    path = tmp_path / "out.pdf"
    n_pages = write_pdf(rows, str(path), experiment="Exp1", date="2026-01-01")
    assert n_pages == 1
    assert path.exists()
    assert path.stat().st_size > 0


def test_write_pdf_multi_page(tmp_path):
    rows = build_layout(_samples(9 * 26), avoid_edges=False)
    path = tmp_path / "out.pdf"
    n_pages = write_pdf(rows, str(path))
    assert n_pages == 3
