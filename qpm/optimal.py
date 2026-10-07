"""Optimal policy-rate path under the model: minimise a quadratic loss over the forecast horizon.

    L = sum_t [ (pi_t - target)^2 + w_gap * gap_t^2 + w_smooth * (i_t - i_{t-1})^2 ]

The forecast is linear in an exogenised rate path, so the problem is a linear least-squares one:
x = rate path, pi(x) = pi0 + M_pi x, gap(x) = gap0 + M_gap x.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import pipeline
from .simulate import Plan


def optimal_path(ctx, plan: Plan, w_gap=0.5, w_smooth=0.5, horizon_end=None, extra_weight_until=None):
    fc = ctx["rngfcast"]
    target = ctx["model"].params["dl_cpi_tar"]
    per = fc if horizon_end is None else fc[fc <= pd.Period(horizon_end, "Q")]
    n = len(per)

    def run_with(path):
        p = pipeline.with_rate_path(plan, {str(q): float(v) for q, v in zip(per, path)})
        return pipeline.run(ctx, p)

    base_rule = pipeline.run(ctx, plan)
    x0 = base_rule["ir_pol"].reindex(per).values
    y0 = run_with(x0)
    M_pi, M_gap = np.zeros((n, n)), np.zeros((n, n))
    for k in range(n):
        x = x0.copy()
        x[k] += 1.0
        yk = run_with(x)
        M_pi[:, k] = (yk["d4l_cpi"].reindex(per) - y0["d4l_cpi"].reindex(per)).values
        M_gap[:, k] = (yk["l_gdp_gap"].reindex(per) - y0["l_gdp_gap"].reindex(per)).values
    pi0 = y0["d4l_cpi"].reindex(per).values - M_pi @ x0
    gap0 = y0["l_gdp_gap"].reindex(per).values - M_gap @ x0
    i_prev = float(base_rule.loc[per[0] - 1, "ir_pol"])
    D = np.eye(n) - np.eye(n, k=-1)
    d0 = np.zeros(n)
    d0[0] = -i_prev
    A = np.vstack([M_pi, np.sqrt(w_gap) * M_gap, np.sqrt(w_smooth) * D])
    b = np.concatenate([target - pi0, -np.sqrt(w_gap) * gap0, -np.sqrt(w_smooth) * d0])
    x_opt, *_ = np.linalg.lstsq(A, b, rcond=None)
    res = run_with(x_opt)

    def loss(df):
        pi, gap, i = (df[c].reindex(per).values for c in ("d4l_cpi", "l_gdp_gap", "ir_pol"))
        di = np.diff(np.concatenate([[i_prev], i]))
        return float(((pi - target) ** 2).sum() + w_gap * (gap ** 2).sum() + w_smooth * (di ** 2).sum())

    return res, pd.Series(x_opt, index=per), {"optimal": loss(res), "rule": loss(base_rule)}
