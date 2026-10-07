"""Графіки для розділу «Огляд економіки» (дані: data/overview, оновлює qpm.overview.build()).

Запуск:  python make_overview_charts.py          # з наявних CSV
         python make_overview_charts.py --fetch  # спершу завантажити свіжі дані
Результат: results/figures/ov_*.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from qpm import overview, plotting as pl
from qpm.data import read_iris_csv

FIG = Path("results/figures")
START = "2024-01"
ROMAN_Q = {1: "I", 2: "II", 3: "III", 4: "IV"}


def inflation():
    cpi, comp = overview.load("cpi"), overview.load("cpi_components")
    fig, ax = pl.grid(1, 2, height=3.6)
    pl.monthly_panel(ax[0], {"ІСЦ": cpi["cpi_yoy"], "Базова інфляція": cpi["core_yoy"]}, "Інфляція", "% р/р",
                     target=5, target_label="ціль 5%", start=START)
    pl.monthly_panel(ax[1], {"Пальне": comp["Ціни на паливо"],
                             "Адмінрегульовані ціни": comp["Адміністративно регульовані ціни"],
                             "Послуги": comp["Послуги"], "Сирі продукти": comp["Сирі продукти"]},
                     "Окремі складові ІСЦ", "% р/р", start=START)
    pl.save(fig, FIG / "ov_inflation.png", "Держстат, НБУ (Інфляційний звіт, липень 2026; коментарі щодо інфляції)")


def expectations():
    e = overview.load("expectations")
    fig, ax = pl.grid(1, 1, width=6.5, height=3.6)
    pl.monthly_panel(ax[0], {"Домогосподарства": e["Домогосподарства"], "Підприємства": e["Підприємства"],
                             "Банки": e["Банки"], "Фінансові аналітики": e["Фінансові аналітики"]},
                     "Інфляційні очікування на 12 місяців", "%", markers=True, start=START)
    pl.save(fig, FIG / "ov_expectations.png", "НБУ (Інфляційний звіт, липень 2026)")


def rates():
    r, cpi = overview.load("rates"), overview.load("cpi")
    real = (r["Облікова ставка"] - cpi["cpi_yoy"]).dropna()
    fig, ax = pl.grid(1, 2, height=3.6)
    pl.monthly_panel(ax[0], {"Облікова ставка": r["Облікова ставка"],
                             "Строкові депозити ФО (середньозв.)": r["Середьозважена ФО"],
                             "ІСЦ, р/р": cpi["cpi_yoy"]}, "Ставки та інфляція", "%", start=START)
    pl.monthly_panel(ax[1], {"Облікова ставка мінус поточна інфляція": real}, "Реальна облікова ставка (ex post)",
                     "в. п.", target=0, start=START)
    pl.save(fig, FIG / "ov_rates.png", "НБУ, Держстат; розрахунки команди")


def fx():
    f, iv, res = overview.load("fx"), overview.load("interventions"), overview.load("reserves")
    fig, ax = pl.grid(1, 3, width=13, height=3.6)
    pl.monthly_panel(ax[0], {"грн/€": f["грн/€"], "грн/$": f["грн/$"]}, "Офіційний курс", "середнє за місяць",
                     start=START)
    s = iv["Продаж"].loc["2025-01":] - iv["Купівля"].loc["2025-01":]
    pl.bar_panel(ax[1], s, "Чистий продаж валюти НБУ", "$ млрд",
                 labels=[p.strftime("%m.%y") if p.month in (1, 4, 7, 10) else "" for p in s.index])
    pl.monthly_panel(ax[2], {"Міжнародні резерви": res.iloc[:, 0]}, "Міжнародні резерви", "$ млрд, кінець місяця",
                     start=START)
    ax[2].scatter(pd.Period("2026-09", "M").to_timestamp(), 53.8, marker="D", s=30, color=pl.SERIES[1], zorder=6,
                  label="Прогноз НБУ на кінець III кв.")
    ax[2].legend(loc="upper left")
    pl.save(fig, FIG / "ov_fx.png", "НБУ (офіційний курс, інтервенції, резерви; прогноз — Інфляційний звіт, липень 2026)")


def activity():
    g, b, w = overview.load("gdp"), overview.load("business"), overview.load("wages")
    fig, ax = pl.grid(1, 3, width=13, height=3.6)
    gq = g.loc["2024Q1":"2027Q4"]
    fact = gq.iloc[:, 0].dropna()
    nbu = gq.iloc[:, 1].loc[fact.index[-1] + 1:]
    nbu = pd.concat([fact.iloc[-1:], nbu])  # start the NBU path from the last actual point
    pl.line_panel(ax[0], {"Факт (Держстат, SA)": fact, "Прогноз НБУ (липень 2026)": nbu},
                  "Реальний ВВП", fact.index[-1] + 1, unit="% р/р", rng=("2024Q1", "2027Q4"))
    pl.bar_panel(ax[1], b["ІДО"].loc["2024Q1":], "Індекс ділових очікувань", "%",
                 labels=[ROMAN_Q[p.quarter] + "\n" + str(p.year)[2:] for p in b.loc["2024Q1":].index])
    pl.monthly_panel(ax[2], {"Номінальна": w["Номінальна"], "Реальна": w["Реальна"]}, "Середня зарплата", "% р/р",
                     start=START)
    pl.save(fig, FIG / "ov_activity.png", "Держстат, НБУ (Інфляційний звіт, липень 2026)")


def fiscal():
    f = overview.load("fiscal").loc[2023:]
    fig, ax = pl.grid(1, 2, height=3.4)
    pl.bar_panel(ax[0], f["Офіційне фінансування, $ млрд"], "Офіційне зовнішнє фінансування", "$ млрд",
                 labels=[f"{y}{'*' if y >= 2026 else ''}" for y in f.index], value_fmt="{:.0f}",
                 highlight={y: pl.BLUE_RAMP[250] for y in f.index if y >= 2026})
    pl.bar_panel(ax[1], f["Дефіцит бюджету без грантів, % ВВП"], "Дефіцит зведеного бюджету без грантів", "% ВВП",
                 labels=[f"{y}{'*' if y >= 2026 else ''}" for y in f.index], value_fmt="{:.0f}",
                 colour=pl.SERIES[1], highlight={y: "#f4a582" for y in f.index if y >= 2026})
    pl.save(fig, FIG / "ov_fiscal.png", "НБУ (макропрогноз, липень 2026); * — прогноз/припущення НБУ")


def external():
    dx, _ = read_iris_csv("data/foreign.csv")
    hicp = (dx["CPI_EA"] / dx["CPI_EA"].shift(4) * 100 - 100).loc["2023Q1":"2028Q4"]
    first_assump = pd.Period("2026Q4", "Q")
    fig, ax = pl.grid(1, 2, height=3.6)
    pl.line_panel(ax[0], {"Інфляція HICP, % р/р": hicp, "Ставка ЄЦБ (депозитна), %": dx["IR_EA"].loc["2023Q1":"2028Q4"]},
                  "Єврозона", first_assump, target=2, target_label="ціль ЄЦБ 2%", rng=("2023Q1", "2028Q4"))
    e = overview.load("energy")
    brent = e["Brent (поточний прогноз)"]
    pl.line_panel(ax[1], {"Припущення НБУ (липень 2026)": brent}, "Нафта Brent", pd.Period("2026Q3", "Q"),
                  unit="$/бар.", rng=("2026Q3", "2028Q4"))
    ax[1].scatter([2026.67], [100], marker="D", s=35, color=pl.SERIES[1], zorder=6, label="Факт: ≈100 (вересень 2026)")
    ax[1].legend(loc="upper right")
    pl.save(fig, FIG / "ov_external.png", "Eurostat, ЄЦБ (прогноз вересня 2026), НБУ; Brent у вересні — Reuters")


def fx_households():
    h = overview.load("fx_market_households")
    s = h["CliBuyPerMFO"].loc["2025-09":]
    fig, ax = pl.grid(1, 1, width=6.5, height=3.6)
    pl.bar_panel(ax[0], s, "Безготівкова купівля валюти населенням", "$ млрд на місяць",
                 labels=[p.strftime("%m.%y") for p in s.index], value_fmt="{:.2f}",
                 highlight={p: pl.SERIES[1] for p in s.index if p >= pd.Period("2026-08", "M")})
    ax[0].annotate("ліміт 50 → 200 тис. грн/міс" + "\n" + "(з 11.08.2026)", xy=(len(s) - 2, s.iloc[-2]),
                   xytext=(len(s) - 6.5, s.max() * 0.98),
                   fontsize=8, color=pl.INK["secondary"], arrowprops=dict(arrowstyle="-", color=pl.INK["muted"], lw=0.8))
    pl.save(fig, FIG / "ov_fx_households.png", "НБУ (API, statdirectory/kursf)")


def main():
    if "--fetch" in sys.argv:
        overview.build()
    for fn in (inflation, expectations, rates, fx, activity, fiscal, external, fx_households):
        fn()
    print("Готово:", sorted(p.name for p in FIG.glob("ov_*.png")))


if __name__ == "__main__":
    main()
