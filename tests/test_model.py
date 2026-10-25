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
    before = plan.shocks["res_dl_cpi_c"][q]          # cost-push judgment in 2027Q1
    plan.shock("res_dl_cpi_c", [q], [1.0])
    assert plan.shocks["res_dl_cpi_c"][q] == pytest.approx(before + 1.0)


def test_look_through_drops_first_round_judgments(ctx):
    first_round = {j["shock"] for j in cfg.JUDGMENTS if j.get("first_round")}
    assert first_round, "expected a first-round (administered prices) judgment"
    lt = pipeline.base_plan(ctx, look_through=True)
    for s in first_round:
        assert not any(p.year >= 2027 for p in lt.shocks.get(s, {}))


def test_baseline_returns_to_point_target_within_horizon():
    """NBU: 5% point target (no tolerance band) within a policy horizon of up to three years."""
    key = json.loads((ROOT / "results/key_numbers.json").read_text(encoding="utf-8"))
    q = key["baseline_quarterly"]
    last_year = [q[f"{cfg.LAST_FORE[:4]}Q{i}"]["cpi_yoy"] for i in range(1, 5)]
    assert sum(last_year) / 4 == pytest.approx(5.0, abs=0.1)          # on target on average in the last year
    assert all(abs(x - 5.0) <= 0.3 for x in last_year)                 # and close to it in every quarter (smoothing)
    for per, rate in cfg.RECOMMENDED_RATE_PATH.items():       # the decision and the promised hold are kept
        assert q[per]["ir_pol"] == pytest.approx(rate, abs=1e-6)


def test_reported_inflation_is_percent_and_matches_data(ctx):
    """Reports show ordinary % y/y (the model works in 100*log differences); the target 100*ln(1.05) is exactly 5%.
    The model's quarterly CPI y/y must match the Derzhstat monthly index averaged by quarter (up to seasonal adjustment)."""
    assert pipeline.pct(ctx["model"].params["dl_cpi_tar"]) == pytest.approx(5.0, abs=1e-3)
    rep = pipeline.add_reporting(ctx["filt"].vars)
    m = pd.read_csv(ROOT / "data/overview/cpi.csv", index_col=0, encoding="utf-8-sig")["cpi_mom"].dropna()
    m.index = pd.PeriodIndex(m.index, freq="M")
    lvl = (1 + m / 100).cumprod()
    qa = lvl.groupby(lvl.index.asfreq("Q")).mean()
    yoy = (qa / qa.shift(4) - 1) * 100
    for p in pd.period_range("2024Q1", cfg.LAST_HIST, freq="Q"):
        assert rep.loc[p, "cpi_yoy"] == pytest.approx(yoy[p], abs=0.5), p


def test_cpi_nowcast_condition_respected(ctx):
    """Both headline and core CPI are pinned to their nowcasts in 2026Q4."""
    out = pipeline.run(ctx, pipeline.base_plan(ctx))
    q4 = pd.Period("2026Q4")
    assert out.loc[q4, "l_cpi"] == pytest.approx(ctx["dq"].loc[q4, "L_CPI"], abs=1e-8)
    assert out.loc[q4, "l_cpi_c"] == pytest.approx(ctx["dq"].loc[q4, "L_CPI_C"], abs=1e-8)


def test_deck_numbers_come_from_model():
    """Every forecast number on the summary slide equals results/key_numbers.json (no hand-typed numbers)."""
    key = json.loads((ROOT / "results/key_numbers.json").read_text(encoding="utf-8"))
    deck = json.loads((ROOT / "deck/deck_data.json").read_text(encoding="utf-8"))
    summary = next(s for s in deck["slides"] if s["type"] == "summary")
    q = key["baseline_quarterly"]
    cpi_row = summary["table"]["rows"][0]
    from decimal import ROUND_HALF_UP, Decimal
    fmt = [f"{Decimal(str(q[p]['cpi_yoy'])).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):f}".replace(".", ",")
           for p in ("2026Q4", "2027Q4", "2028Q4", "2029Q4")]
    assert cpi_row[1:] == fmt
    card_rate = float(summary["cards"][0]["value"].rstrip("%").replace(",", "."))
    assert card_rate == pytest.approx(key["recommendation"]["rate"])
    assert key["baseline_quarterly"]["2026Q4"]["ir_pol"] == pytest.approx(key["recommendation"]["rate"], abs=1e-6)


def test_matches_matlab_iris_if_available():
    """Python engine vs MATLAB/IRIS on the SAME extended model, data and baseline plan (matlab/run_check.m):
    checks the solver, filter and plan simulation, not the economics of the extension. Skipped when the saved MATLAB
    run is stale (results/matlab_status.json: fresh = false after data or code changes until run_check.m is rerun)."""
    out = ROOT / "matlab" / "outputs" / "forecast1_matlab.csv"
    status = ROOT / "results" / "matlab_status.json"
    if not out.exists():
        pytest.skip("немає результатів MATLAB (див. matlab/run_check.m)")
    if status.exists() and not json.loads(status.read_text(encoding="utf-8")).get("fresh", False):
        pytest.skip("результати MATLAB застарілі — перезапустіть matlab/run_check.m")
    from qpm.data import read_iris_csv
    ml, _ = read_iris_csv(out)
    py = pd.read_csv(ROOT / "matlab" / "inputs" / "forecast1_python.csv", index_col=0)
    py.index = pd.PeriodIndex(py.index, freq="Q")
    for v in ("d4l_cpi", "ir_pol", "l_er", "l_gdp_gap"):
        d = (py[v] - ml[v]).loc["2026Q4":cfg.LAST_FORE].abs().max()
        assert d < 1e-4, v


def test_oil_channel_has_no_spurious_reversal(model):
    """+20% real oil: headline inflation rises ≈0.3 pp and the price level stays higher (no RER artefact)."""
    shock = np.log(1.2) * 100 * 4 * (1 - 0.3)
    r = irf(model, "res_dl_roil", shock, 16)
    assert 0.25 < r["d4l_cpi"].max() < 0.45
    assert r["d4l_cpi"].min() > -0.15
    assert r["l_cpi"].iloc[-1] > 0.15


# ----------------------------------------------------------------------------------------------- audit 25.10.2026
def _monthly():
    from qpm.data import read_iris_csv
    dm, _ = read_iris_csv(ROOT / "data/monthly.csv")
    return dm


def test_core_cpi_chain_matches_official_annual():
    """The NBU core-CPI file has three months with a wrong sign (update_data.CORE_CPI_FIXES); with the fix the
    December/December chain of monthly rates reproduces Derzhstat's annual core inflation."""
    core = _monthly()["D_CPI_C_su_m"]
    for year, official in ((2016, 5.8), (2019, 3.9), (2021, 7.9), (2024, 10.7)):
        chain = ((1 + core.loc[f"{year}-01":f"{year}-12"] / 100).prod() - 1) * 100
        assert chain == pytest.approx(official, abs=0.15), year


def test_brent_history_is_spot_only():
    """Model data use the EIA spot price for every historical month (no front-month futures spliced in), and the
    quarterly average in foreign.csv is the mean of those months."""
    raw = pd.read_csv(ROOT / "data/raw/brent_monthly.csv", index_col=0)
    raw.index = pd.PeriodIndex(raw.index, freq="M")
    assert raw["source"].str.startswith("EIA spot").all()
    from qpm.data import read_iris_csv
    dx, _ = read_iris_csv(ROOT / "data/foreign.csv")
    q3 = raw.loc["2026-07":"2026-09", "brent_usd"].mean()
    assert dx.loc[pd.Period("2026Q3"), "BRENT_USD"] == pytest.approx(q3, abs=0.01)
    assert raw.loc[pd.Period("2026-09", "M"), "brent_usd"] > 105   # spot, not the $102 front-month contract


def test_seasonal_window_does_not_let_one_month_write_its_own_factor():
    """September 2026 (+2.1% m/m) must get a seasonal factor like the other Septembers in the same STL run: with the
    chosen window the gap to the 2021–2025 mean is < 0.1 pp (with the statsmodels default 7 it was ≈0.5 pp)."""
    from statsmodels.tsa.seasonal import STL
    from qpm.data import SEASONAL_WINDOW
    x = _monthly()["D_CPI_su_m"].dropna().loc["2010-01":]
    lvl = np.log((1 + x / 100).cumprod())
    res = STL(lvl.values, period=12, seasonal=SEASONAL_WINDOW[12], robust=False).fit()
    s = pd.Series(res.seasonal, index=lvl.index).diff() * 100
    sept = s[s.index.month == 9]
    assert abs(float(sept.loc["2026-09"]) - float(sept.loc["2021-09":"2025-09"].mean())) < 0.1


def test_fx_nowcast_condition_respected(ctx):
    """The baseline's current-quarter UAH/EUR equals the nowcast built from the daily official rate."""
    from qpm.nowcast import fx_nowcast
    out = pipeline.run(ctx, pipeline.base_plan(ctx))
    for q in cfg.FX_NOWCAST:
        level = fx_nowcast(q, data_dir=cfg.DATA_DIR)["level"]
        assert out.loc[pd.Period(q, "Q"), "l_er"] == pytest.approx(100 * np.log(level), abs=1e-8)
        assert out.loc[pd.Period(q, "Q"), "uah_eur"] == pytest.approx(level, rel=1e-6)


def test_robustness_and_options_use_the_same_shocks():
    """The baseline row of the robustness table must equal the loss in the options table for every option: both are
    computed with one set of nowcast-implied shocks (before 25.10.2026 the robustness loop re-implied the shock per
    option and penalised the higher rates)."""
    key = json.loads((ROOT / "results/key_numbers.json").read_text(encoding="utf-8"))
    base_row = key["robust"]["losses"]["λ = 1"]["Базовий"]
    for name, row in key["policy_options"].items():
        rate = str(float(row["Ставка IV кв. 2026"]))
        if rate in base_row and name != "Оптимальна (мін. втрат)":
            assert base_row[rate] == pytest.approx(row["Втрати, λ = 1"], abs=0.05), name


def test_backtest_scores_only_observed_quarters():
    """'Actual' in the backtest comes from published data only: from the 2025Q4 origin the 4th horizon (2026Q4) has
    no data yet and must not be scored; GDP has one quarter less than CPI (2026Q3 is a nowcast)."""
    err = pd.read_csv(ROOT / "results/tables/backtest_errors.csv", index_col=[0, 1], encoding="utf-8-sig")
    n = err["Кварталів з фактом"]
    assert n.loc[("2025Q4", "ІСЦ, % р/р")] == 3
    assert n.loc[("2025Q3", "ІСЦ, % р/р")] == 4
    assert n.loc[("2025Q4", "ВВП, % р/р")] == 2
    assert (n <= 4).all()
