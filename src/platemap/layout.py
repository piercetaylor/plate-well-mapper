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


def capacity(avoid_edges: bool = False, multichannel: bool = False) -> int:
    """Max number of samples (in groups of 3) that fit on one plate after standards."""
    if multichannel:
        if avoid_edges:
            raise PlatemapError("--avoid-edges is not supported with --multichannel")
        return MULTICHANNEL_CAPACITY

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
        start = _try_place(n_wells, row_len, idx, 3)
        if start is None:
            break
        idx = start + 3
        count += 1
    return count


def n_plates(n: int, avoid_edges: bool = False, multichannel: bool = False) -> int:
    """Number of plates needed to hold n samples."""
    if n <= 0:
        return 0
    cap = capacity(avoid_edges, multichannel)
    return math.ceil(n / cap)


def _build_layout_multichannel(samples: list[Sample]) -> list[LayoutRow]:
    """Place standards (cols 1-2), blank (col 3), and samples (cols 4-12, 8-channel) per plate."""
    n = len(samples)
    n_plates_needed = math.ceil(n / MULTICHANNEL_CAPACITY) if n > 0 else 0

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

        start = (plate - 1) * MULTICHANNEL_CAPACITY
        end = min(start + MULTICHANNEL_CAPACITY, n)
        for k in range(start, end):
            idx_in_plate = k - start
            block = idx_in_plate // 8
            row_idx = idx_in_plate % 8
            row_letter = ROWS_FULL[row_idx]
            cols = (4 + 3 * block, 5 + 3 * block, 6 + 3 * block)
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


def build_layout(
    samples: list[Sample], avoid_edges: bool = False, multichannel: bool = False
) -> list[LayoutRow]:
    """Place standards and samples onto plates using the generic row-wise placer."""
    if multichannel:
        if avoid_edges:
            raise PlatemapError("--avoid-edges is not supported with --multichannel")
        return _build_layout_multichannel(samples)

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
            size = 3
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
