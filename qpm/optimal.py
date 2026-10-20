"""Optimal policy-rate path under the model: minimise a quadratic loss over the forecast horizon.

    L = sum_t [ w_t (pi_t - target)^2 + w_gap * gap_t^2 + w_smooth * (i_t - i_{t-1})^2 ]

w_t = 1, except w_last from `last_from` on: a heavier weight at the end of the policy horizon makes the path land
on the point target (NBU: 5% within a horizon of up to three years). Quarters in `fixed` keep the given rate
(e.g. the October decision and the promised hold); only the remaining quarters are optimised.

The forecast is linear in an exogenised rate path, so the problem is a linear least-squares one:
x = rate path, pi(x) = pi0 + M_pi x, gap(x) = gap0 + M_gap x.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import pipeline
from .simulate import Plan


def optimal_path(ctx, plan: Plan, w_gap=0.5, w_smooth=0.5, fixed: dict | None = None, w_last=1.0,
                 last_from: str | None = None):
    fc = ctx["rngfcast"]
    target = ctx["model"].params["dl_cpi_tar"]
    fixed = {pd.Period(k, "Q"): float(v) for k, v in (fixed or {}).items()}
    ctrl = [p for p in fc if p not in fixed]
    assert all(p < ctrl[0] for p in fixed), "fixed quarters must precede the optimised ones"
    n = len(ctrl)
    base = pipeline.with_rate_path(plan, {str(p): v for p, v in fixed.items()})

    def run_with(path):
        return pipeline.run(ctx, pipeline.with_rate_path(base, {str(q): float(v) for q, v in zip(ctrl, path)}))

    base_rule = pipeline.run(ctx, base)          # fixed quarters, then the Taylor rule
    x0 = base_rule["ir_pol"].reindex(ctrl).values
    y0 = run_with(x0)
    M_pi, M_gap = np.zeros((len(fc), n)), np.zeros((len(fc), n))
    for k in range(n):
        x = x0.copy()
        x[k] += 1.0
        yk = run_with(x)
        M_pi[:, k] = (yk["d4l_cpi"].reindex(fc) - y0["d4l_cpi"].reindex(fc)).values
        M_gap[:, k] = (yk["l_gdp_gap"].reindex(fc) - y0["l_gdp_gap"].reindex(fc)).values
    pi0 = y0["d4l_cpi"].reindex(fc).values - M_pi @ x0
    gap0 = y0["l_gdp_gap"].reindex(fc).values - M_gap @ x0
    w = np.array([w_last if last_from and p >= pd.Period(last_from, "Q") else 1.0 for p in fc])
    i_prev = float(base_rule.loc[ctrl[0] - 1, "ir_pol"])
    D = np.eye(n) - np.eye(n, k=-1)
    d0 = np.zeros(n)
    d0[0] = -i_prev
    A = np.vstack([np.sqrt(w)[:, None] * M_pi, np.sqrt(w_gap) * M_gap, np.sqrt(w_smooth) * D])
    b = np.concatenate([np.sqrt(w) * (target - pi0), -np.sqrt(w_gap) * gap0, -np.sqrt(w_smooth) * d0])
    x_opt, *_ = np.linalg.lstsq(A, b, rcond=None)
    res = run_with(x_opt)

    def loss(df):
        pi, gap, i = (df[c].reindex(fc).values for c in ("d4l_cpi", "l_gdp_gap", "ir_pol"))
        di = np.diff(np.concatenate([[i_prev], i[len(fixed):]]))
        return float((w * (pi - target) ** 2).sum() + w_gap * (gap ** 2).sum() + w_smooth * (di ** 2).sum())

    path = pd.Series({**fixed, **dict(zip(ctrl, x_opt))}).sort_index()
    return res, path, {"optimal": loss(res), "rule": loss(base_rule)}


def policy_loss(ctx, df: pd.DataFrame, w_gap=0.5, w_smooth=0.5, w_last=1.0, last_from: str | None = None) -> float:
    """The same loss as in optimal_path, over the whole forecast horizon, including the decision itself (the
    change from the last history quarter): comparable across decision options."""
    fc = ctx["rngfcast"]
    target = ctx["model"].params["dl_cpi_tar"]
    w = np.array([w_last if last_from and p >= pd.Period(last_from, "Q") else 1.0 for p in fc])
    pi, gap, i = (df[c].reindex(fc).values for c in ("d4l_cpi", "l_gdp_gap", "ir_pol"))
    di = np.diff(np.concatenate([[float(ctx["filt"].vars.loc[fc[0] - 1, "ir_pol"])], i]))
    return float((w * (pi - target) ** 2).sum() + w_gap * (gap ** 2).sum() + w_smooth * (di ** 2).sum())
