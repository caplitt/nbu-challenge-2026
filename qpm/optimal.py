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
                 last_from: str | None = None, landing_plan: Plan | None = None):
    """landing_plan: from `last_from` on, inflation and the gap are taken from this plan instead of `plan` — e.g. the
    path reacts to first-round administered prices only partly while they happen (`plan`), but the landing on the
    target at the end of the horizon is judged on actual inflation (`landing_plan`, all judgments in full).

    The CPI nowcast enters as fixed shocks (implied once, under the rule): if it stayed an exogenised value, every
    alternative rate path would imply its own cost-push shock in 2026Q4 — the higher the rate, the bigger the shock —
    and that shock would carry over into 2027, biasing the optimum against higher rates."""
    plan = pipeline.nowcast_to_shock(ctx, plan)
    if landing_plan is not None:
        landing_plan = pipeline.nowcast_to_shock(ctx, landing_plan)
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
    land = np.array([bool(last_from) and p >= pd.Period(last_from, "Q") for p in fc])
    if landing_plan is not None:   # the model is linear and both plans share exo/endo: only the free terms differ
        base_l = pipeline.with_rate_path(landing_plan, {str(p): v for p, v in fixed.items()})
        y0l = pipeline.run(ctx, pipeline.with_rate_path(base_l, {str(q): float(v) for q, v in zip(ctrl, x0)}))
        pi0[land] = (y0l["d4l_cpi"].reindex(fc).values - M_pi @ x0)[land]
        gap0[land] = (y0l["l_gdp_gap"].reindex(fc).values - M_gap @ x0)[land]
    w = np.where(land, w_last, 1.0)
    # the change is measured from the rate in force (not from the quarterly average that includes earlier decisions)
    i_prev = float(ctx.get("rate_now", base_rule.loc[ctrl[0] - 1, "ir_pol"])) if not fixed else float(base_rule.loc[ctrl[0] - 1, "ir_pol"])
    D = np.eye(n) - np.eye(n, k=-1)
    d0 = np.zeros(n)
    d0[0] = -i_prev
    A = np.vstack([np.sqrt(w)[:, None] * M_pi, np.sqrt(w_gap) * M_gap, np.sqrt(w_smooth) * D])
    b = np.concatenate([np.sqrt(w) * (target - pi0), -np.sqrt(w_gap) * gap0, -np.sqrt(w_smooth) * d0])
    x_opt, *_ = np.linalg.lstsq(A, b, rcond=None)
    res = run_with(x_opt)

    def loss(df):
        pi, gap, i = (df[c].reindex(fc).values for c in ("d4l_cpi", "l_gdp_gap", "ir_pol"))
        pi, gap = pi.copy(), gap.copy()
        pi[land] = (pi0 + M_pi @ i[len(fixed):])[land]     # landing quarters as in the objective
        gap[land] = (gap0 + M_gap @ i[len(fixed):])[land]
        di = np.diff(np.concatenate([[i_prev], i[len(fixed):]]))
        return float((w * (pi - target) ** 2).sum() + w_gap * (gap ** 2).sum() + w_smooth * (di ** 2).sum())

    path = pd.Series({**fixed, **dict(zip(ctrl, x_opt))}).sort_index()
    return res, path, {"optimal": loss(res), "rule": loss(base_rule)}


def policy_loss(ctx, df: pd.DataFrame, w_gap=0.5, w_smooth=0.5, w_last=1.0, last_from: str | None = None,
                df_land: pd.DataFrame | None = None) -> float:
    """The same loss as in optimal_path, over the whole forecast horizon, including the decision itself (the
    change from the last history quarter): comparable across decision options. df_land — as landing_plan above."""
    fc = ctx["rngfcast"]
    target = ctx["model"].params["dl_cpi_tar"]
    land = np.array([bool(last_from) and p >= pd.Period(last_from, "Q") for p in fc])
    w = np.where(land, w_last, 1.0)
    pi, gap, i = (df[c].reindex(fc).values.copy() for c in ("d4l_cpi", "l_gdp_gap", "ir_pol"))
    if df_land is not None:
        pi[land] = df_land["d4l_cpi"].reindex(fc).values[land]
        gap[land] = df_land["l_gdp_gap"].reindex(fc).values[land]
    i_now = float(ctx.get("rate_now", ctx["filt"].vars.loc[fc[0] - 1, "ir_pol"]))   # the rate in force now
    di = np.diff(np.concatenate([[i_now], i]))
    return float((w * (pi - target) ** 2).sum() + w_gap * (gap ** 2).sum() + w_smooth * (di ** 2).sum())
