"""Parser for BioTek Gen5 (Cytation5) CSV plate reader exports."""

import csv
import io
import math
import re

from platemap.samples import PlatemapError
from platemap.wells import COLS_FULL, ROWS_FULL

_WELL_RE = re.compile(r"^[A-H](1[0-2]|[1-9])$")

_METADATA_KEYS = (
    "Plate Number",
    "Date",
    "Time",
    "Software Version",
    "Reader Type",
    "Reader Serial Number",
    "Actual Temperature",
)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            return fh.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1", newline="") as fh:
            return fh.read()


def _value_or_nan(cell: str) -> float:
    s = cell.strip()
    if s in ("", "OVRFLW", "?????"):
        return math.nan
    try:
        return float(s)
    except ValueError:
        return math.nan


def _get(row: list, idx: int) -> str:
    return row[idx] if idx < len(row) else ""


def _is_header_row(row: list) -> bool:
    trimmed = [c.strip() for c in row[1:]]
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    expected = [str(c) for c in COLS_FULL]
    return len(trimmed) >= 12 and trimmed[:12] == expected


def _is_blank_line(row: list) -> bool:
    return all(c.strip() == "" for c in row)


def _block_label(rows: list[list[str]], header_idx: int) -> str:
    header_row = rows[header_idx]
    label = _get(header_row, 13).strip()
    if label:
        return label

    if header_idx + 1 < len(rows):
        label = _get(rows[header_idx + 1], 13).strip()
        if label:
            return label

    for j in range(header_idx - 1, -1, -1):
        cells = [c.strip() for c in rows[j]]
        non_empty = [c for c in cells if c != ""]
        if len(non_empty) == 1:
            return non_empty[0]

    return ""


def _find_matrix_blocks(
    rows: list[list[str]],
) -> tuple[list[tuple[str, dict[str, float]]], dict[str, tuple[str, str]]]:
    """Parse every 1..12 matrix block in `rows`.

    Returns (reads, layout): `reads` is a list of (label, well->value) for
    every non-layout numeric group, in file order; `layout` is well ->
    (well_id, conc_dil_text) from the Layout block's "Well ID"/"Conc/Dil"
    groups, or {} if no Layout block was found.
    """
    reads: list[tuple[str, dict[str, float]]] = []
    layout: dict[str, tuple[str, str]] = {}
    i = 0
    n = len(rows)
    while i < n:
        if _is_header_row(rows[i]):
            header_idx = i
            j = header_idx + 1
            current_letter = None
            block_groups: dict[str, dict[str, list[str]]] = {}
            group_order: list[str] = []
            consumed_any = False
            while j < n:
                row = rows[j]
                if _is_blank_line(row):
                    break
                label0 = _get(row, 0).strip()
                if label0 != "" and label0 in ROWS_FULL:
                    current_letter = label0
                elif label0 == "":
                    if current_letter is None:
                        break
                else:
                    break

                cells = [_get(row, c) for c in range(1, 13)]
                trailing = _get(row, 13).strip()
                key = trailing
                if key not in block_groups:
                    block_groups[key] = {}
                    group_order.append(key)
                block_groups[key][current_letter] = cells
                consumed_any = True
                j += 1

            if consumed_any:
                is_layout = any(key == "Well ID" for key in group_order)
                if is_layout:
                    well_id_group = block_groups.get("Well ID", {})
                    conc_group = block_groups.get("Conc/Dil", {})
                    for letter in ROWS_FULL:
                        wid_cells = well_id_group.get(letter, [""] * 12)
                        conc_cells = conc_group.get(letter, [""] * 12)
                        for c, col in enumerate(COLS_FULL):
                            well = f"{letter}{col}"
                            layout[well] = (wid_cells[c].strip(), conc_cells[c].strip())
                else:
                    for key in group_order:
                        label = key if key else _block_label(rows, header_idx)
                        group = block_groups[key]
                        data: dict[str, float] = {}
                        for letter in ROWS_FULL:
                            cells = group.get(letter, [""] * 12)
                            for c, col in enumerate(COLS_FULL):
                                well = f"{letter}{col}"
                                data[well] = _value_or_nan(cells[c])
                        reads.append((label, data))
                i = j
                continue
        i += 1
    return reads, layout


def _label_matches(label: str, wavelength) -> bool:
    label = str(label).strip()
    wl = str(wavelength).strip()
    if label == wl:
        return True
    # Gen5 labels such as "562" or "Read 1:562": compare the trailing number.
    m = re.search(r"(\d+(?:\.\d+)?)\s*$", label)
    try:
        return m is not None and float(m.group(1)) == float(wl)
    except ValueError:
        return False


def _find_long_format(rows: list[list[str]], wavelength) -> dict[str, float] | None:
    header_idx = None
    well_idx = None
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if cell.strip().lower() == "well":
                header_idx, well_idx = i, j
                break
        if header_idx is not None:
            break

    if header_idx is None:
        return None

    header_row = rows[header_idx]
    other_cols = [(j, c.strip()) for j, c in enumerate(header_row) if j != well_idx and c.strip()]
    if not other_cols:
        return None

    col_idx = None
    if wavelength is not None:
        for j, header in other_cols:
            if _label_matches(header, wavelength):
                col_idx = j
                break
    if col_idx is None:
        col_idx = other_cols[0][0]

    data: dict[str, float] = {}
    for row in rows[header_idx + 1 :]:
        well = _get(row, well_idx).strip()
        if not _WELL_RE.match(well):
            continue
        data[well] = _value_or_nan(_get(row, col_idx))

    return data or None


def _read_rows(path: str) -> list[list[str]]:
    text = _read_text(path)
    first_line = ""
    for line in text.splitlines():
        if line.strip():
            first_line = line
            break
    delimiter = "\t" if "\t" in first_line else ","
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def parse_gen5(
    path: str,
    *,
    block_index: int | None = None,
    wavelength=None,
    read_label: str | None = None,
) -> dict[str, float]:
    """Parse a Gen5 CSV export into a well -> value dict for one block/reading."""
    rows = _read_rows(path)

    reads, _layout = _find_matrix_blocks(rows)

    if reads:
        if read_label is not None:
            for label, data in reads:
                if label == read_label:
                    return data
            available = ", ".join(repr(label) for label, _ in reads)
            raise PlatemapError(
                f"no read matching read_label '{read_label}' in {path} (available: {available})"
            )
        if wavelength is not None:
            for label, data in reads:
                if _label_matches(label, wavelength):
                    return data
            raise PlatemapError(f"no block matching wavelength '{wavelength}' in {path}")
        if block_index is not None:
            if 0 <= block_index < len(reads):
                return reads[block_index][1]
            raise PlatemapError(f"block_index {block_index} out of range in {path}")
        for label, data in reads:
            if not label.strip().lower().startswith("blank"):
                return data
        return reads[0][1]

    long_data = _find_long_format(rows, wavelength)
    if long_data is not None:
        return long_data

    raise PlatemapError(f"no plate data found in {path}")


def parse_gen5_reads(path: str) -> dict[str, dict[str, float]]:
    """Parse every numeric read (label -> well -> value) from a Gen5 export."""
    rows = _read_rows(path)
    reads, _layout = _find_matrix_blocks(rows)
    return {label: data for label, data in reads}


def parse_gen5_layout(path: str) -> dict[str, tuple[str, str]]:
    """Parse the Layout block (well -> (well_id, conc_dil_text)) from a Gen5 export."""
    rows = _read_rows(path)
    _reads, layout = _find_matrix_blocks(rows)
    return layout


def parse_gen5_metadata(path: str) -> dict[str, str]:
    """Parse metadata lines (Plate Number, Date, Time, etc.) from a Gen5 export."""
    rows = _read_rows(path)
    metadata: dict[str, str] = {}
    for row in rows:
        if len(row) < 2:
            continue
        key = _get(row, 0).strip().rstrip(":")
        if key in _METADATA_KEYS and key not in metadata:
            value = _get(row, 1).strip()
            if value:
                metadata[key] = value
    return metadata


def check_gen5_layout(
    our_rows_for_plate, gen5_layout: dict[str, tuple[str, str]]
) -> tuple[list[str], list[str]]:
    """Cross-check our plate layout rows against a Gen5 Layout block.

    `our_rows_for_plate` is an iterable of objects with `.well`, `.role`,
    `.short_id`, and `.conc_ugml` attributes (e.g. `LayoutRow`), restricted
    to one plate. `gen5_layout` is well -> (well_id, conc_dil_text) as
    returned by `parse_gen5_layout`.

    Returns (errors, warnings). Wells used in ours but empty/missing in
    Gen5 are errors; wells empty in ours but assigned in Gen5 are warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    our_wells = {row.well: row for row in our_rows_for_plate}

    sample_rows = sorted(
        (row for row in our_wells.values() if row.role == "sample"),
        key=lambda row: (ROWS_FULL.index(row.well[0]), int(row.well[1:])),
    )
    sample_rank: dict[str, int] = {}
    for row in sample_rows:
        if row.short_id not in sample_rank:
            sample_rank[row.short_id] = len(sample_rank) + 1

    all_wells = [f"{r}{c}" for r in ROWS_FULL for c in COLS_FULL]

    for well in all_wells:
        gen5_id, gen5_conc = gen5_layout.get(well, ("", ""))
        gen5_id = gen5_id.strip()
        gen5_conc = gen5_conc.strip()
        our_row = our_wells.get(well)

        if our_row is None:
            if gen5_id:
                warnings.append(f"{well}: empty in ours but Gen5 has '{gen5_id}'")
            continue

        if not gen5_id:
            errors.append(f"{well}: '{our_row.short_id}' in ours but empty in Gen5")
            continue

        if our_row.role == "standard":
            if not (gen5_id.startswith("BCA:") or gen5_id.startswith("STD")):
                errors.append(
                    f"{well}: expected a standard ('BCA:'/'STD' id) in Gen5, got '{gen5_id}'"
                )
                continue
            try:
                conc = float(gen5_conc)
            except ValueError:
                errors.append(f"{well}: Gen5 conc '{gen5_conc}' is not numeric")
                continue
            if not math.isclose(conc, our_row.conc_ugml):
                errors.append(
                    f"{well}: conc mismatch, ours={our_row.conc_ugml} Gen5={conc}"
                )
        elif our_row.role == "blank":
            if gen5_id != "BLK":
                errors.append(f"{well}: expected Gen5 id 'BLK', got '{gen5_id}'")
        elif our_row.role == "sample":
            expected = f"SPL{sample_rank[our_row.short_id]}"
            if gen5_id != expected:
                errors.append(f"{well}: expected Gen5 id '{expected}', got '{gen5_id}'")

    return errors, warnings
