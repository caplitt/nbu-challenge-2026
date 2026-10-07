"""Kalman filter and smoother for the solved QPM — counterpart of IRIS `filter` (a03_run_filter.m)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.linalg as sla

from .model import Model

DIFFUSE = 1e8


@dataclass
class FilterResult:
    vars: pd.DataFrame        # smoothed transition variables
    shocks: pd.DataFrame      # smoothed shocks
    states: np.ndarray        # smoothed full state vectors (incl. auxiliary lags/leads)
    std: pd.DataFrame         # smoothed std of transition variables
    periods: pd.PeriodIndex

    def state_at(self, period) -> np.ndarray:
        return self.states[self.periods.get_loc(pd.Period(period, "Q"))]


def _initial(model: Model, Q0: np.ndarray):
    """Stationary part from its unconditional distribution, unit-root part diffuse."""
    T, C, R = model.T, model.C, model.R0
    Ts, U, k = sla.schur(T, output="real", sort=lambda x, y: abs(complex(x, y)) > 1 - 1e-7)
    c = U.T @ C
    RQR = U.T @ R @ Q0 @ R.T @ U
    n = T.shape[0]
    a = np.zeros(n)
    P = np.zeros((n, n))
    if k < n:
        T22 = Ts[k:, k:]
        a[k:] = np.linalg.solve(np.eye(n - k) - T22, c[k:])
        P[k:, k:] = sla.solve_discrete_lyapunov(T22, RQR[k:, k:])
    P[:k, :k] = DIFFUSE * np.eye(k)
    return U @ a, U @ P @ U.T


def kalman_smoother(model: Model, data: pd.DataFrame, periods: pd.PeriodIndex,
                    std_override: dict[str, pd.Series] | None = None) -> FilterResult:
    """Filter + smoother over `periods`. `data` columns are measurement variable names.

    std_override: {shock: Series of std by period}; non-NaN values replace the model std
    in those periods (IRIS filter 'std' option).
    """
    T, C, R, Z, d = model.T, model.C, model.R0, model.Zm, model.dm
    n, nper = T.shape[0], len(periods)
    base_std = model.std_vector()
    stds = np.tile(base_std, (nper, 1))
    for shock, ser in (std_override or {}).items():
        j = model.shocks.index(shock)
        for i, p in enumerate(periods):
            if p in ser.index and not pd.isna(ser[p]):
                stds[i, j] = ser[p]
    Y = np.full((nper, len(model.mvars)), np.nan)
    for i, mv in enumerate(model.mvars):
        if mv in data.columns:
            Y[:, i] = data[mv].reindex(periods).values

    a, P = _initial(model, np.diag(stds[0] ** 2))
    a_pred = np.zeros((nper, n)); P_pred = np.zeros((nper, n, n))
    store = []
    for t in range(nper):
        Qt = np.diag(stds[t] ** 2)
        a = T @ a + C
        P = T @ P @ T.T + R @ Qt @ R.T
        a_pred[t], P_pred[t] = a, P
        obs = ~np.isnan(Y[t])
        if obs.any():
            Zt = Z[obs]
            v = Y[t, obs] - Zt @ a - d[obs]
            F = Zt @ P @ Zt.T
            Finv = np.linalg.inv(F)
            Kf = P @ Zt.T @ Finv
            a = a + Kf @ v
            P = P - Kf @ Zt @ P
            P = 0.5 * (P + P.T)
            store.append((Zt, v, Finv, Kf))
        else:
            store.append(None)

    r = np.zeros(n); N = np.zeros((n, n))
    s_hat = np.zeros((nper, n)); e_hat = np.zeros((nper, len(model.shocks)))
    V = np.zeros((nper, n))
    I = np.eye(n)
    for t in range(nper - 1, -1, -1):
        if store[t] is None:
            r_b = T.T @ r
            N_b = T.T @ N @ T
        else:
            Zt, v, Finv, Kf = store[t]
            L = T @ (I - Kf @ Zt)
            r_b = Zt.T @ Finv @ v + L.T @ r
            N_b = Zt.T @ Finv @ Zt + L.T @ N @ L
        s_hat[t] = a_pred[t] + P_pred[t] @ r_b
        V[t] = np.diag(P_pred[t] - P_pred[t] @ N_b @ P_pred[t])
        e_hat[t] = (stds[t] ** 2) * (R.T @ r_b)
        r, N = r_b, N_b

    nv = len(model.tvars)
    return FilterResult(
        vars=pd.DataFrame(s_hat[:, :nv], index=periods, columns=model.tvars),
        shocks=pd.DataFrame(e_hat, index=periods, columns=model.shocks),
        states=s_hat,
        std=pd.DataFrame(np.sqrt(np.clip(V[:, :nv], 0, None)), index=periods, columns=model.tvars),
        periods=periods,
    )
