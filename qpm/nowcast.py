"""Short-term CPI nowcast for months not yet published: SA trend + seasonal factor + judgment.

    m-o-m(month) = trend (avg SA m-o-m over the last `trend_window` months)
                 + seasonal factor of that calendar month (avg over the last `seasonal_years` years, STL)
                 + adjustment (judgment, pp per month)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from .data import read_iris_csv


def cpi_nowcast(until: str, data_dir="data", trend_window=3, seasonal_years=5, adjustment=0.0,
                start="2010-01", series="D_CPI_su_m") -> pd.DataFrame:
    """series: D_CPI_su_m (headline) or D_CPI_C_su_m (core) — the same method for both."""
    dm, _ = read_iris_csv(f"{data_dir}/monthly.csv")
    x = dm[series].dropna().loc[start:]
    lvl = np.log((1 + x / 100).cumprod())
    # not robust — as everywhere else (qpm.data.seasonal_adjust): robust STL treats the 2022 shock as outliers and
    # gave implausible December factors (+0.6 pp headline, −0.6 pp core)
    res = STL(lvl.values, period=12, robust=False).fit()
    seas = pd.Series(res.seasonal, index=lvl.index)
    sf = seas.diff() * 100
    factor = sf.groupby(sf.index.month).apply(lambda s: s.iloc[-seasonal_years:].mean())
    sa_mom = pd.Series(lvl.values - res.seasonal, index=lvl.index).diff() * 100
    trend = sa_mom.iloc[-trend_window:].mean()
    months = pd.period_range(x.index.max() + 1, until, freq="M")
    out = pd.DataFrame(index=months)
    out["Тренд (SA)"] = trend
    out["Сезонний фактор"] = [factor[m.month] for m in months]
    out["Судження"] = adjustment
    out["ІСЦ м/м, прогноз"] = out.sum(axis=1).round(2)
    # implied y-o-y using last year's actual m-o-m
    yoy = []
    base = (1 + x.iloc[-12:] / 100).prod()
    hist = list(x.iloc[-12:].values)
    for v in out["ІСЦ м/м, прогноз"]:
        hist = hist[1:] + [v]
        yoy.append((np.prod([1 + h / 100 for h in hist]) - 1) * 100)
    out["ІСЦ р/р, прогноз"] = np.round(yoy, 1)
    out.attrs["last_actual"] = x.index.max()
    return out


def as_dict(nc: pd.DataFrame) -> dict[str, float]:
    return {str(p): float(v) for p, v in nc["ІСЦ м/м, прогноз"].items()}
