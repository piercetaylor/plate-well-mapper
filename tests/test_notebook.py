import csv
import math

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

from platemap.notebook import build_notebook, write_notebook


def test_build_notebook_structure():
    nb = build_notebook()
    assert nb.metadata["kernelspec"]["name"] == "python3"
    assert any(c.cell_type == "markdown" for c in nb.cells)
    param_cells = [c for c in nb.cells if c.metadata.get("tags") == ["parameters"]]
    assert len(param_cells) == 1
    assert "MAPPED_CSV" in param_cells[0].source
    for cell in nb.cells:
        if cell.cell_type == "code":
            assert cell.outputs == []
            assert cell.execution_count is None


def test_write_notebook(tmp_path):
    path = tmp_path / "nb.ipynb"
    write_notebook(str(path))
    assert path.exists()
    nb = nbformat.read(str(path), as_version=4)
    assert nb.metadata["kernelspec"]["name"] == "python3"


def test_build_notebook_params_use_given_mapped_csv():
    nb = build_notebook(mapped_csv="demo_plates_mapped.csv", output_csv="demo_bca_results.csv")
    param_cells = [c for c in nb.cells if c.metadata.get("tags") == ["parameters"]]
    assert "demo_plates_mapped.csv" in param_cells[0].source
    assert "demo_bca_results.csv" in param_cells[0].source


def _four_pl(x, a, b, c, d):
    return d + (a - d) / (1 + (x / c) ** b)


def _write_synthetic_mapped_csv(path):
    params = {"a": 0.05, "b": 1.2, "c": 400.0, "d": 2.2}
    concs = [2000, 1500, 1000, 750, 500, 250, 125, 25, 0]
    rows = []
    for conc in concs:
        role = "blank" if conc == 0 else "standard"
        short_id = "BLK" if conc == 0 else f"STD{conc}"
        for rep in (1, 2):
            rows.append(
                dict(
                    plate=1,
                    well=f"A{rep}",
                    role=role,
                    short_id=short_id,
                    label=short_id,
                    conc_ugml=float(conc),
                    sample_name="",
                    dilution_factor="",
                    replicate=rep,
                    absorbance=_four_pl(float(conc), **params),
                )
            )
    for i in range(1, 3):
        true_conc = 300.0 * i
        for rep in (1, 2, 3):
            rows.append(
                dict(
                    plate=1,
                    well=f"B{i}{rep}",
                    role="sample",
                    short_id=f"S{i}",
                    label=f"Sample{i}",
                    conc_ugml="",
                    sample_name=f"Sample{i}",
                    dilution_factor=1.0,
                    replicate=rep,
                    absorbance=_four_pl(true_conc, **params),
                )
            )

    columns = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_notebook_executes(tmp_path):
    mapped_csv = tmp_path / "platemap_mapped.csv"
    _write_synthetic_mapped_csv(mapped_csv)

    nb = build_notebook()
    params_cell = next(c for c in nb.cells if c.metadata.get("tags") == ["parameters"])
    output_csv = tmp_path / "bca_results.csv"
    params_cell.source = (
        f'MAPPED_CSV = {str(mapped_csv)!r}\n'
        'MODEL = "4pl"\n'
        f'OUTPUT_CSV = {str(output_csv)!r}'
    )

    ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
    ep.preprocess(nb, {"metadata": {"path": str(tmp_path)}})

    assert output_csv.exists()
    wells_csv = tmp_path / "bca_results_wells.csv"
    assert wells_csv.exists()
