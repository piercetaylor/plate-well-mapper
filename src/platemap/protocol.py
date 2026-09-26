"""Auto-generated run protocol: structured document + Markdown/PDF renderers."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from platemap.dilution import (
    STOCK,
    DilutionPlan,
    DilutionWell,
    stock_volume_ul,
    transfer_map as dilution_transfer_map,
)
from platemap.layout import LayoutRow
from platemap.samples import Sample

WR_WELL_UL = 200.0
WR_EXCESS = 1.10
REAGENT_RATIO = 50  # Reagent A : Reagent B = 50 : 1


@dataclass
class Block:
    kind: str  # "paragraph" | "steps" | "table"
    text: str = ""
    items: list = field(default_factory=list)
    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)


@dataclass
class Section:
    title: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class ProtocolDoc:
    title: str
    overview: list[tuple[str, str]]
    sections: list[Section]


def _para(text: str) -> Block:
    return Block(kind="paragraph", text=text)


def _steps(items: list[str]) -> Block:
    return Block(kind="steps", items=list(items))


def _table(headers: list[str], rows: list[list]) -> Block:
    return Block(kind="table", headers=list(headers), rows=[list(r) for r in rows])


def _plate_sample_ranges(layout_rows: list[LayoutRow]) -> list[tuple[int, str, str]]:
    """Return (plate, first_short_id, last_short_id) for the sample rows on each plate."""
    plates = sorted({r.plate for r in layout_rows})
    out = []
    for plate in plates:
        ids = []
        for r in layout_rows:
            if r.plate == plate and r.role == "sample" and r.short_id not in ids:
                ids.append(r.short_id)
        if ids:
            out.append((plate, ids[0], ids[-1]))
    return out


def _wr_volumes(n_wells: int) -> tuple[float, float, float]:
    """Return (total_ul_with_excess, reagent_a_ml, reagent_b_ml) for n_wells at 200 uL/well."""
    total_ul = n_wells * WR_WELL_UL * WR_EXCESS
    a_ul = total_ul * REAGENT_RATIO / (REAGENT_RATIO + 1)
    b_ul = total_ul / (REAGENT_RATIO + 1)
    return total_ul, round(a_ul / 1000, 2), round(b_ul / 1000, 2)


def build_protocol(
    *,
    experiment: str,
    date: str,
    samples: list[Sample],
    layout_rows: list[LayoutRow],
    avoid_edges: bool = False,
    multichannel: bool = False,
    plan: DilutionPlan | None = None,
    dilution_wells: list[DilutionWell] | None = None,
    n_assay_plates: int | None = None,
    standards_warnings: list[str] | None = None,
    file_names: dict[str, str] | None = None,
) -> ProtocolDoc:
    """Build a structured run protocol document from a completed layout (+ optional dilution)."""
    file_names = file_names or {}
    standards_warnings = standards_warnings or []
    n_samples = len(samples)
    plates = sorted({r.plate for r in layout_rows})
    if n_assay_plates is None:
        n_assay_plates = len(plates)
    n_wells_used = len(layout_rows)
    layout_mode = "8-channel column-wise" if multichannel else "row-wise"

    factor = plan.factor if plan else 1.0
    wr_range_low, wr_range_high = 25.0, 2000.0

    # ---- overview -----------------------------------------------------
    plate_ranges = _plate_sample_ranges(layout_rows)
    plate_range_str = "; ".join(f"plate {p}: {lo}-{hi}" for p, lo, hi in plate_ranges) or "n/a"

    overview: list[tuple[str, str]] = [
        ("Experiment", experiment or "(unnamed)"),
        ("Date", date),
        ("Samples", str(n_samples)),
        ("Replicates", "3 per sample"),
        ("Assay plates", f"{n_assay_plates} ({plate_range_str})"),
        ("Wells used", str(n_wells_used)),
        ("Layout mode", layout_mode),
    ]
    if plan:
        overview.append(
            (
                "Dilution",
                f"factor {factor:g}, {plan.sample_volume_ul:g} µL sample + "
                f"{plan.diluent_volume_ul:g} µL diluent per well",
            )
        )
        overview.append(
            (
                "Working range",
                f"{wr_range_low:g}-{wr_range_high:g} µg/mL in well "
                f"({wr_range_low * factor:g}-{wr_range_high * factor:g} µg/mL undiluted sample)",
            )
        )
    else:
        overview.append(("Working range", f"{wr_range_low:g}-{wr_range_high:g} µg/mL in well"))

    for key, label in (
        ("dilution_pdf", "Dilution PDF"),
        ("plate_map_pdf", "Plate map PDF"),
        ("workbook", "Workbook"),
        ("notebook", "Notebook"),
    ):
        if key in file_names:
            overview.append((label, file_names[key]))

    sections: list[Section] = []

    # ---- materials ------------------------------------------------------
    n_dilution_plates = len({w.plate for w in dilution_wells}) if dilution_wells else 0
    materials_lines = [
        "Pierce BCA Protein Assay Kit (Reagent A, Reagent B, BSA standard/ampules).",
        f"{n_assay_plates} clear-bottom 96-well assay plate(s)"
        + (f", {n_dilution_plates} dilution plate(s)" if dilution_wells else "")
        + ".",
    ]
    if dilution_wells:
        total_diluent_ul = sum(w.diluent_ul for w in dilution_wells)
        materials_lines.append(
            f"Diluent (dilution buffer): approx. {round(total_diluent_ul * 1.1 / 1000, 1):.1f} mL "
            "(10% excess) for the dilution plate(s)."
        )
    _wr_total_ul, wr_a_ml, wr_b_ml = _wr_volumes(n_wells_used)
    materials_lines.append(
        f"Working Reagent (WR): Reagent A {wr_a_ml:.2f} mL + Reagent B {wr_b_ml:.2f} mL "
        f"(50:1, 10% excess for {n_wells_used} wells)."
    )
    if multichannel:
        materials_lines.append("8-channel P200 pipette and a reagent reservoir.")
    sections.append(Section("Materials", [_steps(materials_lines)]))

    # ---- before starting --------------------------------------------------
    sample_ul_needed = (plan.sample_volume_ul + 5) if plan else None
    before_lines = [
        "Thaw all samples and standards/BSA ampules completely; equilibrate to room temperature.",
        "Warm the incubator to 37 degrees C.",
        "Label all plates with the experiment name and date before pipetting.",
    ]
    if sample_ul_needed is not None:
        before_lines.insert(
            1,
            f"Ensure at least {sample_ul_needed:g} µL of each sample is available "
            f"({plan.sample_volume_ul:g} µL used + 5 µL dead volume).",
        )
    before_lines.append(
        "Use the SAME diluent for the standards, the blank, and the samples. "
        "The blank must be diluent + Working Reagent, not Working Reagent alone."
    )
    sections.append(Section("Before starting", [_para(x) for x in before_lines]))

    # ---- dilution plate (only when diluting) -------------------------------
    if plan and dilution_wells:
        dil_steps = [
            "Label the dilution plate(s) per the dilution PDF.",
            "Prepare the BSA standards per the standards-prep table below, in stock-then-serial "
            "order, mixing each source well 10x before drawing from it.",
            f"Add {plan.diluent_volume_ul:g} µL diluent, then {plan.sample_volume_ul:g} µL of "
            "each sample, to its dilution well.",
            "Mix all wells by pipetting up and down 10x; avoid bubbles. Seal and spin briefly.",
        ]
        std_rows = sorted(
            (w for w in dilution_wells if w.role in ("standard", "blank")),
            key=lambda w: (w.plate, w.well[0], int(w.well[1:])),
        )
        table_rows = [
            [
                w.well,
                "BLK" if w.role == "blank" else f"{int(w.conc_ugml):g}",
                str(w.source),
                f"{w.source_ul:g}",
                f"{w.diluent_ul:g}",
                f"{w.remaining_ul:g}",
            ]
            for w in std_rows
        ]
        dil_section = Section(
            "Dilution plate",
            [
                _steps(dil_steps),
                _table(
                    ["Well", "Conc (µg/mL)", "Source", "Source µL", "Diluent µL", "Remaining µL"],
                    table_rows,
                ),
                _para(f"BSA stock needed: {stock_volume_ul():g} µL."),
            ],
        )
        if standards_warnings:
            dil_section.blocks.append(
                _steps([f"WARNING: {w}" for w in standards_warnings])
            )
        sections.append(dil_section)

    # ---- working reagent --------------------------------------------------
    wr_total_ul, wr_a_ml, wr_b_ml = _wr_volumes(n_wells_used)
    sections.append(
        Section(
            "Working reagent",
            [
                _para(
                    f"Wells to cover: {n_wells_used}. Volume needed: {n_wells_used * WR_WELL_UL:g} µL "
                    f"(200 µL/well)."
                ),
                _para(
                    f"Prepare with 10% excess: mix Reagent A {wr_a_ml:.2f} mL with Reagent B "
                    f"{wr_b_ml:.2f} mL (50:1 ratio, {wr_total_ul:.0f} µL total)."
                ),
            ],
        )
    )

    # ---- plating -----------------------------------------------------------
    if multichannel:
        transfers = dilution_transfer_map(n_samples) if dilution_wells else []
        plating_steps = []
        if transfers:
            for assay_plate, dplate, dcol, acols, contents in transfers:
                acol_str = ", ".join(str(a) for a in acols)
                plating_steps.append(
                    f"Plate {assay_plate}: dilution plate {dplate} col {dcol} ({contents}) -> "
                    f"assay col(s) {acol_str}, 25 µL, 8-channel pipette."
                )
        else:
            for plate in plates:
                plate_rows = [r for r in layout_rows if r.plate == plate]
                blocks = sorted({(r.col - 4) // 3 for r in plate_rows if r.role == "sample"})
                for block in blocks:
                    cols = (4 + 3 * block, 5 + 3 * block, 6 + 3 * block)
                    plating_steps.append(
                        f"Plate {plate}: source column -> assay cols "
                        f"{', '.join(str(c) for c in cols)}, 25 µL, 8-channel pipette."
                    )
        plating_steps.append(
            f"Add {WR_WELL_UL:g} µL Working Reagent to every used well with an 8-channel "
            "pipette, one assay plate at a time; record the time WR was added for each plate."
        )
        sections.append(Section("Plating", [_steps(plating_steps)]))
    else:
        plating_steps = [
            "Standards: add 25 µL of each standard/blank well to its assay wells (A1-B6 map "
            "1:1; an 8-channel pipette is fine for this block).",
            "Samples: add 25 µL of each dilution/sample well to its 3 triplicate assay wells "
            "(dilution well S# -> assay map S#).",
            f"Add {WR_WELL_UL:g} µL Working Reagent to every used well, one assay plate at a "
            "time; record the time WR was added for each plate.",
        ]
        sections.append(Section("Plating", [_steps(plating_steps)]))

    # ---- incubation & reading ----------------------------------------------
    sections.append(
        Section(
            "Incubation & reading",
            [
                _para(
                    "Incubate all plates at 37 degrees C for 30 minutes, then cool at room "
                    "temperature for 5 minutes."
                ),
                _para(
                    "Read absorbance at 562 nm on the Cytation 5 (Gen5 endpoint protocol). Use "
                    "the same time interval between WR addition and reading for every plate."
                ),
                _para(
                    "Export each plate's results from Gen5 as text, one file per plate, named "
                    f"Plate_N_{file_names.get('prefix', 'platemap')}.txt."
                ),
            ],
        )
    )

    # ---- analysis -----------------------------------------------------------
    workbook = file_names.get("workbook", "platemap_plates.xlsx")
    prefix = file_names.get("prefix", "platemap")
    reader_files = " ".join(f"Plate_{p}_{prefix}.txt" for p in plates) or "Plate_1_<prefix>.txt"
    read_cmd = f"platemap read {workbook} {reader_files}"
    mapped_csv = f"{workbook.rsplit('.', 1)[0].removesuffix('_plates')}_plates_mapped.csv"
    analyze_cmd = f"platemap analyze {mapped_csv}"
    analysis_notes = [
        f"`{read_cmd}`",
        f"`{analyze_cmd}`",
    ]
    if file_names.get("blank_is_wr_only"):
        analysis_notes.append("Add `--no-blank-in-fit` (the blank was WR only, not diluent + WR).")
    analysis_notes.append(
        "The Gen5 protocol layout must match this layout, or pass `--no-layout-check` to "
        "`platemap read`."
    )
    sections.append(Section("Analysis", [_steps(analysis_notes)]))

    # ---- QC -----------------------------------------------------------------
    sections.append(
        Section(
            "QC checks",
            [
                _steps(
                    [
                        "Standard curve R^2 >= 0.99.",
                        "Blank absorbance is similar across plates.",
                        "Replicate %CV < 15% for samples and standards.",
                        "Re-run any out-of-range sample at a different dilution factor.",
                    ]
                )
            ],
        )
    )

    # ---- buffer compatibility -------------------------------------------------
    sections.append(
        Section(
            "Buffer compatibility",
            [
                _para(
                    "Reducing agents (DTT, TCEP, beta-mercaptoethanol), imidazole above 50 mM, "
                    "and chelators (EDTA, EGTA) above 10 mM can interfere with the BCA reaction. "
                    "Lower dilution factors dilute these interferents less; consider a higher "
                    "dilution factor if interference is suspected."
                )
            ],
        )
    )

    # ---- record table --------------------------------------------------------
    record_rows = [[f"Plate {p}", "", "", "", ""] for p in plates] or [["Plate 1", "", "", "", ""]]
    sections.append(
        Section(
            "Record",
            [
                _table(
                    ["Plate", "WR lot", "Sample/std lot", "WR added (time)", "Read (time)"],
                    record_rows,
                ),
                _para("Initials: ________"),
            ],
        )
    )

    return ProtocolDoc(title=f"BCA assay protocol: {experiment or '(unnamed)'}", overview=overview, sections=sections)


def write_protocol_md(doc: ProtocolDoc, path: str) -> None:
    """Render a ProtocolDoc to a Markdown file."""
    lines = [f"# {doc.title}", ""]
    lines.append("## Overview")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    for k, v in doc.overview:
        lines.append(f"| {k} | {v} |")
    lines.append("")

    for section in doc.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        for block in section.blocks:
            if block.kind == "paragraph":
                lines.append(block.text)
                lines.append("")
            elif block.kind == "steps":
                for i, item in enumerate(block.items, start=1):
                    lines.append(f"{i}. {item}")
                lines.append("")
            elif block.kind == "table":
                lines.append("| " + " | ".join(block.headers) + " |")
                lines.append("| " + " | ".join("---" for _ in block.headers) + " |")
                for row in block.rows:
                    lines.append("| " + " | ".join(str(v) for v in row) + " |")
                lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


_PDF_UNSAFE = {
    "→": "->",
    "≥": ">=",
    "≤": "<=",
}


def _pdf_text(text: str, markup: bool = True) -> str:
    """Replace glyphs not present in the standard Helvetica/WinAnsi encoding."""
    for bad, good in _PDF_UNSAFE.items():
        text = text.replace(bad, good)
    if not markup:  # plain table cells
        return text.replace("`", "")
    # Paragraph markup: escape, then render `code` spans in a monospace font.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"`([^`]+)`", lambda m: f'<font name="Courier">{m.group(1)}</font>', text)


def _count_pdf_pages(path: str) -> int:
    with open(path, "rb") as fh:
        data = fh.read()
    matches = re.findall(rb"/Type\s*/Page[^s]", data)
    return max(len(matches), 1)


def write_protocol_pdf(doc: ProtocolDoc, path: str) -> int:
    """Render a ProtocolDoc to a PDF (US Letter, 0.75in margins) and return the page count."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        KeepTogether,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body9", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=12)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=17)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14)

    story = []
    story.append(Paragraph(_pdf_text(doc.title), h1))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Overview", h2))
    overview_rows = [["Field", "Value"]] + [[k, _pdf_text(str(v), markup=False)] for k, v in doc.overview]
    overview_table = Table(overview_rows, colWidths=[1.6 * inch, 5.15 * inch], repeatRows=1)
    overview_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9D9D9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(KeepTogether([overview_table]))
    story.append(Spacer(1, 10))

    for section in doc.sections:
        story.append(Paragraph(_pdf_text(section.title), h2))
        for block in section.blocks:
            if block.kind == "paragraph":
                story.append(Paragraph(_pdf_text(block.text), body))
                story.append(Spacer(1, 4))
            elif block.kind == "steps":
                items = [ListItem(Paragraph(_pdf_text(t), body)) for t in block.items]
                story.append(ListFlowable(
                    items,
                    bulletType="1",
                    start=1,
                    leftIndent=16,
                    bulletFontName=body.fontName,
                    bulletFontSize=body.fontSize,
                    bulletFormat="%s.",
                ))
                story.append(Spacer(1, 6))
            elif block.kind == "table":
                rows = [[_pdf_text(h, markup=False) for h in block.headers]] + [
                    [_pdf_text(str(v), markup=False) for v in row] for row in block.rows
                ]
                table = Table(rows, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9D9D9")),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))
        story.append(Spacer(1, 6))

    doc_template = SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=doc.title,
    )
    doc_template.build(story)
    return _count_pdf_pages(path)
