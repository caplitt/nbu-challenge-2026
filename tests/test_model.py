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
    # w_oil = 0 switches off the team's energy channel: the model then reduces exactly to the NBU template
    r = irf(model.with_params(beta=beta, w_oil=0), "res_ir_tlr", 1, 20)
    assert r["l_gdp_gap"].min() == pytest.approx(gap_min, abs=2e-3)
    assert r["d4l_cpi"].min() == pytest.approx(cpi_min, abs=2e-3)
    assert r["l_er"].iloc[1] == pytest.approx(er_t1, abs=2e-3)


def test_filter_reproduces_observables(ctx):
    v, dq = ctx["filt"].vars, ctx["dq"]
    hist = pd.period_range("2016Q1", "2026Q2", freq="Q")
    for obs, var in (("L_GDP", "l_gdp"), ("L_CPI", "l_cpi"), ("L_CPI_C", "l_cpi_c"), ("IR_POLICY", "ir_pol"),
                     ("L_ER", "l_er")):
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


def test_scenario_shocks_add_to_judgments(ctx):
    """Scenarios go on top of the baseline: a scenario shock adds to a judgment in the same quarter."""
    plan = pipeline.base_plan(ctx)
    q = pd.Period("2027Q1")
    before = plan.shocks["res_l_gdp_gap"][q]
    plan.shock("res_l_gdp_gap", [q], [-0.5])
    assert plan.shocks["res_l_gdp_gap"][q] == pytest.approx(before - 0.5)


def test_look_through_drops_first_round_judgments(ctx):
    first_round = {j["shock"] for j in cfg.JUDGMENTS if j.get("first_round")}
    assert first_round, "expected a first-round (administered prices) judgment"
    lt = pipeline.base_plan(ctx, look_through=True)
    for s in first_round:
        assert not any(p.year >= 2027 for p in lt.shocks.get(s, {}))


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
    from decimal import ROUND_HALF_UP, Decimal
    fmt = [f"{Decimal(str(q[p]['d4l_cpi'])).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):f}".replace(".", ",")
           for p in ("2026Q4", "2027Q4", "2028Q4")]
    assert cpi_row[1:] == fmt
    assert summary["cards"][0]["value"].startswith(f"{key['recommendation']['rate']:.1f}".replace(".", ","))
    assert key["baseline_quarterly"]["2026Q4"]["ir_pol"] == pytest.approx(key["recommendation"]["rate"], abs=1e-6)


def test_matches_matlab_iris_if_available():
    """Python port vs the original NBU template run in MATLAB/IRIS (matlab/run_check.m)."""
    out = ROOT / "matlab" / "outputs" / "forecast1_matlab.csv"
    if not out.exists():
        pytest.skip("немає результатів MATLAB (див. matlab/run_check.m)")
    from qpm.data import read_iris_csv
    ml, _ = read_iris_csv(out)
    py = pd.read_csv(ROOT / "matlab" / "inputs" / "forecast1_python.csv", index_col=0)
    py.index = pd.PeriodIndex(py.index, freq="Q")
    for v in ("d4l_cpi", "ir_pol", "l_er", "l_gdp_gap"):
        d = (py[v] - ml[v]).loc["2026Q4":"2028Q4"].abs().max()
        assert d < 1e-4, v


def test_oil_channel_has_no_spurious_reversal(model):
    """+20% real oil: headline inflation rises ≈0.3 pp and the price level stays higher (no RER artefact)."""
    shock = np.log(1.2) * 100 * 4 * (1 - 0.3)
    r = irf(model, "res_dl_roil", shock, 16)
    assert 0.25 < r["d4l_cpi"].max() < 0.45
    assert r["d4l_cpi"].min() > -0.15
    assert r["l_cpi"].iloc[-1] > 0.15
