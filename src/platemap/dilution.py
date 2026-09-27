"""Pre-dilution planning: BSA standard prep + sample dilution -> dilution plate(s)."""

import csv
import math
from dataclasses import dataclass, replace

from platemap.layout import validate_wr_only_blank_cols
from platemap.samples import PlatemapError, Sample
from platemap.wells import ROWS_FULL, usable_wells

DILUTION_WELLS = usable_wells(False)
N_DILUTION_WELLS = len(DILUTION_WELLS)

STANDARD_FINAL_UL = 200.0

# Order standards are placed on plate 1 (also the stock/serial prep order for
# 2000/1500/1000, then the serial-transfer order 750/500/250/125/25); 0 is the blank.
STANDARD_ORDER = (2000, 1500, 1000, 750, 500, 250, 125, 25, 0)
STANDARD_PREP_ORDER = (2000, 1500, 1000, 750, 500, 250, 125, 25)

STOCK = "BSA stock"
DILUENT = "diluent"

# conc_ugml -> (source, source_ul, diluent_ul); source is STOCK, DILUENT, or another
# concentration (drawn from that concentration's same-replicate well). Final volume for
# every standard/blank well is STANDARD_FINAL_UL.
STANDARD_PREP: dict[float, tuple[object, float, float]] = {
    2000: (STOCK, 200, 0),
    1500: (STOCK, 150, 50),
    1000: (STOCK, 100, 100),
    750: (1500, 100, 100),
    500: (1000, 100, 100),
    250: (500, 100, 100),
    125: (250, 100, 100),
    25: (125, 40, 160),
    0: (DILUENT, 0, 200),
}

# Wells reserved for the standard curve + blank on dilution plate 1 (9 groups x 2 wells).
STANDARD_WELLS_USED = 2 * len(STANDARD_ORDER)
PLATE1_SAMPLE_CAPACITY = N_DILUTION_WELLS - STANDARD_WELLS_USED

# Multichannel dilution plate 1: col 1 = std rep1, col 2 = std rep2, col 3 = blank,
# cols 4-12 = samples (9 columns x 8 rows). Further plates use all 12 columns.
PLATE1_SAMPLE_CAPACITY_MC = 72
N_DILUTION_WELLS_MC = 96
MULTICHANNEL_ASSAY_CAPACITY = 24

# 12-channel dilution plate 1: rows A/B = standards, blanks A9-A12/B9-B12,
# rows C-H = samples (6 rows x 12 columns = 72). Further plates use rows A-H
# (96 samples), no standards.
PLATE1_SAMPLE_CAPACITY_12 = 72
N_DILUTION_WELLS_12 = 96


@dataclass(frozen=True)
class DilutionPlan:
    factor: float
    final_volume_ul: float
    sample_volume_ul: float
    diluent_volume_ul: float


def make_plan(factor: float = 20, final_volume_ul: float = 200) -> DilutionPlan:
    """Compute a 1-step dilution plan for the given factor and final volume."""
    if factor <= 1:
        raise PlatemapError(f"dilution factor must be > 1 (got {factor:g})")
    if final_volume_ul <= 0:
        raise PlatemapError(f"final volume must be > 0 (got {final_volume_ul:g})")
    if final_volume_ul > 300:
        raise PlatemapError(
            f"final volume {final_volume_ul:g} µL exceeds standard 96-well capacity "
            "(300 µL); a deep-well plate is not modelled"
        )
    sample_volume_ul = final_volume_ul / factor
    if sample_volume_ul < 2:
        raise PlatemapError(
            f"sample volume {sample_volume_ul:g} µL is below reliable pipetting accuracy "
            "(2 µL); raise --final-volume"
        )
    diluent_volume_ul = final_volume_ul - sample_volume_ul
    return DilutionPlan(
        factor=factor,
        final_volume_ul=final_volume_ul,
        sample_volume_ul=sample_volume_ul,
        diluent_volume_ul=diluent_volume_ul,
    )


@dataclass(frozen=True)
class DilutionWell:
    plate: int
    well: str
    role: str  # "standard" | "blank" | "sample"
    short_id: str
    label: str
    conc_ugml: float | None
    source: str
    source_ul: float
    diluent_ul: float
    final_ul: float
    remaining_ul: float


def _amount_drawn_from() -> dict[float, float]:
    """Map conc -> total µL drawn out of that conc's well(s) as a source for another conc."""
    drawn: dict[float, float] = {}
    for source, source_ul, _diluent_ul in STANDARD_PREP.values():
        if isinstance(source, (int, float)):
            drawn[source] = drawn.get(source, 0.0) + source_ul
    return drawn


def standard_remaining_ul(conc: float) -> float:
    """µL left in a standard/blank well after any serial transfer drawn from it."""
    drawn = _amount_drawn_from()
    return STANDARD_FINAL_UL - drawn.get(conc, 0.0)


def stock_volume_ul() -> float:
    """Total BSA stock µL needed (both replicate wells) for the standard prep scheme."""
    return sum(
        source_ul * 2
        for source, source_ul, _diluent_ul in STANDARD_PREP.values()
        if source == STOCK
    )


def standard_prep_warnings(n_assay_plates: int) -> list[str]:
    """Warn for any standard/blank well that won't have enough volume left for all assay plates."""
    need_ul = 25 * n_assay_plates
    warnings: list[str] = []
    for conc in STANDARD_ORDER:
        remaining = standard_remaining_ul(conc)
        if remaining < need_ul:
            short_id = "BLK" if conc == 0 else f"STD{int(conc)}"
            warnings.append(
                f"{short_id} well has {remaining:g} µL remaining, needs {need_ul:g} µL "
                f"for {n_assay_plates} assay plate(s)"
            )
    return warnings


def dilution_plate_count(
    n_samples: int, multichannel: bool = False, channels: int | None = None
) -> int:
    """Number of dilution plates needed: plate 1 holds standards + samples, 2+ samples only."""
    if channels is None and multichannel:
        channels = 8
    if channels == 12:
        if n_samples <= 0:
            return 0
        if n_samples <= PLATE1_SAMPLE_CAPACITY_12:
            return 1
        remaining = n_samples - PLATE1_SAMPLE_CAPACITY_12
        return 1 + math.ceil(remaining / N_DILUTION_WELLS_12)

    if channels == 8:
        if n_samples <= 0:
            return 0
        if n_samples <= PLATE1_SAMPLE_CAPACITY_MC:
            return 1
        remaining = n_samples - PLATE1_SAMPLE_CAPACITY_MC
        return 1 + math.ceil(remaining / N_DILUTION_WELLS_MC)

    if n_samples <= PLATE1_SAMPLE_CAPACITY:
        return 1
    remaining = n_samples - PLATE1_SAMPLE_CAPACITY
    return 1 + math.ceil(remaining / N_DILUTION_WELLS)


def _sample_plate_well(index0: int) -> tuple[int, str]:
    """Return (plate, well) for the index0'th (0-based) sample across all samples."""
    if index0 < PLATE1_SAMPLE_CAPACITY:
        return 1, DILUTION_WELLS[STANDARD_WELLS_USED + index0]
    remaining = index0 - PLATE1_SAMPLE_CAPACITY
    plate = 2 + remaining // N_DILUTION_WELLS
    well = DILUTION_WELLS[remaining % N_DILUTION_WELLS]
    return plate, well


def _col_major_wells(start_col: int, end_col: int) -> list[str]:
    """Column-major well order (down each column, left to right) for the given column range."""
    return [f"{r}{c}" for c in range(start_col, end_col + 1) for r in ROWS_FULL]


def _sample_plate_well_mc(index0: int) -> tuple[int, str]:
    """Return (plate, well) for the index0'th (0-based) sample, multichannel column-wise mode."""
    if index0 < PLATE1_SAMPLE_CAPACITY_MC:
        wells = _col_major_wells(4, 12)
        return 1, wells[index0]
    remaining = index0 - PLATE1_SAMPLE_CAPACITY_MC
    plate = 2 + remaining // N_DILUTION_WELLS_MC
    wells = _col_major_wells(1, 12)
    return plate, wells[remaining % N_DILUTION_WELLS_MC]


def _sample_plate_well_12(index0: int) -> tuple[int, str]:
    """Return (plate, well) for the index0'th (0-based) sample, 12-channel row-wise mode."""
    if index0 < PLATE1_SAMPLE_CAPACITY_12:
        row_idx = 2 + index0 // 12
        col = 1 + index0 % 12
        return 1, f"{ROWS_FULL[row_idx]}{col}"
    remaining = index0 - PLATE1_SAMPLE_CAPACITY_12
    plate = 2 + remaining // N_DILUTION_WELLS_12
    r = remaining % N_DILUTION_WELLS_12
    row_idx = r // 12
    col = 1 + r % 12
    return plate, f"{ROWS_FULL[row_idx]}{col}"


def _dilution_col_for_group(g: int) -> tuple[int, int]:
    """Return (dilution_plate, dilution_column) for global 8-sample column group g (0-based)."""
    if g < 9:
        return 1, 4 + g
    g2 = g - 9
    return 2 + g2 // 12, 1 + g2 % 12


def _dilution_row_for_group(g: int) -> tuple[int, str]:
    """Return (dilution_plate, dilution_row) for global 12-sample row group g (0-based)."""
    if g < 6:
        return 1, ROWS_FULL[2 + g]
    g2 = g - 6
    return 2 + g2 // 8, ROWS_FULL[g2 % 8]


def transfer_map(
    n_samples: int, channels: int = 8, replicates: int = 3
) -> list[tuple[int, int, object, tuple, str]]:
    """Return (assay_plate, dilution_plate, dilution_index, assay_indices, contents) transfers.

    8-channel: whole-column transfers, dilution_index/assay_indices are column numbers.
    12-channel: whole-row transfers, dilution_index/assay_indices are row letters.
    Standards (dilution col/row 1 -> assay col/row 1, etc. on every assay plate) plus one
    entry per `n`-sample dilution lane (8 for columns, 12 for rows) feeding its
    `replicates`-wide assay lanes.
    """
    if n_samples <= 0:
        return []

    if channels == 12:
        n_dil_rows = math.ceil(n_samples / 12)
        groups_per_plate = 6 // replicates
        cap = groups_per_plate * 12
        n_assay_plates = math.ceil(n_samples / cap)

        entries: list[tuple[int, int, object, tuple, str]] = []
        for p in range(1, n_assay_plates + 1):
            entries.append((p, 1, "A", ("A",), "standards rep1"))
            entries.append((p, 1, "B", ("B",), "standards rep2"))
            for slot in range(groups_per_plate):
                g = groups_per_plate * (p - 1) + slot
                if g >= n_dil_rows:
                    break
                dplate, drow = _dilution_row_for_group(g)
                start_row_idx = 2 + slot * replicates
                arows = tuple(ROWS_FULL[start_row_idx : start_row_idx + replicates])
                first = g * 12 + 1
                last = min(g * 12 + 12, n_samples)
                contents = f"S{first}" if first == last else f"S{first}-S{last}"
                entries.append((p, dplate, drow, arows, contents))
        return entries

    n_dil_cols = math.ceil(n_samples / 8)
    groups_per_plate = 9 // replicates
    cap = groups_per_plate * 8
    n_assay_plates = math.ceil(n_samples / cap)

    entries = []
    for p in range(1, n_assay_plates + 1):
        entries.append((p, 1, 1, (1,), "standards rep1"))
        entries.append((p, 1, 2, (2,), "standards rep2"))
        entries.append((p, 1, 3, (3,), "blank"))
        for slot in range(groups_per_plate):
            g = groups_per_plate * (p - 1) + slot
            if g >= n_dil_cols:
                break
            dplate, dcol = _dilution_col_for_group(g)
            acols = tuple(4 + replicates * slot + k for k in range(replicates))
            first = g * 8 + 1
            last = min(g * 8 + 8, n_samples)
            contents = f"S{first}" if first == last else f"S{first}-S{last}"
            entries.append((p, dplate, dcol, acols, contents))
    return entries


def apply_dilution(samples: list[Sample], factor: float) -> list[Sample]:
    """Return new Samples with dilution_factor multiplied by factor."""
    return [replace(s, dilution_factor=s.dilution_factor * factor) for s in samples]


def _build_dilution_layout_mc(samples: list[Sample], plan: DilutionPlan) -> list[DilutionWell]:
    """Multichannel dilution plate 1: col 1/2 = standards, col 3 = blank, cols 4-12 = samples."""
    wells_out: list[DilutionWell] = []

    conc_wells: dict[float, tuple[str, str]] = {}
    for row_idx, conc in enumerate(STANDARD_PREP_ORDER):
        row_letter = ROWS_FULL[row_idx]
        conc_wells[conc] = (f"{row_letter}1", f"{row_letter}2")

    for conc in STANDARD_PREP_ORDER:
        source, source_ul, diluent_ul = STANDARD_PREP[conc]
        remaining_ul = standard_remaining_ul(conc)
        for rep, well in enumerate(conc_wells[conc], start=1):
            if isinstance(source, (int, float)):
                source_label = conc_wells[source][rep - 1]
            else:
                source_label = source
            wells_out.append(
                DilutionWell(
                    plate=1,
                    well=well,
                    role="standard",
                    short_id=f"STD{int(conc)}",
                    label=f"BSA {int(conc)} µg/mL",
                    conc_ugml=float(conc),
                    source=source_label,
                    source_ul=float(source_ul),
                    diluent_ul=float(diluent_ul),
                    final_ul=STANDARD_FINAL_UL,
                    remaining_ul=remaining_ul,
                )
            )

    blank_source, blank_source_ul, blank_diluent_ul = STANDARD_PREP[0]
    blank_remaining_ul = standard_remaining_ul(0)
    for row_letter in ROWS_FULL:
        wells_out.append(
            DilutionWell(
                plate=1,
                well=f"{row_letter}3",
                role="blank",
                short_id="BLK",
                label="Blank",
                conc_ugml=0.0,
                source=blank_source,
                source_ul=float(blank_source_ul),
                diluent_ul=float(blank_diluent_ul),
                final_ul=STANDARD_FINAL_UL,
                remaining_ul=blank_remaining_ul,
            )
        )

    for i, samp in enumerate(samples, start=1):
        plate, well = _sample_plate_well_mc(i - 1)
        wells_out.append(
            DilutionWell(
                plate=plate,
                well=well,
                role="sample",
                short_id=f"S{i}",
                label=samp.sample_name,
                conc_ugml=None,
                source="sample",
                source_ul=plan.sample_volume_ul,
                diluent_ul=plan.diluent_volume_ul,
                final_ul=plan.final_volume_ul,
                remaining_ul=plan.final_volume_ul,
            )
        )

    return wells_out


def _build_dilution_layout_12ch(
    samples: list[Sample], plan: DilutionPlan, wr_only_blank_cols: int = 0
) -> list[DilutionWell]:
    """12-channel dilution plate 1: row A/B = standards, blanks A9-A12/B9-B12, rows C-H = samples.

    The last `wr_only_blank_cols` blank columns (9-12) are left empty (reagent_blank,
    no diluent) so the whole-row transfer carries nothing into those assay wells.
    """
    wells_out: list[DilutionWell] = []

    conc_wells: dict[float, tuple[str, str]] = {}
    for col_idx, conc in enumerate(STANDARD_PREP_ORDER):
        col = col_idx + 1
        conc_wells[conc] = (f"A{col}", f"B{col}")

    for conc in STANDARD_PREP_ORDER:
        source, source_ul, diluent_ul = STANDARD_PREP[conc]
        remaining_ul = standard_remaining_ul(conc)
        for rep, well in enumerate(conc_wells[conc], start=1):
            if isinstance(source, (int, float)):
                source_label = conc_wells[source][rep - 1]
            else:
                source_label = source
            wells_out.append(
                DilutionWell(
                    plate=1,
                    well=well,
                    role="standard",
                    short_id=f"STD{int(conc)}",
                    label=f"BSA {int(conc)} µg/mL",
                    conc_ugml=float(conc),
                    source=source_label,
                    source_ul=float(source_ul),
                    diluent_ul=float(diluent_ul),
                    final_ul=STANDARD_FINAL_UL,
                    remaining_ul=remaining_ul,
                )
            )

    blank_source, blank_source_ul, blank_diluent_ul = STANDARD_PREP[0]
    blank_remaining_ul = standard_remaining_ul(0)
    wr_only_cols = set(range(13 - wr_only_blank_cols, 13)) if wr_only_blank_cols else set()
    for row_letter in ("A", "B"):
        for col in (9, 10, 11, 12):
            if col in wr_only_cols:
                wells_out.append(
                    DilutionWell(
                        plate=1,
                        well=f"{row_letter}{col}",
                        role="reagent_blank",
                        short_id="WR",
                        label="WR only (no buffer)",
                        conc_ugml=None,
                        source="",
                        source_ul=0.0,
                        diluent_ul=0.0,
                        final_ul=0.0,
                        remaining_ul=0.0,
                    )
                )
            else:
                wells_out.append(
                    DilutionWell(
                        plate=1,
                        well=f"{row_letter}{col}",
                        role="blank",
                        short_id="BLK",
                        label="Blank",
                        conc_ugml=0.0,
                        source=blank_source,
                        source_ul=float(blank_source_ul),
                        diluent_ul=float(blank_diluent_ul),
                        final_ul=STANDARD_FINAL_UL,
                        remaining_ul=blank_remaining_ul,
                    )
                )

    for i, samp in enumerate(samples, start=1):
        plate, well = _sample_plate_well_12(i - 1)
        wells_out.append(
            DilutionWell(
                plate=plate,
                well=well,
                role="sample",
                short_id=f"S{i}",
                label=samp.sample_name,
                conc_ugml=None,
                source="sample",
                source_ul=plan.sample_volume_ul,
                diluent_ul=plan.diluent_volume_ul,
                final_ul=plan.final_volume_ul,
                remaining_ul=plan.final_volume_ul,
            )
        )

    return wells_out


def build_dilution_layout(
    samples: list[Sample],
    plan: DilutionPlan,
    multichannel: bool = False,
    channels: int | None = None,
    wr_only_blank_cols: int = 0,
) -> list[DilutionWell]:
    """Build dilution plate 1 (BSA standards + blank + samples) plus any overflow sample plates."""
    if channels is None and multichannel:
        channels = 8
    validate_wr_only_blank_cols(wr_only_blank_cols, channels)
    if channels == 12:
        return _build_dilution_layout_12ch(samples, plan, wr_only_blank_cols)
    if channels == 8:
        return _build_dilution_layout_mc(samples, plan)

    wells_out: list[DilutionWell] = []

    # Standards + blank always go on plate 1, mirroring the assay's rows A-B.
    conc_wells: dict[float, tuple[str, str]] = {}
    idx = 0
    for conc in STANDARD_ORDER:
        conc_wells[conc] = (DILUTION_WELLS[idx], DILUTION_WELLS[idx + 1])
        idx += 2

    for conc in STANDARD_ORDER:
        source, source_ul, diluent_ul = STANDARD_PREP[conc]
        remaining_ul = standard_remaining_ul(conc)
        role = "blank" if conc == 0 else "standard"
        short_id = "BLK" if conc == 0 else f"STD{int(conc)}"
        label = "Blank" if conc == 0 else f"BSA {int(conc)} µg/mL"
        for rep, well in enumerate(conc_wells[conc], start=1):
            if isinstance(source, (int, float)):
                source_label = conc_wells[source][rep - 1]
            else:
                source_label = source
            wells_out.append(
                DilutionWell(
                    plate=1,
                    well=well,
                    role=role,
                    short_id=short_id,
                    label=label,
                    conc_ugml=float(conc),
                    source=source_label,
                    source_ul=float(source_ul),
                    diluent_ul=float(diluent_ul),
                    final_ul=STANDARD_FINAL_UL,
                    remaining_ul=remaining_ul,
                )
            )

    for i, samp in enumerate(samples, start=1):
        plate, well = _sample_plate_well(i - 1)
        wells_out.append(
            DilutionWell(
                plate=plate,
                well=well,
                role="sample",
                short_id=f"S{i}",
                label=samp.sample_name,
                conc_ugml=None,
                source="sample",
                source_ul=plan.sample_volume_ul,
                diluent_ul=plan.diluent_volume_ul,
                final_ul=plan.final_volume_ul,
                remaining_ul=plan.final_volume_ul,
            )
        )

    return wells_out


def write_samples_csv(samples: list[Sample], path: str) -> None:
    """Write diluted samples to a CSV (sample_name, dilution_factor, notes)."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(("sample_name", "dilution_factor", "notes"))
        for s in samples:
            writer.writerow((s.sample_name, f"{s.dilution_factor:g}", s.notes))


def write_dilution_csv(wells: list[DilutionWell], path: str) -> None:
    """Write the dilution plate layout (standards + blank + samples) to a CSV."""
    columns = (
        "plate",
        "well",
        "role",
        "short_id",
        "label",
        "conc_ugml",
        "source",
        "source_ul",
        "diluent_ul",
        "final_ul",
        "remaining_ul",
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for w in wells:
            writer.writerow(
                ["" if getattr(w, c) is None else getattr(w, c) for c in columns]
            )
