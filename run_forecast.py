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
    tar = model.params["dl_cpi_tar"]             # model units (100*log); reports show % y/y
    tar_pct = round(float(pipeline.pct(tar)), 2)  # = 5.0
    print(f"Історія до {cfg.LAST_HIST}, прогноз {f}–{cfg.LAST_FORE}")
    ctx["filt"].vars.to_csv(TAB / "filter.csv")
    if ctx["nowcast"] is not None:
        ctx["nowcast"].to_csv(TAB / "cpi_nowcast.csv", encoding="utf-8-sig")
    if ctx.get("nowcast_core") is not None:
        ctx["nowcast_core"].to_csv(TAB / "core_nowcast.csv", encoding="utf-8-sig")

    # ------------------------------------------------------------- scenarios and policy options
    base_plan = pipeline.base_plan(ctx)
    # baseline = decision + hold, then the path returning inflation to the 5% point target within the horizon
    scen = {name: pipeline.run(ctx, plan) for name, plan in pipeline.scenario_plans(ctx).items()}
    base = scen["Базовий"]
    rule = pipeline.run(ctx, pipeline.with_rate_path(base_plan, cfg.RECOMMENDED_RATE_PATH))
    # UAH/USD for reporting (the model works with UAH/EUR): USD/EUR — the last observed month (October 2026, 1.12)
    # held flat over the horizon (update_data.update_oil); the NBU's July assumptions (1.16–1.19) are stale
    usd_eur = ctx["dq"]["USD_EUR"].ffill()
    for df in (*scen.values(), rule):
        df["uah_usd"] = df["uah_eur"] / usd_eur.reindex(df.index).ffill()

    # risk runs on top of the baseline (the rule reacts around the baseline rate path, as in the scenarios):
    # the hryvnia weakens as the market expects; de-anchored expectations (stickier core inflation); VAT 20 -> 21%
    rec_plan = pipeline.policy_plan(ctx, base_plan, cfg.RECOMMENDED_RATE_PATH)
    around = pipeline.rate_path_to_shock(ctx, pipeline.nowcast_to_shock(ctx, rec_plan), keep=[str(f)])
    fxe = read_ir_chart("3.12")["Фінансові аналітики"].dropna()
    usd_now = float(base.loc[f - 1, "uah_usd"])
    dep = float(fxe.iloc[-1]) / usd_now - 1                       # a year ahead, analysts (NBU survey)
    fx_per = pd.period_range(f, "2027Q4", freq="Q")
    fx_path = [100 * np.log(usd_now * (1 + dep) ** ((k + 1) / 4) * float(usd_eur.reindex([q]).ffill().iloc[0]))
               for k, q in enumerate(fx_per)]
    def uip_increment(per, l_er_path):
        """UIP shocks that take UAH/EUR to `l_er_path` under the recommended decision, NET of the UIP shocks the plan
        already carries (the Q4 2026 nowcast shock from nowcast_to_shock). The run returns the total shock and
        Plan.shock adds, so only the increment may be passed on: until 25.10.2026 (found by the model reviewer) the
        total was added on top of the fixed nowcast shock, the Q4 shock was counted twice and the hryvnia
        APPRECIATED in Q4 2026 in the 'weaker hryvnia' scenario (test_fx_risk_scenario_weakens_the_hryvnia)."""
        p_ = around.copy()
        p_.exogenize("l_er", per, l_er_path)
        p_.endogenize("res_l_er_uip", per)
        total = pipeline.run(ctx, p_).attrs["shocks"]["res_l_er_uip"].reindex(per)
        return total - pd.Series({p: around.shocks.get("res_l_er_uip", {}).get(p, 0.0) for p in per})

    # the FX risk is the UIP shock that produces the market path under the recommended decision; it then enters as a
    # shock, so the hryvnia still responds to the policy rate (with a fixed path the decision would hardly matter)
    uip_fx = uip_increment(fx_per, fx_path)

    def sc_fx(plan, f_, ctx_=None):
        plan.shock("res_l_er_uip", list(fx_per), list(uip_fx.values))
        return plan

    # the mirror of the audit's most influential change (USD/EUR 1.12 held flat): the euro back at the NBU's July
    # assumption of 1.16 $ from 2027Q1 with UAH/USD as in the baseline, i.e. UAH/EUR weaker by 1.16/1.12 − 1 ≈ 3.4%,
    # delivered by UIP shocks (the rate still matters). Oil in euro would then be ≈3% cheaper — ignored (w_oil 0.016)
    eur_per = pd.period_range(f + 1, "2027Q4", freq="Q")
    eur_path = [100 * np.log(float(base.loc[q, "uah_usd"]) * cfg.EUR_RISK_USD_PER_EUR) for q in eur_per]
    uip_eur = uip_increment(eur_per, eur_path)

    def sc_eur(plan, f_, ctx_=None):
        plan.shock("res_l_er_uip", list(eur_per), list(uip_eur.values))
        return plan

    def sc_exp(plan, f_, ctx_=None):       # de-anchored expectations: core +1 pp (q/q annualised) every quarter of 2027
        plan.shock("res_dl_cpi_c", list(pd.period_range("2027Q1", "2027Q4", freq="Q")), [1.0] * 4)
        return plan

    def sc_vat(plan, f_, ctx_=None):
        """VAT 20 -> 21% from 2027: a one-off core cost-push shock of 0.8 (q/q annualised) in 2027Q1. Measured the way
        the scenario is run (anticipated shock on top of the baseline, the rule reacting), it lifts CPI y/y by ≈0.54 pp
        at the peak (2027Q2) — the midpoint of the NBU's estimate of +0.4–0.7 pp (Interfax, 17.09.2026). The
        unanticipated IRF of the same shock peaks at only +0.29 pp: the anticipated shock also raises inflation
        before 2027Q1 through the forward-looking Phillips curve, so the calibration must be done in the scenario."""
        plan.shock("res_dl_cpi_c", [pd.Period("2027Q1", "Q")], [0.8])
        return plan

    def sc_weak(plan, f_, ctx_=None):      # counterweight: demand weaker than assumed (attacks, fiscal consolidation)
        plan.shock("res_l_gdp_gap", [f_ + 1, f_ + 2, f_ + 3, f_ + 4], [-0.7, -0.7, -0.5, -0.3])
        return plan

    def sc_core_down(plan, f_, ctx_=None):  # counterweight: September largely one-off, core slows in Q4-Q1
        plan.shock("res_dl_cpi_c", [f_, f_ + 1], [-1.5, -0.75])
        return plan

    RISKS = {"Курс як чекає ринок": sc_fx, cfg.EUR_RISK_NAME: sc_eur, "Розбалансування очікувань": sc_exp,
             "ПДВ 21% з 2027": sc_vat}
    COUNTER = {"Слабкий попит": sc_weak, "Базова сповільнюється": sc_core_down}
    risks = {}
    for name, fn in RISKS.items():
        rr = pipeline.run(ctx, fn(around.copy(), f, ctx))
        ue = usd_eur.reindex(rr.index).ffill()
        if name == cfg.EUR_RISK_NAME:              # in this scenario the dollar price of the euro is 1.16 from 2027Q1
            ue[ue.index >= eur_per[0]] = cfg.EUR_RISK_USD_PER_EUR
        rr["uah_usd"] = rr["uah_eur"] / ue
        dev = (rr["cpi_yoy"] - base["cpi_yoy"]).loc[fc]          # largest lift of CPI y/y over the baseline, and when
        risks[name] = {"ІСЦ IV кв. 2027": _q(rr, "cpi_yoy", "2027Q4"), "ІСЦ пік": float(rr.loc[fc, "cpi_yoy"].max().round(2)),
                       "Макс. +ІСЦ, в. п.": float(round(dev.max(), 2)), "Квартал макс.": str(dev.idxmax()),
                       "Базова IV кв. 2027": _q(rr, "core_yoy", "2027Q4"), "Ставка пік": float(rr.loc[fc, "ir_pol"].max().round(2)),
                       "Курс IV кв. 2027, грн/$": _q(rr, "uah_usd", "2027Q4"), "Курс IV кв. 2026, грн/$": _q(rr, "uah_usd", str(f)),
                       "Курс IV кв. 2027, грн/€": _q(rr, "uah_eur", "2027Q4")}
    fx_risk = {"cpi_2027Q4": risks["Курс як чекає ринок"]["ІСЦ IV кв. 2027"], "rate_peak": risks["Курс як чекає ринок"]["Ставка пік"],
               "uah_usd_2027Q4": risks["Курс як чекає ринок"]["Курс IV кв. 2027, грн/$"], "dep_per_year": round(dep * 100, 1)}
    pd.DataFrame(risks).T.to_csv(TAB / "risks_extra.csv", encoding="utf-8-sig")
    print("Додаткові ризики:", risks)
    print("Базовий vs чисте правило після утримання, ІСЦ IV кв. 2028 / 2029:",
          [round(float(d.loc[q, "cpi_yoy"]), 2) for d in (base, rule) for q in ("2028Q4", "2029Q4")])
    # policy reacts to first-round administered prices only partly (cfg.ADMIN_REACTION): the same principle for the
    # decision, the path after the hold and the losses; the forecast itself keeps all judgments in full
    react = pipeline.reaction_plan(ctx)
    # for comparing rate paths the nowcast enters as fixed shocks (as in optimal.optimal_path)
    react_s, base_s = pipeline.nowcast_to_shock(ctx, react), pipeline.nowcast_to_shock(ctx, base_plan)

    def react_run(plan):
        """The same rate path, inflation measured as policy sees it (first round of admin prices partly netted out)."""
        return pipeline.run(ctx, pipeline.with_rate_path(react_s, {str(k): float(v) for k, v in plan.exo["ir_pol"].items()}))

    def land_run(plan):
        """The same rate path, all judgments in full — for the landing quarters of the loss."""
        return pipeline.run(ctx, pipeline.with_rate_path(base_s, {str(k): float(v) for k, v in plan.exo["ir_pol"].items()}))

    pol_plans = {name: pipeline.policy_plan(ctx, base_plan, path) for name, path in cfg.POLICY_OPTIONS.items()}
    # optimal rate path from the October decision on (min of quadratic loss), sensitivity to the smoothing weight
    tp = {k: v for k, v in cfg.TARGET_PATH.items() if k != "w_smooth"}
    opt_rows = {}

    def opt_row(path_o, L):
        return {**{str(p): round(float(v), 2) for p, v in path_o.items()},
                "Втрати: оптимум": round(L["optimal"], 1), "Втрати: правило": round(L["rule"], 1)}

    for ws in (0.5, 1.0, 2.0):
        _, path_o, L = optimal.optimal_path(ctx, react, w_smooth=ws, landing_plan=base_plan, **tp)
        opt_rows[f"λ = {ws:g}"] = opt_row(path_o, L)
        if ws == cfg.TARGET_PATH["w_smooth"]:
            pol_plans["Оптимальна (мін. втрат)"] = pipeline.with_rate_path(base_plan, {str(k): float(v) for k, v in path_o.items()})
    for lab, lt in (("λ = 1, повна реакція на адмінціни", 0.0), ("λ = 1, без реакції на адмінціни", 1.0)):
        _, path_o, L = optimal.optimal_path(ctx, pipeline.base_plan(ctx, look_through=lt), **cfg.TARGET_PATH)
        opt_rows[lab] = opt_row(path_o, L)
    # Every option is run with the SAME nowcast shocks (land_run: all judgments in full, nowcast as fixed shocks
    # implied once under the rule) — the runs behind the table are the runs behind the losses. Before 25.10.2026 the
    # table columns came from runs that pinned CPI to the nowcast (a different implied shock per option) while the
    # losses came from the fixed-shock runs; the 17% row therefore differs slightly from the baseline forecast, in
    # which the current quarter IS pinned to the nowcast (key_numbers["options_vs_baseline"] reports the gap).
    pol = {name: land_run(plan) for name, plan in pol_plans.items()}
    opt_tab = pd.DataFrame(opt_rows).T
    opt_tab.to_csv(TAB / "optimal_paths.csv", encoding="utf-8-sig")
    print(opt_tab)
    for name, df in {**scen, **{f"policy_{k}": v for k, v in pol.items()}}.items():
        df.to_csv(TAB / f"forecast_{name}.csv", encoding="utf-8-sig")
    pipeline.summary_table({"Базовий": base}, fc).to_csv(TAB / "baseline_quarterly.csv", encoding="utf-8-sig")
    annual = pipeline.annual_table(base)
    annual.to_csv(TAB / "baseline_annual.csv", encoding="utf-8-sig")

    # policy options: the optimiser's own loss (inflation vs target, output gap, rate changes incl. the decision itself)
    # over the whole horizon, on inflation as policy sees it — higher rates cut inflation faster but need sharper rate
    # moves; the smoothing weight is a preference, so the best option is reported for each weight
    pol_react = {name: react_run(plan) for name, plan in pol_plans.items()}
    pol_land = pol
    loss_w = {ws: {name: optimal.policy_loss(ctx, df, df_land=pol_land[name], **{**cfg.TARGET_PATH, "w_smooth": ws})
                   for name, df in pol_react.items()}
              for ws in (0.5, 1.0, 2.0)}
    best_option = {f"λ = {ws:g}": min(cfg.POLICY_OPTIONS, key=loss_w[ws].get) for ws in loss_w}
    # the loss-minimising hold on a wider grid: the table of four options does not have to contain the minimum
    grid = [16.0 + 0.5 * k for k in range(8)]
    grid_plans = {r: pipeline.policy_plan(ctx, base_plan, {q: r for q in cfg.HOLD}) for r in grid}
    grid_runs = {r: (react_run(gp), land_run(gp)) for r, gp in grid_plans.items()}
    best_hold = {f"λ = {ws:g}": min(grid, key=lambda r: optimal.policy_loss(ctx, grid_runs[r][0], df_land=grid_runs[r][1],
                                                                             **{**cfg.TARGET_PATH, "w_smooth": ws}))
                 for ws in (0.5, 1.0, 2.0)}
    print("Найменші втрати серед утримань 16–19,5%:", best_hold)

    # ------------------------------------------------------------- robustness of the October decision
    # each option fixes the October decision (and the promised hold) and its own target-consistent path; in the risk
    # scenarios the rule then reacts around that path. Losses — the optimiser's function: nowcast as shocks, admin first
    # round counted at ADMIN_REACTION (delta below), landing on actual inflation, rate changes from the rate in force
    rob_opts = [16.0, 16.5, 17.0, 17.5, 18.0]
    p_rec = {str(k): float(v) for k, v in rec_plan.exo["ir_pol"].items()}
    delta = {c: (pipeline.run(ctx, pipeline.with_rate_path(base_s, p_rec))[c]
                 - pipeline.run(ctx, pipeline.with_rate_path(react_s, p_rec))[c]) for c in ("d4l_cpi", "l_gdp_gap")}

    def rob_loss(df, lam):
        adj = df.copy()
        for c in ("d4l_cpi", "l_gdp_gap"):
            adj[c] = df[c] - delta[c].reindex(df.index).fillna(0.0)
        return optimal.policy_loss(ctx, adj, df_land=df, **{**cfg.TARGET_PATH, "w_smooth": lam})

    rob_scen = {"Базовий": None, **{k: v for k, v in cfg.SCENARIOS.items() if k != "Базовий"}, **RISKS, **COUNTER}
    rob = {}
    for r in rob_opts:
        p_r = pipeline.policy_plan(ctx, base_plan, {q: r for q in cfg.HOLD})
        # the same nowcast shocks for every option (base_s: implied once, under the rule — as in optimal_path and in
        # the options table). Re-implying them per option (the code until 25.10.2026) pinned Q4 inflation to the
        # nowcast for every option, so a higher rate bought nothing in Q4 and paid the full smoothing penalty; the
        # baseline row now equals the options table (pipeline.nowcast_to_shock, docs/audit_2026-10-25.md). The old
        # convention is re-run below (rob_old) so the reader sees what hangs on it
        p_rs = pipeline.with_rate_path(base_s, {str(k): float(v) for k, v in p_r.exo["ir_pol"].items()})
        around_r = pipeline.rate_path_to_shock(ctx, p_rs, keep=[str(f)])
        for name, fn in rob_scen.items():
            d = pipeline.run(ctx, p_rs if fn is None else fn(around_r.copy(), f, ctx))
            for lam in (0.5, 1.0, 2.0):
                rob.setdefault(f"λ = {lam:g}", {}).setdefault(name, {})[r] = round(rob_loss(d, lam), 2)
            rob.setdefault("cpi27", {}).setdefault(name, {})[r] = _q(d, "cpi_yoy", "2027Q4")
    rob_sum = {}
    for lk in ("λ = 0.5", "λ = 1", "λ = 2"):
        t = pd.DataFrame(rob[lk]).T
        e = {pk: {r: round(float(sum(t.loc[sn, r] * wgt for sn, wgt in pv.items())), 2) for r in rob_opts}
             for pk, pv in cfg.ROBUST_PROBS.items()}
        reg = t.sub(t.min(axis=1), axis=0).max()
        rob_sum[lk] = {"E": e, "regret": {r: round(float(v), 2) for r, v in reg.items()},
                       "best_E": {pk: min(v, key=v.get) for pk, v in e.items()}, "best_regret": float(reg.idxmin())}
    pd.DataFrame(rob["λ = 1"]).T.to_csv(TAB / "robust_losses.csv", encoding="utf-8-sig")
    print("Стійкість рішення (λ = 1):", rob_sum["λ = 1"])

    # Sensitivity to the convention (the model reviewer's point, docs/audit_2026-10-25.md §2 row 1): the code until
    # 25.10.2026 re-implied the nowcast shocks under each option ('the current quarter is a quasi-fact', so the
    # decision cannot move Q4 inflation). Both conventions are used in practice; the one above is kept because it is
    # the one the options table and the optimiser use. What hangs on it is reported here (λ = 1 only).
    rob_old = {}
    for r in rob_opts:
        p_r = pipeline.policy_plan(ctx, base_plan, {q: r for q in cfg.HOLD})
        around_o = pipeline.rate_path_to_shock(ctx, pipeline.nowcast_to_shock(ctx, p_r), keep=[str(f)])
        for name, fn in rob_scen.items():
            d = pipeline.run(ctx, around_o if fn is None else fn(around_o.copy(), f, ctx))
            rob_old.setdefault(name, {})[r] = round(rob_loss(d, 1.0), 2)
    t_old = pd.DataFrame(rob_old).T
    e_old = {pk: {r: round(float(sum(t_old.loc[sn, r] * wgt for sn, wgt in pv.items())), 2) for r in rob_opts}
             for pk, pv in cfg.ROBUST_PROBS.items()}
    reg_old = t_old.sub(t_old.min(axis=1), axis=0).max()
    rob_old_sum = {"Базовий": rob_old["Базовий"], "E": e_old, "best_E": {pk: min(v, key=v.get) for pk, v in e_old.items()},
                   "best_regret": float(reg_old.idxmin())}
    print("Стійкість за старою конвенцією (шоки наукасту під кожну ставку, λ = 1):", rob_old_sum)

    # Sensitivity of the optimum to the exchange-rate assumption — the audit's most influential change (the Q4 2026
    # nowcast: the hryvnia 2% stronger against the euro in October). Three alternatives, each as UIP shocks on top of
    # the plans (the rate still matters): no FX nowcast at all; the October appreciation reversed in 2027Q1 (UAH/EUR
    # back at the level the model gives without the nowcast); the euro back at 1.16 $ from 2027Q1 (the EUR risk).
    ctx_nofx = {**ctx, "fx_nowcast": {}}
    nofx_rec = pipeline.run(ctx_nofx, pipeline.policy_plan(ctx_nofx, pipeline.base_plan(ctx_nofx), cfg.RECOMMENDED_RATE_PATH))
    uip_tmp = uip_increment([f + 1], [float(nofx_rec.loc[f + 1, "l_er"])])

    def opt_with(ctx_, shocks):
        rp, lp = pipeline.reaction_plan(ctx_), pipeline.base_plan(ctx_)
        for sh, per, vals in shocks:
            rp.shock(sh, per, vals)
            lp.shock(sh, per, vals)
        _, path_o, _ = optimal.optimal_path(ctx_, rp, w_smooth=cfg.TARGET_PATH["w_smooth"], landing_plan=lp, **tp)
        rec = pipeline.run(ctx_, pipeline.policy_plan(ctx_, lp, cfg.RECOMMENDED_RATE_PATH))
        return {"Оптимум IV кв. 2026": round(float(path_o[f]), 2), "Оптимум I кв. 2027": round(float(path_o[f + 1]), 2),
                f"ІСЦ IV кв. 2027 за {cfg.RECOMMENDATION['rate']:g}%": _q(rec, "cpi_yoy", "2027Q4"),
                "грн/€ I кв. 2027": _q(rec, "uah_eur", str(f + 1)), "грн/€ IV кв. 2027": _q(rec, "uah_eur", "2027Q4")}

    fx_sens = {"Базовий (жовтневий курс у IV кв., далі модель)": opt_with(ctx, []),
               "Без наукасту курсу": opt_with(ctx_nofx, []),
               "Жовтневе зміцнення тимчасове (I кв. 2027 — рівень без наукасту)": opt_with(ctx, [("res_l_er_uip", [f + 1], list(uip_tmp.values))]),
               f"{cfg.EUR_RISK_NAME} з I кв. 2027": opt_with(ctx, [("res_l_er_uip", list(eur_per), list(uip_eur.values))])}
    pd.DataFrame(fx_sens).T.to_csv(TAB / "fx_sensitivity.csv", encoding="utf-8-sig")
    print("Чутливість оптимуму до курсового припущення:", fx_sens)
    print("Найкращий варіант за вагою згладжування:", best_option)
    pol_tab = pd.DataFrame({
        name: {"Ставка IV кв. 2026": df.loc[f, "ir_pol"], "Ставка I кв. 2027": _q(df, "ir_pol", "2027Q1"),
               "Ставка IV кв. 2027": _q(df, "ir_pol", "2027Q4"), "Ставка IV кв. 2028": _q(df, "ir_pol", "2028Q4"),
               "ІСЦ I кв. 2027": _q(df, "cpi_yoy", "2027Q1"), "ВВП 2027, %": float(pipeline.annual_table(df).loc["Реальний ВВП, % (рік)", 2027]),
               "ІСЦ IV кв. 2027": _q(df, "cpi_yoy", "2027Q4"), "ІСЦ IV кв. 2028": _q(df, "cpi_yoy", "2028Q4"),
               "ІСЦ IV кв. 2029": _q(df, "cpi_yoy", "2029Q4"),
               "Розрив ВВП, сер. 2027": df["l_gdp_gap"].loc["2027Q1":"2027Q4"].mean(),
               **{f"Втрати, λ = {ws:g}": loss_w[ws][name] for ws in loss_w}}
        for name, df in pol.items()}).T.round(2)
    pol_tab.to_csv(TAB / "policy_options.csv", encoding="utf-8-sig")
    scen_tab = pd.DataFrame({
        name: {"ІСЦ IV кв. 2026": _q(df, "cpi_yoy", "2026Q4"), "ІСЦ пік": float(df.loc[fc, "cpi_yoy"].max().round(2)),
               "ІСЦ IV кв. 2027": _q(df, "cpi_yoy", "2027Q4"), "ІСЦ IV кв. 2029": _q(df, "cpi_yoy", "2029Q4"),
               "Ставка пік": float(df.loc[fc, "ir_pol"].max().round(2)),
               "Ставка IV кв. 2027": _q(df, "ir_pol", "2027Q4"), "Курс IV кв. 2027, грн/€": _q(df, "uah_eur", "2027Q4"),
               "Курс IV кв. 2027, грн/$": _q(df, "uah_usd", "2027Q4"),
               "ВВП 2027, % (рік)": float(pipeline.annual_table(df).loc["Реальний ВВП, % (рік)", 2027])}
        for name, df in scen.items()}).T
    scen_tab.to_csv(TAB / "scenarios.csv", encoding="utf-8-sig")
    print(pol_tab, "\n", scen_tab)

    # ------------------------------------------------------------- uncertainty
    sigma = uncertainty.empirical_sigma(ctx["filt"], "2023Q1", cfg.LAST_HIST)
    bands = uncertainty.fan(model, base, fc, sigma)
    bands["cpi_yoy"] = pipeline.pct(bands.pop("d4l_cpi"))   # quantiles map one-to-one through the monotone transform
    for v, b in bands.items():
        b.to_csv(TAB / f"fan_{v}.csv")

    # ------------------------------------------------------------- backtest
    # "actual" = observed data only (no nowcasts, no filter projection): quarters without data stay blank
    full = pipeline.prepare(cfg, use_nowcast=False)
    actual = backtest.actual_from_data(full["dq"])
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
        "ІСЦ IV кв., наш (сер. за кв.)": [_q(base, "cpi_yoy", f"{y}Q4") for y in (2026, 2027, 2028)],
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
        "nowcast_core_dec_yoy": float(ctx["nowcast_core"]["ІСЦ р/р, прогноз"].iloc[-1]) if ctx.get("nowcast_core") is not None else None,
        "nowcast_months": [str(p) for p in nc.index] if nc is not None else [],
        "baseline_quarterly": {str(p): {c: float(round(base.loc[p, c], 2)) for c in
                                        ("cpi_yoy", "core_yoy", "ir_pol", "uah_eur", "uah_usd", "gdp_yoy", "l_gdp_gap", "rir_pol", "rir_tnd")}
                               for p in fc},
        "real_rate_last_hist": {c: float(round(base.loc[f - 1, c], 2)) for c in ("rir_pol", "rir_tnd")},
        "best_option_by_lambda": best_option,
        "fx_risk": fx_risk, "risks_extra": risks,
        "robust": {"losses": rob, "summary": rob_sum, "probs": cfg.ROBUST_PROBS, "options": rob_opts},
        "robust_old_convention": rob_old_sum, "fx_sensitivity": fx_sens,
        "rate_now": ctx["rate_now"],
        "best_hold_by_lambda": best_hold, "admin_reaction": cfg.ADMIN_REACTION,
        "brent_path": {q: round(float(ctx["dq"].loc[pd.Period(q, "Q"), "BRENT_USD"]), 1) for q in ("2026Q4", "2027Q4", "2028Q4")},
        "baseline_annual": {str(y): {k: float(v) for k, v in annual[y].items()} for y in annual.columns},
        "scenarios": scen_tab.to_dict(orient="index"),
        "policy_options": pol_tab.to_dict(orient="index"),
        "recommendation": cfg.RECOMMENDATION,
        "optimal_paths": opt_tab.to_dict(orient="index"),
        "fan_cpi": {q: bands["cpi_yoy"].loc[pd.Period(q)].round(2).to_dict() for q in ("2027Q4", "2028Q4", "2029Q4")},
        "rule_after_hold": {q: _q(rule, "cpi_yoy", q) for q in ("2028Q4", "2029Q4")},
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
        # current-quarter conditioning of the baseline and how far the fixed-shock 17% option run is from it
        "fx_nowcast": {str(p): {**v, "level": round(v["level"], 4)} for p, v in ctx["fx_nowcast"].items()},
        "options_vs_baseline": {q: {c: round(float(pol[cfg.RECOMMENDATION["option"]].loc[pd.Period(q, "Q"), c] - base.loc[pd.Period(q, "Q"), c]), 3)
                                    for c in ("cpi_yoy", "ir_pol", "l_gdp_gap")} for q in ("2026Q4", "2027Q4", "2028Q4")},
        "brent_history_source": "EIA spot, monthly averages (no futures in history)",
    }
    (OUT / "key_numbers.json").write_text(json.dumps(key, ensure_ascii=False, indent=1, default=float), encoding="utf-8")

    # ------------------------------------------------------------- figures
    nbu_cpi_line = nbu_cpi.loc[f:]
    # 1) fan charts
    fig, ax = pl.grid(1, 2, height=3.8)
    b = bands["cpi_yoy"]
    pl.line_panel(ax[0], {"Базовий прогноз": base["cpi_yoy"], "Прогноз НБУ (липень), кінець кв.": nbu_cpi_line},
                  "Інфляція (ІСЦ)", f, target=tar_pct, target_label="ціль 5%", unit="% р/р", rng=RNG,
                  bands=[(b["q15"], b["q85"], pl.BLUE_RAMP[150]), (b["q30"], b["q70"], pl.BLUE_RAMP[250])])
    br = bands["ir_pol"]
    pl.line_panel(ax[1], {"Базовий прогноз": base["ir_pol"], "Прогноз НБУ (липень)": nbu_rate.loc[f:]},
                  "Облікова ставка", f, unit="%, середнє за квартал", rng=RNG,
                  bands=[(br["q15"], br["q85"], pl.BLUE_RAMP[150]), (br["q30"], br["q70"], pl.BLUE_RAMP[250])])
    pl.save(fig, FIG / "fc_fan.png", "розрахунки команди (QPM НБУ; віяло — інтервали 40% і 70% імовірності), НБУ")

    # 2) scenarios (one strip of four panels: fits a full-width slide)
    fig, ax = pl.grid(1, 4, width=15, height=3.5)
    pl.line_panel(ax[0], {k: v["cpi_yoy"] for k, v in scen.items()}, "Інфляція (ІСЦ)", f, target=tar_pct,
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
    pl.line_panel(ax[1], {k: v["cpi_yoy"] for k, v in pol.items()}, "Інфляція", f, target=tar_pct, unit="% р/р", rng=rng2, shared_history=True)
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
    for a, (lab, var) in zip(axb, (("ІСЦ, % р/р", "cpi_yoy"), ("Облікова ставка, %", "ir_pol"))):
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
                         target=tar_pct, target_label="ціль 5%")
        nbu_pts = {pd.Period("2026-09", "M"): float(nbu_cpi[pd.Period("2026Q3")]),
                   pd.Period("2026-12", "M"): float(nbu_cpi[pd.Period("2026Q4")])}
        axn[0].scatter([p.to_timestamp() for p in nbu_pts], list(nbu_pts.values()), marker="D", s=30,
                       color=pl.SERIES[2], zorder=6, label="Прогноз НБУ (липень), кінець кварталу")
        axn[0].legend(loc="upper right")
        pl.save(fig, FIG / "fc_nowcast.png", "Держстат, НБУ; розрахунки команди (тренд + сезонність + судження)")

    # 10) headline vs core: our baseline and NBU July forecast (end of quarter)
    nbu_core = nbu_q("Базова інфляція")
    fig, axc = pl.grid(1, 1, width=7, height=3.6)
    pl.line_panel(axc[0], {"ІСЦ (наш прогноз)": base["cpi_yoy"], "Базова (наш прогноз)": base["core_yoy"],
                           "ІСЦ (НБУ, липень)": nbu_cpi.loc[f:], "Базова (НБУ, липень)": nbu_core.loc[f:]},
                  "Загальна та базова інфляція", f, target=tar_pct, target_label="ціль 5%", unit="% р/р",
                  rng=("2024Q1", cfg.LAST_FORE))
    pl.save(fig, FIG / "fc_core.png", "розрахунки команди (наш прогноз — середнє за квартал); НБУ — кінець кварталу")

    print("Графіки:", sorted(p.name for p in FIG.glob("fc_*.png")))


if __name__ == "__main__":
    main()
