"""Оновлення даних моделі: шаблон НБУ (до 2026Q1) + свіжі дані з офіційних API.

Запуск:  python update_data.py
Пише data/monthly.csv, data/quarterly.csv, data/foreign.csv, сирі дані в data/raw/ і журнал data/UPDATE_LOG.md.
Історію з шаблону НБУ не переписуємо — лише додаємо нові місяці/квартали і звіряємо перекриття.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from qpm import fetch
from qpm.data import read_iris_csv, write_iris_csv

TEMPLATE = Path("nbu_template/data")
OUT = Path("data")
RAW = OUT / "raw"

# Останній повний місяць, який беремо (дата відсічення даних)
CUTOFF_MONTH = "2026-09"

# Реальний ВВП: ручні оновлення (q/q з урахуванням сезонності, %). Джерело — Держстат.
# Перевірте уточнену оцінку Держстату (вересень) і виправте, якщо змінилась.
GDP_UPDATES = {
    "2026Q2": (0.4, "Держстат, оперативна оцінка 04.08.2026: +0,4% кв/кв SA (+0,6% р/р)"),
}


def _period_m(s):
    return pd.Period(s, "M")


def update_monthly(log):
    dm, com = read_iris_csv(TEMPLATE / "monthly.csv")
    last_tmpl = dm["D_CPI_su_m"].dropna().index.max()
    cutoff = _period_m(CUTOFF_MONTH)
    idx = pd.period_range(dm.index.min(), max(dm.index.max(), cutoff), freq="M")
    dm = dm.reindex(idx)

    cpi = fetch.nbu_cpi("2025-01", CUTOFF_MONTH)
    cpi.to_csv(RAW / "nbu_cpi.csv")
    key = fetch.nbu_key_rate()
    key.to_csv(RAW / "nbu_key_rate.csv", header=["key_rate"])
    eur = fetch.nbu_fx("EUR", "2024-01-01", pd.Period(CUTOFF_MONTH, "M").end_time.date())
    eur.to_csv(RAW / "nbu_eur.csv", header=["uah_eur"])

    key_eom = key.resample("ME").last()
    key_eom.index = key_eom.index.to_period("M")
    eur_avg = eur.resample("ME").mean()
    eur_avg.index = eur_avg.index.to_period("M")

    # Звірка перекриття з шаблоном
    ov = pd.DataFrame({
        "ІСЦ м/м шаблон": dm["D_CPI_su_m"], "ІСЦ м/м API": cpi["cpi_mom"],
        "ставка шаблон": dm["IR_POLICY_m"], "ставка API": key_eom,
        "EUR шаблон": dm["ER_m"], "EUR API": eur_avg.round(2),
    }).loc["2025-01":str(last_tmpl)]
    log.append("## Звірка з даними шаблону НБУ (2025M1–" + str(last_tmpl) + ")\n")
    log.append(ov.to_markdown() + "\n")
    diff = {"ІСЦ": (ov["ІСЦ м/м шаблон"] - ov["ІСЦ м/м API"]).abs().max(),
            "ставка": (ov["ставка шаблон"] - ov["ставка API"]).abs().max(),
            "EUR": (ov["EUR шаблон"] - ov["EUR API"]).abs().max()}
    log.append(f"Максимальні розбіжності: {', '.join(f'{k} {v:.2f}' for k, v in diff.items())}\n")

    new = pd.period_range(last_tmpl + 1, cutoff, freq="M")
    dm.loc[new, "D_CPI_su_m"] = cpi["cpi_mom"].reindex(new).values
    dm.loc[new, "IR_POLICY_m"] = key_eom.reindex(new).values
    dm.loc[new, "ER_m"] = eur_avg.reindex(new).round(4).values
    log.append("## Додані місяці\n")
    log.append(dm.loc[new].to_markdown() + "\n")
    log.append(f"Джерела: ІСЦ — Держстат через API НБУ (statdirectory/inflation); облікова ставка — API НБУ "
               f"(statdirectory/key), на кінець місяця; курс EUR — офіційний курс НБУ, середній за місяць.\n")
    write_iris_csv(dm, OUT / "monthly.csv", com)
    return cpi


def update_quarterly(log):
    dq, com = read_iris_csv(TEMPLATE / "quarterly.csv")
    log.append("## ВВП України\n")
    for per, (qoq, src) in GDP_UPDATES.items():
        p = pd.Period(per, "Q")
        if p not in dq.index:
            dq.loc[p] = np.nan
        dq = dq.sort_index()
        dq.loc[p, "GDP"] = round(dq.loc[p - 1, "GDP"] * (1 + qoq / 100))
        log.append(f"- {per}: {dq.loc[p, 'GDP']:.0f} млн грн (ціни 2021) = попередній квартал × (1 + {qoq}%). {src}\n")
    write_iris_csv(dq, OUT / "quarterly.csv", com)


def _chain(level_tmpl: pd.Series, actual_growth: pd.Series, anchor: pd.Period) -> pd.Series:
    """Replace values after `anchor` with actual growth, then keep template growth for the rest."""
    out = level_tmpl.copy()
    tmpl_growth = level_tmpl / level_tmpl.shift(1)
    for p in out.index[out.index > anchor]:
        g = actual_growth.get(p, np.nan)
        out[p] = out[p - 1] * (g if not pd.isna(g) else tmpl_growth[p])
    return out


def update_foreign(log):
    dx, com = read_iris_csv(TEMPLATE / "foreign.csv")
    anchor = pd.Period("2025Q4", "Q")

    hicp = fetch.ea_hicp("2024-01")
    hicp.to_csv(RAW / "ea_hicp_2025eq100.csv", header=["hicp"])
    full = hicp.groupby(hicp.index.asfreq("Q")).agg(["mean", "count"])
    hq = full.loc[full["count"] == 3, "mean"]
    cpi_new = _chain(dx["CPI_EA"], hq / hq.shift(1), anchor)

    gdp = fetch.ea_gdp("2024-Q1")
    gdp.to_csv(RAW / "ea_gdp_i10.csv", header=["gdp"])
    gdp_new = _chain(dx["GDP_EA"], gdp / gdp.shift(1), anchor)

    dfr = fetch.ecb_deposit_rate("2024-01-01")
    dfr.to_csv(RAW / "ecb_dfr.csv", header=["dfr"])
    dfr_q = dfr.resample("QE").last()
    dfr_q.index = dfr_q.index.to_period("Q")
    ir_new = dx["IR_EA"].copy()
    last_full_q = pd.Period(CUTOFF_MONTH, "M").asfreq("Q")
    if pd.Period(CUTOFF_MONTH, "M").month % 3 != 0:
        last_full_q -= 1
    for p in dfr_q.index:
        if anchor < p <= last_full_q:
            ir_new[p] = dfr_q[p]

    tbl = pd.DataFrame({"HICP шаблон": dx["CPI_EA"], "HICP новий": cpi_new.round(2),
                        "ВВП шаблон": dx["GDP_EA"], "ВВП новий": gdp_new.round(2),
                        "DFR шаблон": dx["IR_EA"], "DFR новий": ir_new}).loc["2025Q3":"2027Q4"]
    log.append("## Єврозона\n")
    log.append(f"Фактичні дані замінюють шаблон для кварталів з повними даними (HICP: {hq.index.max()}, "
               f"ВВП: {gdp.index.max()}, ставка ЄЦБ: {last_full_q}); далі — прирости з припущень шаблону НБУ.\n")
    log.append(tbl.to_markdown() + "\n")
    log.append("Джерела: HICP — Eurostat prc_hicp_minr (EA, 2025=100), ланцюгово до ряду шаблону; ВВП — ECB MNA "
               "(EA21, I10), ланцюгово; ставка — депозитна ставка ЄЦБ на кінець кварталу.\n")
    log.append("**TODO:** оновити припущення на горизонті прогнозу за вересневим прогнозом ЄЦБ (2026) "
               "та ринковими очікуваннями щодо ставок.\n")
    dx["CPI_EA"], dx["GDP_EA"], dx["IR_EA"] = cpi_new.round(3), gdp_new.round(3), ir_new
    write_iris_csv(dx, OUT / "foreign.csv", com)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    log = [f"# Журнал оновлення даних\n\nДата оновлення: {date.today()}, дата відсічення: {CUTOFF_MONTH}\n"]
    update_monthly(log)
    update_quarterly(log)
    update_foreign(log)
    (OUT / "UPDATE_LOG.md").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
