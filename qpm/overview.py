"""Datasets for the macro overview slides: NBU API + NBU Inflation Report chart data + manual entries.

Every series is saved to data/overview/<name>.csv; `SOURCES` documents where each came from.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import fetch
from .data import read_iris_csv
from .nbu_files import read_ir_chart, read_nbu_forecast

OUT = Path("data/overview")

# CPI components for months after the last Inflation Report data point (NBU monthly inflation comments)
CPI_COMPONENTS_MANUAL = {
    "2026-07": {"Сирі продукти": 2.2, "Оброблені продукти": 10.0, "Непродовольчі товари": 0.8, "Послуги": 13.7,
                "Адміністративно регульовані ціни": 11.8, "Ціни на паливо": 28.0},
    "2026-08": {"Сирі продукти": 1.0, "Оброблені продукти": 10.0, "Непродовольчі товари": 1.1, "Послуги": 13.4,
                "Адміністративно регульовані ціни": 13.0, "Ціни на паливо": 38.7},
    "2026-09": {"Сирі продукти": 6.7, "Оброблені продукти": 10.7, "Непродовольчі товари": 2.4, "Послуги": 13.7,
                "Адміністративно регульовані ціни": 13.6, "Ціни на паливо": 46.2},
}

SOURCES = {
    "cpi": "Держстат через API НБУ (statdirectory/inflation)",
    "cpi_components": "НБУ, Інфляційний звіт (липень 2026), графік 1.2; липень–вересень 2026 — коментарі НБУ щодо інфляції",
    "expectations": "НБУ, Інфляційний звіт (липень 2026), графік 1.8",
    "rates": "API НБУ (облікова ставка); депозитні ставки — Інфляційний звіт (липень 2026), графік 3.1",
    "fx": "Офіційний курс НБУ (API), середній за місяць; останній місяць — до дати оновлення (колонка note)",
    "fx_daily": "Офіційний курс НБУ (API), щоденно з 2026 р. — для останнього курсу на слайдах",
    "interventions": "API НБУ (statdirectory/kursf), чисті інтервенції за місяць",
    "reserves": "API НБУ (statdirectory/res), офіційні резервні активи на кінець місяця",
    "gdp": "Держстат (реальний ВВП, SA); прогноз НБУ — таблиця макропрогнозу (липень 2026)",
    "business": "НБУ, Інфляційний звіт (липень 2026), графік 2.2 (індекс ділових очікувань)",
    "wages": "НБУ, Інфляційний звіт (липень 2026), графік 1.13",
    "fiscal": "НБУ, макропрогноз (липень 2026): припущення та зведений бюджет",
    "energy": "НБУ, Інфляційний звіт (липень 2026), графік 4.1 (припущення щодо цін на нафту та газ)",
    "nbu_forecast": "НБУ, таблиця макропрогнозу (липень 2026)",
    "fx_market_households": "API НБУ (statdirectory/kursf): операції населення з валютою, $ млрд за місяць",
}


def _monthly_from_reporting(s: pd.Series) -> pd.Series:
    """NBU API 'dt' is the reporting date (1st day of next month) -> reference month."""
    s.index = pd.PeriodIndex(pd.to_datetime(s.index), freq="M") - 1
    return s.sort_index()


def build(start="2023-01", end="2026-09") -> dict[str, pd.DataFrame]:
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}

    cpi = fetch.nbu_cpi(start, end)
    out["cpi"] = cpi[["cpi_yoy", "core_yoy", "cpi_mom", "core_mom"]]

    comp = read_ir_chart("1.2")
    for m, vals in CPI_COMPONENTS_MANUAL.items():
        comp.loc[pd.Period(m, "M"), list(vals)] = list(vals.values())
    out["cpi_components"] = comp.sort_index()

    out["expectations"] = read_ir_chart("1.8")

    key = fetch.nbu_key_rate()
    key_m = key.resample("ME").mean()
    key_m.index = key_m.index.to_period("M")
    dep = read_ir_chart("3.1")
    rates = pd.DataFrame({"Облікова ставка": key_m.loc[start:end]})
    rates = rates.join(dep.drop(columns=["Облікова ставка"], errors="ignore"), how="left")
    out["rates"] = rates

    # official rate up to today: the current month is a month-to-date average (flagged in the 'note' column), and the
    # latest daily rate is kept for the slides — in October 2026 the hryvnia hit a record low vs USD (45.08 on 14.10)
    from datetime import date, timedelta
    # the NBU sets the next business day's rate the afternoon before, so ask up to tomorrow
    eur = fetch.nbu_fx("EUR", f"{start}-01", date.today() + timedelta(days=1))
    usd = fetch.nbu_fx("USD", f"{start}-01", date.today() + timedelta(days=1))
    fx = pd.DataFrame({"грн/€": eur, "грн/$": usd}).resample("ME").mean()
    fx.index = fx.index.to_period("M")
    fx["note"] = ""
    last_day = usd.index.max()
    if last_day != last_day.to_period("M").end_time.normalize():
        fx.loc[fx.index[-1], "note"] = f"середнє за 1–{last_day.day}.{last_day.month:02d}; останній курс {usd.iloc[-1]:.4f} грн/$ ({last_day.date()})"
    out["fx"] = fx
    out["fx_daily"] = pd.DataFrame({"грн/€": eur, "грн/$": usd}).loc["2026-01-01":]

    rows = []
    for p in pd.period_range(start, end, freq="M"):
        rep = (p + 1).start_time.strftime("%Y%m%d")
        for r in fetch._get(f"{fetch.NBU}/kursf?date={rep}&period=m&json").json():
            if r["id_api"] in ("VolumNbuICM_SelPerM", "VolumNbuICM_BuyPerM", "VolumNbuICM_BalPerM"):
                rows.append((p, r["id_api"], r["value"] / 1e9))
    iv = pd.DataFrame(rows, columns=["period", "id", "value"]).pivot(index="period", columns="id", values="value")
    iv = iv.rename(columns={"VolumNbuICM_SelPerM": "Продаж", "VolumNbuICM_BuyPerM": "Купівля",
                            "VolumNbuICM_BalPerM": "Сальдо"})
    iv.index = pd.PeriodIndex(iv.index, freq="M")
    out["interventions"] = iv

    res = fetch.nbu_reserves()
    res = res[res["id_api"] == "RES_OffReserveAssets"]
    rs = pd.Series(res["value"].values / 1e3, index=res["dt"].values)
    rs.index = pd.PeriodIndex(pd.to_datetime(rs.index), freq="M") - 1   # stock on the 1st = end of previous month
    out["reserves"] = rs.sort_index().loc[start:].to_frame("Міжнародні резерви, $ млрд")

    dq, _ = read_iris_csv("data/quarterly.csv")
    gdp = (dq["GDP"] / dq["GDP"].shift(4) * 100 - 100).dropna().loc["2023Q1":]
    fc = read_nbu_forecast()
    nbu_gdp = fc[(fc["indicator"] == "Реальний ВВП") & fc["period"].str.contains("Q")]
    nbu_gdp = pd.Series(nbu_gdp["value"].values, index=pd.PeriodIndex(nbu_gdp["period"], freq="Q"))
    out["gdp"] = pd.DataFrame({"Реальний ВВП, % р/р (SA)": gdp, "Прогноз НБУ (липень 2026)": nbu_gdp})

    out["business"] = read_ir_chart("2.2")
    out["wages"] = read_ir_chart("1.13")

    import openpyxl
    wb = openpyxl.load_workbook("data/raw/nbu/Macroeconomic_Forecast_table_2026_07.xlsx", read_only=True, data_only=True)
    arows = [list(r) for r in wb["Припущення базового сценарію"].iter_rows(values_only=True)]
    hdr = next(r for r in arows if len(r) > 1 and r[1] == "Показники")
    years = [int(str(v).rstrip("*")) for v in hdr[3:] if v is not None]
    aid = next(r for r in arows if len(r) > 1 and r[1] == "Офіційне фінансування")
    usl = next(r for r in arows if len(r) > 1 and str(r[1]).startswith("у т. ч. оборонна складова USL"))
    fc_bal = fc[fc["indicator"] == "Сальдо, % ВВП"].set_index("period")["value"]
    fiscal = pd.DataFrame(index=years)
    fiscal["Офіційне фінансування, $ млрд"] = [float(v) for v in aid[3:3 + len(years)]]
    fiscal["у т. ч. оборонна складова USL, $ млрд"] = [float(v) if v is not None else np.nan
                                                       for v in usl[3:3 + len(years)]]
    fiscal["Дефіцит бюджету без грантів, % ВВП"] = [-fc_bal.get(str(y), np.nan) for y in years]
    out["fiscal"] = fiscal

    out["energy"] = read_ir_chart("4.1")
    # Brent for the overview comes from the same file the model uses (data/raw/brent_monthly.csv, update_data.py):
    # one source for every chart and slide
    out["nbu_forecast"] = fc

    hh = []
    for p in pd.period_range(start, end, freq="M"):
        rep = (p + 1).start_time.strftime("%Y%m%d")
        for r in fetch._get(f"{fetch.NBU}/kursf?date={rep}&period=m&json").json():
            if r["id_api"] in ("CliBuyPerMFO", "CliSelPerMFO", "TotalCliBuyPerMFO", "TotalCliSelPerMFO", "CashVolumBalPerMFO"):
                hh.append((p, r["id_api"], r["value"] / 1e9))
    hh = pd.DataFrame(hh, columns=["period", "id", "value"]).pivot(index="period", columns="id", values="value")
    hh.index = pd.PeriodIndex(hh.index, freq="M")
    out["fx_market_households"] = hh

    for name, df in out.items():
        df.to_csv(OUT / f"{name}.csv", encoding="utf-8-sig")
    (OUT / "SOURCES.md").write_text("# Джерела даних для огляду\n\n" +
                                    "\n".join(f"- `{k}.csv` — {v}" for k, v in SOURCES.items()) +
                                    "\n- Brent для огляду — `data/raw/brent_monthly.csv` (спот EIA, див. `update_data.py`)\n"
                                    "- Ряд `gdp.csv` — % р/р із сезонно скоригованих рівнів (шаблон НБУ + ланцюгування кв/кв "
                                    "за Держстатом); офіційні несезонні темпи Держстату відрізняються (I кв. 2026 −0,6%, "
                                    "II кв. +0,4% р/р після перегляду у вересні 2026)\n",
                                    encoding="utf-8")
    return out


def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(OUT / f"{name}.csv", index_col=0, encoding="utf-8-sig")
    idx = df.index.astype(str)
    if idx.str.fullmatch(r"\d{4}-\d{2}").all():
        df.index = pd.PeriodIndex(idx, freq="M")
    elif idx.str.fullmatch(r"\d{4}Q\d").all():
        df.index = pd.PeriodIndex(idx, freq="Q")
    return df
