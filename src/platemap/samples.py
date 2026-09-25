"""Sample CSV input handling."""

import csv
import math
from dataclasses import dataclass


SAMPLE_NAME_ALIASES = ("sample_id", "sample", "name", "id")


class PlatemapError(Exception):
    """Raised for user-facing errors in platemap."""


@dataclass(frozen=True)
class Sample:
    sample_name: str
    dilution_factor: float = 1.0
    notes: str = ""


def read_samples(path: str) -> list[Sample]:
    """Read samples from a CSV file with columns sample_name, dilution_factor, notes."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is not None:
            names = [name.strip().lower() for name in reader.fieldnames]
            if "sample_name" not in names:
                # Accept common alternative headers for the sample column.
                for alias in SAMPLE_NAME_ALIASES:
                    if alias in names:
                        names[names.index(alias)] = "sample_name"
                        break
            reader.fieldnames = names

        samples: list[Sample] = []
        seen: dict[str, int] = {}
        for line_num, raw_row in enumerate(reader, start=2):
            raw_row.pop(None, None)  # overflow cells from trailing commas
            row = {k: (v.strip() if v is not None else "") for k, v in raw_row.items()}
            if all(v == "" for v in row.values()):
                continue

            name = row.get("sample_name", "")
            if not name:
                raise PlatemapError(f"missing sample_name at line {line_num}")

            if name in seen:
                raise PlatemapError(
                    f"duplicate sample_name '{name}' at lines {seen[name]} and {line_num}"
                )
            seen[name] = line_num

            raw_df = row.get("dilution_factor", "")
            if raw_df == "":
                dilution_factor = 1.0
            else:
                try:
                    dilution_factor = float(raw_df)
                except ValueError:
                    dilution_factor = None
                if dilution_factor is None or not math.isfinite(dilution_factor) or dilution_factor <= 0:
                    raise PlatemapError(
                        f"invalid dilution_factor '{raw_df}' at line {line_num}"
                    )

            notes = row.get("notes", "")
            samples.append(Sample(sample_name=name, dilution_factor=dilution_factor, notes=notes))

    if not samples:
        raise PlatemapError("no samples")

    return samples
