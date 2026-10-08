"""End-to-end steps shared by the run_* scripts (a01 -> a03 -> a04 in the MATLAB template)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import read_data
from .kalman import kalman_smoother
from .model import Model
from .nowcast import as_dict, cpi_nowcast
from .simulate import Plan, forecast

EXTERNAL = [("ir_ea", "res_ir_ea"), ("l_gdp_ea_gap", "res_l_gdp_ea_gap"), ("dl_cpi_ea", "res_dl_cpi_ea"),
            ("dl_roil", "res_dl_roil")]
DOMESTIC_OBS = ("L_GDP", "L_CPI", "L_CPI_C", "IR_POLICY", "L_ER")


def prepare(cfg, last_hist: str | None = None, use_nowcast: bool = True):
    """Read data (+ nowcasts), add tunes, build model, run the Kalman smoother."""
    last_hist = last_hist or cfg.LAST_HIST
    nc = cpi_nowcast(data_dir=cfg.DATA_DIR, **cfg.CPI_NOWCAST) if use_nowcast and getattr(cfg, "CPI_NOWCAST", None) else None
    dq = read_data(cfg.DATA_DIR, as_dict(nc) if nc is not None else None,
                   getattr(cfg, "GDP_NOWCAST", None) if use_nowcast else None)
    dq["L_GDP_GAP"] = np.nan
    for per, val in cfg.GDP_GAP_TUNES.items():
        dq.loc[pd.Period(per, "Q"), "L_GDP_GAP"] = val
    model = Model.from_files(cfg.MODEL_FILE, cfg.PARAMS_FILE, **getattr(cfg, "PARAM_OVERRIDES", {}))
    rngfilt = pd.period_range(cfg.FIRST_HIST, cfg.LAST_FORE, freq="Q")
    # domestic data after last_hist are dropped, foreign assumptions stay (as in the template)
    obs = dq.copy()
    obs.loc[obs.index > pd.Period(last_hist, "Q"), list(DOMESTIC_OBS)] = np.nan
    std = {}
    for shock, spec in cfg.STD_OVERRIDES.items():
        ser = pd.Series(spec.get("default", np.nan), index=rngfilt, dtype=float)
        for (a, b), v in spec.get("periods", {}).items():
            ser.loc[pd.Period(a, "Q"):pd.Period(b, "Q")] = v
        std[shock] = ser
    filt = kalman_smoother(model, obs, rngfilt, std)
    return dict(dq=dq, model=model, filt=filt, rngfilt=rngfilt, nowcast=nc, cfg=cfg,
                hist=pd.period_range(cfg.FIRST_HIST, last_hist, freq="Q"),
                rngfcast=pd.period_range(pd.Period(last_hist, "Q") + 1, cfg.LAST_FORE, freq="Q"))


def base_plan(ctx, judgments: bool = True, look_through: bool = False) -> Plan:
    """External sector fixed to the assumptions; CPI nowcast conditions; judgment shocks.

    look_through=True drops judgments marked first_round (administered prices, excises): the plan a central
    bank that ignores first-round effects of such price changes would optimise against."""
    cfg = ctx["cfg"]
    fc = ctx["rngfcast"]
    plan = Plan(fc)
    for var, shock in EXTERNAL:
        plan.exogenize(var, fc, ctx["filt"].vars[var].reindex(fc).values)
        plan.endogenize(shock, fc)
    if ctx.get("nowcast") is not None:
        for q in getattr(cfg, "CPI_NOWCAST_CONDITION", []):
            p = pd.Period(q, "Q")
            if p in fc and not pd.isna(ctx["dq"].loc[p, "L_CPI"]):
                plan.exogenize("l_cpi", [p], [ctx["dq"].loc[p, "L_CPI"]])
                plan.endogenize("res_dl_rnc", [p])   # near-term surprises are mostly non-core (food, fuel, tariffs)
    if judgments:
        fx = {pd.Period(k, "Q"): v for k, v in getattr(cfg, "FX_TARGET_PATH", {}).items() if pd.Period(k, "Q") in fc}
        if fx:
            plan.exogenize("dl_er_tar", list(fx), list(fx.values()))
            plan.endogenize("res_dl_er_tar", list(fx))
        for j in getattr(cfg, "JUDGMENTS", []):
            if look_through and j.get("first_round"):
                continue
            pers = [pd.Period(x, "Q") for x in j["periods"]]
            keep = [(p, v) for p, v in zip(pers, j["values"]) if p in fc]
            if keep:
                plan.shock(j["shock"], [p for p, _ in keep], [v for _, v in keep])
    return plan


def oil_dl_roil(ctx, brent_usd: dict) -> dict:
    """Real oil price changes (dl_roil, annualized %) implied by an alternative Brent path in USD per barrel."""
    dq = ctx["dq"]
    brent = dq["BRENT_USD"].copy()
    for q, v in brent_usd.items():
        brent[pd.Period(q, "Q")] = v
    l_roil = 100 * np.log(brent / dq["USD_EUR"]) - dq["L_CPI_EA"]
    dl = 4 * l_roil.diff()
    fc = ctx["rngfcast"]
    last = max(pd.Period(q, "Q") for q in brent_usd) + 1
    return {p: float(dl[p]) for p in fc if p <= last}


def with_rate_path(plan: Plan, path: dict | None) -> Plan:
    """Fix the policy rate (quarterly average) on the given quarters; the Taylor-rule shock adjusts."""
    plan = plan.copy()
    if path:
        pers = [pd.Period(k, "Q") for k in path]
        plan.exogenize("ir_pol", pers, list(path.values()))
        plan.endogenize("res_ir_tlr", pers)
    return plan


def policy_plan(ctx, plan: Plan, decision: dict, look_through_loss: bool = False) -> Plan:
    """The decision (and promised hold) on the first quarters, then the rate path that brings inflation back to the
    point target within the policy horizon (cfg.TARGET_PATH) — the way the NBU builds its baseline, instead of a
    mechanical Taylor rule. With look_through_loss the path is chosen ignoring first-round judgments."""
    from .optimal import optimal_path   # optimal imports this module
    cfg = ctx["cfg"]
    lt = base_plan(ctx, look_through=True) if look_through_loss else plan
    _, path, _ = optimal_path(ctx, lt, fixed=decision, **cfg.TARGET_PATH)
    return with_rate_path(plan, {str(p): float(v) for p, v in path.items()})


def scenario_plans(ctx) -> dict:
    """Baseline (recommended decision + target-consistent path) and the risk scenarios built on top of it.
    In scenarios only the October decision stays fixed; afterwards the rule reacts to the scenario shocks
    around the baseline path."""
    cfg = ctx["cfg"]
    f = ctx["rngfcast"][0]
    base_rec = policy_plan(ctx, base_plan(ctx), cfg.RECOMMENDED_RATE_PATH)
    around = rate_path_to_shock(ctx, nowcast_to_shock(ctx, base_rec), keep=[str(f)])
    return {name: base_rec if name == "Базовий" else fn(around.copy(), f, ctx) for name, fn in cfg.SCENARIOS.items()}


def rate_path_to_shock(ctx, plan: Plan, keep: list[str]) -> Plan:
    """Turn a fixed rate path (except `keep` quarters) into the Taylor-rule shocks it implies: the baseline stays the
    same, but in scenarios the rule can react to new shocks around the baseline path."""
    keep = {pd.Period(k, "Q") for k in keep}
    implied = run(ctx, plan).attrs["shocks"]
    out = plan.copy()
    for per in [p for p in out.exo.get("ir_pol", {}) if p not in keep]:
        out.exo["ir_pol"].pop(per)
        out.endo["res_ir_tlr"].discard(per)
        out.shocks.setdefault("res_ir_tlr", {})[per] = float(implied.loc[per, "res_ir_tlr"])  # total, not added
    out.exo = {k: v for k, v in out.exo.items() if v}
    out.endo = {k: v for k, v in out.endo.items() if v}
    return out


def nowcast_to_shock(ctx, plan: Plan) -> Plan:
    """Replace the CPI nowcast condition by the cost-push shock it implies in this plan, so that scenario
    shocks (oil, exchange rate, ...) can move CPI in the nowcast quarters instead of being absorbed."""
    cond = list(plan.exo.get("l_cpi", {}))
    if not cond:
        return plan
    implied = run(ctx, plan).attrs["shocks"]
    out = plan.copy()
    for per in cond:
        out.exo["l_cpi"].pop(per)
        out.endo["res_dl_rnc"].discard(per)
        out.shocks.setdefault("res_dl_rnc", {})[per] = float(implied.loc[per, "res_dl_rnc"])  # total, not added
    out.exo = {k: v for k, v in out.exo.items() if v}
    out.endo = {k: v for k, v in out.endo.items() if v}
    return out


def run(ctx, plan: Plan, model: Model | None = None) -> pd.DataFrame:
    """Forecast from the smoothed state at the last history quarter; returns history + forecast."""
    model = model or ctx["model"]
    last = ctx["rngfcast"][0] - 1
    s0 = ctx["filt"].state_at(last)
    fc, shocks = forecast(model, s0, plan)
    out = pd.concat([ctx["filt"].vars.loc[: last], fc])
    out = add_reporting(out)
    out.attrs["shocks"] = shocks
    return out


def add_reporting(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["gdp_yoy"] = df["l_gdp"].diff(4)
    df["core_yoy"] = df["d4l_cpi_c"]
    df["uah_eur"] = np.exp(df["l_er"] / 100)
    df["uah_eur_yoy"] = df["l_er"].diff(4)
    return df


LABELS = {"d4l_cpi": "ІСЦ, % р/р (сер. за кв.)", "d4l_cpi_c": "Базова інфляція, % р/р", "gdp_yoy": "ВВП, % р/р", "ir_pol": "Облікова ставка, % (сер. за кв.)",
          "uah_eur": "Курс, грн/€ (сер. за кв.)", "l_gdp_gap": "Розрив ВВП, %"}


def summary_table(results: dict[str, pd.DataFrame], periods) -> pd.DataFrame:
    """Key indicators by quarter for each scenario (rows = scenario/indicator, cols = quarter)."""
    rows = {}
    for name, df in results.items():
        for col, lab in LABELS.items():
            rows[(name, lab)] = df[col].reindex(periods)
    t = pd.DataFrame(rows).T
    t.columns = [str(p) for p in periods]
    return t.round(2)


def annual_table(df: pd.DataFrame, years=(2025, 2026, 2027, 2028, 2029)) -> pd.DataFrame:
    """Annual view comparable with NBU tables: CPI y/y in Q4, GDP growth (annual average), rate & FX in Q4."""
    out = {}
    for y in years:
        q4 = pd.Period(f"{y}Q4", "Q")
        lvl = df["l_gdp"]
        gdp = (np.exp(lvl.loc[f"{y}Q1":f"{y}Q4"] / 100).mean() / np.exp(lvl.loc[f"{y - 1}Q1":f"{y - 1}Q4"] / 100).mean() - 1) * 100
        out[y] = {"ІСЦ, % р/р (IV кв.)": df.loc[q4, "d4l_cpi"], "Базова інфляція, % р/р (IV кв.)": df.loc[q4, "d4l_cpi_c"],
                  "Реальний ВВП, % (рік)": gdp,
                  "Облікова ставка, % (IV кв.)": df.loc[q4, "ir_pol"], "Курс, грн/€ (IV кв.)": df.loc[q4, "uah_eur"]}
    return pd.DataFrame(out).round(1)


def rate_decomposition(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Contributions to the policy rate from the Taylor rule (alpha = 1):
    ir = 0.8*ir(-1) + 0.2*(rir_tnd + E pi(+1) + coef*(E pi(+3) - target) + 0.5*gap) + res."""
    rho, w = 0.8, 0.2
    out = pd.DataFrame(index=df.index)
    out["Попередня ставка"] = rho * df["ir_pol"].shift(1)
    out["Нейтральна реальна ставка"] = w * df["rir_tnd"]
    out["Очікувана інфляція"] = w * df["d4l_cpi"].shift(-1)
    out["Відхилення інфляції від цілі"] = w * params["coef"] * (df["d4l_cpi"].shift(-3) - params["dl_cpi_tar"])
    out["Розрив ВВП"] = w * 0.5 * df["l_gdp_gap"]
    out["Залишок"] = df["ir_pol"] - out.sum(axis=1)
    return out


def rate_gap_decomposition(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Where the rule pushes the rate: target-consistent level minus neutral nominal rate, split by driver.
    Neutral nominal = rir_tnd + target; deviation = (E pi(+1) - target) + coef*(E pi(+3) - target) + 0.5*gap."""
    tar = params["dl_cpi_tar"]
    out = pd.DataFrame(index=df.index)
    out["Очікувана інфляція вище цілі"] = df["d4l_cpi"].shift(-1) - tar
    out["Відхилення прогнозу інфляції (t+3)"] = params["coef"] * (df["d4l_cpi"].shift(-3) - tar)
    out["Розрив ВВП"] = 0.5 * df["l_gdp_gap"]
    out["Нейтральна номінальна ставка"] = df["rir_tnd"] + tar
    return out
