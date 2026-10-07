"""Фільтрація + прогноз + сценарії + графіки (a01 -> a04 з шаблону НБУ).

Запуск:  python run_forecast.py
Результати: results/forecast_<сценарій>.csv, results/summary.csv, results/figures/*.png
"""
from pathlib import Path

import pandas as pd

import config as cfg
from qpm import pipeline, plotting as pl


def main():
    out = Path(cfg.RESULTS_DIR)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    ctx = pipeline.prepare(cfg)
    f = ctx["rngfcast"][0]
    print(f"Історія до {cfg.LAST_HIST}, прогноз {f}–{cfg.LAST_FORE}")

    ctx["filt"].vars.to_csv(out / "filter.csv")
    results = {}
    for name, fn in cfg.SCENARIOS.items():
        plan = fn(pipeline.base_plan(ctx), f)
        results[name] = pipeline.run(ctx, plan)
        results[name].to_csv(out / f"forecast_{name}.csv")

    table = pipeline.summary_table(results, ctx["rngfcast"])
    table.to_csv(out / "summary.csv", encoding="utf-8-sig")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(table)

    rng = ("2022Q1", cfg.LAST_FORE)
    tar = ctx["model"].params["dl_cpi_tar"]

    # 1) Сценарії: 4 ключові показники
    fig, ax = pl.grid(2, 2)
    pl.line_panel(ax[0], {k: v["d4l_cpi"] for k, v in results.items()}, "Інфляція (ІСЦ)", f,
                  target=tar, target_label=f"ціль {tar:g}%", unit="% р/р", rng=rng)
    pl.line_panel(ax[1], {k: v["uah_eur"] for k, v in results.items()}, "Курс", f, unit="грн/€", rng=rng)
    pl.line_panel(ax[2], {k: v["l_gdp_gap"] for k, v in results.items()}, "Розрив ВВП", f, target=0,
                  unit="% потенціалу", rng=rng)
    pl.line_panel(ax[3], {k: v["ir_pol"] for k, v in results.items()}, "Облікова ставка", f, unit="%", rng=rng)
    pl.save(fig, out / "figures" / "scenarios.png")

    # 2) Базовий сценарій з тренд/розрив
    b = results["Базовий"]
    fig, ax = pl.grid(1, 2, height=3.4)
    pl.line_panel(ax[0], {"ВВП": b["l_gdp"], "Потенційний ВВП": b["l_gdp_tnd"]}, "ВВП", f,
                  unit="100·ln", rng=("2018Q1", cfg.LAST_FORE))
    pl.line_panel(ax[1], {"Реальна ставка": b["rir_pol"], "Нейтральна реальна ставка": b["rir_tnd"]},
                  "Реальна облікова ставка", f, unit="%", rng=rng)
    pl.save(fig, out / "figures" / "trends.png")

    # 3) Декомпозиція облікової ставки (вклади за правилом Тейлора)
    dec = pipeline.rate_decomposition(b, ctx["model"].params).loc["2024Q1": cfg.LAST_FORE].iloc[:-3]
    dec.to_csv(out / "rate_decomposition.csv", encoding="utf-8-sig")
    fig, axd = pl.grid(1, 1, width=9, height=4)
    import numpy as np
    x = np.arange(len(dec))
    pos = np.zeros(len(dec)); neg = np.zeros(len(dec))
    for i, col in enumerate(dec.columns):
        v = dec[col].values
        bottom = np.where(v >= 0, pos, neg)
        axd[0].bar(x, v, bottom=bottom, width=0.6, color=pl.SERIES[i], label=col,
                   edgecolor=pl.INK["surface"], linewidth=1)
        pos += np.clip(v, 0, None); neg += np.clip(v, None, 0)
    axd[0].plot(x, b["ir_pol"].reindex(dec.index).values, color=pl.INK["primary"], lw=2, label="Облікова ставка")
    axd[0].set_xticks(x); axd[0].set_xticklabels([str(p) for p in dec.index], rotation=90, fontsize=8)
    axd[0].set_title("Декомпозиція облікової ставки, п.п.")
    axd[0].legend(ncol=3, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    pl.save(fig, out / "figures" / "rate_decomposition.png")
    print("Графіки:", sorted(p.name for p in (out / "figures").glob("*.png")))


if __name__ == "__main__":
    main()
