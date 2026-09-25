# platemap usage

## Commands

### `platemap`

```
usage: platemap [-h] [--version] {layout,read,dilute,notebook} ...
```

- `-h`, `--help`: show help and exit.
- `--version`: print the installed version and exit.

Running `platemap` with no subcommand prints help and exits with status 1.
Any user-facing error (bad input, missing data, etc.) prints
`error: <message>` to stderr and the process exits with status 2.

### `platemap layout SAMPLES [options]`

Build a plate layout (standards + samples) from a sample CSV and write the
layout CSV, workbook, and PDF.

```
usage: platemap layout [-h] [-o OUTDIR] [--prefix PREFIX] [--avoid-edges]
                        [--experiment EXPERIMENT] [--date DATE]
                        SAMPLES
```

- `SAMPLES`: path to the sample CSV.
- `-o OUTDIR`, `--outdir OUTDIR`: output directory, created if missing
  (default `.`).
- `--prefix PREFIX`: output filename prefix (default `platemap`).
- `--avoid-edges`: restrict wells to rows B-G, columns 2-11 (60 wells)
  instead of the full 96-well plate.
- `--experiment EXPERIMENT`: experiment name, recorded on the Info sheet
  and the PDF header.
- `--date DATE`: experiment date, `YYYY-MM-DD` (default: today). Rejected
  if not a valid ISO date.

Writes `OUTDIR/<prefix>_layout.csv`, `OUTDIR/<prefix>_plates.xlsx`, and
`OUTDIR/<prefix>_platemap.pdf`, then prints:

```
samples=<N> plates=<P> capacity=<C>
<path to layout csv>
<path to xlsx>
<path to pdf>
```

### `platemap read WORKBOOK READER [READER ...] [options]`

Fill the Reader sheets of a `*_plates.xlsx` workbook from one or more Gen5
CSV exports, and write a mapped CSV.

```
usage: platemap read [-h] [--plate PLATE] [--wavelength WAVELENGTH]
                      [-o OUT.xlsx]
                      WORKBOOK READER [READER ...]
```

- `WORKBOOK`: the `*_plates.xlsx` produced by `platemap layout`.
- `READER`: one or more Gen5 CSV export files.
- `--plate PLATE`: plate number that the single reader file belongs to.
  Requires exactly one `READER` argument; error if `PLATE` is outside
  `1..<plate count>`.
- `--wavelength WAVELENGTH`: wavelength/block label to select within each
  reader file, when a file has more than one read (see below).
- `-o OUT.xlsx`, `--out OUT.xlsx`: output workbook path (default
  `<workbook stem>_filled.xlsx`, next to the input workbook).

Without `--plate`, reader files map to plates 1, 2, 3, ... in the order
given. Supplying more reader files than the workbook has plates is an
error.

Writes the filled workbook and `<workbook stem>_mapped.csv` next to the
output workbook, then prints both paths and `missing=<N>` (wells with no
absorbance value).

### `platemap dilute SAMPLES [options]`

Build 96-well pre-dilution plate map(s) from a sample CSV, then run the
usual `layout` step on the *diluted* samples.

Dilution plate 1 also prepares the BSA standard curve, mirroring wells
A1-B6 of the assay plate: A1-A2 2000, A3-A4 1500, A5-A6 1000, A7-A8 750,
A9-A10 500, A11-A12 250, B1-B2 125, B3-B4 25 (all duplicate, 200 µL
final each), and B5-B6 the blank (200 µL diluent). Each standard well
is prepared either from BSA stock (2000/1500/1000) or serially from the
same-replicate well of the next-higher concentration (750 from 1500,
500 from 1000, 250 from 500, 125 from 250, 25 from 125); the exact
source well, source µL, diluent µL, and remaining µL for each well are
in `dilution.STANDARD_PREP` and the dilution PDF/CSV. Samples start at
B7 (row-major), so plate 1 holds up to 78 samples; any samples beyond
that (and all of plates 2+) go on additional dilution plates with no
standards, starting at A1.

At 25 µL transferred per assay plate per standard well, each standard
well needs at least `25 * <number of assay plates>` µL remaining after
the serial dilution. If it doesn't, `platemap dilute` prints a
`WARNING:` line (and the dilution PDF shows it) naming the well.

```
usage: platemap dilute [-h] [--factor FACTOR] [--final-volume FINAL_VOLUME]
                        [-o OUTDIR] [--prefix PREFIX] [--avoid-edges]
                        [--experiment EXPERIMENT] [--date DATE]
                        SAMPLES
```

- `SAMPLES`: path to the sample CSV.
- `--factor FACTOR`: dilution factor applied to every sample before the
  BCA assay (default `20`, i.e. 1 part sample + 19 parts diluent).
- `--final-volume FINAL_VOLUME`: total well volume in µL for the
  dilution step (default `200`). Sample volume is `final / factor` and
  diluent volume is the remainder. Errors if `FACTOR <= 1`, if
  `FINAL_VOLUME <= 0`, if `FINAL_VOLUME > 300` (a standard 96-well plate
  isn't modelled as deep-well), or if the resulting sample volume is
  below 2 µL (raise `--final-volume`).
- `-o OUTDIR`, `--outdir OUTDIR`, `--prefix PREFIX`, `--avoid-edges`,
  `--experiment EXPERIMENT`, `--date DATE`: same as `platemap layout`.

Writes, in order:

1. `<prefix>_samples_diluted.csv` — the sample CSV with
   `dilution_factor` multiplied by `FACTOR`.
2. `<prefix>_dilution.csv` — one row per standard/blank well and one
   per sample: `plate, well, role, short_id, label, conc_ugml, source,
   source_ul, diluent_ul, final_ul, remaining_ul`.
3. `<prefix>_dilution.pdf` — one page per dilution plate, with the
   pipetting protocol (plate 1 includes the standard-prep table), a
   plate map, and a legend.
4. `<prefix>_layout.csv`, `<prefix>_plates.xlsx`, `<prefix>_platemap.pdf`
   — the normal `layout` outputs, built from the *diluted* samples (so
   the Layout sheet's `dilution_factor` already includes the
   pre-dilution).
5. `<prefix>_bca_analysis.ipynb` — the analysis notebook, with
   `MAPPED_CSV` pre-set to `<prefix>_plates_mapped.csv` and `OUTPUT_CSV`
   to `<prefix>_bca_results.csv`. Skipped with a note if the `notebook`
   extra isn't installed.

Then prints:

```
samples=<N> factor=<F> sample_ul=<S> diluent_ul=<D> dilution_plates=<K> assay_plates=<P>
<path to each file written, in the order above>
```

Range logic: with the standard 25-2000 µg/mL BSA curve, a dilution
factor `F` lets you read undiluted sample concentrations of roughly
`25*F` to `2000*F` µg/mL (the curve's range, scaled back up by `F`). The
default `F=20` covers about 0.5-40 mg/mL, which suits most cell lysates
and tissue homogenates; dilute further (larger `--factor`) for very
concentrated samples, or use a smaller factor (or skip `dilute`
entirely) for dilute samples.

### `platemap notebook [options]`

```
usage: platemap notebook [-h] [-o PATH] [--mapped-csv NAME]
```

- `-o PATH`, `--out PATH`: output notebook path (default
  `bca_analysis.ipynb`).
- `--mapped-csv NAME`: mapped CSV filename baked into the notebook's
  `MAPPED_CSV` parameter (default `platemap_plates_mapped.csv`).

Writes a Jupyter notebook for fitting the standard curve and quantifying
samples from a mapped CSV.

## Sample CSV format

Columns (header required, case-insensitive, whitespace-trimmed):

- `sample_name` (required): unique name for each sample. Blank on a
  non-blank row is an error; a repeated name is an error, naming both
  line numbers. Headers are case-insensitive, and `sample_id`, `sample`,
  `name` or `id` are accepted in place of `sample_name`.
- `dilution_factor` (optional): a positive number. Blank defaults to
  `1.0`. Non-numeric or `<= 0` is an error, naming the line and the bad
  value.
- `notes` (optional): free text, carried through to the layout CSV and
  the workbook's Layout sheet only (not the PDF legend or the mapped
  CSV).

Rows where every field is blank are skipped. A CSV with no data rows is
an error. Encoding is UTF-8 (with or without a BOM).

## Layout rules

Each plate holds a BSA standard curve followed by samples, placed
well-by-well in row-major order (A1, A2, ... A12, B1, ...; or, with
`--avoid-edges`, B2, B3, ... B11, C2, ...).

### Standards

Nine concentrations, each in duplicate (2 wells), in this order:

| Concentration (µg/mL) | short_id | label |
|---|---|---|
| 2000 | STD2000 | BSA 2000 µg/mL |
| 1500 | STD1500 | BSA 1500 µg/mL |
| 1000 | STD1000 | BSA 1000 µg/mL |
| 750  | STD750  | BSA 750 µg/mL |
| 500  | STD500  | BSA 500 µg/mL |
| 250  | STD250  | BSA 250 µg/mL |
| 125  | STD125  | BSA 125 µg/mL |
| 25   | STD25   | BSA 25 µg/mL |
| 0    | BLK     | Blank |

### Samples

After the standards, each sample from the input CSV is placed in
triplicate (3 wells), in input order, with `short_id` `S<n>` where `n` is
the sample's 1-based position across the whole input file (not
per-plate).

### Placement and the triplicate rule

A group (2 wells for a standard, 3 for a sample) is placed in the next N
consecutive wells of the current row. If it does not fit in the
remaining wells of that row, the whole group moves to the start of the
next row — a group is never split across rows. If the plate has no more
room, a new plate is started, and that new plate gets its own full set
of standards before its samples.

### Edge mode

`--avoid-edges` restricts usable wells to rows B-G and columns 2-11 (60
wells), leaving row A, row H, column 1, and column 12 empty. The same
placement algorithm runs over that smaller grid. With 4 samples in edge
mode: standards fill B2-C9, the blank lands at C8-C9, C10 and C11 are
unused (a 3-well sample group doesn't fit in the two wells left on row
C, and a group is never split across rows), and samples start at D2.

### Capacity and multi-plate layouts

`capacity(avoid_edges)` is the number of sample groups (of 3 wells) that
fit on one plate after the 9 standard groups:

- Full plate: 26 samples.
- `--avoid-edges`: 12 samples.

If there are more samples than one plate's capacity, additional plates
are added, each starting a fresh standard curve; `n_plates(n)` is
`ceil(n / capacity)`.

## Output files

### Layout CSV (`<prefix>_layout.csv`)

One row per well used, columns: `plate, well, row, col, role, short_id,
label, conc_ugml, sample_name, dilution_factor, replicate, notes`. `role`
is `standard`, `blank`, or `sample`. Unused fields (e.g. `conc_ugml` for
a sample row) are empty.

### Workbook (`<prefix>_plates.xlsx`)

- `Info`: `A1`/`B1` = "Experiment"/the experiment name, `A2`/`B2` =
  "Date"/the date.
- `Layout`: the same table as the layout CSV, with a bold header row.
- `Plate N Map`: columns 1-12 across the top, rows A-H down the side,
  the label of each used well written into the corresponding cell, and a
  solid fill colored by role (standard = `FFC000`, blank = `A6A6A6`,
  sample = `9DC3E6`). Intended for reference while pipetting, and as a
  visual check.
- `Plate N Reader`: the same grid, left empty. Paste (or type) the
  plate reader's 8x12 absorbance grid into `B2:M9` (row A -> row 2, col
  1 -> column B, etc.).
- `Plate N Mapped`: one row per used well, columns `well, role,
  short_id, label, conc_ugml, sample_name, dilution_factor, replicate,
  absorbance`. `absorbance` is a formula,
  `=INDEX('Plate N Reader'!$B$2:$M$9,<row>,<col>)`, so pasting values
  into the Reader sheet updates the Mapped sheet automatically, in Excel
  or when reopened after `platemap read`.

### Filled workbook and mapped CSV (`platemap read`)

`<workbook stem>_filled.xlsx` is a copy of the input workbook with the
Reader sheet(s) filled from the parsed Gen5 file(s). `<workbook
stem>_mapped.csv` is the well-level table (the Mapped sheet's columns,
plus a leading `plate` column, with computed absorbance values instead
of formulas); missing values are empty cells. This is the file the
analysis notebook expects as `MAPPED_CSV`.

## Gen5 export format

On the Cytation 5, in Gen5, export the plate read as a CSV (or
tab-delimited text) that includes the 8x12 result matrix: a header row
with column numbers `1` to `12`, followed by 8 data rows labeled `A`
through `H`. Gen5 exports typically include metadata lines above the
matrix (software version, protocol name, date/time, reader type,
wavelength, etc.) and a "562" (or similar) label line just before or
inside the header row; `platemap` skips the metadata and locates the
matrix by its header shape.

- If a file contains a single read/wavelength, no `--wavelength` is
  needed.
- If it contains more than one block (e.g. both 562 nm and a reference
  wavelength), pass `--wavelength 562` (or whichever wavelength label
  matches your export) to select the right one. Without `--wavelength`,
  the first block found is used.
- Cells containing `OVRFLW`, `?????`, or anything non-numeric are read
  as missing (empty) rather than erroring.
- A "long format" export (a `Well` column followed by one or more value
  columns) is also supported; the value column matching `--wavelength`
  is used, or the first value column if not specified.
- If no matrix or `Well` column can be found in the file, `platemap
  read` reports an error naming the file.

The parser was built against Gen5's documented export layout and a set
of synthetic fixtures (`tests/fixtures/gen5_example.csv`,
`gen5_two_blocks.csv`, `gen5_long_format.csv`); it has not been
exhaustively tested against every Gen5 version or every export template.
If a real export from your instrument doesn't parse, compare it against
the fixtures and check the header/label lines are in a similar place.

## Analysis notebook

`platemap notebook` writes a notebook with a `parameters`-tagged cell
(for use with Papermill or similar):

```python
MAPPED_CSV = "platemap_plates_mapped.csv"
MODEL = "4pl"
OUTPUT_CSV = "bca_results.csv"
```

Set `MAPPED_CSV` to the mapped CSV from `platemap read`, and `MODEL` to
`"4pl"` or `"linear"`.

Steps performed:

1. Load the mapped CSV.
2. Subtract each plate's mean blank absorbance from every well
   (`abs_blanked`).
3. Fit the standard curve per plate, using the mean blanked absorbance
   at each standard concentration (including the blank, at 0). The 4PL
   model is `y = d + (a-d)/(1+(x/c)^b)`; if the 4PL fit fails to
   converge, the notebook warns and falls back to a linear fit for that
   plate.
4. Plot each plate's standard curve with the fitted line.
5. Quantify every well: `conc_ugml_est` (inverted from the fit, on the
   undiluted well), `conc_ugml_final` (`conc_ugml_est * dilution_factor`),
   and `out_of_range` (blanked absorbance above the top standard or
   below the lowest nonzero standard for that plate).
6. Summarize by plate, `short_id`, `sample_name`, and `dilution_factor`:
   mean, sample standard deviation, `cv_pct`, replicate count `n`, and
   whether any replicate was flagged `out_of_range`.
7. Export the summary to `OUTPUT_CSV` and the full well-level table to
   `OUTPUT_CSV` with `_wells` inserted before the extension (e.g.
   `bca_results_wells.csv`).

## Troubleshooting

- `error: no samples`: the sample CSV had a header but no data rows.
- `error: missing sample_name at line N`: line `N` has other data
  but no `sample_name`.
- `error: duplicate sample_name '...' at lines A and B`: rename one
  of the two samples.
- `error: invalid dilution_factor '...' at line N`: `dilution_factor`
  must be a positive number, or left blank.
- `error: no plate data found in <path>`: `platemap read` could not
  find an 8x12 matrix or a `Well` column in the Gen5 export; check the
  file was exported with the plate results included.
- `error: no block matching wavelength '<w>' in <path>`: the
  `--wavelength` value did not match any block's label in that file;
  check the label text in the export (e.g. `562` vs `562nm`).
- `--plate requires exactly one reader file`: drop `--plate` when
  passing multiple reader files, or run `platemap read` once per plate.
- Reader sheet values don't reach the Mapped sheet: the Mapped
  sheet's `absorbance` column is a formula referencing the Reader sheet
  in the same workbook; open the filled workbook in Excel (or another
  spreadsheet application that evaluates `INDEX`) to see the resolved
  values, or use the `_mapped.csv` file written alongside it.
