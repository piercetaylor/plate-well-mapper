"""Build the BCA standard-curve analysis Jupyter notebook."""

import nbformat as nbf


def build_notebook(
    mapped_csv: str = "platemap_plates_mapped.csv",
    output_csv: str = "bca_results.csv",
    include_blank_in_fit: bool = True,
):
    """Build the analysis notebook (nbformat NotebookNode), outputs stripped."""
    nb = nbf.v4.new_notebook()

    title_md = nbf.v4.new_markdown_cell(
        "# BCA Assay Analysis\n\n"
        "Loads a mapped plate CSV (from `platemap read`), fits BSA standard curves per "
        "plate, quantifies sample concentrations, and exports a summary table.\n\n"
        "Concentrations are multiplied by each sample's `dilution_factor` (this includes "
        "any pre-dilution applied by `platemap dilute`, not just assay-time dilution).\n\n"
        "Edit the parameters cell below, then run all cells."
    )

    imports_code = nbf.v4.new_code_cell(
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "import pandas as pd\n\n"
        "from platemap.analysis import (\n"
        "    fit_standards,\n"
        "    invert_4pl,\n"
        "    invert_linear,\n"
        "    load_mapped,\n"
        "    quantify,\n"
        "    subtract_blank,\n"
        "    summarize,\n"
        ")"
    )

    params_code = nbf.v4.new_code_cell(
        f"MAPPED_CSV = {mapped_csv!r}\n"
        'MODEL = "4pl"\n'
        f"OUTPUT_CSV = {output_csv!r}\n"
        f"INCLUDE_BLANK_IN_FIT = {include_blank_in_fit!r}"
    )
    params_code.metadata["tags"] = ["parameters"]

    load_code = nbf.v4.new_code_cell(
        "df = load_mapped(MAPPED_CSV)\n"
        "df = subtract_blank(df)\n"
        "df.head()"
    )

    fit_code = nbf.v4.new_code_cell(
        "fits = fit_standards(df, MODEL, include_blank=INCLUDE_BLANK_IN_FIT)\n"
        "for plate, fit in sorted(fits.items()):\n"
        "    print(f\"plate {plate}: model={fit.model} params={fit.params} r2={fit.r2:.4f}\")"
    )

    plot_code = nbf.v4.new_code_cell(
        "_std_roles = ['standard', 'blank'] if INCLUDE_BLANK_IN_FIT else ['standard']\n"
        "for plate, fit in sorted(fits.items()):\n"
        "    std = df[(df['plate'] == plate) & (df['role'].isin(_std_roles))]\n"
        "    curve = std.groupby('conc_ugml')['abs_blanked'].mean().sort_index()\n"
        "    xs = curve.index.to_numpy(dtype=float)\n"
        "    ys = curve.to_numpy(dtype=float)\n"
        "\n"
        "    fig, ax = plt.subplots()\n"
        "    ax.scatter(xs, ys, label='standards')\n"
        "\n"
        "    x_line = np.linspace(max(xs.min(), 1e-6), xs.max(), 200)\n"
        "    if fit.model == '4pl':\n"
        "        a, b, c, d = fit.params['a'], fit.params['b'], fit.params['c'], fit.params['d']\n"
        "        y_line = d + (a - d) / (1 + (x_line / c) ** b)\n"
        "    else:\n"
        "        y_line = fit.params['slope'] * x_line + fit.params['intercept']\n"
        "    ax.plot(x_line, y_line, label=fit.model)\n"
        "\n"
        "    ax.set_title(f'Plate {plate} standard curve')\n"
        "    ax.set_xlabel('Concentration (ug/mL)')\n"
        "    ax.set_ylabel('Blanked absorbance')\n"
        "    ax.legend()\n"
        "    plt.show()"
    )

    quantify_code = nbf.v4.new_code_cell(
        "df = quantify(df, MODEL, include_blank=INCLUDE_BLANK_IN_FIT)\ndf.head()"
    )

    summary_code = nbf.v4.new_code_cell("summary = summarize(df)\nsummary")

    export_code = nbf.v4.new_code_cell(
        "from pathlib import Path\n\n"
        "out_path = Path(OUTPUT_CSV)\n"
        "wells_path = out_path.with_name(out_path.stem + '_wells' + out_path.suffix)\n\n"
        "summary.to_csv(out_path, index=False)\n"
        "df.to_csv(wells_path, index=False)"
    )

    nb.cells = [
        title_md,
        imports_code,
        params_code,
        load_code,
        fit_code,
        plot_code,
        quantify_code,
        summary_code,
        export_code,
    ]

    for cell in nb.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None

    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    return nb


def write_notebook(
    path: str,
    mapped_csv: str = "platemap_plates_mapped.csv",
    output_csv: str = "bca_results.csv",
    include_blank_in_fit: bool = True,
) -> None:
    """Build and write the analysis notebook to path."""
    nb = build_notebook(
        mapped_csv=mapped_csv, output_csv=output_csv, include_blank_in_fit=include_blank_in_fit
    )
    with open(path, "w", encoding="utf-8") as fh:
        nbf.write(nb, fh)
