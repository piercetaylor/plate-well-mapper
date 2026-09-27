"""Plate layout: standards + sample placement across 96-well plates."""

import csv
import math
from dataclasses import dataclass

from platemap.samples import PlatemapError, Sample
from platemap.wells import COLS_EDGE, COLS_FULL, ROWS_FULL, usable_wells

STANDARD_CONCS = (2000, 1500, 1000, 750, 500, 250, 125, 25, 0)

# BSA standard concentrations, in the order they run down a multichannel
# standards column (row A..H); the blank has its own column (no 0 here).
STANDARD_CONCS_MC = (2000, 1500, 1000, 750, 500, 250, 125, 25)

MULTICHANNEL_CAPACITY = 24

# Number of dilution-side sample "lanes" per assay plate for each channel mode:
# 8-channel has 9 sample columns (4-12) on dilution plate 1; 12-channel has 6
# sample rows (C-H) on dilution plate 1. Grouped into `replicates`-wide bundles.
_LANES_8CH = 9
_LANES_12CH = 6


def _mc_capacity(channels: int, replicates: int) -> int:
    lanes = _LANES_8CH if channels == 8 else _LANES_12CH
    n_per_lane = 8 if channels == 8 else 12
    return (lanes // replicates) * n_per_lane

ROLE_FILL = {
    "standard": "FFC000",
    "blank": "A6A6A6",
    "sample": "9DC3E6",
}

LAYOUT_COLUMNS = (
    "plate",
    "well",
    "row",
    "col",
    "role",
    "short_id",
    "label",
    "conc_ugml",
    "sample_name",
    "dilution_factor",
    "replicate",
    "notes",
)


@dataclass(frozen=True)
class LayoutRow:
    plate: int
    well: str
    row: str
    col: int
    role: str
    short_id: str
    label: str
    conc_ugml: float | None
    sample_name: str | None
    dilution_factor: float | None
    replicate: int
    notes: str


def _row_len(avoid_edges: bool) -> int:
    return len(COLS_EDGE) if avoid_edges else len(COLS_FULL)


def _try_place(n_wells: int, row_len: int, idx: int, size: int) -> int | None:
    """Return the starting index for a group of `size`, or None if it doesn't fit."""
    while True:
        if idx >= n_wells:
            return None
        row_start = (idx // row_len) * row_len
        row_end = row_start + row_len
        if idx + size <= row_end:
            return idx
        idx = row_end


def capacity(
    avoid_edges: bool = False,
    multichannel: bool = False,
    channels: int | None = None,
    replicates: int = 3,
) -> int:
    """Max number of samples that fit on one plate after standards.

    Row-wise mode places samples in groups of `replicates` wells. Multichannel
    modes (channels=8 or 12) place samples in `replicates`-wide bundles of
    dilution-plate lanes (columns for 8-channel, rows for 12-channel).
    """
    if channels is None and multichannel:
        channels = 8
    if channels is not None:
        if avoid_edges:
            raise PlatemapError("--avoid-edges is not supported with --multichannel")
        return _mc_capacity(channels, replicates)

    wells = usable_wells(avoid_edges)
    row_len = _row_len(avoid_edges)
    n_wells = len(wells)

    idx = 0
    for _ in STANDARD_CONCS:
        start = _try_place(n_wells, row_len, idx, 2)
        if start is None:
            break
        idx = start + 2

    count = 0
    while True:
        start = _try_place(n_wells, row_len, idx, replicates)
        if start is None:
            break
        idx = start + replicates
        count += 1
    return count


def n_plates(
    n: int,
    avoid_edges: bool = False,
    multichannel: bool = False,
    channels: int | None = None,
    replicates: int = 3,
) -> int:
    """Number of plates needed to hold n samples."""
    if n <= 0:
        return 0
    cap = capacity(avoid_edges, multichannel, channels, replicates)
    return math.ceil(n / cap)


def _build_layout_multichannel(samples: list[Sample], replicates: int = 3) -> list[LayoutRow]:
    """Place standards (cols 1-2), blank (col 3), and samples (cols 4-12, 8-channel) per plate."""
    n = len(samples)
    cap = _mc_capacity(8, replicates)
    n_plates_needed = math.ceil(n / cap) if n > 0 else 0

    rows_out: list[LayoutRow] = []
    for plate in range(1, n_plates_needed + 1):
        for row_idx, conc in enumerate(STANDARD_CONCS_MC):
            row_letter = ROWS_FULL[row_idx]
            for rep, col in ((1, 1), (2, 2)):
                well = f"{row_letter}{col}"
                rows_out.append(
                    LayoutRow(
                        plate=plate,
                        well=well,
                        row=row_letter,
                        col=col,
                        role="standard",
                        short_id=f"STD{conc}",
                        label=f"BSA {conc} µg/mL",
                        conc_ugml=float(conc),
                        sample_name=None,
                        dilution_factor=None,
                        replicate=rep,
                        notes="",
                    )
                )

        for row_idx, row_letter in enumerate(ROWS_FULL):
            well = f"{row_letter}3"
            rows_out.append(
                LayoutRow(
                    plate=plate,
                    well=well,
                    row=row_letter,
                    col=3,
                    role="blank",
                    short_id="BLK",
                    label="Blank",
                    conc_ugml=0.0,
                    sample_name=None,
                    dilution_factor=None,
                    replicate=row_idx + 1,
                    notes="",
                )
            )

        start = (plate - 1) * cap
        end = min(start + cap, n)
        for k in range(start, end):
            idx_in_plate = k - start
            block = idx_in_plate // 8
            row_idx = idx_in_plate % 8
            row_letter = ROWS_FULL[row_idx]
            cols = tuple(4 + replicates * block + c for c in range(replicates))
            samp = samples[k]
            global_index = k + 1
            for rep, col in enumerate(cols, start=1):
                well = f"{row_letter}{col}"
                rows_out.append(
                    LayoutRow(
                        plate=plate,
                        well=well,
                        row=row_letter,
                        col=col,
                        role="sample",
                        short_id=f"S{global_index}",
                        label=samp.sample_name,
                        conc_ugml=None,
                        sample_name=samp.sample_name,
                        dilution_factor=samp.dilution_factor,
                        replicate=rep,
                        notes=samp.notes,
                    )
                )

    return rows_out


def _dilution_row_for_group(g: int) -> tuple[int, str]:
    """Return (dilution_plate, dilution_row) for global 12-sample row group g (0-based)."""
    if g < 6:
        return 1, ROWS_FULL[2 + g]
    g2 = g - 6
    return 2 + g2 // 8, ROWS_FULL[g2 % 8]


def _build_layout_12ch(samples: list[Sample], replicates: int = 3) -> list[LayoutRow]:
    """Place standards (rows A/B), blanks (A9-A12/B9-B12), and samples (rows C-H) per plate.

    Every dilution sample row (12 distinct samples, one per column) is dispensed
    into `replicates` consecutive assay rows, same columns (12-channel pipette).
    """
    n = len(samples)
    n_dil_rows = math.ceil(n / 12) if n > 0 else 0
    groups_per_plate = 6 // replicates
    cap = groups_per_plate * 12
    n_plates_needed = math.ceil(n / cap) if n > 0 else 0

    rows_out: list[LayoutRow] = []
    for plate in range(1, n_plates_needed + 1):
        for col_idx, conc in enumerate(STANDARD_CONCS_MC):
            col = col_idx + 1
            for rep, row_letter in ((1, "A"), (2, "B")):
                well = f"{row_letter}{col}"
                rows_out.append(
                    LayoutRow(
                        plate=plate,
                        well=well,
                        row=row_letter,
                        col=col,
                        role="standard",
                        short_id=f"STD{conc}",
                        label=f"BSA {conc} µg/mL",
                        conc_ugml=float(conc),
                        sample_name=None,
                        dilution_factor=None,
                        replicate=rep,
                        notes="",
                    )
                )

        blank_wells = [(r, c) for r in ("A", "B") for c in (9, 10, 11, 12)]
        for i, (row_letter, col) in enumerate(blank_wells, start=1):
            well = f"{row_letter}{col}"
            rows_out.append(
                LayoutRow(
                    plate=plate,
                    well=well,
                    row=row_letter,
                    col=col,
                    role="blank",
                    short_id="BLK",
                    label="Blank",
                    conc_ugml=0.0,
                    sample_name=None,
                    dilution_factor=None,
                    replicate=i,
                    notes="",
                )
            )

        for slot in range(groups_per_plate):
            g = groups_per_plate * (plate - 1) + slot
            if g >= n_dil_rows:
                break
            start_row_idx = 2 + slot * replicates
            assay_rows = ROWS_FULL[start_row_idx : start_row_idx + replicates]
            for col in range(1, 13):
                index0 = g * 12 + (col - 1)
                if index0 >= n:
                    break
                samp = samples[index0]
                global_index = index0 + 1
                for rep, row_letter in enumerate(assay_rows, start=1):
                    well = f"{row_letter}{col}"
                    rows_out.append(
                        LayoutRow(
                            plate=plate,
                            well=well,
                            row=row_letter,
                            col=col,
                            role="sample",
                            short_id=f"S{global_index}",
                            label=samp.sample_name,
                            conc_ugml=None,
                            sample_name=samp.sample_name,
                            dilution_factor=samp.dilution_factor,
                            replicate=rep,
                            notes=samp.notes,
                        )
                    )

    return rows_out


def build_layout(
    samples: list[Sample],
    avoid_edges: bool = False,
    multichannel: bool = False,
    channels: int | None = None,
    replicates: int = 3,
) -> list[LayoutRow]:
    """Place standards and samples onto plates using the generic row-wise placer."""
    if channels is None and multichannel:
        channels = 8
    if channels is not None:
        if avoid_edges:
            raise PlatemapError("--avoid-edges is not supported with --multichannel")
        if channels == 12:
            return _build_layout_12ch(samples, replicates)
        return _build_layout_multichannel(samples, replicates)

    wells = usable_wells(avoid_edges)
    row_len = _row_len(avoid_edges)
    n_wells = len(wells)

    sample_groups: list[tuple[int, Sample]] = list(enumerate(samples, start=1))

    rows_out: list[LayoutRow] = []
    plate = 1
    group_idx = 0

    while True:
        idx = 0
        for conc in STANDARD_CONCS:
            start = _try_place(n_wells, row_len, idx, 2)
            if start is None:
                break
            idx = start + 2
            is_blank = conc == 0
            role = "blank" if is_blank else "standard"
            short_id = "BLK" if is_blank else f"STD{conc}"
            label = "Blank" if is_blank else f"BSA {conc} µg/mL"
            for rep in range(1, 3):
                well = wells[start + rep - 1]
                rows_out.append(
                    LayoutRow(
                        plate=plate,
                        well=well,
                        row=well[0],
                        col=int(well[1:]),
                        role=role,
                        short_id=short_id,
                        label=label,
                        conc_ugml=float(conc),
                        sample_name=None,
                        dilution_factor=None,
                        replicate=rep,
                        notes="",
                    )
                )

        placed_any = True
        while placed_any and group_idx < len(sample_groups):
            global_index, samp = sample_groups[group_idx]
            size = replicates
            start = _try_place(n_wells, row_len, idx, size)
            if start is None:
                placed_any = False
                break
            idx = start + size
            group_idx += 1
            for rep in range(1, size + 1):
                well = wells[start + rep - 1]
                rows_out.append(
                    LayoutRow(
                        plate=plate,
                        well=well,
                        row=well[0],
                        col=int(well[1:]),
                        role="sample",
                        short_id=f"S{global_index}",
                        label=samp.sample_name,
                        conc_ugml=None,
                        sample_name=samp.sample_name,
                        dilution_factor=samp.dilution_factor,
                        replicate=rep,
                        notes=samp.notes,
                    )
                )

        if group_idx >= len(sample_groups):
            break
        plate += 1

    return rows_out


def write_layout_csv(rows: list[LayoutRow], path: str) -> None:
    """Write layout rows to a CSV file, with None written as empty string."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(LAYOUT_COLUMNS)
        for r in rows:
            writer.writerow(["" if getattr(r, c) is None else getattr(r, c) for c in LAYOUT_COLUMNS])


def read_layout_csv(path: str) -> list[LayoutRow]:
    """Read a `<prefix>_layout.csv` (as written by `write_layout_csv`) into LayoutRow objects."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows: list[LayoutRow] = []
        for values in reader:
            rows.append(
                LayoutRow(
                    plate=int(values["plate"]),
                    well=str(values["well"]),
                    row=str(values["row"]),
                    col=int(values["col"]),
                    role=str(values["role"]),
                    short_id=str(values["short_id"]),
                    label=str(values["label"]),
                    conc_ugml=None if values["conc_ugml"] in (None, "") else float(values["conc_ugml"]),
                    sample_name=None if values["sample_name"] in (None, "") else str(values["sample_name"]),
                    dilution_factor=(
                        None if values["dilution_factor"] in (None, "") else float(values["dilution_factor"])
                    ),
                    replicate=int(values["replicate"]),
                    notes="" if values["notes"] is None else str(values["notes"]),
                )
            )
    return rows
