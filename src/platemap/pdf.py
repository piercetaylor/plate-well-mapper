"""PDF plate map generation."""

import math

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

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


def _draw_plate(c: canvas.Canvas, rects: tuple[float, float, float, float], plate: int, plate_rows: list[LayoutRow]) -> None:
    x, y, w, h = rects
    grid_h = h * 0.62
    legend_top = y + h - grid_h - 0.05 * inch
    legend_available_h = legend_top - y - 0.05 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y + h - 0.15 * inch, f"Plate {plate}")

    grid_top = y + h - 0.35 * inch
    grid_left = x + 0.25 * inch
    n_cols = len(COLS_FULL)
    n_rows = len(ROWS_FULL)
    cell_w = (w - 0.3 * inch) / n_cols
    cell_h = (grid_top - (y + h - grid_h)) / n_rows
    radius = min(cell_w, cell_h) * 0.42

    c.setFont("Helvetica", 6)
    for i, col in enumerate(COLS_FULL):
        cx = grid_left + (i + 0.5) * cell_w
        c.drawCentredString(cx, grid_top + 0.03 * inch, str(col))
    for j, row in enumerate(ROWS_FULL):
        cy = grid_top - (j + 0.5) * cell_h
        c.drawRightString(grid_left - 0.05 * inch, cy - 2, row)

    by_well = {row.well: row for row in plate_rows}
    for j, row_letter in enumerate(ROWS_FULL):
        for i, col in enumerate(COLS_FULL):
            well = f"{row_letter}{col}"
            cx = grid_left + (i + 0.5) * cell_w
            cy = grid_top - (j + 0.5) * cell_h
            lr = by_well.get(well)
            if lr is None:
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.circle(cx, cy, radius, stroke=1, fill=0)
                continue
            hexcolor = ROLE_FILL[lr.role]
            c.setFillColor(HexColor(f"#{hexcolor}"))
            c.setStrokeColorRGB(0.3, 0.3, 0.3)
            c.circle(cx, cy, radius, stroke=1, fill=1)
            c.setFillColorRGB(0, 0, 0)
            if lr.role == "standard":
                text = str(int(lr.conc_ugml))
            elif lr.role == "blank":
                text = "BLK"
            else:
                text = lr.short_id
            font_size = _fit_font(text, radius * 1.7)
            c.setFont("Helvetica", font_size)
            c.drawCentredString(cx, cy - font_size * 0.35, text)

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
            seen_samples[lr.short_id] = f"{lr.short_id} — {lr.label}{suffix}"

    std_line = ""
    if std_concs:
        std_concs_sorted = sorted(std_concs, reverse=True)
        conc_str = "/".join(str(int(v)) for v in std_concs_sorted)
        std_line = f"Standards (STD<conc>): BSA {conc_str} µg/mL"
        if has_blank:
            std_line += "; BLK = Blank"

    sample_entries = list(seen_samples.values())

    # Shrink font/columns until everything fits in the available legend height.
    font_size, line_h, n_cols = 6.0, 7.2, 2
    for candidate_font in (6.0, 5.5, 5.0, 4.5, 4.0):
        candidate_line_h = candidate_font + 1.4
        std_rows = 1 if std_line else 0
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

    col_w = w / n_cols
    rows_per_col = math.ceil(len(sample_entries) / n_cols) if sample_entries else 0
    for idx, entry in enumerate(sample_entries):
        col = idx // rows_per_col if rows_per_col else 0
        row = idx % rows_per_col if rows_per_col else 0
        cx = x + col * col_w
        cy = ly - row * line_h
        c.drawString(cx, cy, _truncate(entry, max_chars))


def write_pdf(rows: list[LayoutRow], path: str, experiment: str = "", date: str = "") -> int:
    """Write a plate map PDF (US Letter, 2x2 plates/page) and return the page count."""
    plates = sorted({row.plate for row in rows})
    n_pages = math.ceil(len(plates) / 4) if plates else 0

    c = canvas.Canvas(path, pagesize=letter)
    for page in range(n_pages):
        page_plates = plates[page * 4 : page * 4 + 4]

        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, PAGE_H - MARGIN - 12, f"Experiment: {experiment}")
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, PAGE_H - MARGIN - 28, f"Date: {date}")
        c.drawString(MARGIN, PAGE_H - MARGIN - 42, "Operator: ________")

        rects = _panel_rects()
        for plate, rect in zip(page_plates, rects):
            plate_rows = [r for r in rows if r.plate == plate]
            _draw_plate(c, rect, plate, plate_rows)

        c.showPage()

    c.save()
    return n_pages
