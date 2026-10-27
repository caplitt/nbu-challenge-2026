"""Short-term (current-quarter) nowcasts for months not yet published.

CPI (headline and core — the same method):
    m-o-m(month) = trend (avg SA m-o-m over the last `trend_window` months)
                 + seasonal factor of that calendar month (avg over the last `seasonal_years` years, STL)
                 + adjustment (judgment, pp per month)

Exchange rate (UAH/EUR, the rate the model sees): the quarter's average = months already observed at their
month-to-date average, the remaining months at the latest official rate (unchanged — the usual no-change
assumption for exchange rates). Without it the model's current-quarter rate would ignore the official rate already
known for most of the quarter (in October 2026 the hryvnia moved to a record low vs USD and strengthened vs EUR).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from .data import SEASONAL_WINDOW, read_iris_csv


def cpi_nowcast(until: str, data_dir="data", trend_window=3, seasonal_years=5, adjustment=0.0,
                start="2010-01", series="D_CPI_su_m", factor_sample_end: str | None = None) -> pd.DataFrame:
    """series: D_CPI_su_m (headline) or D_CPI_C_su_m (core) — the same method for both.

    factor_sample_end: estimate the seasonal factors on data up to this month only (e.g. "2025-12": factors
    'projected' from the last complete year, as X-13 producers do) and apply them to later months; None = the whole
    sample. The default is the whole sample with the window below; the sensitivity of the December nowcast to this
    and to `trend_window` / `adjustment` is tabulated in docs/audit_2026-10-25.md."""
    dm, _ = read_iris_csv(f"{data_dir}/monthly.csv")
    x = dm[series].dropna().loc[start:]
    lvl = np.log((1 + x / 100).cumprod())
    # Not robust — as everywhere else (qpm.data.seasonal_adjust): robust STL treats the 2022 shock as outliers and
    # gave implausible December factors (+0.6 pp headline, −0.6 pp core). Seasonal window as in seasonal_adjust
    # (13): with the statsmodels default (7) the newest month largely wrote its own seasonal factor — September 2026
    # (+2.1% m/m) got a factor of 0.75 pp against 0.1–0.3 for the Septembers of 2021–2025 in the same run, hiding a
    # third of the jump inside "seasonality"; with 13 it gets 0.41 against 0.36–0.38 in the same run. That is not
    # proof of stability: STL still revises the factors of the last cycle when a month is added (the Septembers of
    # 2021–2025 rise from 0.32…−0.16 to 0.36–0.38 with September 2026 in the sample, the Octobers fall by ≈0.2 pp —
    # October's factor in this nowcast is 0.24 against ≈0.47 without September 2026, worth ≈+0.2 pp on December),
    # which `factor_sample_end` avoids at the cost of ignoring the newest seasonal information. Hence the
    # sensitivity table in docs/audit_2026-10-25.md: December between 11.3% (window 7) and 13.1% (factors frozen).
    est = lvl if factor_sample_end is None else lvl.loc[:factor_sample_end]
    res = STL(est.values, period=12, seasonal=SEASONAL_WINDOW[12], robust=False).fit()
    seas = pd.Series(res.seasonal, index=est.index)
    sf = seas.diff() * 100
    factor = sf.groupby(sf.index.month).apply(lambda s: s.iloc[-seasonal_years:].mean())
    if factor_sample_end is None:
        sa_mom = pd.Series(lvl.values - res.seasonal, index=lvl.index).diff() * 100
    else:   # months after the estimation sample: raw m-o-m minus the projected factor of that calendar month
        sa_mom = x - np.array([factor[m.month] for m in x.index])
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
    out.attrs["sa_mom_last"] = sa_mom.iloc[-trend_window:].round(2).to_dict()
    return out


def as_dict(nc: pd.DataFrame) -> dict[str, float]:
    return {str(p): float(v) for p, v in nc["ІСЦ м/м, прогноз"].items()}


def fx_nowcast(quarter: str, data_dir="data", raw_file="raw/nbu_eur.csv") -> dict:
    """Quarterly average UAH/EUR for `quarter` from the daily official rate: observed months at their (month-to-date)
    average, later months at the last observed rate. Returns {"level": avg, "months": {...}, "last_date": ...}."""
    s = pd.read_csv(f"{data_dir}/{raw_file}", index_col=0).iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    s = s.dropna()
    q = pd.Period(quarter, "Q")
    months = pd.period_range(q.asfreq("M", "start"), q.asfreq("M", "end"), freq="M")
    detail, vals = {}, []
    s_month = s.index.to_period("M")
    for m in months:
        d = s[s_month == m]
        if len(d):
            vals.append(float(d.mean()))
            detail[str(m)] = f"{d.mean():.4f} (середнє {d.index.min().date()}–{d.index.max().date()})"
        else:
            vals.append(float(s.iloc[-1]))
            detail[str(m)] = f"{s.iloc[-1]:.4f} (без змін від {s.index.max().date()})"
    return {"level": float(np.mean(vals)), "months": detail, "last_date": str(s.index.max().date()),
            "last_rate": float(s.iloc[-1])}
