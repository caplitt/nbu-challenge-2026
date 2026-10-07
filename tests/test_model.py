"""Перевірки коректності: python -m pytest -q"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import config as cfg
from qpm import pipeline
from qpm.model import Model
from qpm.simulate import Plan, forecast, irf

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def model():
    return Model.from_files(ROOT / "model/model.model", ROOT / "model/params.yaml")


@pytest.fixture(scope="module")
def ctx():
    return pipeline.prepare(cfg)


def test_solution_satisfies_equations(model):
    """The RE solution must satisfy every model equation on a path with anticipated shocks."""
    for beta in (0.0, 0.7, 1.0):
        assert model.with_params(beta=beta).check() < 1e-9


def test_blanchard_kahn(model):
    assert model.sol["eu"] == (True, True)
    assert np.abs(np.linalg.eigvals(model.T)).max() < 1 + 1e-6


@pytest.mark.parametrize("beta, gap_min, cpi_min, er_t1", [
    (0.0, -0.342, -0.512, -0.766),   # numbers from the MATLAB/IRIS run of the NBU template (KNU 2025, appendix 4)
    (0.8, -0.201, -0.235, -0.069),
])
def test_irf_matches_matlab(model, beta, gap_min, cpi_min, er_t1):
    r = irf(model.with_params(beta=beta), "res_ir_tlr", 1, 20)
    assert r["l_gdp_gap"].min() == pytest.approx(gap_min, abs=2e-3)
    assert r["d4l_cpi"].min() == pytest.approx(cpi_min, abs=2e-3)
    assert r["l_er"].iloc[1] == pytest.approx(er_t1, abs=2e-3)


def test_filter_reproduces_observables(ctx):
    v, dq = ctx["filt"].vars, ctx["dq"]
    hist = pd.period_range("2016Q1", "2026Q2", freq="Q")
    for obs, var in (("L_GDP", "l_gdp"), ("L_CPI", "l_cpi"), ("IR_POLICY", "ir_pol"), ("L_ER", "l_er")):
        diff = (dq[obs].reindex(hist) - v[var].reindex(hist)).abs().max()
        assert diff < 1e-5, obs


def test_plan_hits_exogenized_values(ctx):
    plan = pipeline.base_plan(ctx)
    plan = pipeline.with_rate_path(plan, {"2026Q4": 17.25, "2027Q1": 17.0})
    out = pipeline.run(ctx, plan)
    assert out.loc[pd.Period("2026Q4"), "ir_pol"] == pytest.approx(17.25, abs=1e-8)
    assert out.loc[pd.Period("2027Q1"), "ir_pol"] == pytest.approx(17.0, abs=1e-8)


def test_plan_requires_balance(model):
    per = pd.period_range("2027Q1", periods=4, freq="Q")
    plan = Plan(per).exogenize("ir_pol", per[:2], 15)
    with pytest.raises(ValueError):
        forecast(model, np.zeros(model.n_states), plan)


def test_cpi_nowcast_condition_respected(ctx):
    out = pipeline.run(ctx, pipeline.base_plan(ctx))
    q4 = pd.Period("2026Q4")
    assert out.loc[q4, "l_cpi"] == pytest.approx(ctx["dq"].loc[q4, "L_CPI"], abs=1e-8)


def test_deck_numbers_come_from_model():
    """Every forecast number on the summary slide equals results/key_numbers.json (no hand-typed numbers)."""
    key = json.loads((ROOT / "results/key_numbers.json").read_text(encoding="utf-8"))
    deck = json.loads((ROOT / "deck/deck_data.json").read_text(encoding="utf-8"))
    summary = next(s for s in deck["slides"] if s["type"] == "summary")
    q = key["baseline_quarterly"]
    cpi_row = summary["table"]["rows"][0]
    assert cpi_row[1:] == [f"{q[p]['d4l_cpi']:.1f}".replace(".", ",") for p in ("2026Q4", "2027Q4", "2028Q4")]
    assert summary["cards"][0]["value"].startswith(f"{key['recommendation']['rate']:.1f}".replace(".", ","))
    assert key["baseline_quarterly"]["2026Q4"]["ir_pol"] == pytest.approx(key["recommendation"]["rate"], abs=1e-6)


def test_matches_matlab_iris_if_available():
    """Python port vs the original NBU template run in MATLAB/IRIS (matlab/run_check.m)."""
    out = ROOT / "matlab" / "outputs" / "forecast_matlab.csv"
    if not out.exists():
        pytest.skip("немає результатів MATLAB (див. matlab/run_check.m)")
    from qpm.data import read_iris_csv
    ml, _ = read_iris_csv(out)
    py = pd.read_csv(ROOT / "matlab" / "inputs" / "forecast_python.csv", index_col=0)
    py.index = pd.PeriodIndex(py.index, freq="Q")
    for v in ("d4l_cpi", "ir_pol", "l_er", "l_gdp_gap"):
        d = (py[v] - ml[v]).loc["2026Q4":"2028Q4"].abs().max()
        assert d < 1e-4, v
