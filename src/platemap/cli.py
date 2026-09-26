"""Command-line interface for platemap."""

import argparse
import datetime as dt
import sys
from pathlib import Path

from platemap import __version__
from platemap.samples import PlatemapError, Sample, read_samples


def _valid_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD") from exc
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="platemap",
        description="Generate 96-well plate layouts, Excel maps, and PDF plate maps for BCA assays.",
        epilog=(
            "examples:\n"
            "  platemap layout samples.csv -o out --experiment \"BCA run 1\"\n"
            "  platemap layout samples.csv --avoid-edges\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    layout_p = subparsers.add_parser(
        "layout",
        help="build a plate layout from a sample CSV",
        description="Build a 96-well plate layout (standards + samples) from a sample CSV.",
        epilog=(
            "examples:\n"
            "  platemap layout samples.csv -o out --experiment \"BCA run 1\"\n"
            "  platemap layout samples.csv --avoid-edges\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    layout_p.add_argument("samples", metavar="SAMPLES", help="path to the sample CSV file")
    layout_p.add_argument("-o", "--outdir", default=".", help="output directory (default: .)")
    layout_p.add_argument("--prefix", default="platemap", help="output filename prefix (default: platemap)")
    layout_p.add_argument("--avoid-edges", action="store_true", help="restrict layout to B-G x 2-11")
    layout_p.add_argument("--experiment", default="", help="experiment name for the output sheets/PDF")
    layout_p.add_argument(
        "--date",
        type=_valid_date,
        default=dt.date.today().isoformat(),
        help="experiment date, YYYY-MM-DD (default: today)",
    )

    read_p = subparsers.add_parser(
        "read",
        help="import Gen5 reader CSV(s) into a plate layout workbook",
        description=(
            "Fill the Reader sheets of a platemap workbook with values from one or more "
            "BioTek Gen5 (Cytation5) CSV exports, and write a mapped CSV of results."
        ),
        epilog=(
            "examples:\n"
            "  platemap read platemap_plates.xlsx plate1.csv plate2.csv\n"
            "  platemap read platemap_plates.xlsx plate3.csv --plate 3 --wavelength 562\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    read_p.add_argument("workbook", metavar="WORKBOOK", help="path to the *_plates.xlsx from `platemap layout`")
    read_p.add_argument("readers", metavar="READER", nargs="+", help="one or more Gen5 CSV export files")
    read_p.add_argument("--plate", type=int, default=None, help="plate number for a single reader file")
    read_p.add_argument("--wavelength", default=None, help="wavelength/block label to select within each reader file")
    read_p.add_argument("--read-label", default=None, help="exact Gen5 read label to select within each reader file (e.g. 'Blank Read 562nm:562')")
    read_p.add_argument("-o", "--out", default=None, metavar="OUT.xlsx", help="output workbook path (default: <workbook stem>_filled.xlsx)")
    read_p.add_argument("--no-layout-check", action="store_true", help="skip cross-checking the Gen5 Layout block and Plate Number against our layout")

    dilute_p = subparsers.add_parser(
        "dilute",
        help="build a pre-dilution plate plus the resulting sample layout",
        description=(
            "Build a 96-well pre-dilution plate map from a sample CSV, then build the "
            "usual layout (CSV, workbook, PDF, notebook) from the diluted samples."
        ),
        epilog=(
            "examples:\n"
            "  platemap dilute samples.csv -o out --experiment \"BCA run 1\"\n"
            "  platemap dilute samples.csv --factor 10 --final-volume 250\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    dilute_p.add_argument("samples", metavar="SAMPLES", help="path to the sample CSV file")
    dilute_p.add_argument("--factor", type=float, default=20, help="dilution factor (default: 20)")
    dilute_p.add_argument("--final-volume", type=float, default=200, help="final well volume in µL (default: 200)")
    dilute_p.add_argument("-o", "--outdir", default=".", help="output directory (default: .)")
    dilute_p.add_argument("--prefix", default="platemap", help="output filename prefix (default: platemap)")
    dilute_p.add_argument("--avoid-edges", action="store_true", help="restrict the assay layout to B-G x 2-11")
    dilute_p.add_argument("--experiment", default="", help="experiment name for the output sheets/PDF")
    dilute_p.add_argument(
        "--date",
        type=_valid_date,
        default=dt.date.today().isoformat(),
        help="experiment date, YYYY-MM-DD (default: today)",
    )

    analyze_p = subparsers.add_parser(
        "analyze",
        help="fit standard curves and quantify samples from a mapped CSV",
        description=(
            "Fit BSA standard curves per plate from a mapped CSV (from `platemap read`), "
            "quantify sample concentrations, and write result tables plus a standard-curve PDF."
        ),
        epilog=(
            "examples:\n"
            "  platemap analyze platemap_plates_mapped.csv\n"
            "  platemap analyze platemap_plates_mapped.csv --model linear --no-blank-in-fit\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analyze_p.add_argument("mapped_csv", metavar="MAPPED.csv", help="mapped CSV from `platemap read`")
    analyze_p.add_argument("--model", choices=("4pl", "linear"), default="4pl", help="standard-curve model (default: 4pl)")
    analyze_p.add_argument("--no-blank-in-fit", action="store_true", help="exclude the blank (0 conc) point from the standard-curve fit")
    analyze_p.add_argument("-o", "--outdir", default=None, help="output directory (default: the mapped CSV's folder)")
    analyze_p.add_argument("--prefix", default=None, help="output filename prefix (default: mapped CSV stem with a trailing '_plates_mapped' or '_mapped' removed)")

    notebook_p = subparsers.add_parser(
        "notebook",
        help="write a Jupyter notebook for BCA standard-curve analysis",
        description="Write a Jupyter notebook that loads a mapped CSV, fits standard curves, and quantifies samples.",
        epilog="examples:\n  platemap notebook -o bca_analysis.ipynb\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    notebook_p.add_argument("-o", "--out", default="bca_analysis.ipynb", metavar="PATH", help="output notebook path (default: bca_analysis.ipynb)")
    notebook_p.add_argument(
        "--mapped-csv",
        default="platemap_plates_mapped.csv",
        metavar="NAME",
        help="mapped CSV filename baked into the parameters cell (default: platemap_plates_mapped.csv)",
    )
    notebook_p.add_argument(
        "--no-blank-in-fit",
        action="store_true",
        help="set INCLUDE_BLANK_IN_FIT = False in the parameters cell (exclude the blank point from the standard-curve fit)",
    )

    return parser


def _write_layout_outputs(
    samples: list[Sample], outdir: Path, prefix: str, avoid_edges: bool, experiment: str, date: str
) -> tuple[Path, Path, Path]:
    """Build a layout from samples and write its CSV, workbook, and PDF; return the paths."""
    from platemap.excel import write_excel
    from platemap.layout import build_layout, write_layout_csv
    from platemap.pdf import write_pdf

    rows = build_layout(samples, avoid_edges=avoid_edges)

    csv_path = outdir / f"{prefix}_layout.csv"
    xlsx_path = outdir / f"{prefix}_plates.xlsx"
    pdf_path = outdir / f"{prefix}_platemap.pdf"

    write_layout_csv(rows, str(csv_path))
    write_excel(rows, str(xlsx_path), experiment=experiment, date=date)
    write_pdf(rows, str(pdf_path), experiment=experiment, date=date)

    return csv_path, xlsx_path, pdf_path


def _run_layout(args: argparse.Namespace) -> int:
    from platemap.layout import capacity, n_plates

    samples = read_samples(args.samples)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    csv_path, xlsx_path, pdf_path = _write_layout_outputs(
        samples, outdir, args.prefix, args.avoid_edges, args.experiment, args.date
    )

    n = len(samples)
    plates = n_plates(n, args.avoid_edges)
    cap = capacity(args.avoid_edges)
    print(f"samples={n} plates={plates} capacity={cap}")
    print(csv_path)
    print(xlsx_path)
    print(pdf_path)
    return 0


def _run_dilute(args: argparse.Namespace) -> int:
    from platemap.dilution import (
        apply_dilution,
        build_dilution_layout,
        dilution_plate_count,
        make_plan,
        standard_prep_warnings,
        write_dilution_csv,
        write_samples_csv,
    )
    from platemap.layout import n_plates
    from platemap.pdf import write_dilution_pdf

    samples = read_samples(args.samples)
    plan = make_plan(factor=args.factor, final_volume_ul=args.final_volume)
    diluted = apply_dilution(samples, plan.factor)
    dilution_wells = build_dilution_layout(samples, plan)

    n = len(samples)
    assay_plates = n_plates(n, args.avoid_edges)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    samples_csv_path = outdir / f"{args.prefix}_samples_diluted.csv"
    dilution_csv_path = outdir / f"{args.prefix}_dilution.csv"
    dilution_pdf_path = outdir / f"{args.prefix}_dilution.pdf"

    write_samples_csv(diluted, str(samples_csv_path))
    write_dilution_csv(dilution_wells, str(dilution_csv_path))
    write_dilution_pdf(
        dilution_wells,
        plan,
        str(dilution_pdf_path),
        n_assay_plates=assay_plates,
        experiment=args.experiment,
        date=args.date,
    )

    layout_csv_path, xlsx_path, pdf_path = _write_layout_outputs(
        diluted, outdir, args.prefix, args.avoid_edges, args.experiment, args.date
    )

    notebook_path = outdir / f"{args.prefix}_bca_analysis.ipynb"
    try:
        from platemap.notebook import write_notebook

        write_notebook(
            str(notebook_path),
            mapped_csv=f"{args.prefix}_plates_mapped.csv",
            output_csv=f"{args.prefix}_bca_results.csv",
        )
    except ImportError:
        print("note: notebook extras not installed, skipping analysis notebook")
        notebook_path = None

    dilution_plates = dilution_plate_count(n)
    print(
        f"samples={n} factor={plan.factor:g} sample_ul={plan.sample_volume_ul:g} "
        f"diluent_ul={plan.diluent_volume_ul:g} dilution_plates={dilution_plates} assay_plates={assay_plates}"
    )
    for warning in standard_prep_warnings(assay_plates):
        print(f"WARNING: {warning}")
    print(samples_csv_path)
    print(dilution_csv_path)
    print(dilution_pdf_path)
    print(layout_csv_path)
    print(xlsx_path)
    print(pdf_path)
    if notebook_path is not None:
        print(notebook_path)
    return 0


def _run_read(args: argparse.Namespace) -> int:
    import csv
    import math
    import re

    from platemap.excel import compute_mapped_rows, fill_reader, plate_count, read_layout
    from platemap.gen5 import (
        check_gen5_layout,
        parse_gen5,
        parse_gen5_layout,
        parse_gen5_metadata,
        parse_gen5_reads,
    )

    total_plates = plate_count(args.workbook)

    if args.plate is not None:
        if len(args.readers) != 1:
            raise PlatemapError("--plate requires exactly one reader file")
        if not (1 <= args.plate <= total_plates):
            raise PlatemapError(f"plate {args.plate} out of range (1..{total_plates})")
        plate_files = {args.plate: args.readers[0]}
    else:
        if len(args.readers) > total_plates:
            raise PlatemapError(
                f"more reader files ({len(args.readers)}) than plates ({total_plates})"
            )
        plate_files = {i: f for i, f in enumerate(args.readers, start=1)}

    rows = read_layout(args.workbook)

    plate_values: dict[int, dict[str, float]] = {}
    plate_reads: dict[int, dict[str, dict[str, float]]] = {}
    plate_layouts: dict[int, dict[str, tuple[str, str]]] = {}
    plate_metadata: dict[int, dict[str, str]] = {}

    for plate, f in plate_files.items():
        metadata = parse_gen5_metadata(f)
        plate_metadata[plate] = metadata

        if not args.no_layout_check:
            match = re.fullmatch(r"Plate\s+(\d+)", metadata.get("Plate Number", ""))
            if match and int(match.group(1)) != plate:
                raise PlatemapError(
                    f"{f}: Gen5 'Plate Number' is 'Plate {match.group(1)}' but is being "
                    f"assigned to plate {plate}"
                )

        plate_values[plate] = parse_gen5(
            f, wavelength=args.wavelength, read_label=args.read_label
        )
        plate_reads[plate] = parse_gen5_reads(f)
        plate_layouts[plate] = parse_gen5_layout(f)

        if plate_layouts[plate] and not args.no_layout_check:
            our_rows_for_plate = [r for r in rows if r.plate == plate]
            errors, warnings = check_gen5_layout(our_rows_for_plate, plate_layouts[plate])
            if errors:
                shown = errors[:10]
                message = f"{f}: {len(errors)} layout mismatch(es) vs Gen5 Layout block: " + "; ".join(shown)
                if len(errors) > 10:
                    message += f" (+{len(errors) - 10} more)"
                raise PlatemapError(message)
            for warning in warnings:
                print(f"WARNING: {f}: {warning}")

    wb_path = Path(args.workbook)
    out_path = Path(args.out) if args.out else wb_path.with_name(f"{wb_path.stem}_filled.xlsx")
    mapped_csv_path = out_path.with_name(f"{wb_path.stem}_mapped.csv")
    gen5_reads_csv_path = out_path.with_name(f"{wb_path.stem}_gen5_reads.csv")

    fill_reader(args.workbook, plate_values, str(out_path))

    mapped = compute_mapped_rows(rows, plate_values)

    columns = ("plate", "well", "role", "short_id", "label", "conc_ugml", "sample_name", "dilution_factor", "replicate", "absorbance")
    with open(mapped_csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in mapped:
            writer.writerow(
                ["" if v is None or (isinstance(v, float) and math.isnan(v)) else v for v in (row[c] for c in columns)]
            )

    gen5_columns = (
        "plate", "well", "read_label", "value", "gen5_well_id", "gen5_conc",
        "plate_number", "date", "time",
    )
    with open(gen5_reads_csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(gen5_columns)
        for plate in sorted(plate_reads):
            metadata = plate_metadata.get(plate, {})
            layout = plate_layouts.get(plate, {})
            for read_label, data in plate_reads[plate].items():
                for well, value in data.items():
                    gen5_id, gen5_conc = layout.get(well, ("", ""))
                    writer.writerow(
                        [
                            plate,
                            well,
                            read_label,
                            "" if isinstance(value, float) and math.isnan(value) else value,
                            gen5_id,
                            gen5_conc,
                            metadata.get("Plate Number", ""),
                            metadata.get("Date", ""),
                            metadata.get("Time", ""),
                        ]
                    )

    missing = sum(1 for row in mapped if isinstance(row["absorbance"], float) and math.isnan(row["absorbance"]))

    print(out_path)
    print(mapped_csv_path)
    print(gen5_reads_csv_path)
    print(f"missing={missing}")
    return 0


def _run_notebook(args: argparse.Namespace) -> int:
    from platemap.notebook import write_notebook

    write_notebook(args.out, mapped_csv=args.mapped_csv, include_blank_in_fit=not args.no_blank_in_fit)
    print(args.out)
    return 0


def _analyze_prefix(mapped_csv: str) -> str:
    stem = Path(mapped_csv).stem
    for suffix in ("_plates_mapped", "_mapped"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _run_analyze(args: argparse.Namespace) -> int:
    import csv
    import json

    try:
        from platemap import analysis

        import matplotlib

        matplotlib.use("Agg")
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError as exc:
        raise PlatemapError(
            "platemap analyze requires the 'notebook' extra "
            "(pandas, numpy, scipy, matplotlib); install with `pip install 'platemap[notebook]'`"
        ) from exc

    mapped_path = Path(args.mapped_csv)
    outdir = Path(args.outdir) if args.outdir else mapped_path.parent
    outdir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix if args.prefix else _analyze_prefix(mapped_path.name)

    include_blank = not args.no_blank_in_fit

    df = analysis.load_mapped(str(mapped_path))
    df = analysis.subtract_blank(df)
    fits = analysis.fit_standards(df, args.model, include_blank)
    df = analysis.quantify(df, args.model, include_blank)
    summary = analysis.summarize(df)

    results_path = outdir / f"{prefix}_results.csv"
    wells_path = outdir / f"{prefix}_results_wells.csv"
    fits_path = outdir / f"{prefix}_curve_fits.csv"
    pdf_path = outdir / f"{prefix}_standard_curves.pdf"

    summary.to_csv(results_path, index=False)
    df.to_csv(wells_path, index=False)

    plates = sorted(fits)
    with open(fits_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["plate", "model", "params", "r2", "n_points", "include_blank"])
        for plate in plates:
            fit = fits[plate]
            x, _y = analysis._standard_curve(df, plate, include_blank)
            writer.writerow([plate, fit.model, json.dumps(fit.params), fit.r2, len(x), include_blank])

    with PdfPages(str(pdf_path)) as pdf:
        for plate in plates:
            fit = fits[plate]
            x, y = analysis._standard_curve(df, plate, include_blank)

            fig, ax = plt.subplots()
            ax.scatter(x, y, label="standards (mean)")

            plate_std = df[(df["plate"] == plate) & (df["role"].isin(["standard", "blank"]))]
            ax.scatter(plate_std["conc_ugml"], plate_std["abs_blanked"], alpha=0.4, label="standard replicates")

            x_max = max(x.max(), 1.0)
            x_line = np.linspace(0.0, x_max, 200)
            x_line_safe = np.where(x_line <= 0, 1e-6, x_line)
            if fit.model == "4pl":
                a, b, c, d = fit.params["a"], fit.params["b"], fit.params["c"], fit.params["d"]
                with np.errstate(all="ignore"):
                    y_line = d + (a - d) / (1 + (x_line_safe / c) ** b)
            else:
                y_line = fit.params["slope"] * x_line + fit.params["intercept"]
            ax.plot(x_line, y_line, label=fit.model)

            samples = df[(df["plate"] == plate) & (df["role"] == "sample")]
            if len(samples):
                ax.scatter(
                    samples["conc_ugml_est"], samples["abs_blanked"], marker="x", color="red", label="samples"
                )

            ax.set_title(f"Plate {plate}: {fit.model} fit, R²={fit.r2:.4f}")
            ax.set_xlabel("Concentration (µg/mL)")
            ax.set_ylabel("Blanked absorbance")
            ax.legend()
            pdf.savefig(fig)
            plt.close(fig)

    for plate in plates:
        fit = fits[plate]
        print(f"plate {plate}: model={fit.model} r2={fit.r2:.4f} params={fit.params}")

    samples_all = df[df["role"] == "sample"]
    in_range = int((~samples_all["out_of_range"]).sum())
    out_range = int(samples_all["out_of_range"].sum())
    print(f"samples: in_range={in_range} out_of_range={out_range}")

    print(results_path)
    print(wells_path)
    print(fits_path)
    print(pdf_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the platemap CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    try:
        if args.command == "layout":
            return _run_layout(args)
        if args.command == "read":
            return _run_read(args)
        if args.command == "dilute":
            return _run_dilute(args)
        if args.command == "notebook":
            return _run_notebook(args)
        if args.command == "analyze":
            return _run_analyze(args)
    except PlatemapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
