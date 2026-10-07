"""Функції відгуку на шоки для кількох значень параметра (b02_irfs.m з шаблону НБУ).

Запуск:  python run_irfs.py            # β = 0; 0,7; 1 (контроль НБУ над курсом)
         python run_irfs.py alpha      # α = 0; 0,6; 1 (правило Тейлора vs UIP)
Результати: results/figures/irf_<шок>_<параметр>.png
"""
import sys
from pathlib import Path

import config as cfg
from qpm import plotting as pl
from qpm.model import Model
from qpm.simulate import irf

SHOCKS = {"res_dl_cpi": "Шок витрат (інфляції)", "res_l_gdp_gap": "Шок попиту",
          "res_ir_tlr": "Шок облікової ставки", "res_prem_uip_gap": "Шок премії за ризик"}
RESPONSES = {"l_gdp_gap": "Розрив ВВП", "d4l_cpi": "ІСЦ, р/р", "ir_pol": "Облікова ставка",
             "l_er": "Курс грн/€ (рівень)", "l_rer_gap": "Розрив реального курсу", "rir_pol_gap": "Розрив реальної ставки"}
GRIDS = {"beta": [0, 0.7, 1], "alpha": [0, 0.6, 1]}


def main(param="beta"):
    base = Model.from_files(cfg.MODEL_FILE, cfg.PARAMS_FILE)
    models = {f"{param} = {v:g}": base.with_params(**{param: v}) for v in GRIDS[param]}
    out = Path(cfg.RESULTS_DIR) / "figures"
    for shock, title in SHOCKS.items():
        res = {k: irf(m, shock, 1, 20) for k, m in models.items()}
        fig, ax = pl.grid(2, 3, width=12, height=6.5)
        for i, (var, lab) in enumerate(RESPONSES.items()):
            a = ax[i]
            for j, (k, df) in enumerate(res.items()):
                a.plot(df.index, df[var], color=pl.SERIES[j], label=k)
            a.axhline(0, color=pl.INK["axis"], lw=1)
            a.set_title(lab)
            a.set_xlabel("квартали після шоку")
            if i == 0:
                a.legend()
        fig.suptitle(f"{title}: відгук на шок 1 п.п.", x=0.07, ha="left", fontsize=12, fontweight="bold")
        pl.save(fig, out / f"irf_{shock}_{param}.png")
    print("Готово:", sorted(p.name for p in out.glob(f"irf_*_{param}.png")))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "beta")
