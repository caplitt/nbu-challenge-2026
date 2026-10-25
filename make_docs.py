"""Генерує docs/assumptions.md, docs/forecast_summary.md і docs/qa_prep.md (з шаблону docs/templates/qa_prep.md)
з config.py та results/ — цифри завжди актуальні.

Запуск:  python make_docs.py
"""
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

import config as cfg

ROOT = Path(__file__).resolve().parent
TAB = ROOT / "results" / "tables"
K = json.loads((ROOT / "results" / "key_numbers.json").read_text(encoding="utf-8"))
DOCS = ROOT / "docs"


def n(x, d=1, sign=False):
    """Decimal comma, half-up rounding (as on the slides); optional explicit sign."""
    q = Decimal(str(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    q = abs(q) if q == 0 else q   # no "−0,0"
    return (f"{q:+f}" if sign else f"{q:f}").replace(".", ",").replace("-", "−")


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
             "(частина вересневого стрибка — разові ефекти пального й руйнувань логістики; мораторій на тарифи ЖКП).")
    nc = pd.read_csv(TAB / "cpi_nowcast.csv", index_col=0, encoding="utf-8-sig")
    L.append("\n" + md_table(nc, lambda v: n(v, 2) if isinstance(v, float) else str(v)) + "\n")
    L.append(f"- ІСЦ IV кв. 2026 фіксується на рівні наукасту (через шок витрат): {', '.join(cfg.CPI_NOWCAST_CONDITION)}.")
    L.append(f"- ВВП III кв. 2026: {', '.join(f'{k}: {n(v)}% кв/кв SA' for k, v in cfg.GDP_NOWCAST.items())} — "
             "КМП: «динаміка реального ВВП у III кварталі суттєво гірша, ніж прогнозував НБУ».\n")
    L.append("## 2. Судження (ручні шоки)\n")
    L.append("| Шок | Квартали | Значення | Обґрунтування | Джерело |\n|---|---|---|---|---|")
    for j in cfg.JUDGMENTS:
        L.append(f"| `{j['shock']}` | {', '.join(j['periods'])} | {', '.join(n(v, 2) for v in j['values'])} | {j['why']} | [{j['source']}]({j['url']}) |")
    L.append("\nОдиниці: `res_dl_cpi_c` / `res_dl_rnc` — в. п. квартальної базової інфляції / зміни небазових цін у річному вимірі; `res_l_gdp_gap` — % потенціалу; "
             "`res_prem_uip_gap` — в. п. премії за ризик; `res_dl_gdp_tnd` — в. п. темпу потенційного ВВП.\n")
    L.append("## 3. Траєкторія цільового курсу (dl_er_tar, % річних)\n")
    L.append(" · ".join(f"{k}: {v}" for k, v in cfg.FX_TARGET_PATH.items()))
    q = K["baseline_quarterly"]
    fo = pd.read_csv(ROOT / "data" / "foreign.csv", index_col=0)
    usd_eur_h = float(fo.loc["2027Q1", "USD_EUR"])
    eur_yr = ((q[cfg.LAST_FORE]["uah_eur"] / q[K["first_forecast"]]["uah_eur"]) ** (4 / (len(q) - 1)) - 1) * 100
    L.append("\nОбґрунтування: допустимий темп послаблення в режимі керованої гнучкості (β = 0,7: фактичний курс лише на 70% "
             "іде за цільовим, решта — паритет ставок). Фактичний курс у моделі залежить ще й від паритету "
             f"ставок: за ставки {n(cfg.RECOMMENDATION['rate'])}% гривня до євро слабшає в середньому на ≈{n(eur_yr)}% на рік "
             f"({n(q[K['first_forecast']]['uah_eur'])} → {n(q[cfg.LAST_FORE]['uah_eur'])} грн/€ до {cfg.LAST_FORE}). "
             "Після 2028 р. цільовий темп — модельний (повернення до рівноважного).")
    fxn = K.get("fx_nowcast", {})
    if fxn:
        L.append("\nКурс у поточному кварталі (`config.FX_NOWCAST`): " + "; ".join(
            f"{qq}: {n(v['level'], 2)} грн/€ = " + ", ".join(f"{m} — {t}" for m, t in v["months"].items()) for qq, v in fxn.items()) + ".")
    L.append(f"\nКурс грн/$ на слайдах = грн/€ ÷ USD/EUR; USD/EUR на горизонті — {n(usd_eur_h, 4)} (останній місяць за ЄЦБ, без змін; "
             "липневе припущення НБУ 1,16 / 1,18 / 1,19 застаріло після падіння EUR/USD у жовтні 2026).\n")
    L.append("## 4. Зовнішні припущення\n")
    L.append("- Єврозона: HICP 3,0 / 2,5 / 2,1% (2026–2028), ВВП 0,9 / 1,4 / 1,5% — прогноз ЄЦБ (вересень 2026); "
             "ставка ЄЦБ 2,75% (IV кв. 2026) → 3,0% (2027–2028) — технічні припущення того самого прогнозу ЄЦБ (EURIBOR 3M ≈3,0%).")
    br = {q: float(fo.loc[q, "BRENT_USD"]) for q in ("2026Q3", "2026Q4", "2027Q4", "2028Q4") if q in fo.index}
    L.append("- Нафта Brent: " + " → ".join(f"{q} ${n(v, 0)}" for q, v in br.items()) +
             " (спот EIA до III кв. 2026; IV кв. 2026 — жовтень за спотом, листопад–грудень за ф'ючерсом; далі ф'ючерсна "
             "крива NYMEX BZ); реальна ціна в євро входить у небазову інфляцію з вагою `w_oil` = 0,016 (`model/params.yaml`).")
    L.append("- Деталі та джерела — `data/UPDATE_LOG.md`.\n")
    L.append("## 5. Рішення, за яким будується базовий прогноз\n")
    L.append(f"- {cfg.RECOMMENDATION['option']}: середня ставка {n(cfg.RECOMMENDATION['rate'])}% у "
             f"{', '.join(cfg.HOLD)} (рішення й утримання до середини 2027 р.).")
    L.append("- Далі — траєкторія ставки, що повертає інфляцію до цілі 5% (точкова ціль, без діапазону) на горизонті "
             "політики до трьох років (Основні засади ГКП НБУ, 2024; підтверджено 03.09.2026): мінімум "
             f"Σ w·(π − 5)² + {n(cfg.TARGET_PATH['w_gap'])}·розрив² + {n(cfg.TARGET_PATH['w_smooth'])}·(Δi)², "
             f"вага w = {n(cfg.TARGET_PATH['w_last'], 0)} з {cfg.TARGET_PATH['last_from']}. За механічним правилом Тейлора "
             f"інфляція наприкінці 2029 р. була б лише {n(K['rule_after_hold']['2029Q4'])}%.")
    (DOCS / "assumptions.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def summary():
    q = pd.DataFrame(K["baseline_quarterly"]).T
    q = q.rename(columns={"cpi_yoy": "ІСЦ, % р/р", "core_yoy": "Базова, % р/р", "ir_pol": "Ставка, %", "uah_eur": "грн/€",
                          "gdp_yoy": "ВВП, % р/р", "l_gdp_gap": "Розрив ВВП, %", "rir_pol": "Реальна ставка, %",
                          "rir_tnd": "Нейтральна реальна ставка, %"})
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
          "Невизначеність (інтервал 70% імовірності для ІСЦ, % р/р): "
          + "; ".join(f"{q[:4]} — {n(v['q15'])}…{n(v['q85'])} (медіана {n(v['q50'])})" for q, v in K["fan_cpi"].items())
          + ".\n",
          "## Бектест (RMSE за горизонтами 1–4 квартали, лише квартали з фактом)\n",
          md_table(pd.read_csv(TAB / "backtest_errors.csv", index_col=[0, 1], encoding="utf-8-sig")), "\n"]
    (DOCS / "forecast_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _base_effect(nc):
    """'у жовтні–грудні 2025 ціни зросли лише на 1,5%' — the same months a year earlier."""
    cpi = pd.read_csv(ROOT / "data" / "overview" / "cpi.csv", index_col=0, encoding="utf-8-sig")
    base = [str(pd.Period(m, "M") - 12) for m in nc.index]
    names = {"01": "січні", "02": "лютому", "03": "березні", "04": "квітні", "05": "травні", "06": "червні", "07": "липні",
             "08": "серпні", "09": "вересні", "10": "жовтні", "11": "листопаді", "12": "грудні"}
    growth = (pd.Series([1 + cpi.loc[m, "cpi_mom"] / 100 for m in base]).prod() - 1) * 100
    return f"у {names[base[0][-2:]]}–{names[base[-1][-2:]]} {base[0][:4]} ціни зросли лише на {n(growth)}%"


def qa():
    """Q&A for the jury: the template's model numbers are filled from the latest results."""
    from qpm.nbu_files import read_ir_chart, read_nbu_forecast
    Q, A, SC, PO, OP = (K[k] for k in ("baseline_quarterly", "baseline_annual", "scenarios", "policy_options", "optimal_paths"))
    rec = cfg.RECOMMENDATION["option"]
    base = pd.read_csv(TAB / "forecast_Базовий.csv", index_col=0, encoding="utf-8-sig")
    nbu = read_nbu_forecast()

    def nbu_v(ind, per):
        return float(nbu[nbu["indicator"].str.startswith(ind) & (nbu["period"] == per)]["value"].iloc[0])

    def half(x):
        return round(x * 2) / 2

    qs = list(Q)
    target_q = next(q for i, q in enumerate(qs) if all(abs(Q[r]["cpi_yoy"] - 5) <= 0.2 for r in qs[i:]))
    peak_q = max(qs, key=lambda r: Q[r]["cpi_yoy"])
    back_q = next(q for q in qs if q > peak_q and Q[q]["cpi_yoy"] <= 5.25)
    band = [Q[q]["cpi_yoy"] for q in qs if q >= back_q]
    rx = K["risks_extra"]
    roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}
    q28 = [Q[f"2028Q{i}"]["cpi_yoy"] for i in range(1, 5)]
    dip = sorted({n(min(q28)), n(Q["2028Q4"]["cpi_yoy"])}, key=lambda t: float(t.replace(",", ".").replace("−", "-")))
    loss = "Втрати, λ = " + n(cfg.TARGET_PATH["w_smooth"], 0)
    best = K["best_option_by_lambda"]
    rate_of = lambda name: name.split(" ")[-1].rstrip("%")  # noqa: E731  'Підвищити до 17,5%' -> '17,5'
    bp = K["brent_path"]
    bt = pd.read_csv(TAB / "backtest_errors.csv", index_col=[0, 1], encoding="utf-8-sig")
    bt.columns = ["model", "naive", "n_obs"]
    bt = bt[[i[1].startswith("ІСЦ") for i in bt.index]]
    nc = pd.read_csv(TAB / "cpi_nowcast.csv", index_col=0, encoding="utf-8-sig")
    months = {"01": "січень", "02": "лютий", "03": "березень", "04": "квітень", "05": "травень", "06": "червень",
              "07": "липень", "08": "серпень", "09": "вересень", "10": "жовтень", "11": "листопад", "12": "грудень"}
    hh = pd.read_csv(ROOT / "data" / "overview" / "fx_market_households.csv", index_col=0, encoding="utf-8-sig")
    hh_jul, hh_sep = float(hh.loc["2026-07", "CliBuyPerMFO"]), float(hh.loc["2026-09", "CliBuyPerMFO"])
    fxe = read_ir_chart("3.12")
    fg, hw, oil, bs = (SC[k] for k in ("Дефіцит фінансування", "Важка зима", "Нафта $120", "Базовий"))
    res, resm = K["reserves_end2026"], K["reserves_months_imports_end2026"]
    # GDP growth ≈ potential growth + change in the output gap (annual averages)
    bq = base.copy()
    bq.index = pd.PeriodIndex(bq.index, freq="Q")

    def yavg(col, y):
        return float(bq[col].loc[f"{y}Q1":f"{y}Q4"].mean())

    def ygrowth(col, y):
        import numpy as np
        lv = np.exp(bq[col] / 100)
        return float((lv.loc[f"{y}Q1":f"{y}Q4"].mean() / lv.loc[f"{y - 1}Q1":f"{y - 1}Q4"].mean() - 1) * 100)

    vs = K["vs_nbu"]
    ov = ROOT / "data" / "overview"
    key_now = float(pd.read_csv(ROOT / "data" / "raw" / "nbu_key_rate.csv", index_col=0).iloc[-1, 0])
    cpi_y = pd.read_csv(ov / "cpi.csv", index_col=0, encoding="utf-8-sig")["cpi_yoy"].dropna()
    exp_an = float(pd.read_csv(ov / "expectations.csv", index_col=0, encoding="utf-8-sig")["Фінансові аналітики"].dropna().iloc[-1])
    usd = pd.read_csv(ov / "fx.csv", index_col=0, encoding="utf-8-sig")["грн/$"].dropna()
    usd_yago = float(usd.loc[str(pd.Period(usd.index[-1], "M") - 12)])
    w26 = pd.read_csv(ov / "wages.csv", index_col=0, encoding="utf-8-sig")["Номінальна"].dropna().loc["2026-01":]
    bh = sorted(set(K["best_hold_by_lambda"].values()))
    fxr = K["fx_risk"]
    v = dict(
        opt_full=n(OP["λ = 1, повна реакція на адмінціни"]["2026Q4"]), opt_l05=n(OP["λ = 0.5"]["2026Q4"]),
        admin=n(K["admin_reaction"] * 100, 0),
        best_hold=" / ".join(f"{k.replace('.', ',')} — {n(x)}%" for k, x in K["best_hold_by_lambda"].items()),
        best_hold_rng=f"{n(bh[0])}–{n(bh[-1])}",
        fx_cpi27=n(fxr["cpi_2027Q4"]), fx_rate=n(fxr["rate_peak"]), fx_usd=n(fxr["uah_usd_2027Q4"]), fx_dep=n(fxr["dep_per_year"]),
        back_q=f"{roman[back_q[-1]]} кв. {back_q[:4]}", back_year=back_q[:4], band=f"{n(min(band))}–{n(max(band))}",
        core_dec=n(K["nowcast_core_dec_yoy"]), nbu_core26=n(nbu_v("Базова інфляція", "2026Q4")),
        exp_cpi27=n(rx["Розбалансування очікувань"]["ІСЦ IV кв. 2027"]), exp_rate=n(rx["Розбалансування очікувань"]["Ставка пік"]),
        vat_peak=n(rx["ПДВ 21% з 2027"]["ІСЦ пік"]), vat_rate=n(rx["ПДВ 21% з 2027"]["Ставка пік"]),
        best_l1=n(K["best_hold_by_lambda"]["λ = 1"]),
        rob_E1=n(K["robust"]["summary"]["λ = 1"]["best_E"]["P1"]), rob_E2=n(K["robust"]["summary"]["λ = 1"]["best_E"]["P2"]),
        rob_reg=n(K["robust"]["summary"]["λ = 1"]["best_regret"]),
        rob_e17=n(K["robust"]["summary"]["λ = 1"]["E"]["P1"]["17.0"]), rob_e165=n(K["robust"]["summary"]["λ = 1"]["E"]["P1"]["16.5"]),
        rob_e175=n(K["robust"]["summary"]["λ = 1"]["E"]["P1"]["17.5"]),
        opt_l1_q1=n(OP["λ = 1"]["2027Q1"]),
        fx_half=n((K["robust"]["losses"]["cpi27"]["Курс як чекає ринок"]["16.5"]
                   - K["robust"]["losses"]["cpi27"]["Курс як чекає ринок"]["17.5"]) / 2),
        key_now=n(key_now, 0), cpi_last=n(cpi_y.iloc[-1]), exp_an=n(exp_an),
        rr_post=n(key_now - cpi_y.iloc[-1]), rr_ante_an=n(key_now - exp_an), rr_ante_fc=n(key_now - Q["2027Q3"]["cpi_yoy"]),
        usd_now=n(usd.iloc[-1]), usd_dep=n((usd.iloc[-1] / usd_yago - 1) * 100, 0),
        wages_rng=f"{n(w26.min(), 0)}–{n(w26.max(), 0)}", wage_last=n(w26.iloc[-1], 0),
        cpi_peak=n(SC["Базовий"]["ІСЦ пік"]),
        pot27=n(ygrowth("l_gdp_tnd", 2027)), pot28=n(ygrowth("l_gdp_tnd", 2028)), pot29=n(ygrowth("l_gdp_tnd", 2029)),
        pot26=n(ygrowth("l_gdp_tnd", 2026)),
        dgap27=n(yavg("l_gdp_gap", 2027) - yavg("l_gdp_gap", 2026), 1, True),
        dgap28=n(yavg("l_gdp_gap", 2028) - yavg("l_gdp_gap", 2027), 1, True),
        dgap29=n(yavg("l_gdp_gap", 2029) - yavg("l_gdp_gap", 2028), 1, True),
        gap26=n(yavg("l_gdp_gap", 2026)), gap28=n(yavg("l_gdp_gap", 2028)),
        rir27=n(yavg("rir_pol", 2027)), rirn27=n(yavg("rir_tnd", 2027)),
        gdp29=n(A["2029"]["Реальний ВВП, % (рік)"]), gdp27_16=n(PO["Утримати 16%"]["ВВП 2027, %"]),
        nbu_r27=n(vs["2027"]["Ставка IV кв., НБУ липень"]), nbu_r28=n(vs["2028"]["Ставка IV кв., НБУ липень"]),
        r27x=n(Q["2027Q4"]["ir_pol"]),
        date=date.today(), rate=n(cfg.RECOMMENDATION["rate"], 0 if cfg.RECOMMENDATION["rate"] % 1 == 0 else 1), last_year=cfg.LAST_FORE[:4], target_year=target_q[:4],
        target_q=f"{roman[target_q[-1]]} кв. {target_q[:4]}", dec=n(K["nowcast_dec_yoy"]),
        opt_lt=n(OP["λ = 1, без реакції на адмінціни"]["2026Q4"]), opt_l2=n(OP["λ = 2"]["2026Q4"]), opt_l1=n(OP["λ = 1"]["2026Q4"]),
        loss_rec=n(PO[rec][loss]), loss_16=n(PO["Утримати 16%"][loss]),
        loss_165=n(PO["Підвищити до 16,5%"][loss]), loss_175=n(PO["Підвищити до 17,5%"][loss]),
        loss_opt=n(PO["Оптимальна (мін. втрат)"][loss]),
        best="; ".join(f"{k.replace('.', ',')} — {rate_of(v)}%" for k, v in best.items()),
        rir_now=n(K["real_rate_last_hist"]["rir_pol"]), rir_tnd_now=n(K["real_rate_last_hist"]["rir_tnd"]),
        rir_q2=n(Q["2027Q2"]["rir_pol"]), rir_tnd_q2=n(Q["2027Q2"]["rir_tnd"]),
        brent26=n(bp["2026Q4"], 0), brent27=n(bp["2027Q4"], 0), brent28=n(bp["2028Q4"], 0),
        cpi26_log=n(float(base.loc[K["first_forecast"], "d4l_cpi"])),
        cpi27_16=n(PO["Утримати 16%"]["ІСЦ IV кв. 2027"]),
        gdp27_rec=n(PO[rec]["ВВП 2027, %"]), gdp27_175=n(PO["Підвищити до 17,5%"]["ВВП 2027, %"]),
        rir26=n(base.loc[K["first_forecast"], "rir_pol"]), rir_tnd26=n(base.loc[K["first_forecast"], "rir_tnd"]),
        r27=n(half(Q["2027Q4"]["ir_pol"])), r28=n(half(Q["2028Q4"]["ir_pol"])), r29=n(round(Q[cfg.LAST_FORE]["ir_pol"]), 0),
        gdp26=n(A["2026"]["Реальний ВВП, % (рік)"]), gdp27=n(A["2027"]["Реальний ВВП, % (рік)"]), gdp28=n(A["2028"]["Реальний ВВП, % (рік)"]),
        nbu_gdp26=n(nbu_v("Реальний ВВП", "2026")), nbu_gdp27=n(nbu_v("Реальний ВВП", "2027")), nbu_gdp28=n(nbu_v("Реальний ВВП", "2028")),
        dip28="–".join(dip), cpi26=n(Q["2026Q4"]["cpi_yoy"]), cpi27=n(Q["2027Q4"]["cpi_yoy"]),
        core27=n(A["2027"]["Базова інфляція, % р/р (IV кв.)"]), core28=n(A["2028"]["Базова інфляція, % р/р (IV кв.)"]),
        nbu_cpi27=n(nbu_v("ІСЦ (на кінець", "2027Q4")), nbu_core27=n(nbu_v("Базова інфляція", "2027Q4")),
        nbu_core28=n(nbu_v("Базова інфляція", "2028Q4")), rule29=n(K["rule_after_hold"]["2029Q4"]),
        nc_trend=n(nc["Тренд (SA)"].iloc[-1], 2),
        base_effect=_base_effect(nc),
        nc_months=", ".join(f"{months[i[-2:]]} {n(r['ІСЦ м/м, прогноз'], 2)}%" for i, r in nc.iterrows()),
        eur26=n(Q[K["first_forecast"]]["uah_eur"]), eur29=n(Q[cfg.LAST_FORE]["uah_eur"]),
        bt_model=f"{n(bt['model'].min())}–{n(bt['model'].max())}", bt_naive=f"{n(bt['naive'].min())}–{n(bt['naive'].max())}",
        fan27_lo=n(K["fan_cpi"]["2027Q4"]["q15"]), fan27_hi=n(K["fan_cpi"]["2027Q4"]["q85"]), fan27_mid=n(K["fan_cpi"]["2027Q4"]["q50"]),
        sales=n(K["reserves_recent"]["sales_per_month"]), inflows=n(K["reserves_recent"]["inflows_per_month"]),
        nbu_res=n(K["reserves_nbu"]["end2026"]), nbu_res_m=n(K["reserves_nbu"]["months"]),
        need=n(K["reserves_nbu"]["inflow_needed_per_month"]),
        res_lo=n(min(res.values()), 0), res_hi=n(max(res.values()), 0),
        res_cases=" / ".join("$" + n(x, 0) if i == 0 else n(x, 0) for i, x in enumerate(res.values())),
        res_months=" / ".join(n(x) for x in resm.values()),
        fg_uah=n(fg["Курс IV кв. 2027, грн/€"], 0), fg_dep=n((fg["Курс IV кв. 2027, грн/€"] / bs["Курс IV кв. 2027, грн/€"] - 1) * 100, 0),
        fg_peak=n(fg["ІСЦ пік"]), fg_rate=n(fg["Ставка пік"]), fg_gdp=n(fg["ВВП 2027, % (рік)"]),
        hw_peak=n(hw["ІСЦ пік"]), hw_rate=n(hw["Ставка пік"]), hw_gdp=n(hw["ВВП 2027, % (рік)"]),
        oil_q4=n(oil["ІСЦ IV кв. 2026"] - bs["ІСЦ IV кв. 2026"]), oil_peak=n(oil["ІСЦ пік"] - bs["ІСЦ пік"]),
        oil_rate=n(oil["Ставка пік"] - bs["Ставка пік"]),
        hh_jul=n(hh_jul, 2), hh_sep=n(hh_sep, 2), hh_pct=n((hh_sep / hh_jul - 1) * 100, 0),
        fx_exp_month=str(fxe["Фінансові аналітики"].dropna().index[-1]),
        fx_exp_an=n(fxe["Фінансові аналітики"].dropna().iloc[-1]), fx_exp_hh=n(fxe["Домогосподарства"].dropna().iloc[-1]),
        # model exchange-rate path over 2027 (Q4 2026 -> Q4 2027) vs USD and EUR, and the USD/EUR assumption behind it
        usd27=n((Q["2027Q4"]["uah_usd"] / Q["2026Q4"]["uah_usd"] - 1) * 100, 1, True),
        eur27=n((Q["2027Q4"]["uah_eur"] / Q["2026Q4"]["uah_eur"] - 1) * 100, 1, True),
        usd_eur=n(float(pd.read_csv(ROOT / "data" / "foreign.csv", index_col=0).loc["2027Q1", "USD_EUR"]), 2),
    )
    tpl = (DOCS / "templates" / "qa_prep.md").read_text(encoding="utf-8")
    (DOCS / "qa_prep.md").write_text(tpl.format_map(v), encoding="utf-8")


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    assumptions()
    summary()
    qa()
    print("docs/assumptions.md, docs/forecast_summary.md, docs/qa_prep.md")
