"""Standard-curve fitting and quantification for BCA plate results."""

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


@dataclass
class FitResult:
    model: str
    params: dict
    r2: float


def load_mapped(path: str) -> pd.DataFrame:
    """Load a mapped CSV (well-level results) into a DataFrame."""
    return pd.read_csv(path)


def subtract_blank(df: pd.DataFrame) -> pd.DataFrame:
    """Add abs_blanked = absorbance - the plate's mean blank absorbance."""
    df = df.copy()
    blank_means = df.loc[df["role"] == "blank"].groupby("plate")["absorbance"].mean()
    df["abs_blanked"] = df["absorbance"] - df["plate"].map(blank_means)
    return df


def _four_pl(x, a, b, c, d):
    return d + (a - d) / (1 + (x / c) ** b)


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0:
        return float("nan")
    return 1 - ss_res / ss_tot


def fit_4pl(conc: np.ndarray, absorbance: np.ndarray) -> FitResult:
    """Fit a 4-parameter logistic curve to standard-curve points."""
    x = np.asarray(conc, dtype=float)
    y = np.asarray(absorbance, dtype=float)
    positive_x = x[x > 0]
    p0 = [float(np.min(y)), 1.0, float(np.median(positive_x)), float(np.max(y))]
    bounds = ([-np.inf, 0, 0, -np.inf], [np.inf, np.inf, np.inf, np.inf])
    popt, _ = curve_fit(_four_pl, x, y, p0=p0, bounds=bounds, maxfev=20000)
    y_pred = _four_pl(x, *popt)
    params = {"a": popt[0], "b": popt[1], "c": popt[2], "d": popt[3]}
    return FitResult(model="4pl", params=params, r2=_r2(y, y_pred))


def fit_linear(conc: np.ndarray, absorbance: np.ndarray) -> FitResult:
    """Fit a straight line (slope, intercept) to standard-curve points."""
    x = np.asarray(conc, dtype=float)
    y = np.asarray(absorbance, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    params = {"slope": float(slope), "intercept": float(intercept)}
    return FitResult(model="linear", params=params, r2=_r2(y, y_pred))


def invert_4pl(y, params: dict):
    """Invert the 4PL curve: y -> x. NaN outside the open interval spanned by a, d."""
    a, b, c, d = params["a"], params["b"], params["c"], params["d"]
    y = np.asarray(y, dtype=float)
    lo, hi = sorted((a, d))
    with np.errstate(invalid="ignore", divide="ignore"):
        x = c * (((a - d) / (y - d)) - 1) ** (1 / b)
    valid = (y > lo) & (y < hi)
    result = np.where(valid, x, np.nan)
    return result if result.ndim else float(result)


def invert_linear(y, params: dict):
    """Invert a linear curve: y -> x."""
    slope, intercept = params["slope"], params["intercept"]
    y = np.asarray(y, dtype=float)
    result = (y - intercept) / slope
    return result if result.ndim else float(result)


def _standard_curve(df: pd.DataFrame, plate) -> tuple[np.ndarray, np.ndarray]:
    std = df[(df["plate"] == plate) & (df["role"].isin(["standard", "blank"]))]
    grouped = std.groupby("conc_ugml")["abs_blanked"].mean().sort_index().dropna()
    if len(grouped) < 2:
        raise ValueError(f"plate {plate}: fewer than 2 standard concentrations have readings")
    return grouped.index.to_numpy(dtype=float), grouped.to_numpy(dtype=float)


def fit_standards(df: pd.DataFrame, model: str = "4pl") -> dict:
    """Fit the standard curve for each plate, falling back to linear on 4PL failure."""
    results = {}
    for plate in sorted(df["plate"].unique()):
        x, y = _standard_curve(df, plate)
        if model == "4pl":
            try:
                results[plate] = fit_4pl(x, y)
                continue
            except (RuntimeError, ValueError):
                warnings.warn(f"4PL fit failed for plate {plate}; falling back to linear")
        results[plate] = fit_linear(x, y)
    return results


def quantify(df: pd.DataFrame, model: str = "4pl") -> pd.DataFrame:
    """Add conc_ugml_est, conc_ugml_final, and out_of_range columns."""
    if "abs_blanked" not in df.columns:
        df = subtract_blank(df)
    else:
        df = df.copy()

    fits = fit_standards(df, model)

    est = np.full(len(df), np.nan)
    out_of_range = np.zeros(len(df), dtype=bool)

    for plate in sorted(df["plate"].unique()):
        fit = fits[plate]
        mask = (df["plate"] == plate).to_numpy()
        y = df.loc[mask, "abs_blanked"].to_numpy(dtype=float)
        if fit.model == "4pl":
            x = invert_4pl(y, fit.params)
        else:
            x = invert_linear(y, fit.params)
        est[mask] = np.atleast_1d(x)

        conc, abs_vals = _standard_curve(df, plate)
        nonzero = conc > 0
        top_abs = abs_vals[np.argmax(conc)]
        low_abs = abs_vals[nonzero][np.argmin(conc[nonzero])]
        lo, hi = sorted((top_abs, low_abs))
        out_of_range[mask] = (y < lo) | (y > hi)

    df["conc_ugml_est"] = est
    df["conc_ugml_final"] = df["conc_ugml_est"] * df["dilution_factor"]
    df["out_of_range"] = out_of_range
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize sample replicates, one row per sample in plate order (S1, S2, ...)."""
    samples = df[df["role"] == "sample"].copy()
    samples["_order"] = samples["short_id"].str[1:].astype(int)
    samples = samples.sort_values(["plate", "_order"])
    grouped = samples.groupby(
        ["plate", "short_id", "sample_name", "dilution_factor"], dropna=False, sort=False
    )
    summary = grouped["conc_ugml_final"].agg(mean="mean", sd=lambda s: s.std(ddof=1), n="count")
    summary["cv_pct"] = summary["sd"] / summary["mean"] * 100
    summary["any_out_of_range"] = grouped["out_of_range"].any()
    return summary.reset_index()
