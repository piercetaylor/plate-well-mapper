"""Plate layout: standards + sample placement across 96-well plates."""

import csv
import math
from dataclasses import dataclass

from platemap.samples import Sample
from platemap.wells import COLS_EDGE, COLS_FULL, usable_wells

STANDARD_CONCS = (2000, 1500, 1000, 750, 500, 250, 125, 25, 0)

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


def capacity(avoid_edges: bool = False) -> int:
    """Max number of samples (in groups of 3) that fit on one plate after standards."""
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


def n_plates(n: int, avoid_edges: bool = False) -> int:
    """Number of plates needed to hold n samples."""
    if n <= 0:
        return 0
    cap = capacity(avoid_edges)
    return math.ceil(n / cap)


def build_layout(samples: list[Sample], avoid_edges: bool = False) -> list[LayoutRow]:
    """Place standards and samples onto plates using the generic row-wise placer."""
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
