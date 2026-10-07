"""End-to-end steps shared by the run_* scripts (a01 -> a03 -> a04 in the MATLAB template)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import read_data
from .kalman import kalman_smoother
from .model import Model
from .nowcast import as_dict, cpi_nowcast
from .simulate import Plan, forecast

EXTERNAL = [("ir_ea", "res_ir_ea"), ("l_gdp_ea_gap", "res_l_gdp_ea_gap"), ("dl_cpi_ea", "res_dl_cpi_ea")]
DOMESTIC_OBS = ("L_GDP", "L_CPI", "IR_POLICY", "L_ER")


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


def base_plan(ctx, judgments: bool = True) -> Plan:
    """External sector fixed to the assumptions; CPI nowcast conditions; judgment shocks."""
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
                plan.endogenize("res_dl_cpi", [p])
    if judgments:
        for j in getattr(cfg, "JUDGMENTS", []):
            pers = [pd.Period(x, "Q") for x in j["periods"]]
            keep = [(p, v) for p, v in zip(pers, j["values"]) if p in fc]
            if keep:
                plan.shock(j["shock"], [p for p, _ in keep], [v for _, v in keep])
    return plan


def with_rate_path(plan: Plan, path: dict | None) -> Plan:
    """Fix the policy rate (quarterly average) on the given quarters; the Taylor-rule shock adjusts."""
    plan = plan.copy()
    if path:
        pers = [pd.Period(k, "Q") for k in path]
        plan.exogenize("ir_pol", pers, list(path.values()))
        plan.endogenize("res_ir_tlr", pers)
    return plan


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
    df["uah_eur"] = np.exp(df["l_er"] / 100)
    df["uah_eur_yoy"] = df["l_er"].diff(4)
    return df


LABELS = {"d4l_cpi": "ІСЦ, % р/р (сер. за кв.)", "gdp_yoy": "ВВП, % р/р", "ir_pol": "Облікова ставка, % (сер. за кв.)",
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


def annual_table(df: pd.DataFrame, years=(2025, 2026, 2027, 2028)) -> pd.DataFrame:
    """Annual view comparable with NBU tables: CPI y/y in Q4, GDP growth (annual average), rate & FX in Q4."""
    out = {}
    for y in years:
        q4 = pd.Period(f"{y}Q4", "Q")
        lvl = df["l_gdp"]
        gdp = (np.exp(lvl.loc[f"{y}Q1":f"{y}Q4"] / 100).mean() / np.exp(lvl.loc[f"{y - 1}Q1":f"{y - 1}Q4"] / 100).mean() - 1) * 100
        out[y] = {"ІСЦ, % р/р (IV кв.)": df.loc[q4, "d4l_cpi"], "Реальний ВВП, % (рік)": gdp,
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
