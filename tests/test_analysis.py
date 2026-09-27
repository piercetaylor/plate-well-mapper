import numpy as np
import pandas as pd
import pytest

from platemap.analysis import (
    fit_4pl,
    fit_linear,
    fit_standards,
    invert_4pl,
    invert_linear,
    quantify,
    reagent_blank_summary,
    subtract_blank,
    summarize,
)

TRUE_PARAMS = {"a": 0.05, "b": 1.2, "c": 400.0, "d": 2.2}
CONCS = [2000, 1500, 1000, 750, 500, 250, 125, 25, 0]


def _four_pl(x, a, b, c, d):
    return d + (a - d) / (1 + (x / c) ** b)


def _synthetic_mapped_df(model="4pl", with_reagent_blank=False, reagent_blank_absorbance=None):
    rows = []
    for plate in (1,):
        for conc in CONCS:
            role = "blank" if conc == 0 else "standard"
            short_id = "BLK" if conc == 0 else f"STD{conc}"
            for rep in (1, 2):
                if model == "4pl":
                    absorbance = _four_pl(float(conc), **TRUE_PARAMS)
                else:
                    absorbance = 0.0005 * conc + 0.1
                rows.append(
                    dict(
                        plate=plate,
                        well=f"A{rep}",
                        role=role,
                        short_id=short_id,
                        label=short_id,
                        conc_ugml=float(conc),
                        sample_name=None,
                        dilution_factor=None,
                        replicate=rep,
                        absorbance=absorbance,
                    )
                )
        for i in range(1, 3):
            true_conc = 300.0 * i
            if model == "4pl":
                absorbance = _four_pl(true_conc, **TRUE_PARAMS)
            else:
                absorbance = 0.0005 * true_conc + 0.1
            for rep in (1, 2, 3):
                rows.append(
                    dict(
                        plate=plate,
                        well=f"B{i}{rep}",
                        role="sample",
                        short_id=f"S{i}",
                        label=f"Sample{i}",
                        conc_ugml=None,
                        sample_name=f"Sample{i}",
                        dilution_factor=1.0,
                        replicate=rep,
                        absorbance=absorbance,
                    )
                )
        if with_reagent_blank:
            wr_absorbance = (
                reagent_blank_absorbance
                if reagent_blank_absorbance is not None
                else _four_pl(0.0, **TRUE_PARAMS) + 0.5
            )
            for rep, well in enumerate(("A11", "A12"), start=1):
                rows.append(
                    dict(
                        plate=plate,
                        well=well,
                        role="reagent_blank",
                        short_id="WR",
                        label="WR only (no buffer)",
                        conc_ugml=None,
                        sample_name=None,
                        dilution_factor=None,
                        replicate=rep,
                        absorbance=wr_absorbance,
                    )
                )
    return pd.DataFrame(rows)


def test_subtract_blank():
    df = _synthetic_mapped_df()
    blanked = subtract_blank(df)
    blank_mean = df[df.role == "blank"]["absorbance"].mean()
    assert blanked.loc[blanked.role == "standard", "abs_blanked"].iloc[0] == pytest.approx(
        df.loc[df.role == "standard", "absorbance"].iloc[0] - blank_mean
    )


def test_fit_4pl_recovers_params():
    x = np.array([c for c in CONCS if c > 0], dtype=float)
    y = _four_pl(x, **TRUE_PARAMS)
    fit = fit_4pl(x, y)
    for key, true_val in TRUE_PARAMS.items():
        assert fit.params[key] == pytest.approx(true_val, rel=0.02)
    assert fit.r2 > 0.99


def test_invert_4pl_recovers_conc():
    x = np.array([c for c in CONCS if c > 0], dtype=float)
    y = _four_pl(x, **TRUE_PARAMS)
    fit = fit_4pl(x, y)
    x_hat = invert_4pl(y, fit.params)
    for orig, hat in zip(x, x_hat):
        assert hat == pytest.approx(orig, rel=0.02)


def test_fit_linear_recovers_params():
    x = np.array([c for c in CONCS], dtype=float)
    y = 0.0005 * x + 0.1
    fit = fit_linear(x, y)
    assert fit.params["slope"] == pytest.approx(0.0005, rel=0.02)
    assert fit.params["intercept"] == pytest.approx(0.1, rel=0.02)
    assert fit.r2 > 0.99


def test_invert_linear():
    params = {"slope": 2.0, "intercept": 1.0}
    assert invert_linear(5.0, params) == pytest.approx(2.0)


def test_fit_standards_per_plate():
    df = subtract_blank(_synthetic_mapped_df())
    fits = fit_standards(df, model="4pl")
    assert set(fits.keys()) == {1}
    assert fits[1].model in ("4pl", "linear")


def test_quantify_recovers_sample_conc():
    df = subtract_blank(_synthetic_mapped_df())
    result = quantify(df, model="4pl")
    sample1 = result[result.short_id == "S1"]
    assert sample1["conc_ugml_final"].mean() == pytest.approx(300.0, rel=0.05)
    sample2 = result[result.short_id == "S2"]
    assert sample2["conc_ugml_final"].mean() == pytest.approx(600.0, rel=0.05)


def test_quantify_linear_fallback():
    df = subtract_blank(_synthetic_mapped_df(model="linear"))
    result = quantify(df, model="4pl")
    sample1 = result[result.short_id == "S1"]
    assert sample1["conc_ugml_final"].mean() == pytest.approx(300.0, rel=0.1)


def test_summarize_gives_cv():
    df = subtract_blank(_synthetic_mapped_df())
    result = quantify(df, model="4pl")
    summary = summarize(result)
    sample_rows = summary[summary.short_id == "S1"]
    assert len(sample_rows) == 1
    row = sample_rows.iloc[0]
    assert row["n"] == 3
    assert row["cv_pct"] >= 0
    assert "any_out_of_range" in summary.columns


def test_nan_top_standard_is_dropped_not_fatal():
    df = _synthetic_mapped_df()
    df.loc[df["conc_ugml"] == 2000, "absorbance"] = np.nan
    fits = fit_standards(subtract_blank(df), "4pl")
    assert all(np.isfinite(list(f.params.values())).all() for f in fits.values())


def test_summarize_only_samples_in_order():
    out = summarize(quantify(subtract_blank(_synthetic_mapped_df()), "4pl"))
    assert not out["short_id"].isin(["BLK"]).any()
    assert not out["short_id"].str.startswith("STD").any()
    ids = out["short_id"].str[1:].astype(int).tolist()
    assert ids == sorted(ids)


def test_uninvertible_reading_is_flagged_out_of_range():
    df = subtract_blank(_synthetic_mapped_df())
    fits = fit_standards(df, "4pl")
    floor = min(fits[1].params["a"], fits[1].params["d"])
    sample_rows = df.index[df["role"] == "sample"]
    df.loc[sample_rows[0], "abs_blanked"] = floor - 0.01
    out = quantify(df, "4pl")
    row = out.loc[sample_rows[0]]
    assert np.isnan(row["conc_ugml_est"]) and bool(row["out_of_range"])


def test_reagent_blank_summary_empty_when_none():
    df = _synthetic_mapped_df()
    out = reagent_blank_summary(df)
    assert out.empty
    assert list(out.columns) == [
        "plate",
        "reagent_blank_mean",
        "reagent_blank_sd",
        "reagent_blank_n",
        "buffer_blank_mean",
        "buffer_background",
    ]


def test_reagent_blank_summary_values():
    df = _synthetic_mapped_df(with_reagent_blank=True, reagent_blank_absorbance=1.0)
    blank_mean = df.loc[df.role == "blank", "absorbance"].mean()
    out = reagent_blank_summary(df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["plate"] == 1
    assert row["reagent_blank_mean"] == pytest.approx(1.0)
    assert row["reagent_blank_sd"] == pytest.approx(0.0)
    assert row["reagent_blank_n"] == 2
    assert row["buffer_blank_mean"] == pytest.approx(blank_mean)
    assert row["buffer_background"] == pytest.approx(blank_mean - 1.0)


def test_subtract_blank_ignores_reagent_blank():
    # Give the reagent (WR-only) blank a wildly different absorbance; blank
    # subtraction (and therefore downstream results) must be unaffected.
    df_no_wr = _synthetic_mapped_df()
    df_with_wr = _synthetic_mapped_df(with_reagent_blank=True, reagent_blank_absorbance=99.0)

    blanked_no_wr = subtract_blank(df_no_wr)
    blanked_with_wr = subtract_blank(df_with_wr)

    std_no_wr = blanked_no_wr.loc[blanked_no_wr.role == "standard", "abs_blanked"].reset_index(drop=True)
    std_with_wr = blanked_with_wr.loc[blanked_with_wr.role == "standard", "abs_blanked"].reset_index(drop=True)
    pd.testing.assert_series_equal(std_no_wr, std_with_wr)

    quantified_no_wr = quantify(blanked_no_wr, "4pl")
    quantified_with_wr = quantify(blanked_with_wr, "4pl")
    summary_no_wr = summarize(quantified_no_wr)
    summary_with_wr = summarize(quantified_with_wr)
    pd.testing.assert_frame_equal(summary_no_wr, summary_with_wr)

    # reagent_blank rows are excluded from the sample summary entirely.
    assert not summary_with_wr["short_id"].isin(["WR"]).any()
