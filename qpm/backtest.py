"""Quasi-real-time backtest: forecast as if made after `origin`, compared with what actually happened.

Domestic data after the origin are hidden; external variables are taken as actually realised (conditional
forecast), and no judgment shocks are used — this measures the model itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import pipeline

VARS = {"d4l_cpi": "ІСЦ, % р/р", "ir_pol": "Облікова ставка, %", "uah_eur": "Курс, грн/€", "gdp_yoy": "ВВП, % р/р"}


def run(cfg, origin: str, actual: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    ctx = pipeline.prepare(cfg, last_hist=origin, use_nowcast=False)
    fc = pipeline.run(ctx, pipeline.base_plan(ctx, judgments=False))
    per = pd.period_range(pd.Period(origin, "Q") + 1, periods=horizon, freq="Q")
    rows = {}
    for v, lab in VARS.items():
        rows[(lab, "Прогноз")] = fc[v].reindex(per)
        rows[(lab, "Факт")] = actual[v].reindex(per)
        rows[(lab, "Без змін (наївний)")] = pd.Series(actual[v].get(pd.Period(origin, "Q"), np.nan), index=per)
    out = pd.DataFrame(rows).T
    out.columns = [str(p) for p in per]
    return out


def errors(table: pd.DataFrame) -> pd.DataFrame:
    """RMSE of the model vs the naive no-change forecast, by variable."""
    res = {}
    for lab in table.index.get_level_values(0).unique():
        f, a, n = (table.loc[(lab, k)].astype(float) for k in ("Прогноз", "Факт", "Без змін (наївний)"))
        mask = a.notna()
        res[lab] = {"RMSE моделі": float(np.sqrt(((f - a)[mask] ** 2).mean())),
                    "RMSE наївного": float(np.sqrt(((n - a)[mask] ** 2).mean()))}
    return pd.DataFrame(res).T.round(2)
