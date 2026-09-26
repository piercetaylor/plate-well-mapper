"""PDF plate map generation."""

import math

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from platemap.dilution import (
    STANDARD_PREP,
    STANDARD_PREP_ORDER,
    STOCK,
    DilutionPlan,
    DilutionWell,
    standard_prep_warnings,
    stock_volume_ul,
)
from platemap.layout import ROLE_FILL, LayoutRow
from platemap.wells import COLS_FULL, ROWS_FULL

PAGE_W, PAGE_H = letter
MARGIN = 0.4 * inch
HEADER_H = 0.6 * inch
GUTTER = 0.35 * inch


def _panel_rects() -> list[tuple[float, float, float, float]]:
    """Return (x, y, w, h) for the four plate panels on a page, top-left origin logic."""
    usable_w = PAGE_W - 2 * MARGIN - GUTTER
    usable_h = PAGE_H - 2 * MARGIN - HEADER_H
    panel_w = usable_w / 2
    panel_h = usable_h / 2
    rects = []
    for row in range(2):
        for col in range(2):
            x = MARGIN + col * (panel_w + GUTTER)
            y = PAGE_H - MARGIN - HEADER_H - (row + 1) * panel_h
            rects.append((x, y, panel_w, panel_h))
    return rects


def _fit_font(text: str, max_width: float, max_size: float = 6.0, min_size: float = 3.0) -> float:
    """Return the largest font size (Helvetica, down to min_size) that fits max_width."""
    size = max_size
    while size > min_size and stringWidth(text, "Helvetica", size) > max_width:
        size -= 0.25
    return size


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(max_chars - 1, 1)] + "…"


def _draw_header(c: canvas.Canvas, experiment: str, date: str) -> None:
    """Draw the experiment/date/operator header at the top of a page."""
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, PAGE_H - MARGIN - 12, f"Experiment: {experiment}")
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN, PAGE_H - MARGIN - 28, f"Date: {date}")
    c.drawString(MARGIN, PAGE_H - MARGIN - 42, "Operator: ________")


def _draw_well_grid(
    c: canvas.Canvas,
    x: float,
    grid_top: float,
    w: float,
    grid_h: float,
    cells: dict[str, tuple[str, str]],
    label_font: float = 6.0,
) -> tuple[float, float, float]:
    """Draw an 8x12 well grid with row/col labels; cells maps well -> (hex_fill, text).

    Returns (cell_w, cell_h, radius) for callers that need the geometry.
    """
    grid_left = x + 0.25 * inch
    n_cols = len(COLS_FULL)
    n_rows = len(ROWS_FULL)
    cell_w = (w - 0.3 * inch) / n_cols
    cell_h = grid_h / n_rows
    radius = min(cell_w, cell_h) * 0.42

    c.setFont("Helvetica", label_font)
    for i, col in enumerate(COLS_FULL):
        cx = grid_left + (i + 0.5) * cell_w
        c.drawCentredString(cx, grid_top + 0.03 * inch, str(col))
    for j, row in enumerate(ROWS_FULL):
        cy = grid_top - (j + 0.5) * cell_h
        c.drawRightString(grid_left - 0.05 * inch, cy - label_font * 0.35, row)

    for j, row_letter in enumerate(ROWS_FULL):
        for i, col in enumerate(COLS_FULL):
            well = f"{row_letter}{col}"
            cx = grid_left + (i + 0.5) * cell_w
            cy = grid_top - (j + 0.5) * cell_h
            entry = cells.get(well)
            if entry is None:
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.circle(cx, cy, radius, stroke=1, fill=0)
                continue
            hexcolor, text = entry
            c.setFillColor(HexColor(f"#{hexcolor}"))
            c.setStrokeColorRGB(0.3, 0.3, 0.3)
            c.circle(cx, cy, radius, stroke=1, fill=1)
            c.setFillColorRGB(0, 0, 0)
            font_size = _fit_font(text, radius * 1.7)
            c.setFont("Helvetica", font_size)
            c.drawCentredString(cx, cy - font_size * 0.35, text)

    return cell_w, cell_h, radius


def _draw_plate(
    c: canvas.Canvas,
    rects: tuple[float, float, float, float],
    plate: int,
    plate_rows: list[LayoutRow],
    transfer_lines: list[str] | None = None,
) -> None:
    x, y, w, h = rects
    grid_h = h * 0.62
    legend_top = y + h - grid_h - 0.05 * inch
    legend_available_h = legend_top - y - 0.05 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y + h - 0.15 * inch, f"Plate {plate}")

    grid_top = y + h - 0.35 * inch

    cells: dict[str, tuple[str, str]] = {}
    by_well = {row.well: row for row in plate_rows}
    for well, lr in by_well.items():
        hexcolor = ROLE_FILL[lr.role]
        if lr.role == "standard":
            text = str(int(lr.conc_ugml))
        elif lr.role == "blank":
            text = "BLK"
        else:
            text = lr.short_id
        cells[well] = (hexcolor, text)

    _draw_well_grid(c, x, grid_top, w, grid_top - (y + h - grid_h), cells)

    seen_samples: dict[str, str] = {}
    std_concs: list[float] = []
    has_blank = False
    for lr in plate_rows:
        if lr.role == "blank":
            has_blank = True
        elif lr.role == "standard":
            if lr.conc_ugml not in std_concs:
                std_concs.append(lr.conc_ugml)
        elif lr.short_id not in seen_samples:
            suffix = f" (DF {lr.dilution_factor:g})" if lr.dilution_factor not in (None, 1) else ""
            seen_samples[lr.short_id] = (f"{lr.short_id} — {lr.label}", suffix)

    std_line = ""
    if std_concs:
        std_concs_sorted = sorted(std_concs, reverse=True)
        conc_str = "/".join(str(int(v)) for v in std_concs_sorted)
        std_line = f"Standards: number in well = BSA µg/mL ({conc_str})"
        if has_blank:
            std_line += "; BLK = Blank"

    sample_entries = list(seen_samples.values())
    transfer_lines = transfer_lines or []

    # Shrink font/columns until everything fits in the available legend height.
    font_size, line_h, n_cols = 6.0, 7.2, 2
    for candidate_font in (6.0, 5.5, 5.0, 4.5, 4.0):
        candidate_line_h = candidate_font + 1.4
        std_rows = (1 if std_line else 0) + len(transfer_lines)
        rows_needed = std_rows + math.ceil(len(sample_entries) / n_cols) if sample_entries else std_rows
        if rows_needed * candidate_line_h <= legend_available_h or candidate_font == 4.0:
            font_size, line_h = candidate_font, candidate_line_h
            break

    max_chars = int((w / n_cols) / (font_size * 0.55))

    ly = legend_top
    c.setFont("Helvetica", font_size)
    if std_line:
        c.drawString(x, ly, _truncate(std_line, int(w / (font_size * 0.5))))
        ly -= line_h
    for line in transfer_lines:
        c.drawString(x, ly, _truncate(line, int(w / (font_size * 0.5))))
        ly -= line_h

    col_w = w / n_cols
    rows_per_col = math.ceil(len(sample_entries) / n_cols) if sample_entries else 0
    for idx, entry in enumerate(sample_entries):
        col = idx // rows_per_col if rows_per_col else 0
        row = idx % rows_per_col if rows_per_col else 0
        cx = x + col * col_w
        cy = ly - row * line_h
        text, suffix = entry
        # Truncate the name, never the dilution factor.
        c.drawString(cx, cy, _truncate(text, max_chars - len(suffix)) + suffix)


def write_pdf(
    rows: list[LayoutRow],
    path: str,
    experiment: str = "",
    date: str = "",
    transfer_lines: dict[int, list[str]] | None = None,
) -> int:
    """Write a plate map PDF (US Letter, 2x2 plates/page) and return the page count."""
    plates = sorted({row.plate for row in rows})
    n_pages = math.ceil(len(plates) / 4) if plates else 0
    transfer_lines = transfer_lines or {}

    c = canvas.Canvas(path, pagesize=letter)
    for page in range(n_pages):
        page_plates = plates[page * 4 : page * 4 + 4]

        _draw_header(c, experiment, date)

        rects = _panel_rects()
        for plate, rect in zip(page_plates, rects):
            plate_rows = [r for r in rows if r.plate == plate]
            _draw_plate(c, rect, plate, plate_rows, transfer_lines.get(plate))

        c.showPage()

    c.save()
    return n_pages


def _draw_dilution_legend(
    c: canvas.Canvas, wells: list[DilutionWell], x: float, top: float, w: float, avail_h: float
) -> None:
    """Draw a 2-column legend table (well, S#, sample, sample µL, diluent µL) for sample wells."""
    n = len(wells)
    n_cols = 2
    rows_per_col = math.ceil(n / n_cols) if n else 0

    font_size, line_h = 4.0, 5.6
    for candidate_font in (6.0, 5.5, 5.0, 4.5, 4.0):
        candidate_line_h = candidate_font + 1.6
        rows_needed = rows_per_col + 1
        if rows_needed * candidate_line_h <= avail_h or candidate_font == 4.0:
            font_size, line_h = candidate_font, candidate_line_h
            break

    col_w = w / n_cols
    well_w = col_w * 0.14
    id_w = col_w * 0.10
    ul_w1 = col_w * 0.16
    ul_w2 = col_w * 0.16
    gap = 2
    name_w = col_w - (well_w + id_w + ul_w1 + ul_w2) - 4 * gap
    max_chars = max(int(name_w / (font_size * 0.55)), 3)

    c.setFont("Helvetica-Bold", font_size)
    for col in range(n_cols):
        hx = x + col * col_w
        c.drawString(hx, top, "Well")
        hx += well_w + gap
        c.drawString(hx, top, "S#")
        hx += id_w + gap
        c.drawString(hx, top, "Sample")
        hx += name_w + gap
        c.drawString(hx, top, "Smpl µL")
        hx += ul_w1 + gap
        c.drawString(hx, top, "Dil µL")

    ly = top - line_h
    c.setFont("Helvetica", font_size)
    for idx, dw in enumerate(wells):
        col = idx // rows_per_col if rows_per_col else 0
        row = idx % rows_per_col if rows_per_col else 0
        hx = x + col * col_w
        cy = ly - row * line_h
        c.drawString(hx, cy, dw.well)
        hx += well_w + gap
        c.drawString(hx, cy, dw.short_id)
        hx += id_w + gap
        c.drawString(hx, cy, _truncate(dw.label, max_chars))
        hx += name_w + gap
        c.drawString(hx, cy, f"{dw.source_ul:g}")
        hx += ul_w1 + gap
        c.drawString(hx, cy, f"{dw.diluent_ul:g}")


def _draw_standards_table(
    c: canvas.Canvas, rows: list[DilutionWell], x: float, top: float, w: float, font_size: float = 5.0
) -> float:
    """Draw the standard-prep table (well, conc, source, src/dil/remain µL); return height used."""
    line_h = font_size + 1.4
    headers = ("Well", "Conc", "Source", "Src µL", "Dil µL", "Remain µL")
    fracs = (0.05, 0.06, 0.12, 0.07, 0.07, 0.09)
    widths = [w * f for f in fracs]

    c.setFont("Helvetica-Bold", font_size)
    hx = x
    for label, cw in zip(headers, widths):
        c.drawString(hx, top, label)
        hx += cw

    c.setFont("Helvetica", font_size)
    y = top - line_h
    for row in rows:
        conc_text = "BLK" if row.role == "blank" else str(int(row.conc_ugml))
        values = (
            row.well,
            conc_text,
            str(row.source),
            f"{row.source_ul:g}",
            f"{row.diluent_ul:g}",
            f"{row.remaining_ul:g}",
        )
        hx = x
        for val, cw in zip(values, widths):
            c.drawString(hx, y, val)
            hx += cw
        y -= line_h

    return (len(rows) + 1) * line_h


def _draw_transfer_table(
    c: canvas.Canvas,
    transfers: list[tuple[int, int, int, tuple[int, ...], str]],
    x: float,
    top: float,
    w: float,
    font_size: float = 5.5,
) -> float:
    """Draw a (assay plate, dilution column -> assay columns, contents) transfer table."""
    line_h = font_size + 1.6
    headers = ("Assay plate", "Dil col", "-> Assay cols", "Contents")
    fracs = (0.14, 0.10, 0.20, 0.20)
    widths = [w * f for f in fracs]

    c.setFont("Helvetica-Bold", font_size)
    hx = x
    for label, cw in zip(headers, widths):
        c.drawString(hx, top, label)
        hx += cw

    c.setFont("Helvetica", font_size)
    y = top - line_h
    for assay_plate, _dplate, dcol, acols, contents in transfers:
        acol_str = ",".join(str(a) for a in acols)
        values = (f"Plate {assay_plate}", str(dcol), acol_str, contents)
        hx = x
        for val, cw in zip(values, widths):
            c.drawString(hx, y, val)
            hx += cw
        y -= line_h

    return (len(transfers) + 1) * line_h


def write_dilution_pdf(
    wells: list[DilutionWell],
    plan: DilutionPlan,
    path: str,
    n_assay_plates: int = 1,
    experiment: str = "",
    date: str = "",
    multichannel: bool = False,
    n_samples: int = 0,
) -> int:
    """Write a dilution-plate protocol + map PDF, one plate per page, and return the page count."""
    from platemap.dilution import transfer_map

    plates = sorted({w.plate for w in wells})
    n_pages = len(plates)
    content_w = PAGE_W - 2 * MARGIN

    all_transfers = transfer_map(n_samples) if multichannel else []

    c = canvas.Canvas(path, pagesize=letter)
    for plate in plates:
        plate_wells = [w for w in wells if w.plate == plate]
        sample_wells = [w for w in plate_wells if w.role == "sample"]
        standard_wells = [w for w in plate_wells if w.role in ("standard", "blank")]

        _draw_header(c, experiment, date)
        cursor = PAGE_H - MARGIN - 0.8 * inch

        factor = plan.factor
        sample_ul = plan.sample_volume_ul
        diluent_ul = plan.diluent_volume_ul
        final_ul = plan.final_volume_ul
        first = sample_wells[0].well if sample_wells else ""
        last = sample_wells[-1].well if sample_wells else ""
        count = len(sample_wells)

        title = f"Dilution plate {plate}: 1 + {factor - 1:g} (dilution factor {factor:g})"
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGIN, cursor, title)
        cursor -= 15

        warnings: list[str] = []
        if multichannel:
            plate_transfers = [t for t in all_transfers if t[1] == plate and t[4].startswith("S")]
            if standard_wells:
                warnings = standard_prep_warnings(n_assay_plates)
                stock_concs = [c for c in STANDARD_PREP_ORDER if STANDARD_PREP[c][0] == STOCK]
                serial_concs = [c for c in STANDARD_PREP_ORDER if c not in stock_concs]
                stock_list = ", ".join(str(c) for c in stock_concs)
                serial_list = ", ".join(str(c) for c in serial_concs)
                steps = [
                    f'1) Label a clear 96-well plate "Dilution {plate}" (also the standard-prep plate).',
                    (
                        f"2) Add diluent to sample columns 4-12 ({diluent_ul:g} µL/well) and "
                        "200 µL diluent to blank column 3 (A3-H3); standard volumes vary, see "
                        "the table below."
                    ),
                    (
                        f"3) Make the standards in this order: {stock_list} µg/mL from BSA stock; "
                        f"then {serial_list} µg/mL serially, each from the same column, same-row "
                        "well of the previous concentration (see table for source wells/volumes). "
                        "Mix each source well 10x before drawing from it."
                    ),
                    (
                        f"4) Add {sample_ul:g} µL of each sample to its well per the map "
                        "(fresh tip each; dispense into the liquid)."
                    ),
                    "5) Mix all wells by pipetting up and down 10x; avoid bubbles.",
                    "6) Seal or cover and spin briefly.",
                    (
                        "7) Transfer 25 µL column-to-column with an 8-channel pipette: dilution "
                        "col 1 -> assay col 1, col 2 -> col 2, col 3 -> col 3 (every assay plate); "
                        "each 8-sample dilution column -> its triplicate assay columns, see the "
                        "transfer table below."
                    ),
                    (
                        f"8) Results are multiplied by the factor (x {factor:g}) automatically; "
                        "standards are NOT multiplied - they are already at final concentration."
                    ),
                ]
            else:
                steps = [
                    f'1) Label a clear 96-well plate "Dilution {plate}".',
                    (
                        f"2) Add {diluent_ul:g} µL diluent (same buffer as BCA standards) to all "
                        "used wells; a multichannel/reservoir is fine."
                    ),
                    (
                        f"3) Add {sample_ul:g} µL of each sample to its well per the map "
                        "(fresh tip each; dispense into the liquid)."
                    ),
                    f"4) Mix by pipetting up and down 10x at ~{0.6 * final_ul:g} µL; avoid bubbles.",
                    "5) Seal or cover and spin briefly.",
                    (
                        "6) Transfer 25 µL column-to-column with an 8-channel pipette: each "
                        "8-sample dilution column -> its triplicate assay columns, see the "
                        "transfer table below."
                    ),
                    f"7) Results are reported for the undiluted sample (x {factor:g}) automatically.",
                ]
            step_font, line_h = 7.5, 8.8
        elif standard_wells:
            warnings = standard_prep_warnings(n_assay_plates)
            stock_concs = [c for c in STANDARD_PREP_ORDER if STANDARD_PREP[c][0] == STOCK]
            serial_concs = [c for c in STANDARD_PREP_ORDER if c not in stock_concs]
            stock_list = ", ".join(str(c) for c in stock_concs)
            serial_list = ", ".join(str(c) for c in serial_concs)
            blank_diluent_ul = STANDARD_PREP[0][2]
            steps = [
                f'1) Label a clear 96-well plate "Dilution {plate}" (also the standard-prep plate).',
                (
                    f"2) Add diluent to all wells: {diluent_ul:g} µL to sample wells "
                    f"{first}–{last} ({count} wells); {blank_diluent_ul:g} µL to the blank "
                    "(B5–B6); standard volumes vary, see the table below."
                ),
                (
                    f"3) Make the standards in this order: {stock_list} µg/mL from BSA stock; "
                    f"then {serial_list} µg/mL serially, each from the same-replicate well "
                    "of the previous concentration (see table for source wells/volumes). Mix each "
                    "source well 10× before drawing from it."
                ),
                (
                    f"4) Add {sample_ul:g} µL of each sample to its well per the map "
                    "(fresh tip each; dispense into the liquid)."
                ),
                "5) Mix all wells by pipetting up and down 10×; avoid bubbles.",
                "6) Seal or cover and spin briefly.",
                (
                    "7) Transfer 25 µL to the assay plates: standards A1–A12 and B1–B6 map 1:1 "
                    "onto the same wells of every assay plate (multichannel OK). Do NOT "
                    "multichannel B7–B12: samples go dilution well S# → assay map S# "
                    "(triplicate, 3 wells each)."
                ),
                (
                    f"8) Results are multiplied by the factor (× {factor:g}) automatically; "
                    "standards are NOT multiplied — they are already at final concentration."
                ),
            ]
            step_font, line_h = 7.5, 8.8
        else:
            steps = [
                f'1) Label a clear 96-well plate "Dilution {plate}".',
                (
                    f"2) Add {diluent_ul:g} µL diluent (same buffer as BCA standards) to wells "
                    f"{first}–{last} ({count} wells); a multichannel/reservoir is fine."
                ),
                (
                    f"3) Add {sample_ul:g} µL of each sample to its well per the map "
                    "(fresh tip each; dispense into the liquid)."
                ),
                f"4) Mix by pipetting up and down 10× at ~{0.6 * final_ul:g} µL; avoid bubbles.",
                "5) Seal or cover and spin briefly.",
                (
                    "6) Transfer 25 µL of each diluted sample in triplicate to the BCA assay "
                    "plates; dilution well S# = assay map S#."
                ),
                f"7) Results are reported for the undiluted sample (× {factor:g}) automatically.",
            ]
            step_font, line_h = 8, 9.5

        c.setFont("Helvetica", step_font)
        for step in steps:
            for line in simpleSplit(step, "Helvetica", step_font, content_w):
                c.drawString(MARGIN, cursor, line)
                cursor -= line_h

        if warnings:
            cursor -= 2
            c.setFillColorRGB(0.7, 0, 0)
            for warn in warnings:
                c.setFont("Helvetica-Bold", step_font)
                for line in simpleSplit(f"WARNING: {warn}", "Helvetica-Bold", step_font, content_w):
                    c.drawString(MARGIN, cursor, line)
                    cursor -= line_h
            c.setFillColorRGB(0, 0, 0)

        cursor -= 4
        c.setFont("Helvetica-Bold", 8)
        if standard_wells:
            total_diluent_ul = sum(w.diluent_ul for w in plate_wells)
            total_diluent_ml = round(total_diluent_ul * 1.1 / 1000, 1)
            c.drawString(
                MARGIN,
                cursor,
                f"Total diluent needed: {total_diluent_ml:.1f} mL (10% excess, {len(plate_wells)} wells); "
                f"BSA stock needed: {stock_volume_ul():g} µL",
            )
        else:
            total_diluent_ml = round(count * diluent_ul * 1.1 / 1000, 1)
            c.drawString(
                MARGIN, cursor, f"Total diluent needed: {total_diluent_ml:.1f} mL (10% excess, {count} wells)"
            )
        cursor -= 14

        if standard_wells:
            if multichannel:
                # Side-by-side to save vertical space: standards (cols 1-2) on the left,
                # blank (col 3) on the right.
                std_rows = sorted(
                    (r for r in standard_wells if r.role == "standard"),
                    key=lambda r: (int(r.well[1:]), r.well[0]),
                )
                blank_rows = sorted(
                    (r for r in standard_wells if r.role == "blank"), key=lambda r: r.well
                )
                half_w = content_w * 0.5
                h1 = _draw_standards_table(c, std_rows, MARGIN, cursor, half_w, font_size=5.0)
                h2 = _draw_standards_table(
                    c, blank_rows, MARGIN + half_w + 6, cursor, half_w, font_size=5.0
                )
                table_h = max(h1, h2)
            else:
                table_rows = sorted(standard_wells, key=lambda r: (r.well[0], int(r.well[1:])))
                table_h = _draw_standards_table(c, table_rows, MARGIN, cursor, content_w, font_size=5.0)
            cursor -= table_h + 6

        if multichannel and plate_transfers:
            transfer_h = _draw_transfer_table(c, plate_transfers, MARGIN, cursor, content_w)
            cursor -= transfer_h + 6

        available_h = cursor - MARGIN
        legend_gap = 10
        rows_per_col = math.ceil(count / 2) + 1 if count else 1
        legend_need = rows_per_col * (5.0 + 1.6)
        grid_h = min(available_h * 0.5, available_h - legend_gap - legend_need)
        grid_h = max(grid_h, available_h * (0.3 if standard_wells else 0.35))
        grid_top = cursor - 8

        cells: dict[str, tuple[str, str]] = {}
        for pw in plate_wells:
            hexcolor = ROLE_FILL[pw.role]
            if pw.role == "standard":
                text = str(int(pw.conc_ugml))
            elif pw.role == "blank":
                text = "BLK"
            else:
                text = pw.short_id
            cells[pw.well] = (hexcolor, text)
        _draw_well_grid(c, MARGIN, grid_top, content_w, grid_h, cells, label_font=8.0)

        legend_top_y = grid_top - grid_h - legend_gap
        legend_available_h = legend_top_y - MARGIN
        _draw_dilution_legend(c, sample_wells, MARGIN, legend_top_y, content_w, legend_available_h)

        c.showPage()

    c.save()
    return n_pages
