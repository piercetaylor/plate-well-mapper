"""Pre-dilution planning: BSA standard prep + sample dilution -> dilution plate(s)."""

import csv
import math
from dataclasses import dataclass, replace

from platemap.samples import PlatemapError, Sample
from platemap.wells import usable_wells

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


def dilution_plate_count(n_samples: int) -> int:
    """Number of dilution plates needed: plate 1 holds standards + samples, 2+ samples only."""
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


def apply_dilution(samples: list[Sample], factor: float) -> list[Sample]:
    """Return new Samples with dilution_factor multiplied by factor."""
    return [replace(s, dilution_factor=s.dilution_factor * factor) for s in samples]


def build_dilution_layout(samples: list[Sample], plan: DilutionPlan) -> list[DilutionWell]:
    """Build dilution plate 1 (BSA standards + blank + samples) plus any overflow sample plates."""
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
