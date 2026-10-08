"""Reserves projection by simple FX-flow accounting (more transparent than a regression on the model's `interv`).

    Reserves(m+1) = Reserves(m) + net official inflows(m) - NBU net FX sales(m)

'Net official inflows' = aid to reserves net of public FX debt service and valuation; its recent value is
backed out of the data as ΔReserves + NBU net sales.
"""
from __future__ import annotations

import pandas as pd

from . import overview

# Months of imports as the NBU counts them: reserves at the end of 2026 vs imports of the NEXT year
# ("місяців імпорту майбутнього періоду"): 2027 imports of goods & services, NBU forecast (July 2026), $ bn per month
IMPORTS_PER_MONTH = 134.5 / 12
NBU_RESERVES_END2026 = 69.7     # NBU July 2026 forecast, $ bn (6.2 months of next-year imports)


def implied_inflows(window=3) -> pd.DataFrame:
    res = overview.load("reserves").iloc[:, 0]
    iv = overview.load("interventions")
    sales = iv["Продаж"] - iv["Купівля"]
    df = pd.DataFrame({"Резерви": res, "Чистий продаж НБУ": sales})
    df["Чисті офіційні надходження (розрах.)"] = df["Резерви"].diff() + df["Чистий продаж НБУ"]
    return df.dropna()


def project(until="2026-12", cases: dict[str, float] | None = None, sales: float | None = None) -> pd.DataFrame:
    """Monthly reserves path for several inflow cases ($ bn per month); NBU sales default = last-3-month average."""
    hist = implied_inflows()
    last = hist.index.max()
    sales = sales if sales is not None else hist["Чистий продаж НБУ"].iloc[-3:].mean()
    recent = hist["Чисті офіційні надходження (розрах.)"].iloc[-3:].mean()
    cases = cases or {"Надолуження допомоги": 8.0, "Як у липні–вересні": round(recent, 1), "Затримка допомоги": 2.0}
    months = pd.period_range(last + 1, until, freq="M")
    out = pd.DataFrame(index=pd.period_range(last, until, freq="M"))
    for name, inflow in cases.items():
        path = [hist.loc[last, "Резерви"]]
        for _ in months:
            path.append(path[-1] + inflow - sales)
        out[name] = path
    out.attrs.update(sales=sales, recent_inflows=recent, cases=cases)
    return out
