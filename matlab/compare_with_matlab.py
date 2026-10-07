"""Порівнює результати Python і MATLAB/IRIS: python matlab/compare_with_matlab.py

Пише звіт у docs/matlab_check.md.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qpm.data import read_iris_csv  # noqa: E402

VARS = ["d4l_cpi", "ir_pol", "l_er", "l_gdp_gap", "l_gdp_tnd", "l_rer_gap", "rir_tnd", "prem_uip_gap"]
NL = "\n"


def load_py(name):
    df = pd.read_csv(ROOT / "matlab" / "inputs" / name, index_col=0)
    df.index = pd.PeriodIndex(df.index, freq="Q")
    return df


def main():
    out = ROOT / "matlab" / "outputs"
    if not (out / "filter_matlab.csv").exists():
        sys.exit("Немає matlab/outputs/*.csv — спершу запустіть run_check.m у MATLAB")
    report = ["# Звірка Python-порту з MATLAB/IRIS", "",
              "Ті самі дані, параметри й план прогнозу; MATLAB R2026b + IRIS 20230622 (`matlab/run_check.m`).", ""]
    worst = 0.0
    for kind, py_name, ml_name, rng in (("Фільтр", "filter_python.csv", "filter_matlab.csv", ("2016Q1", "2026Q3")),
                                         ("Прогноз", "forecast_python.csv", "forecast_matlab.csv", ("2026Q4", "2028Q4"))):
        py = load_py(py_name)
        ml, _ = read_iris_csv(out / ml_name)
        rows = {}
        for v in VARS:
            if v in ml.columns and v in py.columns:
                d = (py[v] - ml[v]).loc[rng[0]:rng[1]].dropna()
                rows[v] = {"макс. |різниця|": f"{np.abs(d).max():.1e}", "кварталів": len(d)}
                worst = max(worst, float(np.abs(d).max()))
        print(NL + f"== {kind} ({rng[0]}–{rng[1]})")
        print(pd.DataFrame(rows).T)
        report += [f"## {kind} ({rng[0]}–{rng[1]})", "", "| Змінна | Макс. абсолютна різниця | Кварталів |",
                   "|---|---|---|"]
        report += [f"| `{v}` | {r['макс. |різниця|']} | {r['кварталів']} |" for v, r in rows.items()]
        report.append("")
    report.append(f"**Найбільша розбіжність: {worst:.1e}** (одиниці моделі: в. п. або 100·ln).")
    (ROOT / "docs" / "matlab_check.md").write_text(NL.join(report) + NL, encoding="utf-8")
    print(NL + f"Найбільша розбіжність: {worst:.1e}; звіт — docs/matlab_check.md")


if __name__ == "__main__":
    main()
