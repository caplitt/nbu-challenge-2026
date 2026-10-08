"""Фільтр, базовий прогноз, сценарії, варіанти політики, невизначеність, бектест, резерви + графіки й таблиці.

Запуск:  python run_forecast.py
Результати:
  results/tables/*.csv      — таблиці для слайдів і документації
  results/key_numbers.json  — єдине джерело цифр для презентації (усі слайди беруть числа звідси)
  results/figures/fc_*.png  — графіки прогнозу
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg
from qpm import backtest, optimal, pipeline, plotting as pl, reserves, uncertainty
from qpm.nbu_files import read_ir_chart, read_nbu_forecast

OUT = Path(cfg.RESULTS_DIR)
FIG, TAB = OUT / "figures", OUT / "tables"
RNG = ("2023Q1", cfg.LAST_FORE)


def _q(df, col, per):
    return float(round(df.loc[pd.Period(per, "Q"), col], 2))


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    for old in TAB.glob("forecast_*.csv"):   # scenario / option names may change between runs
        old.unlink()
    ctx = pipeline.prepare(cfg)
    model, f, fc = ctx["model"], ctx["rngfcast"][0], ctx["rngfcast"]
    tar = model.params["dl_cpi_tar"]
    print(f"Історія до {cfg.LAST_HIST}, прогноз {f}–{cfg.LAST_FORE}")
    ctx["filt"].vars.to_csv(TAB / "filter.csv")
    if ctx["nowcast"] is not None:
        ctx["nowcast"].to_csv(TAB / "cpi_nowcast.csv", encoding="utf-8-sig")

    # ------------------------------------------------------------- scenarios and policy options
    base_plan = pipeline.base_plan(ctx)
    # baseline = decision + hold, then the path returning inflation to the 5% point target within the horizon
    scen = {name: pipeline.run(ctx, plan) for name, plan in pipeline.scenario_plans(ctx).items()}
    base = scen["Базовий"]
    rule = pipeline.run(ctx, pipeline.with_rate_path(base_plan, cfg.RECOMMENDED_RATE_PATH))
    print("Базовий vs чисте правило після утримання, ІСЦ IV кв. 2028 / 2029:",
          [round(float(d.loc[q, "d4l_cpi"]), 2) for d in (base, rule) for q in ("2028Q4", "2029Q4")])
    pol = {name: pipeline.run(ctx, pipeline.policy_plan(ctx, base_plan, path)) for name, path in cfg.POLICY_OPTIONS.items()}
    # optimal rate path from the October decision on (min of quadratic loss), sensitivity to the smoothing weight
    tp = {k: v for k, v in cfg.TARGET_PATH.items() if k != "w_smooth"}
    opt_rows = {}
    for ws in (0.5, 1.0, 2.0):
        res_o, path_o, L = optimal.optimal_path(ctx, base_plan, w_smooth=ws, **tp)
        opt_rows[f"λ = {ws:g}"] = {**{str(p): round(float(v), 2) for p, v in path_o.items()},
                                   "Втрати: оптимум": round(L["optimal"], 1), "Втрати: правило": round(L["rule"], 1)}
        if ws == cfg.TARGET_PATH["w_smooth"]:
            pol["Оптимальна (мін. втрат)"] = res_o
    # the same with first-round effects of administered prices looked through (they are not in the loss)
    _, path_lt, L = optimal.optimal_path(ctx, pipeline.base_plan(ctx, look_through=True), **cfg.TARGET_PATH)
    opt_rows["λ = 1, без реакції на адмінціни"] = {**{str(p): round(float(v), 2) for p, v in path_lt.items()},
                                                    "Втрати: оптимум": round(L["optimal"], 1), "Втрати: правило": round(L["rule"], 1)}
    opt_tab = pd.DataFrame(opt_rows).T
    opt_tab.to_csv(TAB / "optimal_paths.csv", encoding="utf-8-sig")
    print(opt_tab)
    for name, df in {**scen, **{f"policy_{k}": v for k, v in pol.items()}}.items():
        df.to_csv(TAB / f"forecast_{name}.csv", encoding="utf-8-sig")
    pipeline.summary_table({"Базовий": base}, fc).to_csv(TAB / "baseline_quarterly.csv", encoding="utf-8-sig")
    annual = pipeline.annual_table(base)
    annual.to_csv(TAB / "baseline_annual.csv", encoding="utf-8-sig")

    # policy options: simple loss over the policy horizon 2027-2029 = sum of (CPI - target)^2 + 0.5 * gap^2
    per_loss = pd.period_range("2027Q1", cfg.LAST_FORE, freq="Q")
    pol_tab = pd.DataFrame({
        name: {"Ставка IV кв. 2026": df.loc[f, "ir_pol"], "Ставка I кв. 2027": _q(df, "ir_pol", "2027Q1"),
               "Ставка IV кв. 2027": _q(df, "ir_pol", "2027Q4"), "Ставка IV кв. 2028": _q(df, "ir_pol", "2028Q4"),
               "ІСЦ I кв. 2027": _q(df, "d4l_cpi", "2027Q1"), "ВВП 2027, %": float(pipeline.annual_table(df).loc["Реальний ВВП, % (рік)", 2027]),
               "ІСЦ IV кв. 2027": _q(df, "d4l_cpi", "2027Q4"), "ІСЦ IV кв. 2028": _q(df, "d4l_cpi", "2028Q4"),
               "ІСЦ IV кв. 2029": _q(df, "d4l_cpi", "2029Q4"),
               "Розрив ВВП, сер. 2027": df["l_gdp_gap"].loc["2027Q1":"2027Q4"].mean(),
               "Втрати (інфляція² + 0,5·розрив²)": float(((df.loc[per_loss, "d4l_cpi"] - tar) ** 2
                                                         + 0.5 * df.loc[per_loss, "l_gdp_gap"] ** 2).sum())}
        for name, df in pol.items()}).T.round(2)
    pol_tab.to_csv(TAB / "policy_options.csv", encoding="utf-8-sig")
    scen_tab = pd.DataFrame({
        name: {"ІСЦ IV кв. 2026": _q(df, "d4l_cpi", "2026Q4"), "ІСЦ пік": float(df.loc[fc, "d4l_cpi"].max().round(2)),
               "ІСЦ IV кв. 2027": _q(df, "d4l_cpi", "2027Q4"), "ІСЦ IV кв. 2029": _q(df, "d4l_cpi", "2029Q4"),
               "Ставка пік": float(df.loc[fc, "ir_pol"].max().round(2)),
               "Ставка IV кв. 2027": _q(df, "ir_pol", "2027Q4"), "Курс IV кв. 2027, грн/€": _q(df, "uah_eur", "2027Q4"),
               "ВВП 2027, % (рік)": float(pipeline.annual_table(df).loc["Реальний ВВП, % (рік)", 2027])}
        for name, df in scen.items()}).T
    scen_tab.to_csv(TAB / "scenarios.csv", encoding="utf-8-sig")
    print(pol_tab, "\n", scen_tab)

    # ------------------------------------------------------------- uncertainty
    sigma = uncertainty.empirical_sigma(ctx["filt"], "2023Q1", cfg.LAST_HIST)
    bands = uncertainty.fan(model, base, fc, sigma)
    for v, b in bands.items():
        b.to_csv(TAB / f"fan_{v}.csv")

    # ------------------------------------------------------------- backtest
    full = pipeline.prepare(cfg, use_nowcast=False)
    actual = pipeline.add_reporting(full["filt"].vars)
    bt = backtest.run(cfg, "2025Q3", actual, horizon=4)
    bt.to_csv(TAB / "backtest_2025Q3.csv", encoding="utf-8-sig")
    bt_err = pd.concat({o: backtest.errors(backtest.run(cfg, o, actual, 4)) for o in ("2025Q2", "2025Q3", "2025Q4")})
    bt_err.to_csv(TAB / "backtest_errors.csv", encoding="utf-8-sig")

    # ------------------------------------------------------------- reserves
    resv = reserves.project("2026-12")
    resv.to_csv(TAB / "reserves_projection.csv", encoding="utf-8-sig")

    # ------------------------------------------------------------- NBU comparison
    nbu = read_nbu_forecast()

    def nbu_q(prefix):
        s = nbu[nbu["indicator"].str.startswith(prefix) & nbu["period"].str.contains("Q")]
        return pd.Series(s["value"].values, index=pd.PeriodIndex(s["period"], freq="Q"))

    nbu_cpi, nbu_rate = nbu_q("ІСЦ (на кінець періоду)"), read_ir_chart("0.2").iloc[:, 0]
    nbu_gap = read_ir_chart("2.18").iloc[:, 0]
    comp = pd.DataFrame({
        "ІСЦ IV кв., наш (сер. за кв.)": [_q(base, "d4l_cpi", f"{y}Q4") for y in (2026, 2027, 2028)],
        "ІСЦ грудень, НБУ липень": [float(nbu_cpi[pd.Period(f"{y}Q4")]) for y in (2026, 2027, 2028)],
        "Ставка IV кв., наш": [_q(base, "ir_pol", f"{y}Q4") for y in (2026, 2027, 2028)],
        "Ставка IV кв., НБУ липень": [float(nbu_rate[pd.Period(f"{y}Q4")]) for y in (2026, 2027, 2028)],
        "ВВП, наш": [float(annual.loc["Реальний ВВП, % (рік)", y]) for y in (2026, 2027, 2028)],
        "ВВП, НБУ липень": [float(nbu[(nbu.indicator == "Реальний ВВП") & (nbu.period == str(y))]["value"].iloc[0])
                            for y in (2026, 2027, 2028)],
    }, index=[2026, 2027, 2028]).T
    comp.to_csv(TAB / "vs_nbu.csv", encoding="utf-8-sig")
    print(comp)

    # ------------------------------------------------------------- key numbers (single source for the deck)
    nc = ctx["nowcast"]
    key = {
        "data_cutoff": cfg.LAST_HIST, "first_forecast": str(f),
        "nowcast_dec_yoy": float(nc["ІСЦ р/р, прогноз"].iloc[-1]) if nc is not None else None,
        "nowcast_months": [str(p) for p in nc.index] if nc is not None else [],
        "baseline_quarterly": {str(p): {c: float(round(base.loc[p, c], 2)) for c in ("d4l_cpi", "ir_pol", "uah_eur", "gdp_yoy", "l_gdp_gap")}
                               for p in fc},
        "baseline_annual": {str(y): {k: float(v) for k, v in annual[y].items()} for y in annual.columns},
        "scenarios": scen_tab.to_dict(orient="index"),
        "policy_options": pol_tab.to_dict(orient="index"),
        "recommendation": cfg.RECOMMENDATION,
        "optimal_paths": opt_tab.to_dict(orient="index"),
        "fan_cpi": {q: bands["d4l_cpi"].loc[pd.Period(q)].round(2).to_dict() for q in ("2027Q4", "2028Q4", "2029Q4")},
        "rule_after_hold": {q: _q(rule, c, q) for q in ("2028Q4", "2029Q4") for c in ("d4l_cpi",)},
        "reserves_end2026": resv.iloc[-1].round(1).to_dict(),
        "reserves_months_imports_end2026": (resv.iloc[-1] / reserves.IMPORTS_PER_MONTH).round(1).to_dict(),
        "reserves_recent": {"sales_per_month": round(resv.attrs["sales"], 3),
                            "inflows_per_month": round(resv.attrs["recent_inflows"], 3)},
        "reserves_nbu": {"end2026": reserves.NBU_RESERVES_END2026,
                         "months": round(reserves.NBU_RESERVES_END2026 / reserves.IMPORTS_PER_MONTH, 1),
                         "inflow_needed_per_month": round((reserves.NBU_RESERVES_END2026 - resv.iloc[0, 0]) / (len(resv) - 1)
                                                          + resv.attrs["sales"], 1)},
        "backtest_rmse": bt_err.reset_index().rename(columns={"level_0": "origin", "level_1": "var"}).to_dict(orient="records"),
        "vs_nbu": comp.to_dict(),
        "sigma": sigma.round(2).to_dict(),
    }
    (OUT / "key_numbers.json").write_text(json.dumps(key, ensure_ascii=False, indent=1, default=float), encoding="utf-8")

    # ------------------------------------------------------------- figures
    nbu_cpi_line = nbu_cpi.loc[f:]
    # 1) fan charts
    fig, ax = pl.grid(1, 2, height=3.8)
    b = bands["d4l_cpi"]
    pl.line_panel(ax[0], {"Базовий прогноз": base["d4l_cpi"], "Прогноз НБУ (липень), кінець кв.": nbu_cpi_line},
                  "Інфляція (ІСЦ)", f, target=tar, target_label="ціль 5%", unit="% р/р", rng=RNG,
                  bands=[(b["q15"], b["q85"], pl.BLUE_RAMP[150]), (b["q30"], b["q70"], pl.BLUE_RAMP[250])])
    br = bands["ir_pol"]
    pl.line_panel(ax[1], {"Базовий прогноз": base["ir_pol"], "Прогноз НБУ (липень)": nbu_rate.loc[f:]},
                  "Облікова ставка", f, unit="%, середнє за квартал", rng=RNG,
                  bands=[(br["q15"], br["q85"], pl.BLUE_RAMP[150]), (br["q30"], br["q70"], pl.BLUE_RAMP[250])])
    pl.save(fig, FIG / "fc_fan.png", "розрахунки команди (QPM НБУ; віяло — інтервали 40% і 70% імовірності), НБУ")

    # 2) scenarios (one strip of four panels: fits a full-width slide)
    fig, ax = pl.grid(1, 4, width=15, height=3.5)
    pl.line_panel(ax[0], {k: v["d4l_cpi"] for k, v in scen.items()}, "Інфляція (ІСЦ)", f, target=tar,
                  target_label="ціль 5%", unit="% р/р", rng=RNG, shared_history=True)
    pl.line_panel(ax[1], {k: v["ir_pol"] for k, v in scen.items()}, "Облікова ставка", f, unit="%", rng=RNG,
                  shared_history=True)
    pl.line_panel(ax[2], {k: v["uah_eur"] for k, v in scen.items()}, "Курс", f, unit="грн/€", rng=RNG,
                  shared_history=True)
    pl.line_panel(ax[3], {k: v["l_gdp_gap"] for k, v in scen.items()}, "Розрив ВВП", f, target=0,
                  unit="% потенціалу", rng=RNG, shared_history=True)
    for a in ax[1:]:
        a.get_legend().remove() if a.get_legend() else None
    pl.save(fig, FIG / "fc_scenarios.png", "розрахунки команди (QPM НБУ)")

    # 3) policy options
    fig, ax = pl.grid(1, 3, width=13, height=3.6)
    rng2 = ("2025Q1", cfg.LAST_FORE)
    pl.line_panel(ax[0], {k: v["ir_pol"] for k, v in pol.items()}, "Облікова ставка", f, unit="%", rng=rng2, shared_history=True)
    pl.line_panel(ax[1], {k: v["d4l_cpi"] for k, v in pol.items()}, "Інфляція", f, target=tar, unit="% р/р", rng=rng2, shared_history=True)
    pl.line_panel(ax[2], {k: v["l_gdp_gap"] for k, v in pol.items()}, "Розрив ВВП", f, target=0,
                  unit="% потенціалу", rng=rng2, shared_history=True)
    for a in ax[1:]:
        a.get_legend().remove() if a.get_legend() else None
    pl.save(fig, FIG / "fc_policy.png", "розрахунки команди (QPM НБУ)")

    # 4) what drives the rule: deviation from the neutral nominal rate
    dec = pipeline.rate_gap_decomposition(base, model.params).loc["2025Q1": fc[-4]]
    fig, axd = pl.grid(1, 1, width=10, height=3.9)
    x = np.arange(len(dec))
    pos, neg = np.zeros(len(dec)), np.zeros(len(dec))
    for i, col in enumerate(dec.columns[:3]):
        v = 0.2 * dec[col].values / 0.2  # contributions in pp of the rule's target rate (before smoothing)
        bottom = np.where(v >= 0, pos, neg)
        axd[0].bar(x, v, bottom=bottom, width=0.6, color=pl.SERIES[i], label=col, edgecolor=pl.INK["surface"], lw=1.5)
        pos += np.clip(v, 0, None)
        neg += np.clip(v, None, 0)
    axd[0].plot(x, (base["ir_pol"] - dec["Нейтральна номінальна ставка"]).reindex(dec.index).values,
                color=pl.INK["primary"], lw=2, label="Облікова ставка мінус нейтральна")
    axd[0].axhline(0, color=pl.INK["axis"], lw=1)
    axd[0].axvspan(list(dec.index).index(f) - 0.5, len(dec) - 0.5, color=pl.INK["forecast"], zorder=0, lw=0)
    axd[0].set_xticks(x)
    axd[0].set_xticklabels([f"{['I', 'II', 'III', 'IV'][p.quarter - 1]}.{str(p.year)[2:]}" for p in dec.index], fontsize=8)
    axd[0].grid(axis="x", visible=False)
    axd[0].set_title("Чинники облікової ставки за правилом відносно нейтральної, в. п.")
    axd[0].legend(ncol=2, fontsize=8, loc="upper right")
    pl.save(fig, FIG / "fc_rate_drivers.png", "розрахунки команди (правило Тейлора QPM НБУ)")
    dec.to_csv(TAB / "rate_drivers.csv", encoding="utf-8-sig")

    # 5) output gap vs NBU
    ours = base["l_gdp_gap"].groupby(base.index.year).mean().loc[2020:fc[-1].year]
    fig, axg = pl.grid(1, 1, width=7, height=3.6)
    yrs = list(range(2020, fc[-1].year + 1))
    xi = np.arange(len(yrs))
    axg[0].bar(xi - 0.18, [ours.get(y, np.nan) for y in yrs], width=0.34, color=pl.SERIES[0], label="Наша оцінка (фільтр Калмана)",
               edgecolor=pl.INK["surface"], lw=1.5)
    axg[0].bar(xi + 0.18, [nbu_gap.get(y, np.nan) for y in yrs], width=0.34, color=pl.SERIES[1], label="НБУ (липень 2026)",
               edgecolor=pl.INK["surface"], lw=1.5)
    axg[0].axhline(0, color=pl.INK["axis"], lw=1)
    axg[0].set_xticks(xi)
    axg[0].set_xticklabels([f"{y}{'*' if y >= 2026 else ''}" for y in yrs])
    axg[0].grid(axis="x", visible=False)
    axg[0].set_title("Розрив ВВП, % потенційного (середнє за рік)")
    axg[0].legend(loc="lower right")
    pl.save(fig, FIG / "fc_gap_vs_nbu.png", "розрахунки команди; НБУ (Інфляційний звіт, липень 2026); * — прогноз")

    # 6) backtest
    fig, axb = pl.grid(1, 2, height=3.6)
    for a, (lab, var) in zip(axb, (("ІСЦ, % р/р", "d4l_cpi"), ("Облікова ставка, %", "ir_pol"))):
        per = pd.PeriodIndex([pd.Period(c, "Q") for c in bt.columns])
        hist = actual[var].loc["2024Q1":per[-1]]
        fcl = pd.concat([actual[var].loc[["2025Q3"]], pd.Series(bt.loc[(lab, "Прогноз")].values.astype(float), index=per)])
        pl.line_panel(a, {"Факт": hist, "Прогноз моделі з даними до III кв. 2025": fcl}, lab, pd.Period("2025Q4", "Q"),
                      rng=("2024Q1", str(per[-1])))
    pl.save(fig, FIG / "fc_backtest.png", "розрахунки команди: прогноз без суджень, зовнішні змінні — факт")

    # 7) reserves
    fig, axr = pl.grid(1, 1, width=7.5, height=4.9)
    hist_r = reserves.implied_inflows()["Резерви"].loc["2025-07":]
    series = {"Факт": hist_r}
    series.update({k: resv[k] for k in resv.columns})
    pl.monthly_panel(axr[0], series, "Міжнародні резерви: сценарії надходжень у IV кв. 2026", "$ млрд")
    axr[0].scatter([pd.Period("2026-12", "M").to_timestamp()], [reserves.NBU_RESERVES_END2026], marker="D", s=36,
                   color=pl.SERIES[6], zorder=6, label="Прогноз НБУ (липень)")
    axr[0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=8)
    fig.subplots_adjust(bottom=0.29)
    axr[0].axhline(3 * reserves.IMPORTS_PER_MONTH, color=pl.SERIES[7], lw=1)
    axr[0].annotate("3 місяці імпорту", xy=(0.01, 3 * reserves.IMPORTS_PER_MONTH), xycoords=("axes fraction", "data"),
                    xytext=(0, 3), textcoords="offset points", fontsize=8, color=pl.INK["secondary"])
    pl.save(fig, FIG / "fc_reserves.png", "НБУ (резерви, інтервенції); розрахунки команди: продаж валюти НБУ "
            f"≈${resv.attrs['sales']:.1f} млрд/міс")

    # 8) trends
    fig, ax = pl.grid(1, 2, height=3.4)
    pl.line_panel(ax[0], {"Потенційний ВВП, кв/кв анулізовано": base["dl_gdp_tnd"]}, "Темп потенційного ВВП", f,
                  unit="%", rng=("2018Q1", cfg.LAST_FORE))
    pl.line_panel(ax[1], {"Реальна облікова ставка": base["rir_pol"], "Нейтральна реальна ставка": base["rir_tnd"]},
                  "Реальна ставка", f, unit="%", rng=RNG)
    pl.save(fig, FIG / "fc_trends.png", "розрахунки команди (QPM НБУ, фільтр Калмана)")

    # 9) monthly CPI with the short-term nowcast and NBU's July path
    if nc is not None:
        cpi_m = pd.read_csv("data/overview/cpi.csv", index_col=0, encoding="utf-8-sig")
        cpi_m.index = pd.PeriodIndex(cpi_m.index, freq="M")
        act = cpi_m["cpi_yoy"].loc["2025-01":]
        nowc = pd.concat([act.iloc[-1:], nc["ІСЦ р/р, прогноз"]])
        fig, axn = pl.grid(1, 1, width=7, height=3.6)
        pl.monthly_panel(axn[0], {"Факт": act, "Наш короткостроковий прогноз": nowc}, "Інфляція (ІСЦ)", "% р/р",
                         target=tar, target_label="ціль 5%")
        nbu_pts = {pd.Period("2026-09", "M"): float(nbu_cpi[pd.Period("2026Q3")]),
                   pd.Period("2026-12", "M"): float(nbu_cpi[pd.Period("2026Q4")])}
        axn[0].scatter([p.to_timestamp() for p in nbu_pts], list(nbu_pts.values()), marker="D", s=30,
                       color=pl.SERIES[2], zorder=6, label="Прогноз НБУ (липень), кінець кварталу")
        axn[0].legend(loc="upper right")
        pl.save(fig, FIG / "fc_nowcast.png", "Держстат, НБУ; розрахунки команди (тренд + сезонність + судження)")

    # 10) headline vs core: our baseline and NBU July forecast (end of quarter)
    nbu_core = nbu_q("Базова інфляція")
    fig, axc = pl.grid(1, 1, width=7, height=3.6)
    pl.line_panel(axc[0], {"ІСЦ (наш прогноз)": base["d4l_cpi"], "Базова (наш прогноз)": base["d4l_cpi_c"],
                           "ІСЦ (НБУ, липень)": nbu_cpi.loc[f:], "Базова (НБУ, липень)": nbu_core.loc[f:]},
                  "Загальна та базова інфляція", f, target=tar, target_label="ціль 5%", unit="% р/р",
                  rng=("2024Q1", cfg.LAST_FORE))
    pl.save(fig, FIG / "fc_core.png", "розрахунки команди (наш прогноз — середнє за квартал); НБУ — кінець кварталу")

    print("Графіки:", sorted(p.name for p in FIG.glob("fc_*.png")))


if __name__ == "__main__":
    main()
