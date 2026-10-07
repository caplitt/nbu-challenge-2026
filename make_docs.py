"""Генерує docs/assumptions.md і docs/forecast_summary.md з config.py та results/ (цифри завжди актуальні).

Запуск:  python make_docs.py
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

import config as cfg

ROOT = Path(__file__).resolve().parent
TAB = ROOT / "results" / "tables"
K = json.loads((ROOT / "results" / "key_numbers.json").read_text(encoding="utf-8"))
DOCS = ROOT / "docs"


def n(x, d=1):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def md_table(df: pd.DataFrame, fmt=lambda v: n(v) if isinstance(v, float) else str(v)) -> str:
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join([""] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in df.iterrows():
        out.append("| " + " | ".join([str(i)] + [fmt(v) for v in r.values]) + " |")
    return "\n".join(out)


def assumptions():
    L = [f"# Припущення та судження прогнозу\n\nЗгенеровано {date.today()} з `config.py` (`python make_docs.py`). "
         f"Історія — до {cfg.LAST_HIST}, прогноз — {K['first_forecast']}–{cfg.LAST_FORE}.\n"]
    L.append("## 1. Короткостроковий прогноз (наукаст)\n")
    L.append(f"- ІСЦ на місяці без даних: тренд (SA, середнє за {cfg.CPI_NOWCAST['trend_window']} міс.) + сезонний фактор "
             f"(середнє за {cfg.CPI_NOWCAST['seasonal_years']} років) + поправка {n(cfg.CPI_NOWCAST['adjustment'])} в. п./міс. "
             "(велика пропозиція продовольства, мораторій на тарифи ЖКП, охолодження попиту).")
    nc = pd.read_csv(TAB / "cpi_nowcast.csv", index_col=0, encoding="utf-8-sig")
    L.append("\n" + md_table(nc, lambda v: n(v, 2) if isinstance(v, float) else str(v)) + "\n")
    L.append(f"- ІСЦ IV кв. 2026 фіксується на рівні наукасту (через шок витрат): {', '.join(cfg.CPI_NOWCAST_CONDITION)}.")
    L.append(f"- ВВП III кв. 2026: {', '.join(f'{k}: {n(v)}% кв/кв SA' for k, v in cfg.GDP_NOWCAST.items())} — "
             "КМП: «динаміка реального ВВП у III кварталі суттєво гірша, ніж прогнозував НБУ».\n")
    L.append("## 2. Судження (ручні шоки)\n")
    L.append("| Шок | Квартали | Значення | Обґрунтування | Джерело |\n|---|---|---|---|---|")
    for j in cfg.JUDGMENTS:
        L.append(f"| `{j['shock']}` | {', '.join(j['periods'])} | {', '.join(n(v, 2) for v in j['values'])} | {j['why']} | {j['source']} |")
    L.append("\nОдиниці: `res_dl_cpi` — в. п. квартальної інфляції в річному вимірі; `res_l_gdp_gap` — % потенціалу; "
             "`res_prem_uip_gap` — в. п. премії за ризик; `res_dl_gdp_tnd` — в. п. темпу потенційного ВВП.\n")
    L.append("## 3. Траєкторія цільового курсу (dl_er_tar, % річних)\n")
    L.append(" · ".join(f"{k}: {v}" for k, v in cfg.FX_TARGET_PATH.items()))
    L.append("\nОбґрунтування: EUR/USD 1,16 → 1,18 → 1,19 (припущення НБУ) + помірне послаблення гривні до долара в "
             "режимі керованої гнучкості; без цього номінальний курс майже не змінюється, і гривня реально зміцнюється "
             "на 4–6% на рік, що механічно занижує інфляцію і вимагає великих інтервенцій.\n")
    L.append("## 4. Зовнішні припущення\n")
    L.append("- Єврозона: HICP 3,0 / 2,5 / 2,1% (2026–2028), ВВП 0,9 / 1,4 / 1,5% — прогноз ЄЦБ (вересень 2026); "
             "ставка ЄЦБ 2,75% (IV кв. 2026) → 3,0% (2027) → 2,5% (кінець 2028) — ринкові очікування (OIS).")
    L.append("- Деталі та джерела — `data/UPDATE_LOG.md`.\n")
    L.append("## 5. Рішення, за яким будується базовий прогноз\n")
    L.append(f"- {cfg.RECOMMENDATION['option']}: середня ставка IV кв. 2026 = {n(cfg.RECOMMENDATION['rate'])}%, "
             "далі — правило Тейлора моделі.")
    (DOCS / "assumptions.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def summary():
    q = pd.DataFrame(K["baseline_quarterly"]).T
    q = q.rename(columns={"d4l_cpi": "ІСЦ, % р/р", "ir_pol": "Ставка, %", "uah_eur": "грн/€", "gdp_yoy": "ВВП, % р/р",
                          "l_gdp_gap": "Розрив ВВП, %"})
    L = [f"# Підсумки прогнозу\n\nЗгенеровано {date.today()} (`python make_docs.py`) з `results/key_numbers.json`.\n",
         "## Рекомендація\n"]
    R = K["recommendation"]
    L += [f"- **Облікова ставка:** {R['option']} ({n(R['rate'])}%); {R['guidance']}.",
          f"- **Курс:** {R['fx']}.", f"- **Валютні обмеження:** {R['fx_restrictions']}.\n",
          "## Базовий прогноз по кварталах\n", md_table(q.T.T, lambda v: n(float(v))), "\n",
          f"Інфляція на кінець грудня 2026 (наукаст): **{n(K['nowcast_dec_yoy'])}%**.\n",
          "## Порівняння з прогнозом НБУ (липень 2026)\n", md_table(pd.DataFrame(K["vs_nbu"])), "\n",
          "## Сценарії\n", md_table(pd.DataFrame(K["scenarios"]).T), "\n",
          "## Варіанти рішення 29.10.2026\n", md_table(pd.DataFrame(K["policy_options"]).T), "\n",
          "## Оптимальна траєкторія ставки (чутливість до ваги згладжування λ)\n", md_table(pd.DataFrame(K["optimal_paths"]).T), "\n",
          "## Резерви на кінець 2026 ($ млрд / місяців імпорту)\n",
          md_table(pd.DataFrame({"$ млрд": K["reserves_end2026"], "міс. імпорту": K["reserves_months_imports_end2026"]})), "\n",
          f"Імовірність, що інфляція буде в діапазоні 5 ± 1%: кінець 2027 — {n(100 * K['p_cpi_in_target_range']['2027Q4'], 0)}%, "
          f"кінець 2028 — {n(100 * K['p_cpi_in_target_range']['2028Q4'], 0)}%.\n",
          "## Бектест (RMSE прогнозу на 4 квартали)\n",
          md_table(pd.read_csv(TAB / "backtest_errors.csv", index_col=[0, 1], encoding="utf-8-sig")), "\n"]
    (DOCS / "forecast_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    assumptions()
    summary()
    print("docs/assumptions.md, docs/forecast_summary.md")
