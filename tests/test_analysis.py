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
    subtract_blank,
    summarize,
)

TRUE_PARAMS = {"a": 0.05, "b": 1.2, "c": 400.0, "d": 2.2}
CONCS = [2000, 1500, 1000, 750, 500, 250, 125, 25, 0]


def _four_pl(x, a, b, c, d):
    return d + (a - d) / (1 + (x / c) ** b)


def _synthetic_mapped_df(model="4pl"):
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
