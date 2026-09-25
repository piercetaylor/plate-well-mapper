"""96-well plate geometry helpers."""

ROWS_FULL = "ABCDEFGH"
ROWS_EDGE = "BCDEFG"
COLS_FULL = range(1, 13)
COLS_EDGE = range(2, 12)


def well_name(row: str, col: int) -> str:
    """Format a row letter and column number as a well name, e.g. "B7"."""
    return f"{row}{col}"


def parse_well(name: str) -> tuple[str, int]:
    """Parse a well name like "B7" into (row, col)."""
    return name[0], int(name[1:])


def usable_wells(avoid_edges: bool = False) -> list[str]:
    """Return the row-major list of usable well names for the given mode."""
    rows = ROWS_EDGE if avoid_edges else ROWS_FULL
    cols = COLS_EDGE if avoid_edges else COLS_FULL
    return [well_name(r, c) for r in rows for c in cols]
