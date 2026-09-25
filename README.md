# platemap

Generates 96-well plate layouts for Pierce BCA protein assays on a BioTek
Cytation 5, and analyzes the resulting absorbance data.

Given a CSV of sample names, `platemap` places a BSA standard curve and
your samples (in triplicate) onto one or more 96-well plates, and writes:

- a layout CSV
- an Excel workbook with a printable plate map, an empty "Reader" grid to
  paste absorbance values into, and a "Mapped" sheet that pulls those
  values back onto each well via formulas
- a PDF plate map for the bench

If samples are too concentrated for the curve, `platemap dilute` adds a
pre-dilution step: a dilution plate that also prepares the BSA standards,
with the dilution factor carried through to the analysis.

After reading the plate on the Cytation 5 and exporting the results from
Gen5, `platemap read` fills the Reader sheets and writes a mapped CSV.
`platemap notebook` writes a Jupyter notebook that fits the standard
curve (4PL or linear) and quantifies your samples.

## Install

Requires Python 3.10 or later (3.12 recommended).

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[notebook]"
```

The `notebook` extra pulls in pandas, numpy, scipy, matplotlib, nbformat,
nbconvert, and ipykernel, needed for `platemap notebook` and the notebook
it generates.

## Quickstart

1. Write a sample CSV (`sample_name`, `dilution_factor`, `notes`). See
   `examples/samples.csv`. `sample_id` is accepted as the header too.
2. `platemap layout samples.csv -o out --experiment "BCA run 1"`
   Writes `out/platemap_layout.csv`, `out/platemap_plates.xlsx`, and
   `out/platemap_platemap.pdf`.
3. Print the PDF plate map and pipette standards and samples into the
   wells it shows.
4. Read the plate on the Cytation 5 (562 nm) and export the results from
   Gen5 as CSV.
5. `platemap read out/platemap_plates.xlsx plate1.csv plate2.csv`
   Fills the Reader sheets in a new workbook and writes a mapped CSV.
6. `platemap notebook -o out/bca_analysis.ipynb`, then open and run it against
   the mapped CSV to fit the standard curve and get sample concentrations.

## Dilute workflow

Use this when samples are more concentrated than the 25-2000 µg/mL curve
allows. A dilution factor F puts samples from 25F to 2000F µg/mL on the
curve; the default F = 20 covers 0.5-40 mg/mL. Pick F so that your
highest sample / F < 2000 µg/mL and your lowest sample / F > 25 µg/mL.

1. `platemap dilute samples.csv --factor 20 -o out --prefix run1 --experiment "BCA run 1"`
   This replaces `platemap layout` and writes:
   - `run1_dilution.pdf` and `run1_dilution.csv`: the dilution plate map
     and step-by-step protocol
   - `run1_samples_diluted.csv`: the sample list with `dilution_factor`
     multiplied by F
   - `run1_layout.csv`, `run1_plates.xlsx`, `run1_platemap.pdf`: the
     assay plate outputs, built from the diluted samples
   - `run1_bca_analysis.ipynb`: the notebook, already pointed at
     `run1_plates_mapped.csv`
2. Prepare the dilution plate from `run1_dilution.pdf`. It uses the
   following layout (F = 20, 200 µL final per well):

   ```
        1     2     3     4     5     6     7     8     9    10    11    12
   A  2000  2000  1500  1500  1000  1000   750   750   500   500   250   250
   B   125   125    25    25   BLK   BLK    S1    S2    S3    S4    S5    S6
   C    S7    S8    S9   S10   S11   S12   S13   S14   S15   S16   S17   S18
   ...
   ```

   - Standards in A1-B4 are made in duplicate from one 1 mL BSA ampule
     (900 µL used): 2000/1500/1000 from stock, then 750 to 25 serially.
     The PDF lists the source well and volumes for each well.
   - B5-B6 hold the blank (200 µL diluent).
   - Each sample gets one well: 200/F µL sample + the rest diluent
     (10 + 190 µL at F = 20). Plate 1 holds 78 samples; further dilution
     plates hold 96 samples and no standards.
3. Transfer 25 µL into each assay plate. Wells A1-B6 map 1:1 onto the
   same wells of the assay plate, so a multichannel works for the
   standards. Samples go from dilution well S# into the three S# wells
   of the assay map; do not multichannel B7-B12.
4. Read, run `platemap read`, and run the notebook as in steps 4-6 of
   the quickstart. Sample concentrations are multiplied by F so results
   refer to the undiluted sample. Standards are not multiplied.

The command prints a warning if a standard well cannot supply 25 µL to
every assay plate (5 or more assay plates at the default volumes).

## Plate 1 layout (full mode)

Rows A and B hold the BSA standard curve in duplicate, high to low
concentration, followed by a blank; samples start at B7 in triplicate.

```
     1     2     3     4     5     6     7     8     9    10    11    12
A  2000  2000  1500  1500  1000  1000   750   750   500   500   250   250
B   125   125    25    25   BLK   BLK    S1    S1    S1    S2    S2    S2
C    S3    S3    S3    S4    S4    S4    S5    S5    S5    S6    S6    S6
D    S7    S7    S7    S8    S8    S8    S9    S9    S9   S10   S10   S10
...
```

Concentrations are µg/mL BSA. `BLK` is the 0 µg/mL blank. `S1`, `S2`, ...
are sample groups in the order they appear in the input CSV. When samples
run out, remaining wells on the plate are left empty; a second plate
repeats the same standard curve.

## Capacity

- Full plate (all 96 wells): 8 standards + 1 blank, 2 wells each (18
  wells), leaving room for 26 sample groups of 3 wells each.
- `--avoid-edges` (restricts to rows B-G, columns 2-11, 60 wells): 12
  sample groups.

Samples beyond a plate's capacity spill onto additional plates, each with
its own standard curve.

## Outputs

| File | From | Contents |
|---|---|---|
| `<prefix>_layout.csv` | `layout`, `dilute` | flat table of every well: plate, well, role, concentration/sample, replicate |
| `<prefix>_plates.xlsx` | `layout`, `dilute` | Info, Layout, and per-plate Map/Reader/Mapped sheets |
| `<prefix>_platemap.pdf` | `layout`, `dilute` | printable plate map with a legend |
| `<prefix>_dilution.pdf`, `<prefix>_dilution.csv` | `dilute` | dilution plate map and protocol, with standard prep |
| `<prefix>_samples_diluted.csv` | `dilute` | sample list with the dilution factor applied |
| `<prefix>_bca_analysis.ipynb` | `dilute` | analysis notebook pointed at `<prefix>_plates_mapped.csv` |
| `<wb stem>_filled.xlsx` | `read` | the workbook with Reader sheets filled in |
| `<wb stem>_mapped.csv` | `read` | well-level table with absorbance, for analysis |
| `bca_analysis.ipynb` | `notebook` | standard-curve fit and quantification notebook |
| `bca_results.csv`, `bca_results_wells.csv` | notebook run | summary and well-level results |

See `docs/usage.md` for the full command reference, the Gen5 export
format, and the analysis notebook.

## Tests

```
pip install -e ".[notebook,dev]"
.venv\Scripts\python.exe -m pytest -q
```
