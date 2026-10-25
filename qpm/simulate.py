"""Simulations: impulse responses and forecasts with exogenized variables (IRIS `plan`)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .model import Model


def irf(model: Model, shock: str, size: float = 1.0, horizon: int = 20) -> pd.DataFrame:
    """Response to a one-off shock in period 1 (deviation from steady state, like IRIS srf).

    Row 0 is the pre-shock period (all zeros), rows 1..horizon follow the shock.
    """
    j = model.shocks.index(shock)
    s = np.zeros((horizon + 1, model.n_states))
    s[1] = model.R0[:, j] * size
    for t in range(2, horizon + 1):
        s[t] = model.T @ s[t - 1]
    return pd.DataFrame(s[:, : len(model.tvars)], columns=model.tvars)


@dataclass
class Plan:
    """Conditions for a forecast: fix variable paths, freeing the same number of shocks.

    exogenize(var, periods, values) + endogenize(shock, periods) mirrors IRIS.
    Shocks are anticipated (perfect foresight over the horizon), as in jforecast(..., 'anticipate', true).
    Fixed shock values (judgment) are added with `shock(name, periods, values)`.
    """

    periods: pd.PeriodIndex
    exo: dict = field(default_factory=dict)      # var -> {period: value}
    endo: dict = field(default_factory=dict)     # shock -> set(periods)
    shocks: dict = field(default_factory=dict)   # shock -> {period: value}

    def copy(self) -> "Plan":
        return Plan(self.periods,
                    {k: dict(v) for k, v in self.exo.items()},
                    {k: set(v) for k, v in self.endo.items()},
                    {k: dict(v) for k, v in self.shocks.items()})

    def _pers(self, periods):
        if isinstance(periods, (str, pd.Period)):
            return [pd.Period(periods, "Q")]
        return [pd.Period(p, "Q") for p in periods]

    def exogenize(self, var, periods, values):
        pers = self._pers(periods)
        vals = np.broadcast_to(np.asarray(values, float), (len(pers),))
        self.exo.setdefault(var, {}).update(dict(zip(pers, vals)))
        return self

    def endogenize(self, shock, periods):
        self.endo.setdefault(shock, set()).update(self._pers(periods))
        return self

    def shock(self, shock, periods, values):
        """Add a judgment shock; values add up with shocks already in the plan (scenarios go on top of the baseline)."""
        pers = self._pers(periods)
        vals = np.broadcast_to(np.asarray(values, float), (len(pers),))
        d = self.shocks.setdefault(shock, {})
        for p, v in zip(pers, vals):
            d[p] = d.get(p, 0.0) + float(v)
        return self


def _simulate(model: Model, s0: np.ndarray, eps: np.ndarray, anticipate=True) -> np.ndarray:
    """Simulate H periods from state s0 with the shock matrix eps (H x shocks). With anticipate=True agents see the
    whole shock path at t=0: the period-t state adds R(j) @ eps[t+j] for every future shock j (perfect foresight,
    IRIS jforecast 'anticipate' true); otherwise only the current shock enters (R0)."""
    H = eps.shape[0]
    R = [model.R(j) for j in range(H)] if anticipate else [model.R0]
    s = np.zeros((H, model.n_states))
    prev = s0
    for t in range(H):
        x = model.T @ prev + model.C
        if anticipate:
            for j in range(H - t):
                x = x + R[j] @ eps[t + j]
        else:
            x = x + R[0] @ eps[t]
        s[t] = x
        prev = x
    return s


def forecast(model: Model, s0: np.ndarray, plan: Plan, anticipate=True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run a conditional forecast from initial state s0 (state at the period before plan.periods[0]).

    Returns (variables, shocks) as DataFrames indexed by plan.periods.
    """
    per = list(plan.periods)
    H, k = len(per), len(model.shocks)
    pidx = {p: i for i, p in enumerate(per)}
    # 1) judgment shocks from the plan, 2) the free (endogenized) shocks and the fixed (exogenized) points
    eps = np.zeros((H, k))
    for name, d in plan.shocks.items():
        for p, v in d.items():
            eps[pidx[p], model.shocks.index(name)] = v
    free = [(pidx[p], model.shocks.index(sh)) for sh, ps in plan.endo.items() for p in sorted(ps)]
    cons = [(pidx[p], model.si[v], val) for v, d in plan.exo.items() for p, val in d.items()]
    if len(free) != len(cons):
        raise ValueError(f"Plan is not exactly determined: {len(cons)} exogenized points vs {len(free)} endogenized shocks")
    base = _simulate(model, s0, eps, anticipate)
    if cons:
        # The model is linear, so each exogenized point is a linear function of the free shocks: M[i, j] = response
        # of fixed point i to a unit free shock j (anticipated, hence the full-horizon simulation per shock). Solving
        # M x = (target − unconditional path) gives the shock values that hit every fixed point exactly — the same
        # algebra as IRIS jforecast with exogenize/endogenize.
        M = np.zeros((len(cons), len(free)))
        for jcol, (t, sh) in enumerate(free):
            e = np.zeros_like(eps); e[t, sh] = 1.0
            resp = _simulate(model, np.zeros_like(s0), e, anticipate) - _simulate(model, np.zeros_like(s0), np.zeros_like(eps), anticipate)
            M[:, jcol] = [resp[t2, i] for (t2, i, _) in cons]
        gap = np.array([val - base[t2, i] for (t2, i, val) in cons])
        x = np.linalg.solve(M, gap)
        for (t, sh), xv in zip(free, x):
            eps[t, sh] += xv
        base = _simulate(model, s0, eps, anticipate)
    vars_df = pd.DataFrame(base[:, : len(model.tvars)], index=plan.periods, columns=model.tvars)
    shocks_df = pd.DataFrame(eps, index=plan.periods, columns=model.shocks)
    return vars_df, shocks_df
