"""End-to-end steps shared by the run_* scripts (a01 -> a03 -> a04 in the MATLAB template)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import read_data
from .kalman import kalman_smoother
from .model import Model
from .simulate import Plan, forecast

EXTERNAL = [("ir_ea", "res_ir_ea"), ("l_gdp_ea_gap", "res_l_gdp_ea_gap"), ("dl_cpi_ea", "res_dl_cpi_ea")]


def prepare(cfg):
    """Read data, add tunes, build model, run the Kalman smoother."""
    dq = read_data(cfg.DATA_DIR)
    dq["L_GDP_GAP"] = np.nan
    for per, val in cfg.GDP_GAP_TUNES.items():
        dq.loc[pd.Period(per, "Q"), "L_GDP_GAP"] = val
    model = Model.from_files(cfg.MODEL_FILE, cfg.PARAMS_FILE, **getattr(cfg, "PARAM_OVERRIDES", {}))
    rngfilt = pd.period_range(cfg.FIRST_HIST, cfg.LAST_FORE, freq="Q")
    hist = pd.period_range(cfg.FIRST_HIST, cfg.LAST_HIST, freq="Q")
    # domestic data after LAST_HIST are dropped, foreign assumptions stay (as in the template)
    obs = dq.copy()
    after = obs.index > pd.Period(cfg.LAST_HIST, "Q")
    for col in ("L_GDP", "L_CPI", "IR_POLICY", "L_ER"):
        obs.loc[after, col] = np.nan
    std = {}
    for shock, spec in cfg.STD_OVERRIDES.items():
        ser = pd.Series(spec.get("default", np.nan), index=rngfilt, dtype=float)
        for (a, b), v in spec.get("periods", {}).items():
            ser.loc[pd.Period(a, "Q"):pd.Period(b, "Q")] = v
        std[shock] = ser
    filt = kalman_smoother(model, obs, rngfilt, std)
    return dict(dq=dq, model=model, filt=filt, rngfilt=rngfilt, hist=hist,
                rngfcast=pd.period_range(pd.Period(cfg.LAST_HIST, "Q") + 1, cfg.LAST_FORE, freq="Q"))


def base_plan(ctx) -> Plan:
    """External sector fixed to the assumptions (filtered values on the forecast horizon)."""
    plan = Plan(ctx["rngfcast"])
    for var, shock in EXTERNAL:
        plan.exogenize(var, ctx["rngfcast"], ctx["filt"].vars[var].reindex(ctx["rngfcast"]).values)
        plan.endogenize(shock, ctx["rngfcast"])
    return plan


def run(ctx, plan: Plan, model: Model | None = None) -> pd.DataFrame:
    """Forecast from the smoothed state at LAST_HIST; returns history + forecast for all variables."""
    model = model or ctx["model"]
    last = ctx["rngfcast"][0] - 1
    s0 = ctx["filt"].state_at(last)
    fc, shocks = forecast(model, s0, plan)
    hist = ctx["filt"].vars.loc[: last]
    out = pd.concat([hist, fc])
    out.attrs["shocks"] = shocks
    return add_reporting(out)


def add_reporting(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["gdp_yoy"] = df["l_gdp"].diff(4)
    df["uah_eur"] = np.exp(df["l_er"] / 100)
    df["uah_eur_yoy"] = df["l_er"].diff(4)
    return df


def summary_table(results: dict[str, pd.DataFrame], periods) -> pd.DataFrame:
    """Key indicators by quarter for each scenario (rows = scenario/indicator, cols = quarter)."""
    rows = {}
    labels = {"d4l_cpi": "ІСЦ, % р/р", "gdp_yoy": "ВВП, % р/р", "ir_pol": "Облікова ставка, %",
              "uah_eur": "Курс, грн/€", "l_gdp_gap": "Розрив ВВП, %"}
    for name, df in results.items():
        for col, lab in labels.items():
            rows[(name, lab)] = df[col].reindex(periods)
    t = pd.DataFrame(rows).T
    t.columns = [str(p) for p in periods]
    return t.round(2)


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
