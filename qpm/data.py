"""Data handling for the QPM — Python counterpart of nbu_template/a01_read_data.m."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.filters.hp_filter import hpfilter
from statsmodels.tsa.seasonal import STL

NO_LOG = ("IR_EA", "IR_POLICY")


def _parse_period(s: str) -> pd.Period:
    s = s.strip()
    m = re.fullmatch(r"(\d{4})M(\d{1,2})", s)
    if m:
        return pd.Period(year=int(m.group(1)), month=int(m.group(2)), freq="M")
    m = re.fullmatch(r"(\d{4})Q(\d)", s)
    if m:
        return pd.Period(year=int(m.group(1)), quarter=int(m.group(2)), freq="Q")
    raise ValueError(f"Bad date: {s}")


def read_iris_csv(path) -> tuple[pd.DataFrame, dict]:
    """Read an IRIS databank CSV (row 1 = names, row 2 = 'comments')."""
    raw = pd.read_csv(path, header=0, dtype=str, keep_default_na=False)
    first = raw.columns[0]
    comments = {}
    if raw.iloc[0, 0].strip().lower() == "comments":
        comments = raw.iloc[0, 1:].to_dict()
        raw = raw.iloc[1:]
    idx = pd.PeriodIndex([_parse_period(x) for x in raw[first]])
    df = raw.drop(columns=first).replace("", np.nan).astype(float)
    df.index = idx
    return df, comments


def write_iris_csv(df: pd.DataFrame, path, comments: dict | None = None):
    comments = comments or {}
    rows = [[""] + list(df.columns), ["comments"] + [comments.get(c, "") for c in df.columns]]
    for p, r in df.iterrows():
        label = f"{p.year}M{p.month}" if p.freqstr.startswith("M") else f"{p.year}Q{p.quarter}"
        rows.append([label] + ["" if pd.isna(v) else f"{v:.10g}" for v in r.values])
    Path(path).write_text("\n".join(",".join(f'"{x}"' if "," in str(x) else str(x) for x in r) for r in rows) + "\n",
                          encoding="utf-8")


def seasonal_adjust(s: pd.Series, period: int) -> pd.Series:
    """Multiplicative seasonal adjustment with STL on logs (stand-in for IRIS x12)."""
    x = s.dropna()
    res = STL(np.log(x.values), period=period, robust=True).fit()
    out = pd.Series(np.nan, index=s.index)
    out.loc[x.index] = np.exp(np.log(x.values) - res.seasonal)
    return out


def hp_gap(s: pd.Series, lamb: float = 1600) -> pd.Series:
    x = s.dropna()
    cycle, _ = hpfilter(x.values, lamb=lamb)
    out = pd.Series(np.nan, index=s.index)
    out.loc[x.index] = cycle
    return out


def read_data(data_dir="data", cpi_nowcast: dict | None = None, gdp_nowcast: dict | None = None) -> pd.DataFrame:
    """Return the quarterly databank `dq` as a01_read_data.m builds it.

    cpi_nowcast: {"2026-09": m-o-m %, ...} fills months without data (actual data always wins).
    gdp_nowcast: {"2026Q3": q-o-q % SA, ...} fills quarters without GDP data.
    """
    data_dir = Path(data_dir)
    dm, _ = read_iris_csv(data_dir / "monthly.csv")
    dq, _ = read_iris_csv(data_dir / "quarterly.csv")
    dx, _ = read_iris_csv(data_dir / "foreign.csv")
    nowcast_months = []
    for m, v in (cpi_nowcast or {}).items():
        p = pd.Period(m, "M")
        if p not in dm.index:
            dm.loc[p] = np.nan
        if pd.isna(dm.loc[p, "D_CPI_su_m"]):
            dm.loc[p, "D_CPI_su_m"] = v
            nowcast_months.append(p)
    dm = dm.sort_index()
    for qtr, v in (gdp_nowcast or {}).items():
        p = pd.Period(qtr, "Q")
        if p not in dq.index:
            dq.loc[p] = np.nan
        dq = dq.sort_index()
        if pd.isna(dq.loc[p, "GDP"]):
            dq.loc[p, "GDP"] = dq.loc[p - 1, "GDP"] * (1 + v / 100)

    # Monthly CPI: m-o-m % -> level (2000M1 = 1), then seasonal adjustment
    cpi = (1 + dm["D_CPI_su_m"] / 100).cumprod(skipna=False)
    cpi = cpi / cpi.loc[pd.Period("2000-01", "M")]
    dm["CPI_m"] = seasonal_adjust(cpi, 12)

    # Monthly -> quarterly averages. Unlike the template's nanmean, a quarter needs all 3 months:
    # a partial quarter (e.g. Jul-Aug only) would bias the level; the Kalman filter fills it instead.
    q = pd.DataFrame(index=pd.period_range(min(dm.index.min().asfreq("Q"), dq.index.min(), dx.index.min()),
                                           max(dm.index.max().asfreq("Q"), dq.index.max(), dx.index.max()), freq="Q"))
    for name, src in (("CPI", "CPI_m"), ("IR_POLICY", "IR_POLICY_m"), ("ER", "ER_m")):
        g = dm[src].groupby(dm.index.asfreq("Q"))
        q[name] = g.mean().where(g.count() == 3)
    for col in dq.columns:
        name = col[:-3] if col.endswith("_su") else col
        q[name] = seasonal_adjust(dq[col], 4) if col.endswith("_su") else dq[col]
    for col in dx.columns:
        name = col[:-3] if col.endswith("_su") else col
        q[name] = seasonal_adjust(dx[col], 4) if col.endswith("_su") else dx[col]

    # Logs, q-o-q annualized and y-o-y changes
    for name in list(q.columns):
        if name in NO_LOG:
            continue
        q[f"L_{name}"] = 100 * np.log(q[name])
        q[f"DL_{name}"] = 4 * q[f"L_{name}"].diff()
        q[f"D4L_{name}"] = q[f"L_{name}"].diff(4)

    q["L_GDP_EA_GAP"] = hp_gap(q["L_GDP_EA"])
    q.attrs["months_in_quarter"] = dm["D_CPI_su_m"].notna().groupby(dm.index.asfreq("Q")).sum()
    q.attrs["cpi_nowcast_months"] = nowcast_months
    return q


def last_full_quarter(dq: pd.DataFrame) -> pd.Period:
    """Last quarter with all three months of CPI and a GDP observation."""
    months = dq.attrs.get("months_in_quarter")
    full_cpi = months[months == 3].index.max()
    gdp = dq["GDP"].dropna().index.max()
    return min(full_cpi, gdp)
