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
    r, cpi, e = overview.load("rates"), overview.load("cpi"), overview.load("expectations")
    real = (r["Облікова ставка"] - cpi["cpi_yoy"]).dropna()
    # ex ante, as the NBU computes it: policy rate minus 12-month inflation expectations of financial analysts
    exante = (r["Облікова ставка"] - e["Фінансові аналітики"].ffill()).dropna()
    fig, ax = pl.grid(1, 3, width=14, height=3.6)
    pl.monthly_panel(ax[0], {"Облікова ставка": r["Облікова ставка"],
                             "Строкові депозити ФО": r["Середьозважена ФО"],
                             "ІСЦ, р/р": cpi["cpi_yoy"]}, "Ставки та інфляція", "%", start=START)
    pl.monthly_panel(ax[1], {"Від очікувань аналітиків (як у НБУ)": exante, "Від фактичної інфляції": real},
                     "Реальна облікова ставка", "в. п.", target=0, start=START)
    pl.monthly_panel(ax[2], {"Домогосподарства": e["Домогосподарства"], "Підприємства": e["Підприємства"],
                             "Банки": e["Банки"], "Фінансові аналітики": e["Фінансові аналітики"]},
                     "Інфляційні очікування на 12 міс.", "%", markers=True, start=START)
    pl.save(fig, FIG / "ov_rates.png", "НБУ (Інфляційний звіт, липень 2026), Держстат; розрахунки команди")


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


def bop():
    """Balance of payments (NBU July 2026 forecast table + Inflation Report chart 3.13): trade and its financing."""
    from qpm.nbu_files import read_ir_chart, read_nbu_forecast
    fc = read_nbu_forecast()
    years = [2023, 2024, 2025, 2026, 2027, 2028]

    def ann(name):
        s = fc[fc["indicator"] == name].set_index("period")["value"]
        return pd.Series([float(s.get(str(y), np.nan)) for y in years], index=years)

    trade = pd.DataFrame({"Експорт": ann("Експорт товарів та послуг, млрд дол."),
                          "Імпорт": ann("Імпорт товарів та послуг, млрд дол."),
                          "Перекази": ann("Приватні грошові перекази в Україну, млрд дол.")})
    fin = read_ir_chart("3.13").loc[2023:2028]
    trade.to_csv("data/overview/bop_trade.csv", encoding="utf-8-sig")
    fin.to_csv("data/overview/bop_financing.csv", encoding="utf-8-sig")

    fig, ax = pl.grid(1, 2, width=13, height=3.7)
    x = np.arange(len(years))
    labels = [f"{y}{'*' if y >= 2026 else ''}" for y in years]
    for k, (col, dx) in enumerate((("Експорт", -0.2), ("Імпорт", 0.2))):
        ax[0].bar(x + dx, trade[col], width=0.38, color=pl.SERIES[k], label=col, edgecolor=pl.INK["surface"], lw=1.5,
                  zorder=3)
    for xi, (e, m) in enumerate(zip(trade["Експорт"], trade["Імпорт"])):
        ax[0].annotate(f"−{m - e:.0f}", (xi + 0.2, m), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8,
                       color=pl.INK["secondary"])
    ax[0].set_xticks(x, labels)
    ax[0].set_ylim(0, trade["Імпорт"].max() * 1.12)
    ax[0].grid(axis="x", visible=False)
    ax[0].set_title("Експорт та імпорт товарів і послуг, $ млрд (над стовпцем — дефіцит)")

    parts = [("Поточний рахунок", pl.SERIES[1]), ("ПІІ", pl.SERIES[2]), ("ERA (кредити)", pl.SERIES[0]),
             ("Ukraine Facility", pl.SERIES[3]), ("MFA", pl.SERIES[6]), ("Очікувані позики", pl.SERIES[4])]
    pos, neg = np.zeros(len(years)), np.zeros(len(years))
    for col, colour in parts:
        v = fin[col].reindex(years).fillna(0).values
        bottom = np.where(v >= 0, pos, neg)
        ax[1].bar(x, v, bottom=bottom, width=0.6, color=colour, label=col, edgecolor=pl.INK["surface"], lw=1.5, zorder=3)
        pos += np.clip(v, 0, None)
        neg += np.clip(v, None, 0)
    ax[1].plot(x, fin["Широкий базовий баланс"].reindex(years).values, "o-", color=pl.INK["primary"], lw=2, zorder=5,
               label="Широкий базовий баланс")
    ax[1].axhline(0, color=pl.INK["axis"], lw=1)
    ax[1].set_xticks(x, labels)
    ax[1].grid(axis="x", visible=False)
    ax[1].set_title("Фінансування поточного рахунку, $ млрд")
    ax[1].set_ylim(neg.min() * 1.12, pos.max() * 1.12)
    ax[1].legend(ncol=4, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
    ax[0].legend(loc="upper left", bbox_to_anchor=(0.0, -0.1), ncol=2, frameon=False)
    fig.subplots_adjust(bottom=0.3)
    pl.save(fig, FIG / "ov_bop.png", "НБУ, макропрогноз та Інфляційний звіт (липень 2026), графік 3.13; * — прогноз НБУ")


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
    # Derzhstat did not publish wages for some months under martial law (e.g. Apr–Dec 2024);
    # the NBU fills them with its own estimate — shown dashed, joined to the official points at both ends
    for i, col in enumerate(("Номінальна (оцінка)", "Реальна (оцінка)")):
        est = w[col].loc[START:]
        valid = est.dropna()
        if not valid.empty:
            full = est.reindex(pd.period_range(valid.index.min(), valid.index.max(), freq="M"))
            ax[2].plot(full.index.to_timestamp(), full.values, color=pl.SERIES[i], ls=(0, (3, 2)), lw=1.6)
    from matplotlib.lines import Line2D
    h, lab = ax[2].get_legend_handles_labels()
    h.append(Line2D([], [], color=pl.INK["secondary"], ls=(0, (3, 2)), lw=1.6))
    lab.append("Оцінка НБУ (без даних Держстату)")
    ax[2].set_ylim(top=40)   # room for the legend above the lines
    ax[2].legend(h, lab, loc="upper right", fontsize=8)
    pl.save(fig, FIG / "ov_activity.png", "Держстат, НБУ (Інфляційний звіт, липень 2026); пунктир — оцінка НБУ "
            "для місяців без даних Держстату")


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
    # Brent: monthly actual, futures curve (model assumption) and NBU's July assumption (quarterly)
    b = pd.read_csv("data/raw/brent_monthly.csv", index_col=0)["brent_usd"]
    b.index = pd.PeriodIndex(b.index, freq="M")
    fut = dx["BRENT_USD"].loc["2026Q4":"2028Q4"]
    nbu = overview.load("energy")["Brent (поточний прогноз)"]
    a = ax[1]
    act = b.loc["2023-01":]
    a.plot(act.index.to_timestamp(), act.values, color=pl.SERIES[0], label="Факт (середнє за місяць)")
    a.plot([p.asfreq("M", "end").to_timestamp() for p in fut.index], fut.values, color=pl.SERIES[1], marker="o", ms=4,
           mec=pl.INK["surface"], label="Ф'ючерсна крива (наше припущення)")
    a.plot([p.asfreq("M", "end").to_timestamp() for p in nbu.index], nbu.values, color=pl.SERIES[2], marker="o", ms=4,
           mec=pl.INK["surface"], label="Припущення НБУ (липень 2026)")
    a.axvspan(pd.Timestamp("2026-10-01"), pd.Timestamp("2028-12-31"), color=pl.INK["forecast"], zorder=0, lw=0)
    import matplotlib.dates as mdates
    a.xaxis.set_major_locator(mdates.YearLocator())
    a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    a.set_title("Нафта Brent, $/бар.")
    a.legend(loc="upper left", fontsize=8)
    pl.save(fig, FIG / "ov_external.png", "Eurostat, ЄЦБ (прогноз вересня 2026); Brent — EIA, NYMEX (ф'ючерси), НБУ")


def fx_households():
    h = overview.load("fx_market_households")
    s = h["CliBuyPerMFO"].loc["2025-09":]
    fig, ax = pl.grid(1, 1, width=6.5, height=4.6)
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
    for fn in (inflation, expectations, rates, fx, bop, activity, fiscal, external, fx_households):
        fn()
    print("Готово:", sorted(p.name for p in FIG.glob("ov_*.png")))


if __name__ == "__main__":
    main()
