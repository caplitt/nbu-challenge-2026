"""Forecast uncertainty: fan charts by stochastic simulation around the baseline.

The model is linear, so each draw = baseline + response to unanticipated shocks e_t ~ N(0, sigma^2).
Sigma for each shock = std of its smoothed estimates over a recent window (2023Q1 onwards), i.e. the volatility the
economy actually showed after the 2022 shock. The shocks are the domestic ones plus the oil price and the
euro-area block: on the forecast those variables are fixed to assumptions (futures curve, ECB projections), and the
fan shows what their usual surprises would do. The calibrated std in model/params.yaml are not used here: they
matter only for the filter (how the data are split between shocks), not for the forecast bands.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .kalman import FilterResult
from .model import Model

DOMESTIC_SHOCKS = ["res_dl_cpi_c", "res_dl_rnc", "res_l_gdp_gap", "res_l_er_uip", "res_dl_er_tar", "res_ir_tlr", "res_prem_uip_gap"]
EXTERNAL_SHOCKS = ["res_dl_roil", "res_ir_ea", "res_dl_cpi_ea", "res_l_gdp_ea_gap"]
FAN_SHOCKS = DOMESTIC_SHOCKS + EXTERNAL_SHOCKS


def empirical_sigma(filt: FilterResult, start="2023Q1", end=None, shocks=FAN_SHOCKS) -> pd.Series:
    """Standard deviation of the smoothed shocks over [start, end] (the fan's shock volatility)."""
    sh = filt.shocks.loc[start:end]
    return sh[list(shocks)].std()


def fan(model: Model, baseline: pd.DataFrame, periods: pd.PeriodIndex, sigma: pd.Series,
        variables=("d4l_cpi", "ir_pol", "l_gdp_gap", "l_er"), n=2000, seed=42,
        quantiles=(0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 0.95)) -> dict[str, pd.DataFrame]:
    """Quantiles of each variable over the forecast `periods` (columns = quantiles)."""
    rng = np.random.default_rng(seed)
    H, N = len(periods), model.n_states
    idx = [model.shocks.index(s) for s in sigma.index]
    R = model.R0[:, idx]
    T = model.T
    draws = {v: np.zeros((n, H)) for v in variables}
    vi = {v: model.si[v] for v in variables}
    # the state carries all lags the y-o-y rates need (d4l_cpi is itself a model variable), so deviations from the
    # baseline are simply propagated with T and added to the baseline afterwards (linearity)
    for k in range(n):
        e = rng.normal(size=(H, len(idx))) * sigma.values
        x = np.zeros(N)
        for t in range(H):
            x = T @ x + R @ e[t]
            for v in variables:
                draws[v][k, t] = x[vi[v]]
    out = {}
    for v in variables:
        base = baseline[v].reindex(periods).values
        q = np.quantile(draws[v] + base, quantiles, axis=0).T
        out[v] = pd.DataFrame(q, index=periods, columns=[f"q{int(x * 100):02d}" for x in quantiles])
    return out


def probability_below(model, baseline, periods, sigma, var="d4l_cpi", threshold=6.0, n=2000, seed=7) -> pd.Series:
    """P(var < threshold) by quarter, e.g. the chance inflation is back within the target range (5% ± 1)."""
    f = fan(model, baseline, periods, sigma, variables=(var,), n=n, seed=seed,
            quantiles=tuple(np.linspace(0.01, 0.99, 99)))[var]
    probs = (f < threshold).mean(axis=1)
    return probs
