"""Gen5 3.12 plate-layout setup sheet generator.

Gen5 has no documented layout import format: the user enters the layout by
hand on Gen5's Plate Layout screen (Protocol > Plate Layout) and imports
Sample IDs from a plain text file (one ID per line, assigned to SPL1, SPL2,
... in order; Plate > Batch Sample IDs > Import From File fills one plate's
SPL table, then the next). This module builds the setup sheet (PDF), the
sample-ID text file(s), and a flat CSV of the Gen5 ids we expect, from an
existing platemap layout.
"""

import csv
import math
import re
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from platemap.layout import ROLE_FILL, STANDARD_CONCS_MC, LayoutRow
from platemap.wells import COLS_FULL, ROWS_FULL

PAGE_W, PAGE_H = letter
MARGIN = 0.5 * inch

GEN5_LAYOUT_COLUMNS = (
    "plate",
    "well",
    "gen5_type",
    "gen5_id",
    "conc_ugml",
    "short_id",
    "sample_name",
    "replicate",
)

_ROLE_TO_GEN5_TYPE = {"standard": "Standard", "blank": "Blank", "sample": "Sample"}


def _short_id_num(short_id: str) -> int | None:
    m = re.search(r"(\d+)", short_id)
    return int(m.group(1)) if m else None


def _sample_rank_for_plate(plate_rows: list[LayoutRow]) -> dict[str, int]:
    """Rank each sample short_id on a plate by its S-number (ascending), 1-based."""
    sample_rows = [r for r in plate_rows if r.role == "sample"]
    first_order: dict[str, int] = {}
    for r in sorted(sample_rows, key=lambda r: (ROWS_FULL.index(r.row), r.col)):
        if r.short_id not in first_order:
            first_order[r.short_id] = len(first_order)
    unique_ids = sorted(
        first_order,
        key=lambda sid: (
            _short_id_num(sid) is None,
            _short_id_num(sid) if _short_id_num(sid) is not None else 0,
            first_order[sid],
        ),
    )
    return {sid: i + 1 for i, sid in enumerate(unique_ids)}


def gen5_assignments(rows: list[LayoutRow]) -> list[dict]:
    """Return per-well Gen5 assignments (plate, well, gen5_type, gen5_id, conc, ...).

    `gen5_id` follows the Gen5 conventions `check_gen5_layout` accepts: "BCA:k"
    (k = 1-based rank of the concentration in descending STANDARD_CONCS_MC) for
    standards, "BLK" for blanks, and "SPLk" (k = rank of the sample group's
    S-number within the plate) for samples.
    """
    out: list[dict] = []
    plates = sorted({r.plate for r in rows})
    for plate in plates:
        plate_rows = [r for r in rows if r.plate == plate]
        rank = _sample_rank_for_plate(plate_rows)

        for r in plate_rows:
            conc = None
            if r.role == "standard":
                k = STANDARD_CONCS_MC.index(r.conc_ugml) + 1
                gen5_id = f"BCA:{k}"
                conc = r.conc_ugml
            elif r.role == "blank":
                gen5_id = "BLK"
            else:
                gen5_id = f"SPL{rank[r.short_id]}"

            out.append(
                {
                    "plate": plate,
                    "well": r.well,
                    "gen5_type": _ROLE_TO_GEN5_TYPE[r.role],
                    "gen5_id": gen5_id,
                    "conc": conc,
                    "short_id": r.short_id,
                    "sample_name": r.sample_name,
                    "replicate": r.replicate,
                }
            )
    return out


def replicate_orientation(rows: list[LayoutRow]) -> str:
    """"horizontal" if each (plate, short_id) group's wells share a row, "vertical"
    if they share a column, else "mixed". Callers filter `rows` to one role
    (e.g. just samples, or just standards without blanks) before calling this,
    since a role with disjoint groups (like a spread-out blank) isn't a single
    replicate group.
    """
    groups: dict[tuple[int, str], list[LayoutRow]] = {}
    for r in rows:
        groups.setdefault((r.plate, r.short_id), []).append(r)

    orientations: set[str] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        row_set = {r.row for r in group}
        col_set = {r.col for r in group}
        if len(row_set) == 1:
            orientations.add("horizontal")
        elif len(col_set) == 1:
            orientations.add("vertical")
        else:
            orientations.add("mixed")

    if orientations == {"horizontal"}:
        return "horizontal"
    if orientations == {"vertical"}:
        return "vertical"
    if not orientations:
        return "mixed"
    return "mixed"


def gen5_protocol_layout(rows: list[LayoutRow]) -> list[dict]:
    """Return the single Gen5 protocol layout: the assignments of the plate with
    the most samples (plate 1, in every layout this codebase builds). Gen5
    defines one layout per protocol, applied to every plate.
    """
    assignments = gen5_assignments(rows)
    if not assignments:
        return []

    sample_counts: dict[int, int] = {}
    for r in rows:
        if r.role == "sample":
            sample_counts[r.plate] = sample_counts.get(r.plate, 0) + 1

    plates = sorted({a["plate"] for a in assignments})
    protocol_plate = min(plates, key=lambda p: (-sample_counts.get(p, 0), p))
    return [a for a in assignments if a["plate"] == protocol_plate]


def _protocol_missing_wells(rows: list[LayoutRow]) -> dict[int, list[str]]:
    """For every plate other than the protocol-source plate, list the wells that
    the protocol layout labels "Sample" but that are empty on that plate.
    """
    protocol = gen5_protocol_layout(rows)
    if not protocol:
        return {}
    protocol_plate = protocol[0]["plate"]
    protocol_by_well = {a["well"]: a for a in protocol}

    def _well_key(well: str) -> tuple[int, int]:
        return ROWS_FULL.index(well[0]), int(well[1:])

    plates = sorted({r.plate for r in rows})
    result: dict[int, list[str]] = {}
    for plate in plates:
        if plate == protocol_plate:
            continue
        our_wells = {r.well for r in rows if r.plate == plate}
        missing = sorted(
            (
                well
                for well, a in protocol_by_well.items()
                if a["gen5_type"] == "Sample" and well not in our_wells
            ),
            key=_well_key,
        )
        if missing:
            result[plate] = missing
    return result


def write_gen5_layout_csv(rows: list[LayoutRow], path: str) -> None:
    """Write the flat Gen5 assignment table: plate,well,gen5_type,gen5_id,conc_ugml,
    short_id,sample_name,replicate.
    """
    assignments = gen5_assignments(rows)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(GEN5_LAYOUT_COLUMNS)
        for a in assignments:
            writer.writerow(
                [
                    a["plate"],
                    a["well"],
                    a["gen5_type"],
                    a["gen5_id"],
                    "" if a["conc"] is None else a["conc"],
                    a["short_id"],
                    "" if a["sample_name"] is None else a["sample_name"],
                    a["replicate"],
                ]
            )


def _write_lines_crlf(path: Path, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for line in lines:
            fh.write(line + "\r\n")


def _spl_num(gen5_id: str) -> int:
    return int(gen5_id[3:])


def write_gen5_sample_ids(rows: list[LayoutRow], prefix_path) -> tuple[Path, dict[int, Path]]:
    """Write `<prefix>_gen5_sample_ids.txt` (all plates concatenated, in SPL order,
    padded between plates to the protocol's SPL count so Batch Sample IDs
    import lands each plate's samples on its own SPL1) and one
    `<prefix>_gen5_sample_ids_plate{N}.txt` per plate (no padding).

    Returns (combined_path, {plate: per_plate_path}).
    """
    prefix_path = Path(prefix_path)
    assignments = gen5_assignments(rows)
    plates = sorted({a["plate"] for a in assignments})

    protocol = gen5_protocol_layout(rows)
    protocol_spl_count = len({a["gen5_id"] for a in protocol if a["gen5_type"] == "Sample"})

    per_plate_names: dict[int, list[str]] = {}
    for plate in plates:
        by_id: dict[str, str] = {}
        for a in assignments:
            if a["plate"] != plate or a["gen5_type"] != "Sample":
                continue
            if a["gen5_id"] not in by_id:
                by_id[a["gen5_id"]] = a["sample_name"] or ""
        ordered_ids = sorted(by_id, key=_spl_num)
        per_plate_names[plate] = [by_id[sid] for sid in ordered_ids]

    combined_lines: list[str] = []
    per_plate_paths: dict[int, Path] = {}
    for i, plate in enumerate(plates):
        names = per_plate_names[plate]
        combined_lines.extend(names)
        if i < len(plates) - 1:
            pad = max(protocol_spl_count - len(names), 0)
            combined_lines.extend([""] * pad)

        plate_path = Path(f"{prefix_path}_gen5_sample_ids_plate{plate}.txt")
        _write_lines_crlf(plate_path, names)
        per_plate_paths[plate] = plate_path

    combined_path = Path(f"{prefix_path}_gen5_sample_ids.txt")
    _write_lines_crlf(combined_path, combined_lines)

    return combined_path, per_plate_paths


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _fit_font(text: str, max_width: float, max_size: float = 7.0, min_size: float = 3.0) -> float:
    size = max_size
    while size > min_size and stringWidth(text, "Helvetica", size) > max_width:
        size -= 0.25
    return size


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(max_chars - 1, 1)] + "…"


def _draw_header(c: canvas.Canvas, title: str, experiment: str, date: str) -> float:
    """Draw a title/experiment/date header; return the y cursor below it."""
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, PAGE_H - MARGIN - 14, title)
    c.setFont("Helvetica", 9.5)
    c.drawString(MARGIN, PAGE_H - MARGIN - 30, f"Experiment: {experiment}    Date: {date}")
    return PAGE_H - MARGIN - 46


def _draw_matrix(
    c: canvas.Canvas,
    x: float,
    top: float,
    w: float,
    h: float,
    cells: dict[str, tuple[str, list[str]]],
) -> float:
    """Draw an 8x12 matrix of filled rectangles with up to 3 centered text lines
    per cell; cells maps well -> (hex_fill, lines). Returns the bottom y.
    """
    grid_left = x + 0.3 * inch
    n_cols = len(COLS_FULL)
    n_rows = len(ROWS_FULL)
    cell_w = (w - 0.3 * inch) / n_cols
    cell_h = h / n_rows

    c.setFont("Helvetica", 7)
    for i, col in enumerate(COLS_FULL):
        cx = grid_left + (i + 0.5) * cell_w
        c.drawCentredString(cx, top + 0.05 * inch, str(col))
    for j, row in enumerate(ROWS_FULL):
        cy = top - (j + 0.5) * cell_h
        c.drawRightString(grid_left - 0.06 * inch, cy - 2.5, row)

    for j, row_letter in enumerate(ROWS_FULL):
        for i, col in enumerate(COLS_FULL):
            well = f"{row_letter}{col}"
            cx = grid_left + i * cell_w
            cy = top - (j + 1) * cell_h
            entry = cells.get(well)
            if entry is None:
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.rect(cx + 1, cy + 1, cell_w - 2, cell_h - 2, stroke=1, fill=0)
                continue
            hexcolor, lines = entry
            c.setFillColor(HexColor(f"#{hexcolor}"))
            c.setStrokeColorRGB(0.3, 0.3, 0.3)
            c.rect(cx + 1, cy + 1, cell_w - 2, cell_h - 2, stroke=1, fill=1)
            c.setFillColorRGB(0, 0, 0)
            n_lines = len(lines)
            line_h = min(cell_h / (n_lines + 1), 9)
            start_y = cy + cell_h / 2 + (n_lines - 1) * line_h / 2
            for k, line in enumerate(lines):
                font_size = _fit_font(line, cell_w - 3)
                c.setFont("Helvetica", font_size)
                c.drawCentredString(cx + cell_w / 2, start_y - k * line_h - font_size * 0.35, line)

    return top - h


def _conc_text(conc: float | None) -> str:
    if conc is None:
        return ""
    return str(int(conc)) if float(conc).is_integer() else f"{conc:g}"


def _protocol_prefix(path: str) -> str:
    stem = Path(path).stem
    if stem.endswith("_gen5_setup"):
        return stem[: -len("_gen5_setup")]
    return stem


def write_gen5_setup_pdf(rows: list[LayoutRow], path: str, experiment: str = "", date: str = "") -> int:
    """Write the Gen5 plate-layout setup sheet PDF and return the page count."""
    protocol = gen5_protocol_layout(rows)
    protocol_plate = protocol[0]["plate"] if protocol else 1
    by_id: dict[str, dict] = {}
    for a in protocol:
        by_id.setdefault(a["gen5_id"], a)

    standard_entries = sorted(
        (a for a in protocol if a["gen5_type"] == "Standard"),
        key=lambda a: _short_id_num(a["gen5_id"]) or 0,
    )
    blank_wells = sorted(
        (a["well"] for a in protocol if a["gen5_type"] == "Blank"),
        key=lambda w: (ROWS_FULL.index(w[0]), int(w[1:])),
    )
    sample_entries = [a for a in protocol if a["gen5_type"] == "Sample"]

    standards_by_k: dict[int, dict] = {}
    for a in standard_entries:
        k = _short_id_num(a["gen5_id"])
        standards_by_k.setdefault(k, {"conc": a["conc"], "wells": []})
        standards_by_k[k]["wells"].append(a["well"])
    for k in standards_by_k:
        standards_by_k[k]["wells"].sort(key=lambda w: (ROWS_FULL.index(w[0]), int(w[1:])))

    spl_wells: dict[int, list[str]] = {}
    for a in sample_entries:
        k = _spl_num(a["gen5_id"])
        spl_wells.setdefault(k, []).append(a["well"])
    for k in spl_wells:
        spl_wells[k].sort(key=lambda w: (ROWS_FULL.index(w[0]), int(w[1:])))

    n_samples = len(spl_wells)
    replicates = max((a["replicate"] for a in sample_entries), default=1)

    protocol_layout_rows = [r for r in rows if r.plate == protocol_plate]
    sample_orientation = replicate_orientation([r for r in protocol_layout_rows if r.role == "sample"])
    standard_orientation = replicate_orientation([r for r in protocol_layout_rows if r.role == "standard"])

    prefix = _protocol_prefix(path)
    missing_by_plate = _protocol_missing_wells(rows)

    content_w = PAGE_W - 2 * MARGIN

    c = canvas.Canvas(path, pagesize=letter)

    # ---- page 1: protocol layout + entry steps -------------------------
    cursor = _draw_header(c, "Gen5 plate layout setup", experiment, date)
    cursor -= 6

    cells: dict[str, tuple[str, list[str]]] = {}
    for a in protocol:
        hexcolor = ROLE_FILL[a["gen5_type"].lower()] if a["gen5_type"].lower() in ROLE_FILL else ROLE_FILL["sample"]
        if a["gen5_type"] == "Standard":
            lines = [a["gen5_id"], _conc_text(a["conc"])]
        elif a["gen5_type"] == "Blank":
            lines = ["BLK"]
        else:
            lines = [a["gen5_id"]]
        cells[a["well"]] = (hexcolor, lines)

    grid_h = 3.4 * inch
    cursor = _draw_matrix(c, MARGIN, cursor, content_w, grid_h, cells)
    cursor -= 0.15 * inch

    # ---- standards table -------------------------------------------------
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN, cursor, "Standards (group \"BCA\")")
    cursor -= 11
    c.setFont("Helvetica", 7.5)
    for k in sorted(standards_by_k):
        entry = standards_by_k[k]
        wells_str = ", ".join(entry["wells"])
        c.drawString(
            MARGIN,
            cursor,
            f"BCA:{k} = {_conc_text(entry['conc'])} µg/mL  →  wells {wells_str}",
        )
        cursor -= 9.5
    cursor -= 4

    # ---- blanks line -------------------------------------------------------
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN, cursor, "Blanks")
    cursor -= 11
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, cursor, f"BLK → wells {', '.join(blank_wells)}" if blank_wells else "BLK: none")
    cursor -= 15

    # ---- samples summary -----------------------------------------------
    first_spl = min(spl_wells) if spl_wells else 0
    last_spl = max(spl_wells) if spl_wells else 0
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN, cursor, "Samples")
    cursor -= 11
    c.setFont("Helvetica", 7.5)
    c.drawString(
        MARGIN,
        cursor,
        f"SPL{first_spl}-SPL{last_spl} ({n_samples} groups), {replicates}x replicate each, "
        f"{sample_orientation} orientation",
    )
    cursor -= 15

    # ---- entry steps -----------------------------------------------------
    prt_name = f"{prefix}_Gen5_layout.prt"
    sample_ids_name = f"{prefix}_gen5_sample_ids.txt"
    steps = [
        "Protocol > Plate Layout.",
        f'Well type Standard, ID "BCA", replicates = 2, direction = {standard_orientation}; '
        f"place BCA:1..BCA:8 on the wells listed above (click/drag in order, high to low "
        "concentration).",
        "Enter the concentrations (µg/mL) in the standards concentration table exactly "
        "as listed above.",
        "Well type Blank: select the blank wells listed above.",
        f'Well type Sample, ID "SPL", replicates = {replicates}, direction = '
        f"{sample_orientation}, auto-numbering; place SPL1..SPL{last_spl} by dragging along "
        "the rows/columns in the order shown in the matrix above.",
        f'Save the protocol under a new name (e.g. "{prt_name}") and use it for all plates.',
        f"In the experiment, Plate > Batch Sample IDs > Import From File: {sample_ids_name} "
        "(all plates) or the per-plate files.",
        "Export results per plate as text for `platemap read`.",
    ]

    step_font, line_h = 8.0, 9.3
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN, cursor, "Gen5 entry steps")
    cursor -= 11
    c.setFont("Helvetica", step_font)
    for i, step in enumerate(steps, start=1):
        text = f"{i}) {step}"
        for line in simpleSplit(text, "Helvetica", step_font, content_w):
            if cursor < MARGIN + 2 * line_h:
                c.showPage()
                cursor = PAGE_H - MARGIN - 14
                c.setFont("Helvetica", step_font)
            c.drawString(MARGIN, cursor, line)
            cursor -= line_h

    cursor -= 4
    warn_text = (
        "Dilution factors are applied by platemap analyze; leave Gen5 sample dilution at 1."
    )
    if cursor < MARGIN + 2 * line_h:
        c.showPage()
        cursor = PAGE_H - MARGIN - 14
    c.setFont("Helvetica-Bold", step_font)
    for line in simpleSplit(warn_text, "Helvetica-Bold", step_font, content_w):
        c.drawString(MARGIN, cursor, line)
        cursor -= line_h

    c.showPage()

    # ---- page 2+: per-plate confirmation -----------------------------------
    plates = sorted({r.plate for r in rows})
    for plate in plates:
        plate_assignments = [a for a in gen5_assignments(rows) if a["plate"] == plate]
        cursor = _draw_header(c, f"Plate {plate}: confirm actual contents", experiment, date)
        cursor -= 6

        cells = {}
        for a in plate_assignments:
            gen5_type_lower = a["gen5_type"].lower()
            hexcolor = ROLE_FILL.get(gen5_type_lower, ROLE_FILL["sample"])
            if a["gen5_type"] == "Standard":
                lines = [a["gen5_id"], _conc_text(a["conc"])]
            elif a["gen5_type"] == "Blank":
                lines = ["BLK"]
            else:
                name = _truncate(a["sample_name"] or "", 10)
                lines = [a["gen5_id"], a["short_id"], name]
            cells[a["well"]] = (hexcolor, lines)

        grid_h = 4.2 * inch
        cursor = _draw_matrix(c, MARGIN, cursor, content_w, grid_h, cells)
        cursor -= 0.2 * inch

        missing = missing_by_plate.get(plate, [])
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(MARGIN, cursor, "Notes")
        cursor -= 11
        c.setFont("Helvetica", 7.5)
        if missing:
            note = (
                f"The saved protocol labels {len(missing)} well(s) as SPL that are empty on "
                f"this plate (fewer samples than plate {protocol_plate}): {', '.join(missing)}. "
                "`platemap read` will report these as warnings, not errors."
            )
        else:
            note = "This plate uses every well the saved protocol labels."
        for line in simpleSplit(note, "Helvetica", 7.5, content_w):
            c.drawString(MARGIN, cursor, line)
            cursor -= 9.5

        c.showPage()

    c.save()

    with open(path, "rb") as fh:
        data = fh.read()
    return max(len(re.findall(rb"/Type\s*/Page[^s]", data)), 1)
