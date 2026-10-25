"""Зміст презентації: тексти + цифри з results/key_numbers.json і results/tables (єдине джерело чисел).

Запуск з кореня репозиторію:  python deck/content.py   ->  deck/deck_data.json
Потім:                         node deck/build_deck.js  ->  presentation/*.pptx
Правте тексти тут; цифри підставляються автоматично після кожного прогону моделі.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config as cfg  # noqa: E402
from qpm.nbu_files import read_ir_chart, read_nbu_forecast  # noqa: E402
from qpm.reserves import IMPORTS_PER_MONTH  # noqa: E402

TEAM = {"name": "Команда [назва]", "university": "[Університет, факультет]",
        "members": "[Учасники команди]", "advisor": "[Викладач-консультант]"}

K = json.loads((ROOT / "results" / "key_numbers.json").read_text(encoding="utf-8"))
TAB = ROOT / "results" / "tables"
FIG = ROOT / "results" / "figures"


def n(x, d=1, sign=False):
    """Number in Ukrainian style: decimal comma, optional sign; rounds half up as people expect (16,45 -> 16,5)."""
    q = Decimal(str(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    if q == 0:
        q = abs(q)   # no "−0,0"
    s = f"{q:+f}" if sign else f"{q:f}"
    return s.replace(".", ",").replace("-", "−")


def pr(x):
    """Policy rate as the NBU writes it: 17% but 16,5%."""
    return n(x, 0) if float(x) % 1 == 0 else n(x)


def img(name):
    p = FIG / f"{name}.png"
    w, h = Image.open(p).size
    return {"path": str(p), "w": w, "h": h}


def table_csv(name, index_col=0, **kw):
    return pd.read_csv(TAB / f"{name}.csv", index_col=index_col, encoding="utf-8-sig", **kw)


Q = K["baseline_quarterly"]
A = K["baseline_annual"]
SC = K["scenarios"]
PO = K["policy_options"]
REC = K["recommendation"]
RES = K["reserves_end2026"]
RESM = K["reserves_months_imports_end2026"]
RR = K["reserves_recent"]
VS = K["vs_nbu"]
# NBU target: 5% point target within a policy horizon of up to three years.
# back_q — first quarter after the peak with inflation back at ≈5%; first_target_q — from which it stays within ±0.2 pp
_qs = list(Q)
_peak_q = max(_qs, key=lambda r: Q[r]["cpi_yoy"])
back_q = next(q for q in _qs if q > _peak_q and Q[q]["cpi_yoy"] <= 5.25)
first_target_q = next(q for i, q in enumerate(_qs) if all(abs(Q[r]["cpi_yoy"] - 5) <= 0.2 for r in _qs[i:]))
_after = [Q[q]["cpi_yoy"] for q in _qs if q >= back_q]
band_lo, band_hi = min(_after), max(_after)
dip28 = min(Q[f"2028Q{i}"]["cpi_yoy"] for i in range(1, 5))
# actual (model) depreciation of UAH vs EUR, average % a year over the horizon: the NBU target path allows up to
# 4% a year, but the high policy rate (UIP) keeps the hryvnia stronger
fx_yr = ((Q[f"{_qs[-1]}"]["uah_eur"] / Q[_qs[0]]["uah_eur"]) ** (4 / (len(_qs) - 1)) - 1) * 100
roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}


def qlabel(q):
    return f"{roman[q[-1]]} кв. {q[:4]}"


# wording of the return to target: back_q — first quarter below ≈5%; 2028 may undershoot (oil falls along the futures
# curve, demand is weak), and tgt_year is the year from which inflation stays within ±0.2 pp of 5%
tgt_year = first_target_q[:4]
band28_lo, band28_hi = (f(Q[f"2028Q{i}"]["cpi_yoy"] for i in range(1, 5)) for f in (min, max))
ret_short = f"нижче 5% з {qlabel(back_q)}, ≈5% у {tgt_year}"


bt = table_csv("backtest_errors")
bt.columns = ["var", "model", "naive", "n_obs"]
bt_cpi = bt[bt["var"].str.startswith("ІСЦ")]
fan = K["fan_cpi"]
rule29 = K["rule_after_hold"]["2029Q4"]
hh = pd.read_csv(ROOT / "data" / "overview" / "fx_market_households.csv", index_col=0, encoding="utf-8-sig")
hh_jul, hh_aug, hh_sep = (float(hh.loc[m, "CliBuyPerMFO"]) for m in ("2026-07", "2026-08", "2026-09"))

SECTIONS = ["Огляд", "Прогноз", "Рекомендації", "Додатки"]

_mc = ROOT / "docs" / "matlab_check.md"
if _mc.exists():
    import re
    _m = re.search(r"Найбільша розбіжність: ([0-9.]+)e([-+]\d+)", _mc.read_text(encoding="utf-8"))
    matlab_diff = f"~1e−{abs(int(_m.group(2)))}" if _m else "= MATLAB"
else:
    matlab_diff = "= MATLAB"
# MATLAB/IRIS charts go into the deck only when the MATLAB run matches the current Python results
_ms = ROOT / "results" / "matlab_status.json"
ML = json.loads(_ms.read_text(encoding="utf-8")).get("fresh", False) if _ms.exists() else False


def ml_img(matlab_name, python_name):
    return img(matlab_name) if ML and (FIG / f"{matlab_name}.png").exists() else img(python_name)


_nbu = read_nbu_forecast()


def nbu_val(indicator, period):
    r = _nbu[_nbu["indicator"].str.startswith(indicator) & (_nbu["period"] == period)]
    return float(r["value"].iloc[0])


def pr_opt(name):
    """'Підвищити до 17,5%' -> '17,5'."""
    return name.split(" ")[-1].rstrip("%")


def half(x):
    """Round to the nearest 0.5 (for rate guidance)."""
    return round(x * 2) / 2


# Sources actually used (files and pages the data and facts were taken from) — clickable in the deck
SRC = {k: {"text": t, "url": u} for k, (t, u) in {
    "ir": ("НБУ, Інфляційний звіт (липень 2026)", "https://bank.gov.ua/ua/news/all/inflyatsiya-prishvidshitsya-u-drugomu-pivrichchi-ale-povernetsya-do-znijennya-nastupnogo-roku--inflyatsiyniy-zvit"),
    "ir_data": ("дані графіків ІЗ", "https://bank.gov.ua/admin_uploads/article/Tables_Charts_2026-Q3.xlsx?v=19"),
    "nbu_fc": ("макропрогноз НБУ", "https://bank.gov.ua/admin_uploads/article/Macroeconomic_Forecast_table_2026_07.xlsx?v=19"),
    "api": ("API НБУ", "https://bank.gov.ua/ua/open-data/api-dev"),
    "ccpi": ("базовий ІСЦ (НБУ)", "https://bank.gov.ua/files/macro/CCPI_m.xlsx"),
    "cpi_sep": ("коментар НБУ: інфляція у вересні", "https://bank.gov.ua/ua/news/all/komentar-natsionalnogo-banku-schodo-rivnya-inflyatsiyi-u-veresni-2026-roku"),
    "cpi_aug": ("коментар НБУ: інфляція в серпні", "https://bank.gov.ua/ua/news/all/komentar-natsionalnogo-banku-schodo-rivnya-inflyatsiyi-v-serpni-2026-roku"),
    "gdp_q2": ("коментар НБУ: ВВП II кв.", "https://bank.gov.ua/ua/news/all/komentar-natsionalnogo-banku-schodo-zmini-realnogo-vvp-u-ii-kvartali-2026-roku"),
    "kmp": ("підсумки дискусії КМП", "https://bank.gov.ua/ua/news/all/pidsumki-diskusiyi-chleniv-komitetu-z-monetarnoyi-politiki-natsionalnogo-banku-schodo-rivnya-oblikovoyi-stavki-16-veresnya-2026-roku"),
    "rate": ("рішення НБУ 17.09.2026", "https://bank.gov.ua/ua/news/all/natsionalniy-bank-ukrayini-pidvischiv-oblikovu-stavku-do-16"),
    "fx_pack": ("пакет пом'якшення валютних обмежень", "https://bank.gov.ua/ua/news/all/nbu-vprovadjuye-paket-pomyakshennya-valyutnih-obmejen-z-osnovnim-fokusom-na-pidtrimtsi-naselennya"),
    "fx_strat": ("Стратегія пом'якшення валютних обмежень", "https://bank.gov.ua/admin_uploads/article/Strategy_for_easing_FX_restrictions_07-07-2023.pdf?v=19"),
    "mpg": ("Основні засади ГКП (2024)", "https://p4.bank.gov.ua/admin_uploads/article/MPG_2024-mt_eng.pdf"),
    "imf": ("Рада МВФ: перегляд програми", "https://bank.gov.ua/ua/news/all/rada-mvf-shvalila-pershiy-pereglyad-programi-rozshirenogo-finansuvannya-ta-zatverdila-vidilennya-transhu-obsyagom-690-mln-dol-ssha"),
    "budget": ("бюджет (НБУ)", "https://bank.gov.ua/files/macro/S_budget_m.xlsx"),
    "wages": ("зарплати (НБУ)", "https://bank.gov.ua/files/macro/Wages_m.xlsx"),
    "ecb_proj": ("прогноз ЄЦБ (вересень 2026)", "https://www.ecb.europa.eu/press/projections/html/index.en.html"),
    "ecb": ("ЄЦБ Data Portal", "https://data.ecb.europa.eu/"),
    "eurostat": ("Eurostat HICP", "https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table"),
    "eia": ("EIA Brent", "https://db.nomics.world/EIA/PET/RBRTE.M"),
    "fut": ("ф'ючерси Brent", "https://finance.yahoo.com/quote/BZ%3DF/"),
    "template": ("модель-шаблон НБУ", "https://events.bank.gov.ua/uchallenge2026/files/nbu_challenge_model_2026.zip"),
    "derzh": ("Держстат", "https://stat.gov.ua/"),
    "ovdp": ("аукціон ОВДП 06.10.2026", "https://minfin.com.ua/ua/2026/10/07/183076902/"),
    "cd": ("принцип обсягів 3-міс. ДС (НБУ)", "https://bank.gov.ua/ua/news/all/nbu-informuye-pro-golovniy-printsip-viznachennya-obsyagiv-rozmischennya-trimisyachnih-depozitnih-sertifikativ"),
    "law": ("Закон «Про НБУ», ст. 6", "https://zakon.rada.gov.ua/laws/show/679-14"),
    "vat": ("НБУ про ПДВ 21% (Interfax)", "https://interfax.com.ua/news/economic/1205936.html"),
    "ied": ("ІЕД: ВВП у липні–серпні", "https://minfin.com.ua/ua/2026/09/23/182198642/"),
    "minecon": ("Мінекономіки: прогноз ВВП", "https://interfax.com.ua/news/economic/1211092.html"),
    "res_sep": ("НБУ: резерви у вересні (USL $3,81 млрд)", "https://bank.gov.ua/ua/news/all/mijnarodni-rezervi-stanovili-471-mlrd-dol-ssha-za-pidsumkami-veresnya"),
    "pyshnyi": ("А. Пишний: три роки керованої гнучкості", "https://epravda.com.ua/finances/valyutniy-rinok-ukrajini-rezultati-troh-rokiv-rezhimu-kerovanoji-gnuchkosti-826509/"),
}.items()}

opt_lt = K["optimal_paths"]["λ = 1, без реакції на адмінціни"]
DATA_CUTOFF = "24.10.2026"   # official FX rate for 26.10 (set on 24.10), Brent spot to 20.10 (FRED lag), futures close 24.10
_cpi_m = pd.read_csv(ROOT / "data" / "overview" / "cpi.csv", index_col=0, encoding="utf-8-sig")
_nc0 = table_csv("cpi_nowcast")
nc_trend = float(_nc0["Тренд (SA)"].iloc[-1])
nc_months = [str(m) for m in _nc0.index]
_base = [str(pd.Period(m, "M") - 12) for m in nc_months]
base_effect = (pd.Series([1 + _cpi_m.loc[m, "cpi_mom"] / 100 for m in _base]).prod() - 1) * 100
_mname = {"01": "січні", "02": "лютому", "03": "березні", "04": "квітні", "05": "травні", "06": "червні", "07": "липні",
          "08": "серпні", "09": "вересні", "10": "жовтні", "11": "листопаді", "12": "грудні"}
base_span = f"{_mname[_base[0][-2:]].replace('і', 'і', 1)}–{_mname[_base[-1][-2:]]} {_base[0][:4]}"
last_cpi = _cpi_m.dropna(subset=["cpi_yoy"]).iloc[-1]
# balance of payments (NBU July forecast + IR chart 3.13), FX expectations (IR chart 3.12), NBU reserves forecast
bop_t = pd.read_csv(ROOT / "data" / "overview" / "bop_trade.csv", index_col=0, encoding="utf-8-sig")
bop_f = pd.read_csv(ROOT / "data" / "overview" / "bop_financing.csv", index_col=0, encoding="utf-8-sig")
fis = pd.read_csv(ROOT / "data" / "overview" / "fiscal.csv", index_col=0, encoding="utf-8-sig")
fxe = read_ir_chart("3.12")
fx_exp = {c: float(fxe[c].dropna().iloc[-1]) for c in ("Фінансові аналітики", "Домогосподарства")}
fx_exp_month = str(fxe["Фінансові аналітики"].dropna().index[-1])
# UAH/USD: the last monthly average in fx.csv is the current month to date; the latest official rate is daily
_fxm = pd.read_csv(ROOT / "data" / "overview" / "fx.csv", index_col=0, encoding="utf-8-sig")
_fxd = pd.read_csv(ROOT / "data" / "overview" / "fx_daily.csv", index_col=0, encoding="utf-8-sig", parse_dates=True)["грн/$"].dropna()
usd_now = float(_fxm["грн/$"].dropna().iloc[-1])          # October 2026 month-to-date average
usd_last, usd_last_date = float(_fxd.iloc[-1]), pd.Timestamp(_fxd.index[-1]).strftime("%d.%m")
usd_jun_sep = float(_fxm["грн/$"].loc["2026-06":"2026-09"].mean())   # the plateau before October
usd_oct_max, usd_oct_max_date = float(_fxd.loc["2026-10"].max()), pd.Timestamp(_fxd.loc["2026-10"].idxmax()).strftime("%d.%m")
usd_record = usd_oct_max >= float(_fxd.loc[:"2026-09-30"].max())   # October high = all-time low of the hryvnia?
fx_oct_text = (f"у жовтні — до {n(usd_oct_max, 2)} ({usd_oct_max_date}{', історичний мінімум гривні' if usd_record else ''}), "
               f"{usd_last_date} — {n(usd_last, 2)}")
RN = K["reserves_nbu"]
core = {y: A[y]["Базова інфляція, % р/р (IV кв.)"] for y in ("2026", "2027", "2028", "2029")}
nbu_cpi27 = nbu_val("ІСЦ (на кінець", "2027Q4")
nbu_core27, nbu_core28 = nbu_val("Базова інфляція", "2027Q4"), nbu_val("Базова інфляція", "2028Q4")


def dec_proxy(y):
    """Our quarterly averages vs NBU's end-of-quarter (December) values: December sits a third of the way from the
    middle of Q4 (mid-November) to the middle of the next Q1 (mid-February), so interpolate between the two quarters."""
    q4, q1 = Q[f"{y}Q4"]["core_yoy"], Q[f"{y + 1}Q1"]["core_yoy"]
    return q4 + (q1 - q4) / 3


core_dec27 = dec_proxy(2027)
core_vs_nbu = ("стійкіша, ніж у НБУ" if core_dec27 > nbu_core27 + 0.15 else
               "близька до прогнозу НБУ" if abs(core_dec27 - nbu_core27) <= 0.15 else "нижча, ніж у НБУ")
# Brent: monthly EIA spot (the last month is month-to-date, see the 'source' column) and the futures curve
_braw = pd.read_csv(ROOT / "data" / "raw" / "brent_monthly.csv", index_col=0)
_brent = _braw["brent_usd"]
_b26 = _brent.loc["2026-01":][~_braw["source"].loc["2026-01":].str.contains("month-to-date")]   # complete months only
brent_peak_m, brent_peak = _mname[_b26.idxmax()[-2:]], float(_b26.max())
brent_last = float(_brent.iloc[-1])
brent_last_m = _mname[_brent.index[-1][-2:]]
_mtd = re.search(r"to (\d{4})-(\d{2})-(\d{2})", str(_braw["source"].iloc[-1]))
brent_last_note = f"1–{int(_mtd.group(3))}.{_mtd.group(2)}" if _mtd else ""
brent_sep = float(_brent.loc["2026-09"])
BP = K["brent_path"]
# real policy rate: ex post = key rate minus the latest CPI y/y; ex ante (model) = rate minus next quarter's inflation
_kr = pd.read_csv(ROOT / "data" / "raw" / "nbu_key_rate.csv", index_col=0).iloc[:, 0]
_cpi_y = _cpi_m["cpi_yoy"].dropna()
key_now = float(_kr.iloc[-1])
rr_post = key_now - float(_cpi_y.iloc[-1])
_m_prev = _cpi_y.index[-2]
rr_post_prev = float(_kr.loc[:str(pd.Period(_m_prev, 'M').end_time.date())].iloc[-1]) - float(_cpi_y.iloc[-2])
RRH = K["real_rate_last_hist"]
# ex ante real rate (as the NBU looks at it): from analysts' 12-month expectations and from our own forecast a year ahead
_exp = pd.read_csv(ROOT / "data" / "overview" / "expectations.csv", index_col=0, encoding="utf-8-sig")
exp_an = float(_exp["Фінансові аналітики"].dropna().iloc[-1])
rr_ante_an = key_now - exp_an
rr_ante_fc = key_now - Q["2027Q3"]["cpi_yoy"]
# FX: flat June–September, a record low vs USD in October; risk if the hryvnia keeps weakening as the market expects
_fx = _fxm["грн/$"].dropna()
usd_yago = float(_fx.loc[str(pd.Period(_fx.index[-1], 'M') - 12)])
usd_dep_yr = (float(_fx.iloc[-1]) / usd_yago - 1) * 100
FXR = K["fx_risk"]
# model path vs USD over the next year (Q3 2026 -> Q3 2027), comparable with the analysts' 12-month expectation
usd_q3 = float(table_csv("forecast_Базовий").loc["2026Q3", "uah_usd"]) if "uah_usd" in table_csv("forecast_Базовий").columns else usd_now
model_dep_12m = (Q["2027Q3"]["uah_usd"] / usd_q3 - 1) * 100
market_dep_12m = (fx_exp["Фінансові аналітики"] / usd_q3 - 1) * 100
usd_eur_h = float(pd.read_csv(ROOT / "data" / "foreign.csv", skiprows=[1], index_col=0).loc["2027Q1", "USD_EUR"])
FXN = K.get("fx_nowcast", {})
# wages: the whole first half of the year, not one month
_w = pd.read_csv(ROOT / "data" / "overview" / "wages.csv", index_col=0, encoding="utf-8-sig")["Номінальна"].dropna()
_w26 = _w.loc["2026-01":]
wages_rng = f"{n(_w26.min(), 0)}–{n(_w26.max(), 0)}"
BH = K["best_hold_by_lambda"]
RX = K["risks_extra"]
nc_core_dec = K["nowcast_core_dec_yoy"]
gap26 = Q["2026Q4"]["l_gdp_gap"]
_bh = sorted(set(BH.values()))
best_hold_rng = pr(_bh[0]) if len(_bh) == 1 else f"{pr(_bh[0])}–{pr(_bh[-1])}"
ADMIN = int(round(K["admin_reaction"] * 100))
ROB = K["robust"]["summary"]["λ = 1"]
_rbE = sorted({float(v) for v in ROB["best_E"].values()})
rob_best = pr(_rbE[0]) if len(_rbE) == 1 else f"{pr(_rbE[0])}–{pr(_rbE[-1])}"
_rl = K["robust"]["losses"]["cpi27"]["Курс як чекає ринок"]
fx_per_half = (_rl["16.5"] - _rl["17.5"]) / 2            # CPI IV кв. 2027 lower per +0.5 pp in October (FX risk)
rir_now, rir_tnd_now = RRH["rir_pol"], RRH["rir_tnd"]
rir_q2, rir_tnd_q2 = Q["2027Q2"]["rir_pol"], Q["2027Q2"]["rir_tnd"]
BEST = {k.replace(".", ","): v for k, v in K["best_option_by_lambda"].items()}
LOSS = "Втрати, λ = " + n(cfg.TARGET_PATH["w_smooth"], 0)
slides = []


def add(**s):
    slides.append(s)


# ----------------------------------------------------------------------------------------------- title
add(type="title", section=None,
    title="Рекомендації щодо монетарної політики",
    subtitle=f"Рішення Правління НБУ 29 жовтня 2026 року",
    meta=[TEAM["name"], TEAM["university"], "NBU University Challenge 2026"],
    notes="Ми — " + TEAM["name"] + ". Наша рекомендація — для засідання Правління НБУ 29 жовтня 2026 року, "
          f"на якому НБУ оновить макропрогноз. Дані — станом на {DATA_CUTOFF}.")

# ----------------------------------------------------------------------------------------------- summary
add(type="summary", section=None, title=f"Головне: ставка {pr(REC['rate'])}%, гнучкіший курс, пауза в лібералізації",
    cards=[
        {"label": "Облікова ставка", "value": f"{pr(REC['rate'])}%", "delta": f"{n(REC['change_pp'], 1, True)} в. п.",
         "text": f"утримувати щонайменше до середини 2027; далі — зниження; інфляція {ret_short}"},
        {"label": "Курс гривні", "value": "Гнучкий", "delta": "",
         "text": f"після плато ≈{n(usd_jun_sep)} грн/$ (червень–вересень) {fx_oct_text}; "
                 "допускати двосторонні коливання, інтервенції лише згладжують; рівень не фіксувати"},
        {"label": "Валютні обмеження", "value": "Пауза", "delta": "етап III",
         "text": "серпневий пакет зберегти; нові кроки — після відновлення резервів і допомоги"},
    ],
    table={"header": ["", "IV кв. 2026", "IV кв. 2027", "IV кв. 2028", "IV кв. 2029"],
           "rows": [["ІСЦ, % р/р*"] + [n(Q[f"{y}Q4"]["cpi_yoy"]) for y in range(2026, 2030)],
                    ["Базова інфляція, % р/р*"] + [n(core[str(y)]) for y in range(2026, 2030)],
                    ["Реальний ВВП, % (рік)"] + [n(A[str(y)]["Реальний ВВП, % (рік)"]) for y in range(2026, 2030)],
                    ["Облікова ставка, %"] + [n(Q[f"{y}Q4"]["ir_pol"]) for y in range(2026, 2030)],
                    ["Курс, грн/$ (модель)**"] + [n(Q[f"{y}Q4"]["uah_usd"]) for y in range(2026, 2030)]]},
    footnote=f"* Середнє за квартал (SA); грудень 2026 — {n(K['nowcast_dec_yoy'])}% (наукаст). ** Грн/€ з моделі ÷ EUR/USD "
             f"{n(usd_eur_h, 2)} (жовтневий рівень); аналітики чекають ≈{n(fx_exp['Фінансові аналітики'], 0)} грн/$ через рік — "
             f"курсовий ризик. Інфляція {ret_short} (у 2028 — {n(band28_lo)}–{n(band28_hi)}%). Дані на {DATA_CUTOFF}.",
    notes="Три рішення: ставка, курс без заморожування, пауза в лібералізації (текст — у словнику SPEECH).")

# ----------------------------------------------------------------------------------------------- section 1
add(type="section", section="Огляд", number="01", title="Огляд економіки",
    subtitle="Інфляція прискорюється, резерви тануть, економіка сповільнюється")

add(type="chart", section="Огляд",
    title=f"Зовнішнє середовище стало проінфляційним: нафта ≈${n(brent_last, 0)}, ЄЦБ підвищує ставку",
    image=img("ov_external"), layout="below",
    bullets=[f"Війна на Близькому Сході (з 28.02.2026): Brent (спот) — в середньому ${n(brent_peak, 0)} у {brent_peak_m}, ${n(brent_sep, 0)} у вересні, "
             f"≈${n(brent_last, 0)} за {brent_last_note} (НБУ закладав $80–85); ф'ючерси — ${n(BP['2027Q4'], 0)} наприкінці 2027",
             "ЄЦБ підвищив ставку до 2,5% (червень, вересень); його технічні припущення — ≈3% у 2027–2028",
             "Інфляція в єврозоні — 3,8% у вересні; ЄЦБ чекає пік ≈3,6% у IV кв. 2026 і 3,0% / 2,5% / 2,1% у середньому за 2026–2028"],
    notes="Зовнішній фон гірший, ніж у липневому прогнозі НБУ: дорожча нафта підживлює ціни на пальне в Україні, "
          "а підвищення ставок у світі зменшує простір для пом'якшення. У прогнозі ми беремо ф'ючерсну криву Brent: "
          f"ринок очікує поступового здешевлення нафти (до ${n(BP['2028Q4'], 0)} наприкінці 2028), і це дезінфляційний чинник. "
          "Ціни в історії — лише спот EIA (ф'ючерси найближчого місяця в бекварда́ції були на $10–12 нижчі за спот).")

add(type="chart", section="Огляд",
    title="Інфляція у вересні — 10,0%: пальне, руйнування логістики, прискорення базової",
    image=img("ov_inflation"), layout="below",
    bullets=["+2,1% за місяць: пальне +46,2% р/р, адмінціни +13,6% (проїзд, вода, алкоголь), атаки на склади й логістику",
             "Базова інфляція 8,8% (з 8,1%): оброблені продукти +10,7%, послуги +13,7% (зарплати, оренда)",
             "Сирі продукти прискорилися до 6,7%: менші врожаї овочів, витрати на транспорт і зберігання"],
    notes="Вересень значно перевищив траєкторію НБУ: пальне, атаки на логістику, прискорення базової інфляції.")

add(type="chart", section="Огляд",
    title=f"Очікування підвищені; реальна ставка від очікувань ≈{n(rr_ante_an, 0)}% — гривневі активи поки привабливі",
    image=img("ov_rates"), layout="below",
    bullets=["Очікування домогосподарств 10–14% — вище фактичної інфляції; аналітики підвищили до 7,9% (липень)",
             f"Реальна ставка (як рахує НБУ — від липневих очікувань аналітиків): ≈{n(rr_ante_an)}%; але депозитні ставки великих "
             "банків після липня й вересня майже не зросли — трансмісія слабка",
             "ОВДП (06.10): 1 рік — 15,1%, 2,5 року — 16,5% — ринок чекає високих ставок надовго, але не різкого "
             "посилення; кредити бізнесу +30% р/р (КМП)"],
    notes="Ризик — розбалансування очікувань: домогосподарства очікують інфляцію вище фактичної, а члени КМП "
          "звертають увагу на зростання очікувань фінансових аналітиків.")

add(type="chart", section="Огляд",
    title=f"Активність: врожай підтримав III кв., але промисловість і логістика слабкі, а зарплати +{wages_rng}%",
    image=img("ov_activity"), layout="below",
    bullets=["ВВП II кв.: +0,4% р/р; III кв. — ≈+1% р/р (ІЕД: липень +4%, серпень +1,2% — врожай), «суттєво гірше» "
             "за прогноз НБУ (+2,1%)",
             "Атаки б'ють і по попиту, і по потенціалу (енергетика, логістика, порти; −0,9 в. п. до ВВП-2026 за НБУ)",
             f"Потенціал постраждав сильніше: дефіцит кадрів, зарплати +{wages_rng}% р/р у I пів., +23% у серпні — "
             "розрив ВВП додатний, послуги дорожчають"],
    notes="ВВП слабкий, але потенціал постраждав ще більше, тому розрив додатний і ціни послуг ростуть.")

add(type="chart", section="Огляд",
    title=f"НБУ продає ≈${n(RR['sales_per_month'])} млрд на місяць — резерви впали до $47,1 млрд",
    image=img("ov_fx"), layout="below",
    bullets=[f"Чистий продаж валюти НБУ: $4,8 млрд у серпні, $5,5 млрд у вересні — рекорд року",
             f"Резерви: $51,2 млрд (липень) → $47,1 млрд (вересень) проти $53,8 млрд у прогнозі НБУ на кінець III кв.",
             f"Курс: ≈{n(usd_jun_sep)} грн/$ з червня по вересень, {fx_oct_text} (за рік — +{n(usd_dep_yr, 0)}%); продаж "
             "валюти здебільшого «доносить» допомогу: у вересні уряд конвертував $3,81 млрд оборонного траншу"],
    notes="Чотири місяці курс тримали інтервенції, а надходження допомоги в липні–вересні були меншими за очікувані; "
          "у жовтні НБУ допустив послаблення. Це ключовий аргумент для нашої курсової рекомендації: курс має "
          "поглинати шоки, а не накопичувати їх.")

e26, m26, r26 = (float(bop_t.loc[2026, c]) for c in ("Експорт", "Імпорт", "Перекази"))
ca26, ca28 = float(bop_f.loc[2026, "Поточний рахунок"]), float(bop_f.loc[2028, "Поточний рахунок"])
bb28, loans26, era25 = (float(bop_f.loc[2028, "Широкий базовий баланс"]), float(bop_f.loc[2026, "Очікувані позики"]),
                        float(bop_f.loc[2025, "ERA (кредити)"]))
of26, of28 = float(fis.loc[2026].iloc[0]), float(fis.loc[2028].iloc[0])
add(type="chart", section="Огляд",
    title=f"Платіжний баланс: імпорт у {n(m26 / e26)} раза більший за експорт — розрив покривають позики партнерів",
    image=img("ov_bop"), layout="below",
    bullets=[f"2026: експорт ${n(e26, 0)} млрд, імпорт ${n(m26, 0)} млрд — дефіцит ${n(m26 - e26, 0)} млрд; приватні перекази — "
             f"лише ${n(r26)} млрд",
             f"Поточний рахунок −${n(-ca26, 0)} млрд фінансують партнери: ERA (${n(era25)} млрд у 2025), Ukraine Facility; "
             f"у 2026 НБУ чекає ще ${n(loans26)} млрд позик",
             f"2028: офіційне фінансування ${n(of26, 0)} → ${n(of28, 0)} млрд, поточний рахунок −${n(-ca28, 0)} млрд, широкий "
             f"баланс −${n(-bb28, 0)} млрд → резерви — буфер, лібералізація — поступово"],
    notes="Дані — прогноз НБУ (липень 2026). Широкий базовий баланс = поточний рахунок + ПІІ + офіційні позики. "
          "Поточний рахунок уже враховує гранти, тому його погіршення у 2028 році відображає скорочення допомоги.")

add(type="chart", section="Огляд",
    title="Бюджет залежить від допомоги: $87 млрд у 2026, але надходження затримуються",
    image=img("ov_fiscal"), layout="below",
    bullets=["Дефіцит без грантів ≈35% ВВП у 2026; оборонна складова USL — $33,2 млрд (2026) і $16,7 млрд (2027)",
             f"Бюджетна декларація 2027–2029: дефіцит держбюджету 17,7% ВВП у 2027 і 11,1% у 2028; уряд закладає інфляцію "
             f"8,9% на грудень 2027 (НБУ — {n(nbu_cpi27)}%, ми — {n(Q['2027Q4']['cpi_yoy'])}% у IV кв.)",
             "Частина допомоги прив'язана до ухвалення законів — ризик подальших затримок"],
    notes="Локалізація ОПК коштом USL підтримує внутрішній попит і попит на валюту, але загалом дефіцит скорочується "
          "(35 → 26% ВВП), тож окремого бюджетного імпульсу в прогнозі немає. НБУ в липні, навпаки, закладав «суттєве "
          "нарощування бюджетних стимулів» — це одна з причин, чому наш розрив ВВП у 2027 нижчий за його.")

# ----------------------------------------------------------------------------------------------- section 2
add(type="section", section="Прогноз", number="02", title="Макроекономічний прогноз",
    subtitle="QPM НБУ на Python + короткостроковий прогноз + судження + сценарії")

add(type="process", section="Прогноз",
    title="Модель: QPM НБУ з нашим розширенням — у Python і MATLAB/IRIS",
    steps=[{"head": "Дані", "text": "API НБУ, Держстат, ЄЦБ, Eurostat, Brent; оновлення одним скриптом"},
           {"head": "Фільтр Калмана", "text": "розриви й тренди: ВВП, реальний курс, нейтральна ставка"},
           {"head": "Прогноз із планом", "text": "наукаст ІСЦ, судження з джерелами, ф'ючерси на нафту, прогноз ЄЦБ"},
           {"head": "Політика й ризики", "text": "сценарії, віяло, оптимальна ставка; перевірка в MATLAB/IRIS"}],
    stats=[{"value": "1e−13", "label": "похибка розв'язку рівнянь моделі"},
           {"value": matlab_diff if ML else "1e−5*",
            "label": "розбіжність Python і MATLAB/IRIS на тому самому файлі моделі: фільтр і всі 5 сценаріїв"
                     + ("" if ML else " (* звірка від 21.10 на попередніх даних; після оновлення 25.10 run_check.m треба перезапустити)")},
           {"value": f"{n(bt_cpi['model'].min())}–{n(bt_cpi['model'].max())} в. п.",
            "label": f"помилка ІСЦ на 1–4 кв. уперед, 3 прогони 2025 р. із фактичними зовнішніми умовами "
                     f"(«без змін»: {n(bt_cpi['naive'].min())}–{n(bt_cpi['naive'].max())})"}],
    chips=["Базова + небазова інфляція", "Канал нафти Brent", "Наукаст ІСЦ і курсу", "Судження з джерелами",
           "Віялові графіки", "Оптимальна ставка", "Бектест", "Резерви", "Звірка з MATLAB/IRIS"],
    notes="Ми взяли шаблон QPM від НБУ, переписали його на Python і розширили: окремо базова й небазова інфляція "
          "та канал світових цін на нафту. Python дав автоматизацію даних, віяла, оптимальну політику й бектест. "
          "Усі розрахунки — у Python; той самий файл моделі, дані й плани ми проганяємо в MATLAB/IRIS для звірки: "
          "фільтр і всі сценарії збігаються до п'ятого знака."
          + (" Графіки сценаріїв і функцій відгуку на слайдах — з MATLAB." if ML else
             " Графіки на слайдах — з Python (звірку з MATLAB слід повторити після останнього оновлення даних)."))

add(type="chart", section="Прогноз",
    title="Наше розширення QPM: нафта змінює небазові ціни, а ставка на нафтовий шок реагує слабко",
    image=ml_img("ml_irf_oil", "irf_res_dl_roil_beta"), layout="below",
    bullets=["ІСЦ = базова інфляція + зміна відносних цін небазових товарів; крива Філіпса НБУ описує базову",
             "Brent +20% → ІСЦ +0,3 в. п. упродовж року; правило реагує на загальний ІСЦ, але ставка — лише +0,2 в. п.",
             "З вагою нафти 0 функції відгуку збігаються з шаблоном НБУ (тест); поділ на базову й небазову інфляцію лишається"],
    notes="Ми розділили інфляцію на базову і небазову: крива Філіпса з шаблону НБУ тепер описує базову інфляцію "
          "(дані Держстату про базовий ІСЦ), а небазові ціни реагують на реальну ціну нафти в євро і на курс. "
          "Вага 0,016 — калібрування, а не оцінка: пальне ≈4% кошика × частка нафти в його ціні ≈40%; з інерцією "
          "рівняння +20% нафти дають ≈+0,3 в. п. до інфляції (чутливість: 0,2–0,5 в. п. за ваги 0,01–0,025). "
          "Коефіцієнти шаблону не змінювалися." + (" Графік побудовано в MATLAB/IRIS." if ML else ""))

judg_rows = [["Інфляція IV кв. 2026", f"Наукаст ІСЦ і базового ІСЦ (тренд + сезонність − 0,1 в. п.): грудень — {n(K['nowcast_dec_yoy'])}% "
              f"і {n(nc_core_dec)}% р/р; в IV кв. фіксуємо обидва ряди", {"text": "Держстат, API НБУ", "url": SRC["api"]["url"]}],
             ["ВВП III кв. 2026", "+1,1% кв/кв SA (≈+1% р/р): ІЕД — липень +4%, серпень +1,2%; КМП — «суттєво гірше» за прогноз НБУ (+2,1%)",
              {"text": "ІЕД, підсумки КМП", "url": SRC["kmp"]["url"]}]]
for j in cfg.JUDGMENTS:
    label = {"res_dl_cpi_c": "Шок витрат 2027", "res_dl_rnc": "Адмінціни та акцизи", "res_l_gdp_gap": "Бюджетний імпульс",
             "res_prem_uip_gap": "Премія за ризик", "res_dl_gdp_tnd": "Потенційний ВВП"}[j["shock"]]
    why = j["why"].split(" (")[0]
    why = why[len(label) + 2:] if why.startswith(label + ":") else why
    judg_rows.append([label, why[0].upper() + why[1:], {"text": j["source"].split(";")[0].split(" (")[0], "url": j["url"]}])
judg_rows.append(["Бюджет", "Без окремого імпульсу: дефіцит без грантів 35 → 26% ВВП, оборонна частина USL $33,2 → $16,7 млрд; "
                  "локалізація ОПК коштом USL частково компенсує", {"text": "НБУ, макропрогноз липень 2026", "url": SRC["nbu_fc"]["url"]}])
judg_rows.append(["Курс гривні до €", f"IV кв. 2026 — за фактом жовтня й останнім курсом ({n(FXN['2026Q4']['level'], 1) if FXN else '—'} грн/€); далі допустиме "
                  f"послаблення (цільовий темп) 4% у 2027, 3% у 2028; фактичний — з моделі (≈{n(fx_yr, 0)}% на рік); EUR/USD {n(usd_eur_h, 2)} без змін",
                  {"text": "Офіційний курс НБУ, ЄЦБ", "url": SRC["api"]["url"]}])
judg_rows.append(["Нафта Brent", f"Спот до вересня; IV кв. 2026 ${n(BP['2026Q4'], 0)} (жовтень — спот, далі ф'ючерс); ф'ючерсна крива ({DATA_CUTOFF[:5]}): "
                  f"${n(BP['2027Q4'], 0)} (кінець 2027) → ${n(BP['2028Q4'], 0)} (кінець 2028)",
                  [SRC["eia"], {"text": ", "}, {"text": "NYMEX", "url": SRC["fut"]["url"]}]])
judg_rows.append(["Єврозона", "HICP 3,0 / 2,5 / 2,1%, ВВП 0,9 / 1,4 / 1,5%, ставка ЄЦБ ≈3% у 2027–2028", {"text": "ЄЦБ, вер. 2026", "url": SRC["ecb_proj"]["url"]}])
add(type="table", section="Прогноз", title="Припущення та судження базового сценарію — кожне з джерелом",
    table={"header": ["Чинник", "Що закладено", "Джерело"], "rows": judg_rows, "colw": [2.4, 7.5, 2.43], "font": 12, "rowH": 0.44},
    notes="Модель має лише кілька основних рівнянь, тому все, чого в ній немає — енергетика, бюджет, допомога, "
          "тарифи, — входить через явні судження. Кожне судження має кількісне обґрунтування та джерело. Адмінціни: "
          "у середньому за 2016–2026 роки загальна інфляція перевищувала базову на 1,7 в. п. на рік, і НБУ закладає "
          "таку саму різницю на 2027–2028 роки.")

nc = table_csv("cpi_nowcast")
add(type="chart_table", section="Прогноз",
    title=f"Короткостроковий прогноз: інфляція зросте до ≈{n(K['nowcast_dec_yoy'])}% у грудні",
    image=img("fc_nowcast"),
    table={"header": ["Місяць", "Тренд", "Сезон", "Поправка", "м/м", "р/р"], "colw": [1.12, 0.75, 0.8, 1.05, 0.7, 0.66],
           "rows": [[i, n(r["Тренд (SA)"], 2), n(r["Сезонний фактор"], 2), n(r["Судження"], 1),
                     n(r["ІСЦ м/м, прогноз"], 2), n(r["ІСЦ р/р, прогноз"])] for i, r in nc.iterrows()]},
    bullets=[f"Ефект бази: у {base_span} ціни зросли лише на {n(base_effect)}% → річна інфляція механічно зростає",
             f"Тренд {n(nc_trend, 2)}% на місяць (без сезонності) — це ≈{n(((1 + nc_trend / 100) ** 12 - 1) * 100, 0)}% "
             "у річному вимірі; вересневий стрибок частково разовий (−0,1 в. п./міс.)",
             f"Грудень {n(K['nowcast_dec_yoy'])}% — вище липневого прогнозу НБУ (10%); базова тим самим методом — "
             f"{n(nc_core_dec)}% (НБУ: {n(nbu_val('Базова інфляція', '2026Q4'))}%)"],
    notes="Для поточного кварталу беремо трендовий темп і сезонність; поправка −0,1 в. п. — разові ефекти вересня.")

peak_when = "наприкінці 2026" if _peak_q == "2026Q4" else ("на початку 2027" if _peak_q.startswith("2027Q1") else f"у {qlabel(_peak_q)}")
add(type="chart", section="Прогноз",
    title=f"Інфляція досягне піку {peak_when} і повернеться до цілі у {tgt_year} — у межах горизонту політики",
    image=img("fc_fan"), layout="below",
    bullets=[f"Пік — {qlabel(_peak_q)}: ≈{n(SC['Базовий']['ІСЦ пік'])}% у середньому за квартал (у грудні — ≈{n(K['nowcast_dec_yoy'])}% за місяць); "
             f"{n(Q['2027Q4']['cpi_yoy'])}% у IV кв. 2027 (НБУ: {n(nbu_cpi27)}% у грудні); нижче 5% — з {qlabel(back_q)}, "
             f"у 2028 — {n(band28_lo)}–{n(band28_hi)}% (дешевша нафта, слабкий попит), ≈5% — у {tgt_year}",
             f"Ставка: {pr(REC['rate'])}% до середини 2027 → {n(Q['2027Q4']['ir_pol'])}% наприкінці 2027 → "
             f"{n(Q['2028Q4']['ir_pol'])}% — 2028 → {n(Q['2029Q4']['ir_pol'])}% — 2029",
             f"Невизначеність велика: з імовірністю 70% інфляція наприкінці 2027 — від {n(fan['2027Q4']['q15'])} до "
             f"{n(fan['2027Q4']['q85'])}%"],
    notes="Ціль НБУ — 5% без діапазону відхилень, горизонт політики — до трьох років (Основні засади ГКП, 2024). "
          "Тому після рішення ставка йде траєкторією, що повертає інфляцію до 5% на горизонті, а не за механічним "
          f"правилом: за правилом інфляція наприкінці 2029 була б лише {n(rule29)}%. Віяло — стохастичні симуляції з "
          "волатильністю шоків 2023–2026 років; широке віяло — чесне відображення воєнної невизначеності.")

add(type="chart", section="Прогноз",
    title=f"Базова інфляція у 2027 — {core_vs_nbu}: {n(core['2027'])}% у IV кв. (≈{n(core_dec27)}% у грудні) проти {n(nbu_core27)}% у НБУ",
    image=img("fc_core"), layout="right",
    bullets=["Наша базова — середнє за IV кв., у НБУ — грудень; для порівняння показуємо й грудневий еквівалент (інтерполяція)",
             f"Що її тримає в моделі: додатний розрив ВВП, перенесення вересневого шоку витрат і курсу; у 2027 — шок витрат "
             "опалювального сезону (судження за оцінкою НБУ)",
             f"Загальна: {n(Q['2027Q4']['cpi_yoy'])}% у IV кв. 2027 (НБУ {n(nbu_cpi27)}% у грудні) — тарифи й акцизи додають "
             "≈1,7 в. п. на рік, дешевша нафта (ф'ючерси) — віднімає",
             f"2028: базова {n(core['2028'])}% (НБУ {n(nbu_core28)}%) — слабкий попит → простір для зниження ставки з II пів. 2027"],
    notes="Базову інфляцію порівнюємо з НБУ коректно: наша цифра — середнє за квартал, у НБУ — на кінець кварталу, тому "
          "наводимо грудневий еквівалент. Ринку праці в моделі немає: тиск на базову інфляцію йде через розрив ВВП, "
          "курс і шоки витрат. Загальна інфляція близька до НБУ, бо дешевша за ф'ючерсами нафта частково компенсує "
          "тарифи й акцизи. У 2028 базова інфляція опускається нижче цілі — як і в прогнозі НБУ, — тому орієнтир "
          "на зниження ставки з другого півріччя 2027 року.")

gap27 = sum(Q[f"2027Q{i}"]["l_gdp_gap"] for i in range(1, 5)) / 4
nbu_gap27 = float(read_ir_chart("2.18").iloc[:, 0].loc[2027])
add(type="chart", section="Прогноз",
    title=f"Економіка слабка, але потенціал постраждав ще більше: розрив ≈{n(gap26)}% зараз, ≈{n(gap27)}% у 2027 (НБУ: {n(nbu_gap27)}%)",
    image=img("fc_gap_vs_nbu"), layout="right", side_image=img("fc_trends"),
    bullets=[f"ВВП: {n(VS['2026']['ВВП, наш'])}% / {n(VS['2027']['ВВП, наш'])}% / {n(VS['2028']['ВВП, наш'])}% у 2026–2028 "
             f"(НБУ: {n(VS['2026']['ВВП, НБУ липень'])} / {n(VS['2027']['ВВП, НБУ липень'])} / {n(VS['2028']['ВВП, НБУ липень'])}%)",
             "Мінекономіки теж погіршує прогноз: ≈0,5% у 2026, 0,8–1% у 2027",
             "Розрив додатний → послуги дорожчають; у 2027 висока реальна ставка охолоджує попит; бюджетного стимулу не "
             "закладаємо: дефіцит скорочується з 35 до 26% ВВП"],
    notes="Одна історія: ВВП слабкий, але потенціал постраждав ще більше, тому розрив додатний і ціни послуг ростуть.")

scn = SC
fg, hw, oil, bs = (scn[k] for k in ("Дефіцит фінансування", "Важка зима", "Нафта $120", "Базовий"))
fx_dep = (fg["Курс IV кв. 2027, грн/$"] / bs["Курс IV кв. 2027, грн/$"] - 1) * 100
add(type="chart_table", section="Прогноз", title="Сценарії: головні ризики — дефіцит фінансування, курс і очікування, а не нафта",
    image=ml_img("ml_scenarios", "fc_scenarios"), layout="stack",
    table={"header": ["Сценарій", "ІСЦ пік", "ІСЦ IV кв. 27", "Ставка пік", "грн/$ IV кв. 27", "ВВП 2027"],
           "rows": [[k, n(v["ІСЦ пік"]), n(v["ІСЦ IV кв. 2027"]), n(v["Ставка пік"]), n(v["Курс IV кв. 2027, грн/$"]),
                     n(v["ВВП 2027, % (рік)"])] for k, v in scn.items()]},
    bullets=[f"Дефіцит фінансування: гривня на ≈{n(fx_dep, 0)}% слабша (≈{n(fg['Курс IV кв. 2027, грн/$'], 0)} грн/$) → "
             f"інфляція до {n(fg['ІСЦ пік'])}%, ставка до {n(fg['Ставка пік'])}%",
             f"Важка зима: інфляція до {n(hw['ІСЦ пік'])}%, ставка до {n(hw['Ставка пік'])}%, ВВП 2027 — {n(hw['ВВП 2027, % (рік)'])}%",
             f"Нафта $120: +{n(oil['ІСЦ пік'] - bs['ІСЦ пік'])} в. п. до піку інфляції, ставка майже не змінюється",
             f"Ще три ризики (додаток): курс, як чекає ринок → ІСЦ IV кв. 2027 ≈{n(RX['Курс як чекає ринок']['ІСЦ IV кв. 2027'], 0)}%; "
             f"розбалансування очікувань → ≈{n(RX['Розбалансування очікувань']['ІСЦ IV кв. 2027'], 0)}%; ПДВ 21% → "
             f"+{n(RX['ПДВ 21% з 2027']['ІСЦ пік'] - bs['ІСЦ пік'])} в. п. до піку"],
    notes="Сценарії побудовано поверх базового: однакове рішення в жовтні, далі правило Тейлора реагує на шоки "
          "сценарію навколо базової траєкторії ставки. Величини шоків — судження команди, підібрані під описані події. "
          + ("Графік побудовано в MATLAB/IRIS за тими самими планами, що й у Python. " if ML else "")
          + "Висновок: головний ризик для інфляції — "
          "курс і резерви; нафтовий шок — це перший раунд для цін пального, він майже не потребує реакції ставки.")

add(type="matrix", section="Прогноз", title="Матриця ризиків: баланс зміщений у бік вищої інфляції",
    rows=["Високий", "Середній", "Низький"], cols=["Слабкий", "Помірний", "Сильний"],
    cells={
        ("Високий", "Помірний"): [("↑", "Тривала нафта ≈$100"), ("↓", "Блокада портів: дешевше продовольство")],
        ("Високий", "Сильний"): [("↑", "Атаки на енергетику взимку"), ("↑", "Затримки допомоги, резерви < $45 млрд")],
        ("Середній", "Помірний"): [("↑", "Підвищення ПДВ / акцизів"), ("↓", "Охолодження попиту від обстрілів")],
        ("Середній", "Сильний"): [("↑", "Розбалансування очікувань домогосподарств"), ("↑", "Зарплатна спіраль (дефіцит кадрів)")],
        ("Низький", "Сильний"): [("↓", "Перемир'я, повернення мігрантів"), ("↑", "Ескалація, прорив фронту")],
        ("Низький", "Помірний"): [("↑", "Швидше підвищення ставок ЄЦБ")],
        ("Середній", "Слабкий"): [("↓", "Зміцнення євро — дешевший імпорт з ЄС")],
    },
    notes="↑ — ризик вищої інфляції, ↓ — нижчої. Більшість сильних і ймовірних ризиків — проінфляційні; це "
          "аргумент на користь підвищення ставки зараз.")

# ----------------------------------------------------------------------------------------------- section 3
add(type="section", section="Рекомендації", number="03", title="Рекомендації для Правління НБУ",
    subtitle="Процентна політика, курс і валютні обмеження — як єдиний пакет")

add(type="bullets2", section="Рекомендації", title="Рамка рішення: ціль 5% на горизонті до 3 років; у вересні КМП розділився",
    groups=[{"head": "Мета і режим", "items": [
        "Мета — цінова стабільність; також сприяння фінстабільності й зростанню",
        "Ціль — 5% «на належному горизонті політики (до 3-х років)»",
        "Гнучке ІТ з керованою гнучкістю курсу"]},
        {"head": "Інструменти", "items": [
            "Облікова ставка; 3-міс. депсертифікати — з 07.08 через тендери",
            "Обсяги ДС залежать від ліміту банків, прив'язаного до строкових депозитів",
            "Інтервенції згладжують курс; обмеження — за Стратегією 2023"]},
        {"head": "КМП у вересні", "items": [
            "Рішення +0,5 в. п. до 16%; троє — за 15,5%",
            "Далі: 7 — тримати 16%, 2 — ще одне підвищення, 1 — знижувати",
            "Вересневий ІСЦ 10,0% — вище прогнозу НБУ: ми — за +1 в. п."]}],
    quote=f"Наша відповідь на питання конкурсу: облікова ставка — {pr(REC['rate'])}% з утриманням до середини 2027 р.; "
          "депсертифікати — обмежити обсяги тендерів, щоб підвищення дійшло до депозитних ставок; офіційний курс — "
          "не заморожувати, лише згладжувати коливання; валютні обмеження — серпневий пакет зберегти, III етап — після "
          "відновлення резервів.",
    notes="Рамка з Основних засад ГКП (2024) і Закону «Про НБУ». Позиції КМП — з підсумків дискусії 28.09.2026.")

po_rows = []
for k, v in PO.items():
    po_rows.append([k + (" ★" if k == REC["option"] else ""), n(v["Ставка IV кв. 2026"]), n(v["Ставка IV кв. 2027"]),
                    n(v["ІСЦ IV кв. 2027"]), n(v["ВВП 2027, %"]), n(v[LOSS], 0)])
opt = K["optimal_paths"]
_best = sorted({float(pr_opt(BEST[k]).replace(",", ".")) for k in BEST})
best_rng = pr(_best[0]) if len(_best) == 1 else f"{pr(_best[0])}–{pr(_best[-1])}"
# how much the recommended option loses to the best one under risks (expected loss, P1 and P2), in % of the best
_E = {pk: {str(float(k)): v for k, v in ROB["E"][pk].items()} for pk in ("P1", "P2")}
rob_gap_pct = max((_E[pk][str(float(REC["rate"]))] / min(_E[pk].values()) - 1) * 100 for pk in _E)
add(type="chart_table", section="Рекомендації",
    title=f"Варіанти рішення: мінімум втрат у моделі — {best_hold_rng}%; обираємо {pr(REC['rate'])}% і готові йти далі",
    image=img("fc_policy"), layout="stack",
    table={"header": ["Рішення (до середини 2027)", "Ставка IV кв. 26", "Ставка IV кв. 27", "ІСЦ IV кв. 27", "ВВП 2027", "Втрати"],
           "rows": po_rows},
    bullets=[f"Втрати: відхилення інфляції від 5%, розрив ВВП, різкі зміни ставки; адмінціни — з вагою {ADMIN}% (вони ростуть "
             "щороку, але це перший раунд) — той самий принцип для рішення й усієї траєкторії",
             f"Оптимальна траєкторія: {n(opt['λ = 1']['2026Q4'])}% зараз ({n(opt['λ = 2']['2026Q4'])}–{n(opt['λ = 0.5']['2026Q4'])}% "
             f"залежно від згладжування), ≈{n(opt['λ = 1']['2027Q1'])}% у I кв. 2027",
             f"Під ризиками (10 сценаріїв, два набори ймовірностей) найменші очікувані втрати — {rob_best}%; "
             + (f"{pr(REC['rate'])}% — серед них (різниця з мінімумом < 0,5% втрат)" if rob_gap_pct < 0.5 else
                f"{pr(REC['rate'])}% поступається їм на ≈{n(rob_gap_pct, 0)}% втрат — у межах точності суджень про ваги й імовірності"),
             f"Наш вибір — {pr(REC['rate'])}% (+1 в. п., найбільший крок НБУ за 2025 р.) і готовність до +0,5 у грудні, коли буде "
             "жовтневий прогноз НБУ і дані за жовтень"],
    notes="Кожен варіант: ставка утримується до середини 2027, далі — траєкторія, яка повертає інфляцію до 5% на "
          "горизонті політики. Втрати — та сама функція, що й в оптимізації: квадрати відхилень інфляції від цілі, "
          "половина квадрата розриву ВВП і квадрати змін ставки за IV кв. 2026 – 2029; наукаст IV кв. входить у всі варіанти "
          "однаковими шоками. Рекомендація — рішення команди з урахуванням моделі, а не її «вихід»: модель дає діапазон, "
          "а крок у пункт усередині нього обираємо з огляду на ризики й прецеденти.")

add(type="reco", section="Рекомендації", title=f"Облікова ставка: підвищити до {pr(REC['rate'])}% і утримувати до середини 2027",
    big=f"{pr(REC['rate'])}%", big_label=f"{n(REC['change_pp'], 1, True)} в. п. з 30.10.2026",
    groups=[{"head": "Чому підвищити", "items": [
        f"Вересень — 10,0%, значно вище прогнозу НБУ; у грудні — ≈{n(K['nowcast_dec_yoy'], 0)}%; ризики зміщені вгору",
        f"Базова інфляція прискорилася до 8,8% і за наукастом сягне ≈{n(nc_core_dec)}% у грудні — вторинні ефекти вже є; "
        f"очікування домогосподарств 10–14%",
        f"Курс: якщо гривня слабшатиме, як чекає ринок, ІСЦ IV кв. 2027 — ≈{n(FXR['cpi_2027Q4'], 0)}%; кожні +0,5 в. п. зараз "
        f"знижують його на ≈{n(fx_per_half)} в. п.",
        "До депозитів: знизити коефіцієнт використання ліміту 3-міс. ДС (прив'язаного до строкових вкладів)"]},
        {"head": "Чому 17, а не 16,5 чи 17,5", "items": [
            f"Модель: оптимум ≈{n(opt['λ = 1']['2026Q4'])}%, під ризиками — {rob_best}%; ринок (ОВДП, курсові очікування) не чекає "
            "різкого посилення — ми рішучіші за ринок, обережніші за модель",
            "+1 в. п. — як у січні й березні 2025; +1,5 одразу — надмірний сигнал за слабкого ВВП і до оновленого прогнозу НБУ",
            "16,5% — якби жовтневі дані показали сповільнення базової інфляції і стабільні очікування"]},
        {"head": "Орієнтири (forward guidance)", "items": [
            f"Не знижувати щонайменше до III кв. 2027; за базовим прогнозом далі — ≈{n(half(Q['2027Q4']['ir_pol']))}% наприкінці "
            f"2027 і ≈{n(half(Q['2028Q4']['ir_pol']))}% — 2028",
            "Наступний крок радше вгору: ще +0,5 у грудні, якщо базова без сезонності ≥ 0,6% м/м або посиляться "
            "курсові очікування",
            "Швидше пом'якшення — якщо базова інфляція < 7% і очікування знижуються"]}],
    notes="Рекомендація — рішуче підвищення на 1 в. п. з упередженням до подальшого посилення і чіткими умовами.")

add(type="chart", section="Рекомендації",
    title=f"Курс і резерви: за надходжень липня–вересня резерви на кінець 2026 — ${n(RES['Як у липні–вересні'], 0)} млрд "
          f"({n(RESM['Як у липні–вересні'])} міс. імпорту)",
    image=img("fc_reserves"), layout="right",
    bullets=[f"Продаж НБУ ≈${n(RR['sales_per_month'])} млрд/міс, надходження ≈${n(RR['inflows_per_month'])} млрд/міс. НБУ (липень) "
             f"чекав ${n(RN['end2026'])} млрд на кінець 2026 — для цього треба ≈${n(RN['inflow_needed_per_month'], 0)} млрд/міс",
             f"Наші сценарії на кінець 2026: ${n(RES['Надолуження допомоги'], 0)} / {n(RES['Як у липні–вересні'], 0)} / "
             f"{n(RES['Затримка допомоги'], 0)} млрд = {n(RESM['Надолуження допомоги'])} / {n(RESM['Як у липні–вересні'])} / "
             f"{n(RESM['Затримка допомоги'])} міс. імпорту 2027 р.; центральний — ${n(RES['Як у липні–вересні'], 0)} млрд, "
             "надолуження — якщо Рада ухвалить закони під допомогу",
             f"Ринок чекає ≈{n(fx_exp['Фінансові аналітики'], 0)} грн/$ через рік (≈{n(market_dep_12m, 0)}% послаблення); модель — "
             f"≈{n(Q['2027Q3']['uah_usd'])} грн/$ (≈{n(model_dep_12m, 0)}%; до євро ≈{n(fx_yr, 0)}% на рік); якщо правий ринок, "
             f"ІСЦ IV кв. 2027 — ≈{n(FXR['cpi_2027Q4'], 0)}%",
             f"Рекомендація: не фіксувати курс — жовтневе послаблення до {n(usd_oct_max, 2)} грн/$ показує, що амортизатор працює; "
             "інтервенції — лише згладжувати. Резерви залежать від ритму допомоги (продаж валюти її «доносить»), тому "
             "захищає їх пауза в лібералізації"],
    notes="Простий балансовий розрахунок: резерви = попередні + офіційні надходження − продаж валюти НБУ. "
          "Підхід «1% курсу = X млрд інтервенцій» не використовуємо: у моделі змінна інтервенцій не пов'язана з резервами, "
          "а на даних продаж валюти визначається структурним дефіцитом і ритмом допомоги, а не відхиленням курсу. "
          "Курс грн/$ у моделі = грн/€ ÷ EUR/USD, який утримуємо на жовтневому рівні.")

add(type="chart", section="Рекомендації",
    title="Валютні обмеження: серпневий пакет зберегти, наступні кроки — на паузу",
    image=img("ov_fx_households"), layout="right",
    bullets=[f"Після підвищення ліміту (50 → 200 тис. грн/міс) купівля валюти населенням зросла з ${n(hh_jul, 2)} до "
             f"${n(hh_sep, 2)} млрд/міс (+{n((hh_sep / hh_jul - 1) * 100, 0)}%) — керовано",
             "Стратегія НБУ: кроки — за передумовами (резерви, очікування, реальна ставка), а не за календарем",
             f"Пауза для III етапу (капітальні операції, операції населення) до: резерви ≥ $50 млрд (≈{n(50 / IMPORTS_PER_MONTH)} міс. імпорту), "
             "ритмічна допомога, стабільні очікування",
             "Продовжити стимулюючу лібералізацію (нові інвестиції, «додатковий» ліміт) — вона залучає валюту",
             "Нові обмеження не запроваджувати: вони не замінюють макрокоригування"],
    notes="Рекомендація спирається на Стратегію пом'якшення валютних обмежень (2023): пріоритет поточних операцій "
          "над капітальними і можливість призупинення кроків за несприятливих умов.")

add(type="bullets2", section="Рекомендації", title="Комунікація: «ставка — якір, курс — амортизатор»",
    groups=[{"head": "Ключові меседжі", "items": [
        f"НБУ підвищує ставку на {n(REC['change_pp'], 0)} в. п., щоб інфляція повернулася до цілі у {tgt_year} році",
        "Курс не заморожений: НБУ згладжує коливання, але не фіксує рівень",
        "Обмежені обсяги депсертифікатів — щоб підвищення дійшло до ставок за депозитами"]},
        {"head": "Орієнтир для ринку", "items": [
            f"Утримання {pr(REC['rate'])}% щонайменше до середини 2027",
            "Пом'якшення — з другого півріччя 2027, якщо інфляція й очікування знижуватимуться",
            "Готовність до додаткових заходів, якщо резерви й курс опиняться під тиском"]},
        {"head": "Чого уникати", "items": [
            "Обіцянок конкретного курсу",
            "Сигналів про швидке зниження ставки до стабілізації допомоги"]}],
    quote=f"Проєкт пресрелізу: «Правління НБУ ухвалило рішення підвищити облікову ставку до {pr(REC['rate'])}% з огляду на "
          "прискорення базової інфляції, зміщення ризиків угору й ризики для курсових очікувань. НБУ не знижуватиме ставку "
          "щонайменше до III кварталу 2027 року, готовий за потреби до подальших кроків і допускатиме більшу гнучкість "
          "курсу, згладжуючи надмірні коливання».",
    notes="Комунікація має пояснити логіку пакета: ставка — якір очікувань, курс — амортизатор шоків.")

add(type="summary_end", section="Рекомендації", title="Підсумок",
    items=[f"Підвищити облікову ставку до {pr(REC['rate'])}% та утримувати щонайменше до середини 2027",
           "Не заморожувати курс; обмежити обсяги тендерів депсертифікатів, щоб підвищення дійшло до депозитів",
           "Пауза в лібералізації валютних обмежень до відновлення резервів і допомоги",
           f"Базовий прогноз: інфляція ≈{n(K['nowcast_dec_yoy'])}% у грудні 2026, {n(Q['2027Q4']['cpi_yoy'])}% у IV кв. 2027, "
           f"{ret_short}"],
    notes="Дякуємо! Готові до запитань.")

# ----------------------------------------------------------------------------------------------- appendix
add(type="section", section="Додатки", number="", title="Додатки", subtitle="")
_rx_why = {"Курс як чекає ринок": f"Гривня слабшає на {n(FXR['dep_per_year'])}% на рік до долара — як чекають аналітики (НБУ)",
           "Розбалансування очікувань": "Базова інфляція вища на 1 в. п. (кв/кв, у річному вимірі) щокварталу 2027 р.",
           "ПДВ 21% з 2027": "Разове підвищення цін на ≈0,5% (оцінка НБУ: +0,4–0,7 в. п. до інфляції)"}
add(type="table", section="Додатки", title="Додаткові ризики: курс, очікування, ПДВ — ставка реагує за правилом",
    table={"header": ["Ризик", "Що закладено", "ІСЦ IV кв. 27", "ІСЦ пік", "Ставка пік", "грн/$ IV кв. 27"],
           "colw": [2.5, 4.9, 1.25, 1.15, 1.2, 1.33], "font": 12, "rowH": 0.55,
           "rows": [["Базовий", f"Рішення {pr(REC['rate'])}% і траєкторія повернення до цілі", n(bs["ІСЦ IV кв. 2027"]),
                     n(bs["ІСЦ пік"]), n(bs["Ставка пік"]), n(bs["Курс IV кв. 2027, грн/$"])]]
                   + [[k, _rx_why[k], n(v["ІСЦ IV кв. 2027"]), n(v["ІСЦ пік"]), n(v["Ставка пік"]),
                       n(v["Курс IV кв. 2027, грн/$"])] for k, v in RX.items()]},
    notes="Розраховано поверх базового сценарію, як і основні сценарії: правило Тейлора реагує на нові шоки. "
          "Найсильніший — курс: модель передає послаблення гривні в ціни швидко (перенос у шаблоні ≈0,75 за рік — верхня "
          "межа; в останні роки фактичний перенос був нижчим), тому реальний ефект, імовірно, менший.")
_RB = K["robust"]
_rl1 = _RB["losses"]["λ = 1"]
_ro = [str(float(r)) for r in _RB["options"]]
_pp = _RB["probs"]
_rs = ROB


def _mark(vals, best):
    return [f"{n(v, 0)}{' ●' if k == best else ''}" for k, v in vals]


_rob_rows = [[s, f"{n(_pp['P1'][s] * 100, 0)} / {n(_pp['P2'][s] * 100, 0)}"]
             + [n(_rl1[s][r], 0) for r in _ro] for s in _rl1]
for _pk in ("P1", "P2"):
    _e = {str(float(k)): v for k, v in _rs["E"][_pk].items()}
    _bk = str(float(_rs["best_E"][_pk]))
    _rob_rows.append([f"Очікувані втрати ({_pk})", ""] + _mark([(r, _e[r]) for r in _ro], _bk))
_rg = {str(float(k)): v for k, v in _rs["regret"].items()}
_rob_rows.append(["Максимальний жаль", ""] + _mark([(r, _rg[r]) for r in _ro], str(float(_rs["best_regret"]))))
add(type="table", section="Додатки",
    title=f"Стійкість рішення: під ризиками найменші очікувані втрати — {rob_best}%",
    table={"header": ["Сценарій (втрати, λ = 1)", "Ймовірн., % P1 / P2"] + [f"{pr(float(r))}%" for r in _ro],
           "colw": [3.6, 2.13, 1.32, 1.32, 1.32, 1.32, 1.32], "font": 11, "rowH": 0.3, "rows": _rob_rows},
    notes="Кожен варіант: рішення в жовтні й утримання, далі траєкторія повернення до цілі; у ризикових сценаріях "
          "правило реагує навколо траєкторії варіанта. Втрати — функція оптимізації (λ = 1). P1 — ризики зміщені вгору, "
          "P2 — збалансовані; «Слабкий попит» і «Базова сповільнюється» — дезінфляційні противаги. Максимальний жаль — "
          "найбільше відставання від найкращого варіанта в будь-якому сценарії. ● — найкращий варіант у рядку.")
add(type="equations", section="Додатки", title="Додаток 1. Модель: QPM НБУ + розширення команди",
    eqs=[("Попит (розрив ВВП)", "ŷₜ = 0,7·ŷₜ₋₁ − 0,4·MCIₜ + 0,3·ŷ*ₜ + εʸ;   MCI = −0,5·z̃ + 0,3·r̃ + 0,2·prem̃"),
         ("Базова інфляція (Філіпс)", "πᶜₜ = 0,4·πᶜₜ₋₁ + 0,6·Eₜπᶜₜ₊₁ + 0,3·rmcₜ + εᶜ;   rmc = 0,6·ŷ + 0,4·z̃,  z = s − pᶜ + p*"),
         ("Небазові ціни (наше)", "Δrncₜ = 0,3·Δrncₜ₋₁ + 0,016·(Δoilₜ + 4·Δzₜ) + εⁿᶜ;   πₜ = πᶜₜ + Δrncₜ"),
         ("Курс (керована гнучкість)", "sₜ = β·s̄ₜ + (1−β)·sᵘⁱᵖₜ,  β = 0,7;   sᵘⁱᵖ = Eₜsₜ₊₁ + (i* + prem − i)/4"),
         ("Ставка (правило Тейлора)", "iₜ = 0,8·iₜ₋₁ + 0,2·(r̄ₜ + Eπₜ₊₁ + (Eπₜ₊₃ − π*) + 0,5·ŷₜ) + εⁱ")],
    bullets=["Калібрування — шаблон НБУ (Grui, Vdovychenko, 2019); вага нафти — наша",
             "Темпи в моделі — 100·ln-різниці, на слайдах — % р/р: π* = 4,88 = 5% р/р",
             "Тренди й розриви — фільтр Калмана, 2016–2026; злам 2022: шок потенційного ВВП, розрив −18% у II кв."],
    notes="ŷ — розрив ВВП, z̃ — розрив реального курсу (за базовими цінами), r̃ — розрив реальної ставки, prem — премія "
          "за ризик, oil — реальна ціна Brent у євро, rnc — відносна ціна небазових товарів. З вагою нафти 0 модель "
          "збігається з шаблоном НБУ.")
add(type="chart", section="Додатки", title="Додаток 2. Реакція на шок ставки залежить від контролю над курсом (β)",
    image=ml_img("ml_irf_rate", "irf_res_ir_tlr_beta"), layout="full", bullets=[],
    notes="Чим сильніше НБУ контролює курс (β → 1), тим слабше ставка впливає на курс і інфляцію — валютний канал головний. "
          + ("Функції відгуку побудовано в MATLAB/IRIS." if ML else "Функції відгуку побудовано в Python; з вагою нафти 0 вони "
             "збігаються з опублікованими MATLAB-результатами шаблону (тест)."))
add(type="chart", section="Додатки",
    title="Додаток 3. Ставка має лишатися високою, доки прогноз інфляції вищий за ціль на 3–4 в. п.",
    image=img("fc_rate_drivers"), layout="right",
    bullets=["Головний чинник — прогноз інфляції на 3 квартали вперед вище цілі",
             "Внесок розриву ВВП у правило невеликий (вага 0,5) — головне прогноз інфляції; але додатний розрив підтримує ціни послуг",
             "З другого півріччя 2027 внесок інфляції зменшується → простір для зниження ставки",
             "Лінія — наша траєкторія ставки (повернення до цілі), стовпці — чинники правила Тейлора"],
    notes="Графік показує, на скільки ставка має бути вищою за нейтральну за правилом Тейлора і чому.")
if ML:
    add(type="chart", section="Додатки", title=f"Додаток 4. Python і MATLAB/IRIS дають той самий прогноз (розбіжність {matlab_diff})",
        image=img("fc_matlab_check"), layout="below",
        bullets=["Один файл моделі model/model.model, ті самі дані, параметри й плани всіх 5 сценаріїв",
                 "Фільтр Калмана 2016–2026 і прогнози до 2029 збігаються з точністю до округлення",
                 "Збірка однією командою: python build.py → MATLAB → звірка → графіки → презентація"],
        notes="Лінії — розрахунок у Python, кружки — у MATLAB R2026b з IRIS. Це підтверджує, що наш Python-рушій "
              "(розв'язувач, фільтр Калмана, симуляції з планом) рахує те саме, що IRIS, на тому самому файлі моделі; "
              "економічну коректність розширення звірка не перевіряє — для цього є функції відгуку, тести й порівняння з НБУ.")
bt_tab = table_csv("backtest_2025Q3")
add(type="chart", section="Додатки", title=f"Додаток {5 if ML else 4}. Бектест: прогноз з даними до III кв. 2025",
    image=img("fc_backtest"), layout="below",
    bullets=[f"Помилка прогнозу ІСЦ на 1–4 квартали вперед: {n(bt_cpi['model'].min())}–{n(bt_cpi['model'].max())} в. п. («без змін»: "
             f"{n(bt_cpi['naive'].min())}–{n(bt_cpi['naive'].max())}); лише 3 прогони, зовнішні умови — фактичні, тож це перевірка, "
             "а не доказ переваги над НБУ",
             "Ставку краще прогнозує «без змін»: НБУ змінює її рідко",
             "Курс грн/€ модель не прогнозує краще за наївний — залежить від EUR/USD (обмеження моделі)"],
    notes="Бектест квазіреальний: сезонне згладжування й фільтр бачать лише дані до дати прогнозу, судження й наукасти не "
          "використовувалися, зовнішні змінні — фактичні; «факт» — лише опубліковані дані (IV кв. 2026 не оцінюється).")
qt = table_csv("baseline_quarterly", index_col=[0, 1])
qt = qt[[c for c in qt.columns if c.endswith(("Q2", "Q4"))]]   # half-years: fits the slide
qt_rows = [[i[1]] + [n(v) for v in r.values] for i, r in qt.iterrows()]
add(type="table", section="Додатки", title=f"Додаток {6 if ML else 5}. Базовий прогноз по півріччях",
    table={"header": ["Показник"] + [qlabel(c) for c in qt.columns], "rows": qt_rows, "font": 12, "rowH": 0.5},
    notes=f"Значення базового сценарію в II і IV кварталах (рішення {pr(REC['rate'])}% у жовтні з утриманням до середини 2027, далі — "
          "траєкторія повернення до цілі). Усі квартали — results/tables/baseline_quarterly.csv.")
add(type="table", section="Додатки", title=f"Додаток {7 if ML else 6}. Джерела даних",
    table={"header": ["Дані", "Джерело"], "colw": [3.6, 8.7], "font": 13, "rowH": 0.48, "rows": [
        ["ІСЦ, базова інфляція, складові", [SRC["api"], {"text": " (Держстат); "}, SRC["ccpi"], {"text": "; "}, SRC["ir_data"],
                                            {"text": "; "}, SRC["cpi_sep"]]],
        ["Облікова ставка, курси, інтервенції, резерви", [SRC["api"], {"text": " (statdirectory/key, exchange, kursf, res)"}]],
        ["Реальний ВВП, зарплати, бюджет", [SRC["derzh"], {"text": "; "}, SRC["gdp_q2"], {"text": "; "}, SRC["wages"], {"text": "; "}, SRC["budget"]]],
        ["Прогноз і припущення НБУ", [SRC["ir"], {"text": "; "}, SRC["nbu_fc"], {"text": "; "}, SRC["ir_data"]]],
        ["Ціль і горизонт політики", [SRC["mpg"]]],
        ["Єврозона", [SRC["eurostat"], {"text": "; "}, SRC["ecb"], {"text": "; "}, SRC["ecb_proj"]]],
        ["Нафта Brent", [SRC["eia"], {"text": " (DBnomics); "}, SRC["fut"], {"text": " (NYMEX BZ)"}]],
        ["Рішення та дискусія КМП", [SRC["rate"], {"text": "; "}, SRC["kmp"]]],
        ["Валютні обмеження, МВФ", [SRC["fx_strat"], {"text": "; "}, SRC["fx_pack"], {"text": "; "}, SRC["imf"]]],
        ["Модель", [SRC["template"], {"text": " + розширення команди; Python і MATLAB R2026b + IRIS"}]]]},
    notes=f"Усі дані завантажуються скриптами; дата відсічення — {DATA_CUTOFF}.")

# ----------------------------------------------------------------------------------------------- speech (15 min)
# Full text of the talk for the main slides: becomes the speaker notes and docs/speech.md (with timing).
# Keys are unique fragments of slide titles; numbers come from the model like everything else.
_ord = {"1": "першому", "2": "другому", "3": "третьому", "4": "четвертому"}
tq = f"{_ord[first_target_q[-1]]} кварталі {first_target_q[:4]} року"
dec, dec0 = n(K["nowcast_dec_yoy"]), n(K["nowcast_dec_yoy"], 0)
q27, r27h, r28 = n(Q["2027Q4"]["cpi_yoy"]), n(half(Q["2027Q4"]["ir_pol"])), n(Q["2028Q4"]["ir_pol"])
g26 = VS["2026"]["ВВП, наш"]
g26s = "фактично нульове зростання цього року" if abs(g26) < 0.25 else f"{n(g26)}% цього року"
SPEECH = {
    "Рекомендації щодо монетарної політики":
        f"Добрий день, шановні члени журі. Ми — {TEAM['name']}. Сьогодні представимо наші рекомендації для "
        f"засідання Правління НБУ 29 жовтня 2026 року. Усі дані — станом на {DATA_CUTOFF[:5].replace('.10', ' жовтня')}.",
    "Головне:":
        "Почнемо з головного. Ми пропонуємо три рішення, які працюють як єдиний пакет. "
        f"Перше — підвищити облікову ставку на {n(REC['change_pp'], 0)} пункт, до {pr(REC['rate'])}%, і утримувати її щонайменше до "
        f"середини 2027 року: у вересні інфляція сягнула 10%, у грудні буде близько {dec0}%. "
        f"Друге — не заморожувати курс: у жовтні гривня послабилася до {n(usd_last, 1)} за долар, і це правильно — курс має "
        "поглинати шоки. "
        "І обмежити обсяги тендерів депсертифікатів, щоб підвищення дійшло до депозитів. Третє — поставити "
        f"на паузу наступні кроки валютної лібералізації, доки не відновляться резерви. За такої політики інфляція "
        f"знизиться до {q27}% у четвертому кварталі 2027 року і повернеться до цілі у {tgt_year} році — у межах "
        "трирічного горизонту НБУ.",
    "Зовнішнє середовище":
        f"Зовнішнє середовище стало помітно проінфляційним. Через війну на Близькому Сході нафта Brent у {brent_peak_m} "
        f"коштувала в середньому {n(brent_peak, 0)} доларів за барель, у вересні — {n(brent_sep, 0)}, а в {brent_last_m} — близько "
        f"{n(brent_last, 0)} — тоді як НБУ в липні закладав 80–85. Ринок очікує здешевлення: ф'ючерси вказують на "
        f"{n(BP['2027Q4'], 0)} доларів наприкінці 2027 року, і саме цю криву ми беремо в прогноз. Водночас ЄЦБ підвищує "
        "ставку, тож простору для пом'якшення в Україні менше.",
    "Інфляція у вересні":
        "У вересні інфляція стрибнула до 10% — ціни за місяць зросли на 2,1%. Пальне подорожчало на 46% за рік, "
        "атаки на склади й логістику здорожчили доставку. Але більше нас турбує базова інфляція: вона прискорилася "
        "до 8,8%, послуги дорожчають на 14%. І навіть продовольство, яке досі стримувало ціни, почало дорожчати.",
    "Очікування підвищені":
        "Інфляційні очікування підвищені: домогосподарства чекають 10–14% — більше, ніж фактична інфляція, а "
        f"фінансові аналітики підвищили свої очікування до {n(exp_an)}%. Реальна ставка, якщо рахувати як НБУ — від очікувань, — "
        f"близько {n(rr_ante_an, 0)}%, тож гривневі активи поки привабливі. Але великі банки майже не підняли депозитні "
        "ставки — трансмісія слабка, і ризик розбалансування очікувань реальний.",
    "Активність:":
        "Економіка тим часом сповільнюється. ВВП у другому кварталі зріс лише на 0,4% за рік, у третьому — близько 1%, "
        "і то завдяки врожаю: це суттєво гірше прогнозу НБУ. Але атаки й дефіцит кадрів б'ють по потенціалу ще "
        "сильніше, ніж по попиту. Ринок праці напружений: номінальні зарплати цього року "
        f"зростають на {wages_rng.replace('–', '–')}%. Тож навіть за слабкого ВВП тиск на ціни послуг зберігається.",
    "НБУ продає":
        f"Найгостріша проблема — валютний ринок. НБУ продає в середньому близько {n(RR['sales_per_month'])} мільярда "
        "доларів на місяць, у вересні — рекордні 5,5 мільярда. Резерви за два місяці скоротилися з 51,2 до 47,1 "
        "мільярда, тоді як НБУ очікував 53,8. Але важливо: продаж валюти здебільшого «доносить» допомогу на ринок — у "
        "вересні уряд конвертував 3,81 мільярда оборонного траншу. Тож резерви падають через ритм допомоги. Курс "
        f"чотири місяці стояв біля {n(usd_jun_sep, 1)} гривні за долар, а в жовтні НБУ допустив послаблення до {n(usd_last, 1)}.",
    "Платіжний баланс":
        f"Звідки тиск на резерви — видно з платіжного балансу. Імпорт цього року в {n(m26 / e26)} раза більший за "
        f"експорт, дефіцит — близько {n(m26 - e26, 0)} мільярдів доларів. Поточний рахунок фінансують позики партнерів. "
        f"Але офіційне фінансування скорочується з {n(of26, 0)} мільярдів у 2026 році до {n(of28, 0)} у 2028-му, і, за "
        f"прогнозом НБУ, поточний рахунок тоді погіршиться до мінус {n(-ca28, 0)} мільярдів. Тому резерви потрібні як "
        "буфер, а лібералізацію варто проводити поступово.",
    "Бюджет залежить від допомоги":
        "Причина — залежність бюджету від допомоги. Дефіцит без грантів — близько 35% ВВП, потреба у зовнішньому "
        "фінансуванні — 87 мільярдів доларів, а влітку надходження затрималися. Оборонний кредит USL підтримує попит "
        "через локалізацію ОПК і водночас створює попит на валюту, але загалом дефіцит скорочується, тож окремого "
        "бюджетного стимулу ми не закладаємо. Уряд у Бюджетній декларації закладає інфляцію 8,9% наприкінці 2027 року — "
        "вище, ніж НБУ і ми.",
    "Модель:":
        "Тепер — прогноз. Ми взяли квартальну прогнозну модель НБУ, переписали її на Python і розширили. Дані "
        "завантажуються автоматично, фільтр Калмана оцінює розриви й тренди, далі — прогноз із судженнями й аналіз "
        "політики. Наше розширення — окремо базова й небазова інфляція і канал світових цін на нафту: нафта на 20% "
        "дорожча додає 0,3 пункта до інфляції, а ставка реагує слабко. Той самий файл моделі, дані й плани ми проганяємо "
        "в MATLAB з IRIS для звірки: розбіжність — у п'ятому знаку.",
    "Наше розширення QPM":
        "Що ми змінили в моделі. У шаблоні одна крива Філіпса для всієї інфляції, тож нафтовий шок дає хибні "
        "коливання через курс. Ми розділили інфляцію на базову і небазову: небазові ціни реагують на нафту та курс. "
        "Нафта на 20% дорожча — це плюс 0,3 пункта до інфляції впродовж року, ставка зростає лише на 0,2 пункта, а "
        "базова інфляція не прискорюється. Без нафтового каналу функції відгуку моделі збігаються з шаблоном НБУ.",
    "Припущення та судження":
        "Модель не описує все — енергетику, бюджет, допомогу, тарифи. Тому ці чинники входять через явні судження, "
        "і кожне має кількісне обґрунтування та джерело. Наприклад, вторинні ефекти атак в опалювальний сезон ми "
        "калібруємо за оцінкою НБУ. Окремо закладаємо адмінціни й акцизи: у 2016–2026 роках загальна інфляція в "
        "середньому перевищувала базову на 1,7 пункта на рік, і НБУ закладає таку саму різницю на 2027–2028 роки.",
    "Короткостроковий прогноз":
        "Для найближчих місяців ми будуємо короткостроковий прогноз: трендовий темп цін, сезонність і поправка на "
        f"разовість вересневого стрибка. Тренд — {n(nc_trend, 2)}% на місяць. До того ж діє ефект бази: у {base_span} "
        f"ціни зросли лише на {n(base_effect)}%. Тому річна інфляція підніметься до {dec}% у грудні — помітно вище, "
        f"ніж НБУ прогнозував у липні. Базову інфляцію рахуємо тим самим методом: у грудні — {n(nc_core_dec)}%.",
    "Інфляція досягне піку":
        "Базовий прогноз. Нагадаю: ціль НБУ — 5% без діапазону відхилень, і повернути інфляцію до неї треба на "
        f"горизонті до трьох років. У середньому за квартал інфляція досягне піку — близько {n(SC['Базовий']['ІСЦ пік'])}% — "
        f"{peak_when} року; у місячному вимірі це близько {dec0}% у грудні. Далі вона знизиться до {q27}% у четвертому "
        f"кварталі 2027-го, у 2028 році опуститься нижче цілі — до {n(band28_lo)}–{n(band28_hi)}%, бо нафта дешевшає за "
        f"ф'ючерсами, а попит слабкий, — і стабілізується біля 5% у {tgt_year} році. Базова інфляція в нас {core_vs_nbu}: "
        f"{n(core['2027'])}% у середньому за четвертий квартал "
        f"2027 року, у грудневому вимірі — близько {n(core_dec27)}%, проти {n(nbu_core27)}% у НБУ. Ставка — {pr(REC['rate'])}% до "
        f"середини 2027 року, далі поступово знижується до {r28}% наприкінці 2028-го. Невизначеність велика — це показує віяло.",
    "Базова інфляція у 2027":
        f"Окремо про базову інфляцію. Наша оцінка на четвертий квартал 2027 року — {n(core['2027'])}% у середньому за "
        f"квартал, тобто близько {n(core_dec27)}% у грудні, проти {n(nbu_core27)}% у НБУ — {core_vs_nbu}. У моделі її тримають "
        "додатний розрив ВВП, перенесення вересневого шоку витрат і курсу та шок витрат опалювального сезону. Загальна "
        "інфляція при цьому близька до НБУ: тарифи й акцизи додають близько 1,7 пункта на рік, а дешевша нафта частково "
        "це компенсує. Висновок: підвищити ставку зараз, щоб швидше пом'якшити її пізніше.",
    "потенціал постраждав":
        f"Тепер — попит. ВВП ми бачимо слабшим, ніж НБУ в липні: {g26s}, {n(VS['2027']['ВВП, наш'])}% у 2027-му і "
        f"{n(VS['2028']['ВВП, наш'])}% у 2028-му. Мінекономіки теж погіршує прогноз — до 0,8–1% на 2027 рік. Але "
        "потенціал економіки постраждав ще більше: атаки й дефіцит кадрів. Тому розрив ВВП зараз додатний, і ціни "
        "послуг ростуть. Бюджетного стимулу ми не закладаємо: дефіцит скорочується з 35 до 26% ВВП. У 2027 році висока "
        "реальна ставка охолоджує попит, і розрив закривається — це ціна повернення інфляції до цілі.",
    "Сценарії:":
        "Ми розглянули чотири ризикові сценарії. Найнебезпечніший — дефіцит фінансування: "
        f"якщо допомога затримається, гривня буде приблизно на {n(fx_dep, 0)}% слабшою, інфляція зросте до "
        f"{n(fg['ІСЦ пік'])}%, а ставку доведеться підняти до {n(fg['Ставка пік'])}%. Важка зима з ударами по "
        f"енергетиці підніме інфляцію до {n(hw['ІСЦ пік'])}% і майже зупинить зростання ВВП. Натомість нафта по "
        f"120 доларів додає лише {n(oil['ІСЦ пік'] - bs['ІСЦ пік'])} пункта до піку інфляції, і ставка майже не "
        "реагує — це шок першого раунду. Ще два ризики для інфляції 2027 року — курс і очікування: якщо гривня "
        f"слабшатиме так, як чекає ринок, інфляція наприкінці 2027 року буде близько "
        f"{n(RX['Курс як чекає ринок']['ІСЦ IV кв. 2027'], 0)}% замість {n(Q['2027Q4']['cpi_yoy'], 0)}%, розбалансування "
        f"очікувань дало б близько {n(RX['Розбалансування очікувань']['ІСЦ IV кв. 2027'], 0)}%, а ПДВ 21% — ще "
        f"{n(RX['ПДВ 21% з 2027']['ІСЦ пік'] - bs['ІСЦ пік'])} пункта до піку.",
    "Матриця ризиків":
        "Матриця ризиків підсумовує: більшість імовірних і сильних ризиків — проінфляційні. Це атаки на "
        "енергетику, затримки допомоги, розбалансування очікувань і зарплатна спіраль. Дезінфляційних менше — "
        "блокада портів, охолодження попиту, можливе перемир'я. Баланс зміщений угору.",
    "Рамка рішення":
        "Переходимо до рекомендацій. Спершу — рамка. Головна мета НБУ — цінова стабільність: ціль 5%, "
        "і повернути до неї інфляцію треба на горизонті до трьох років. Інструменти — облікова ставка, депозитні "
        "сертифікати, які з серпня розміщуються на тендерах, валютні інтервенції та обмеження. У вересні КМП підвищив "
        "ставку до 16%, але думки розділилися: семеро вважають, що цього достатньо, двоє чекають ще одного "
        "підвищення, один — зниження. Ми — за підвищення, і ось чому.",
    "Варіанти рішення":
        "Ми порівняли чотири варіанти рішення — від утримання 16% до підвищення до 17,5%. У кожному ставка "
        "утримується до середини 2027 року, а далі знижується так, щоб інфляція повернулася саме до 5%. "
        "Критерій — втрати: відхилення інфляції від цілі, розрив ВВП і різкі зміни ставки. Адмінціни ми враховуємо "
        f"наполовину: вони ростуть щороку, але це перший раунд. Мінімум втрат — від {best_hold_rng.replace('–', ' до ')}% "
        f"залежно від ваги згладжування, за центральної — {pr(BH['λ = 1'])}%; оптимальна траєкторія починається з "
        f"{n(opt['λ = 1']['2026Q4'])}% і в першому кварталі 2027-го підіймається до {n(opt['λ = 1']['2027Q1'])}%. Ми перевірили "
        f"рішення на десяти сценаріях: найменші очікувані втрати — на {rob_best.replace('–', ' і ')}%"
        + (f", і {pr(REC['rate'])}% — серед них. " if rob_gap_pct < 0.5 else
           f", а {pr(REC['rate'])}% поступається їм лише на близько {n(rob_gap_pct, 0)}% — це в межах точності наших суджень "
           "про ваги й імовірності. ")
        + "Тому ми обираємо пункт зараз і готовність до ще пів пункта в грудні, коли буде оновлений прогноз НБУ, а не "
          "півтора пункта одразу.",
    "Облікова ставка: підвищити":
        f"Тому перша рекомендація — підвищити облікову ставку до {pr(REC['rate'])}%. Чому підвищити: інфляція в грудні "
        f"сягне близько {dec0}%, базова інфляція прискорюється, курсові ризики високі, а гнучкіший курс потребує "
        f"сильного якоря для очікувань. Ринок не чекає різкого посилення, але ризики зміщені вгору, і НБУ вже робив крок у "
        "пункт — у січні й березні 2025 року. Чому не більше: економіка слабка, а півтора пункта одразу — надмірний сигнал "
        "до оновленого прогнозу НБУ. "
        "Щоб підвищення дійшло до депозитів, обсяги тендерів депсертифікатів варто обмежити. Орієнтир: не знижувати "
        "ставку щонайменше до третього кварталу 2027 року, а наступний крок — радше вгору: ще пів пункта в грудні, якщо "
        "базова інфляція не сповільниться або посиляться курсові очікування.",
    "Курс і резерви":
        f"Друга рекомендація — щодо курсу. НБУ продає близько {n(RR['sales_per_month'])} мільярда доларів на місяць, а "
        f"надходить близько {n(RR['inflows_per_month'])}. Якщо так і залишиться, на кінець року резерви становитимуть "
        f"{n(RES['Як у липні–вересні'], 0)} мільярди. Структурно попит на валюту високий: імпорт у {n(m26 / e26)} раза "
        f"більший за експорт, а офіційне фінансування скоротиться з {n(of26, 0)} до {n(of28, 0)} мільярдів у 2028 році. "
        "Водночас продаж валюти "
        "здебільшого «доносить» допомогу до ринку, тож резерви визначає її ритм, а не курс. Наша рекомендація щодо курсу "
        f"інша: не фіксувати його. Чотири місяці гривня стояла біля {n(usd_jun_sep, 1)} за долар, а в жовтні послабилася до "
        f"{n(usd_last, 1)} — за рік це плюс {n(usd_dep_yr, 0)}%, і це нормальна робота амортизатора. Курс має поглинати шоки, "
        "а НБУ — лише згладжувати коливання.",
    "Валютні обмеження":
        "Третя рекомендація — валютні обмеження. Серпневий пакет варто зберегти: купівля валюти населенням зросла з "
        f"{n(hh_jul, 2)} до {n(hh_sep, 2)} мільярда доларів на місяць — помітно, але керовано. За Стратегією НБУ кроки "
        "робляться за передумовами, а не за календарем. Тому третій етап — операції населення й капітальні операції — "
        "пропонуємо відкласти, доки резерви не повернуться до 50 мільярдів, а допомога — до ритмічності. Нових "
        "обмежень не запроваджувати.",
    "Комунікація":
        "Усе це має пояснити комунікація. Ключова формула — «ставка — якір, курс — амортизатор»: НБУ підвищує "
        "ставку рішуче, курс не заморожений, а обмежені обсяги депсертифікатів доносять підвищення до депозитних "
        "ставок. Чого уникати — обіцянок конкретного курсу і сигналів про швидке зниження ставки. На слайді — наш "
        "проєкт пресрелізу.",
    "Підсумок":
        f"Підсумуємо. Перше — підвищити облікову ставку до {pr(REC['rate'])}% і утримувати щонайменше до середини "
        "2027 року. Друге — не заморожувати курс і обмежити обсяги депсертифікатів. Третє — пауза в "
        f"лібералізації валютних обмежень. Формула комунікації — «ставка — якір, курс — амортизатор». За такої політики "
        f"інфляція повернеться до цілі у {tgt_year} році. Дякуємо за увагу! "
        "Будемо раді відповісти на ваші запитання.",
}
# Main part: 18 slides for 15 minutes (≈50 s each); the rest goes to the appendix, its speech text becomes notes
MOVE_TO_APPENDIX = ["Платіжний баланс", "Бюджет залежить", "Наше розширення QPM", "Припущення та судження",
                    "Базова інфляція у 2027", "Матриця ризиків", "Комунікація"]
_moved = [s for s in slides if s["type"] != "section" and s["section"] not in (None, "Додатки")
          and any(k in s["title"] for k in MOVE_TO_APPENDIX)]
for _s in _moved:
    slides.remove(_s)
    _s["section"] = "Додатки"
_app = next(i for i, s in enumerate(slides) if s["type"] == "section" and s["section"] == "Додатки")
slides[_app + 1:_app + 1] = _moved
_k = 0
for _s in slides:
    if _s["section"] == "Додатки" and _s["type"] != "section":
        _k += 1
        _s["title"] = f"Додаток {_k}. " + re.sub(r"^Додаток \d+\. ", "", _s["title"])

WPM = 120   # planning pace for a talk in Ukrainian, words per minute
SPEAKERS = {None: "Доповідач 1", "Огляд": "Доповідач 1", "Прогноз": "Доповідач 2", "Рекомендації": "Доповідач 3"}
used = set()
talk = []
for i, sl in enumerate(slides, 1):
    if sl["section"] == "Додатки" or sl["type"] == "section":
        mk = [k for k in SPEECH if k in sl["title"]] if any(sl is m for m in _moved) else []
        if mk:
            sl["notes"] = SPEECH[mk[0]]
            used.add(mk[0])
        continue
    keys = [k for k in SPEECH if k in sl["title"]]
    assert len(keys) == 1, (i, sl["title"], keys)
    used.add(keys[0])
    sl["notes"] = SPEECH[keys[0]]
    talk.append((i, sl))
assert used == set(SPEECH), set(SPEECH) - used
md = [f"# Текст виступу (≈15 хв)", "",
      "Згенеровано `deck/content.py` разом із презентацією — правте текст там (словник `SPEECH`); цифри підставляються "
      "з моделі. Цей самий текст — у нотатках доповідача кожного слайда. Додатки — для відповідей на запитання.", ""]
total = sum(len(sl["notes"].split()) for _, sl in talk)
mins = f"{total / WPM:.1f}".replace(".", ",")
words = "слово" if total % 10 == 1 and total % 100 != 11 else (
    "слова" if total % 10 in (2, 3, 4) and total % 100 not in (12, 13, 14) else "слів")
md += [f"**Обсяг:** {total} {words} ≈ {mins} хв мовлення в темпі {WPM} слів/хв; разом зі зміною слайдів і паузами — "
       f"≈{total / WPM + 1.5:.0f} хв, тобто є запас до 15. Розподіл на трьох доповідачів — за розділами (якщо доповідачів інша кількість, "
       "переділіть за розділами). Перед виступом прорепетируйте з таймером.", ""]
t, speaker = 0.0, None
for i, sl in talk:
    if SPEAKERS[sl["section"]] != speaker:
        speaker = SPEAKERS[sl["section"]]
        md += [f"## {speaker}: {sl['section'] or 'вступ і головне'}" + (" + огляд" if sl["section"] is None else ""), ""]
    sec = len(sl["notes"].split()) / WPM * 60
    md += [f"### Слайд {i}. {sl['title']}", f"*{int(t // 60)}:{int(t % 60):02d} → ≈{sec:.0f} с*", "", sl["notes"], ""]
    t += sec
md += [f"**Кінець: {int(t // 60)}:{int(t % 60):02d}**", ""]
(ROOT / "docs" / "speech.md").write_text("\n".join(md), encoding="utf-8")
print(f"docs/speech.md: {total} {words} ≈ {mins} хв")

# Clickable sources at the bottom of each slide (title fragment -> keys of SRC)
SOURCES = {
    "Головне:": ["mpg", "ir"],
    "Зовнішнє середовище": ["ecb_proj", "eurostat", "eia", "fut"],
    "Інфляція у вересні": ["cpi_sep", "ir_data", "api"],
    "Очікування підвищені": ["ir_data", "ovdp", "kmp"],
    "Активність:": ["gdp_q2", "ied", "kmp"],
    "НБУ продає": ["api", "res_sep", "pyshnyi"],
    "Бюджет залежить": ["nbu_fc", "ir_data", "imf"],
    "Платіжний баланс": ["nbu_fc", "ir_data"],
    "Рамка рішення": ["law", "mpg", "kmp", "cd"],
    "Модель:": ["template", "api", "ecb", "eurostat"],
    "Наше розширення QPM": ["ccpi", "eia", "fut"],
    "Припущення та судження": ["ir", "nbu_fc", "kmp"],
    "Короткостроковий прогноз": ["api", "cpi_sep"],
    "Інфляція досягне піку": ["mpg", "nbu_fc"],
    "Базова інфляція у 2027": ["ccpi", "nbu_fc"],
    "потенціал постраждав": ["ir_data", "nbu_fc", "minecon"],
    "Додаткові ризики": ["vat", "fut", "kmp"],
    "Ставка має лишатися високою": ["template"],
    "Сценарії:": ["kmp", "fut", "nbu_fc"],
    "Матриця ризиків": ["kmp", "ir"],
    "Варіанти рішення": ["mpg"],
    "Облікова ставка: підвищити": ["rate", "kmp"],
    "Курс і резерви": ["res_sep", "pyshnyi", "nbu_fc"],
    "Валютні обмеження": ["fx_pack", "fx_strat", "api"],
    "Комунікація": ["rate"],
    "Модель: QPM НБУ +": ["template"],
    "Реакція на шок ставки": ["template"],
    "Бектест": ["api"],
}
for sl in slides:
    keys = [k for k in SOURCES if k in sl.get("title", "")]
    if keys:
        sl["sources"] = [SRC[s] for s in SOURCES[keys[0]]]

for sl in slides:
    if sl["type"] == "matrix":
        sl["cells"] = [{"row": r, "col": c, "items": [{"dir": d, "text": t} for d, t in items]}
                       for (r, c), items in sl["cells"].items()]
out = {"sections": SECTIONS, "slides": slides, "team": TEAM, "data_cutoff": DATA_CUTOFF}
(ROOT / "deck" / "deck_data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"deck_data.json: {len(slides)} слайдів")
