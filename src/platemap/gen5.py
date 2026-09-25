"""Parser for BioTek Gen5 (Cytation5) CSV plate reader exports."""

import csv
import io
import math
import re

from platemap.samples import PlatemapError
from platemap.wells import COLS_FULL, ROWS_FULL

_WELL_RE = re.compile(r"^[A-H](1[0-2]|[1-9])$")


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


def _find_blocks(rows: list[list[str]]) -> list[tuple[str, dict[str, float]]]:
    blocks: list[tuple[str, dict[str, float]]] = []
    i = 0
    while i < len(rows):
        if _is_header_row(rows[i]) and i + 8 < len(rows):
            ok = all(
                _get(rows[i + 1 + k], 0).strip() == ROWS_FULL[k] for k in range(8)
            )
            if ok:
                label = _block_label(rows, i)
                data: dict[str, float] = {}
                for k in range(8):
                    data_row = rows[i + 1 + k]
                    row_letter = ROWS_FULL[k]
                    for c, col in enumerate(COLS_FULL, start=1):
                        well = f"{row_letter}{col}"
                        data[well] = _value_or_nan(_get(data_row, c))
                blocks.append((label, data))
                i += 9
                continue
        i += 1
    return blocks


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


def parse_gen5(path: str, *, block_index: int | None = None, wavelength=None) -> dict[str, float]:
    """Parse a Gen5 CSV export into a well -> value dict for one block/reading."""
    text = _read_text(path)
    first_line = text.splitlines()[0] if text else ""
    delimiter = "\t" if "\t" in first_line else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))

    blocks = _find_blocks(rows)

    if blocks:
        if wavelength is not None:
            for label, data in blocks:
                if _label_matches(label, wavelength):
                    return data
            raise PlatemapError(f"no block matching wavelength '{wavelength}' in {path}")
        if block_index is not None:
            if 0 <= block_index < len(blocks):
                return blocks[block_index][1]
            raise PlatemapError(f"block_index {block_index} out of range in {path}")
        return blocks[0][1]

    long_data = _find_long_format(rows, wavelength)
    if long_data is not None:
        return long_data

    raise PlatemapError(f"no plate data found in {path}")
