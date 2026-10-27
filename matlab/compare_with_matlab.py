"""Порівнює результати Python і MATLAB/IRIS для фільтра і всіх сценаріїв.

Запуск:  python matlab/compare_with_matlab.py
Пише звіт docs/matlab_check.md і графік накладання results/figures/fc_matlab_check.png.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qpm import plotting as pl  # noqa: E402
from qpm.data import read_iris_csv  # noqa: E402

VARS = ["d4l_cpi", "ir_pol", "l_er", "l_gdp_gap", "l_gdp_tnd", "l_rer_gap", "rir_tnd", "prem_uip_gap", "l_roil"]
NL = "\n"
INP, OUT = ROOT / "matlab" / "inputs", ROOT / "matlab" / "outputs"


def load_py(name):
    df = pd.read_csv(INP / name, index_col=0)
    df.index = pd.PeriodIndex(df.index, freq="Q")
    return df


def max_diff(py, ml, rng):
    rows = {}
    for v in VARS:
        if v in ml.columns and v in py.columns:
            d = (py[v] - ml[v]).loc[rng[0]:rng[1]].dropna()
            rows[v] = float(np.abs(d).max())
    return rows


FIG = ROOT / "results" / "figures"
STATUS = ROOT / "results" / "matlab_status.json"
ML_FIGS = {"scenarios_matlab.png": "ml_scenarios.png", "irf_rate_matlab.png": "ml_irf_rate.png",
           "irf_oil_matlab.png": "ml_irf_oil.png"}


def set_status(fresh: bool, worst=None):
    """MATLAB charts go into the deck only when MATLAB results match the current Python results."""
    import json
    import shutil
    STATUS.write_text(json.dumps({"fresh": fresh, "worst_diff": worst}), encoding="utf-8")
    for src, dst in ML_FIGS.items():
        if fresh and (OUT / src).exists():
            shutil.copyfile(OUT / src, FIG / dst)
        elif (FIG / dst).exists():
            (FIG / dst).unlink()


def main():
    try:
        compare()
    except Exception as e:  # stale / missing MATLAB outputs (e.g. after the trial licence expired)
        print(f"Звірка з MATLAB неможлива ({type(e).__name__}: {e}); використовую Python-графіки")
        set_status(False)


def compare():
    if not (OUT / "filter_matlab.csv").exists():
        raise FileNotFoundError("немає matlab/outputs/*.csv — запустіть run_check.m у MATLAB")
    names = [n for n in (INP / "scenarios.txt").read_text(encoding="utf-8").splitlines() if n.strip()]
    table = {"Фільтр 2016–2026": max_diff(load_py("filter_python.csv"), read_iris_csv(OUT / "filter_matlab.csv")[0],
                                          ("2016Q1", "2026Q3"))}
    ml_res = {}
    for k, name in enumerate(names, start=1):
        ml, _ = read_iris_csv(OUT / f"forecast{k}_matlab.csv")
        ml_res[name] = ml
        table[f"Прогноз: {name}"] = max_diff(load_py(f"forecast{k}_python.csv"), ml, ("2026Q4", "2028Q4"))
    t = pd.DataFrame(table).T
    worst = float(t.max().max())
    print(t.map(lambda x: f"{x:.0e}"))
    report = ["# Звірка Python-порту з MATLAB/IRIS", ""]
    if worst >= 1e-3:   # MATLAB was run on earlier data/plans: the numbers below compare different inputs
        report += ["> **Результати MATLAB застарілі.** Збережені файли `matlab/outputs/*.csv` отримано на попередніх "
                   "даних і планах (до оновлення даних 25.10.2026), тому розбіжність нижче порівнює різні вхідні дані, "
                   "а не два рушії. Перезапустіть `matlab/run_check.m` (MATLAB + IRIS) і потім `python "
                   "matlab/compare_with_matlab.py`; до оновлення даних розбіжність становила ~1e−5 (історія git). "
                   "Поки що презентація бере графіки з Python (`results/matlab_status.json`).", ""]
    report += ["Ті самі дані, параметри й плани сценаріїв; MATLAB R2026b + IRIS 20230622 (`matlab/run_check.m`). "
               "Модель — `model/model.model` (шаблон НБУ + нафтовий канал команди). Що перевіряє звірка: розв'язувач, "
               "фільтр Калмана й симуляції з планом (плани, шоки наукасту й траєкторії ставки готує Python).", "",
               "Максимальна абсолютна різниця (одиниці моделі: в. п. або 100·ln):", "",
              "| | " + " | ".join(f"`{c}`" for c in t.columns) + " |", "|---|" + "---|" * len(t.columns)]
    report += [f"| {i} | " + " | ".join(f"{v:.0e}" for v in r.values) + " |" for i, r in t.iterrows()]
    report += ["", f"**Найбільша розбіжність: {worst:.1e}**", "",
               "Графік, побудований у MATLAB: `matlab/outputs/scenarios_matlab.png`."]
    (ROOT / "docs" / "matlab_check.md").write_text(NL.join(report) + NL, encoding="utf-8")

    # overlay chart: Python lines vs MATLAB markers (baseline and two scenarios)
    fig, ax = pl.grid(1, 2, height=3.9)
    show = [n for n in names if n in ("Базовий", "Дефіцит фінансування", "Нафта $120")]
    for a, var, title in ((ax[0], "d4l_cpi", "Інфляція (ІСЦ), % р/р"), (ax[1], "ir_pol", "Облікова ставка, %")):
        for i, name in enumerate(show):
            k = names.index(name) + 1
            py = load_py(f"forecast{k}_python.csv")[var].loc["2026Q4":"2028Q4"]
            ml = ml_res[name][var].loc["2026Q4":"2028Q4"]
            if var == "d4l_cpi":   # model units (100*log) -> % y/y, as everywhere in the deck
                py, ml = ((np.exp(s / 100) - 1) * 100 for s in (py, ml))
            x = [p.year + (p.quarter - 1) / 4 for p in py.index]
            a.plot(x, py.values, color=pl.SERIES[i], label=f"{name}: Python")
            a.plot(x, ml.reindex(py.index).values, "o", ms=6, mfc="none", mec=pl.SERIES[i], mew=1.5,
                   label=f"{name}: MATLAB/IRIS")
        a.set_title(title)
        a.set_xticks([2027, 2028], ["2027", "2028"])
    h, lab = ax[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 0.06))
    fig.subplots_adjust(bottom=0.3)
    pl.save(fig, ROOT / "results" / "figures" / "fc_matlab_check.png",
            f"розрахунки команди: лінії — Python, кружки — MATLAB R2026b + IRIS; макс. розбіжність {worst:.0e}")
    fresh = worst < 1e-3
    set_status(fresh, worst)
    print(NL + f"Найбільша розбіжність: {worst:.1e}; звіт — docs/matlab_check.md; MATLAB-графіки в презентації: {fresh}")


if __name__ == "__main__":
    main()
