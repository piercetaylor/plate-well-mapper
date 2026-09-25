"""Command-line interface for platemap."""

import argparse
import datetime as dt
import sys
from pathlib import Path

from platemap import __version__
from platemap.samples import PlatemapError, read_samples


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
    read_p.add_argument("-o", "--out", default=None, metavar="OUT.xlsx", help="output workbook path (default: <workbook stem>_filled.xlsx)")

    notebook_p = subparsers.add_parser(
        "notebook",
        help="write a Jupyter notebook for BCA standard-curve analysis",
        description="Write a Jupyter notebook that loads a mapped CSV, fits standard curves, and quantifies samples.",
        epilog="examples:\n  platemap notebook -o bca_analysis.ipynb\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    notebook_p.add_argument("-o", "--out", default="bca_analysis.ipynb", metavar="PATH", help="output notebook path (default: bca_analysis.ipynb)")

    return parser


def _run_layout(args: argparse.Namespace) -> int:
    from platemap.excel import write_excel
    from platemap.layout import build_layout, capacity, n_plates, write_layout_csv
    from platemap.pdf import write_pdf

    samples = read_samples(args.samples)
    rows = build_layout(samples, avoid_edges=args.avoid_edges)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / f"{args.prefix}_layout.csv"
    xlsx_path = outdir / f"{args.prefix}_plates.xlsx"
    pdf_path = outdir / f"{args.prefix}_platemap.pdf"

    write_layout_csv(rows, str(csv_path))
    write_excel(rows, str(xlsx_path), experiment=args.experiment, date=args.date)
    write_pdf(rows, str(pdf_path), experiment=args.experiment, date=args.date)

    n = len(samples)
    plates = n_plates(n, args.avoid_edges)
    cap = capacity(args.avoid_edges)
    print(f"samples={n} plates={plates} capacity={cap}")
    print(csv_path)
    print(xlsx_path)
    print(pdf_path)
    return 0


def _run_read(args: argparse.Namespace) -> int:
    import csv
    import math

    from platemap.excel import compute_mapped_rows, fill_reader, plate_count, read_layout
    from platemap.gen5 import parse_gen5

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

    plate_values = {
        plate: parse_gen5(f, wavelength=args.wavelength) for plate, f in plate_files.items()
    }

    wb_path = Path(args.workbook)
    out_path = Path(args.out) if args.out else wb_path.with_name(f"{wb_path.stem}_filled.xlsx")
    mapped_csv_path = out_path.with_name(f"{wb_path.stem}_mapped.csv")

    fill_reader(args.workbook, plate_values, str(out_path))

    rows = read_layout(args.workbook)
    mapped = compute_mapped_rows(rows, plate_values)

    columns = ("plate", "well", "role", "short_id", "label", "conc_ugml", "sample_name", "dilution_factor", "replicate", "absorbance")
    with open(mapped_csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in mapped:
            writer.writerow(
                ["" if v is None or (isinstance(v, float) and math.isnan(v)) else v for v in (row[c] for c in columns)]
            )

    missing = sum(1 for row in mapped if isinstance(row["absorbance"], float) and math.isnan(row["absorbance"]))

    print(out_path)
    print(mapped_csv_path)
    print(f"missing={missing}")
    return 0


def _run_notebook(args: argparse.Namespace) -> int:
    from platemap.notebook import write_notebook

    write_notebook(args.out)
    print(args.out)
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
        if args.command == "notebook":
            return _run_notebook(args)
    except PlatemapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
