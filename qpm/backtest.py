"""Quasi-real-time backtest: forecast as if made after `origin`, compared with what actually happened.

Domestic data after the origin are hidden — before seasonal adjustment, so the SA factors use only data available at
the origin (qpm.data.read_data(cutoff=origin)); external variables are taken as actually realised (conditional
forecast), and no judgment shocks or nowcasts are used — this measures the model itself.
"Actual" values come from the observed data only (actual_from_data): quarters without data are left blank, so a
model projection is never compared with itself (before 25.10.2026 the smoothed filter path, which runs past the
data, served as "actual" and the 4th horizon of the 2025Q4 origin was scored against the model's own projection).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import pipeline

VARS = {"cpi_yoy": "ІСЦ, % р/р", "ir_pol": "Облікова ставка, %", "uah_eur": "Курс, грн/€", "gdp_yoy": "ВВП, % р/р"}
OBS = {"cpi_yoy": "L_CPI", "ir_pol": "IR_POLICY", "uah_eur": "L_ER", "gdp_yoy": "L_GDP"}


def actual_from_data(dq: pd.DataFrame) -> pd.DataFrame:
    """Reporting variables (as pipeline.add_reporting) computed from the observed databank: NaN where no data."""
    out = pd.DataFrame(index=dq.index)
    out["cpi_yoy"] = pipeline.pct(dq["L_CPI"].diff(4))
    out["ir_pol"] = dq["IR_POLICY"]
    out["uah_eur"] = np.exp(dq["L_ER"] / 100)
    out["gdp_yoy"] = pipeline.pct(dq["L_GDP"].diff(4))
    return out


def run(cfg, origin: str, actual: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    """Forecast table for one origin: rows (variable, Прогноз / Факт / наївний), columns = horizon quarters."""
    ctx = pipeline.prepare(cfg, last_hist=origin, use_nowcast=False, cutoff=origin)
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
    """RMSE of the model vs the naive no-change forecast, by variable, over the horizons with actual data
    (1–4 quarters ahead; a quarter without data is skipped, and the number of scored quarters is reported)."""
    res = {}
    for lab in table.index.get_level_values(0).unique():
        f, a, n = (table.loc[(lab, k)].astype(float) for k in ("Прогноз", "Факт", "Без змін (наївний)"))
        mask = a.notna()
        res[lab] = {"RMSE моделі": float(np.sqrt(((f - a)[mask] ** 2).mean())),
                    "RMSE наївного": float(np.sqrt(((n - a)[mask] ** 2).mean())),
                    "Кварталів з фактом": int(mask.sum())}
    return pd.DataFrame(res).T.round(2)
