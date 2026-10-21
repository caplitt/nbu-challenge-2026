"""Зміст презентації: тексти + цифри з results/key_numbers.json і results/tables (єдине джерело чисел).

Запуск з кореня репозиторію:  python deck/content.py   ->  deck/deck_data.json
Потім:                         node deck/build_deck.js  ->  presentation/*.pptx
Правте тексти тут; цифри підставляються автоматично після кожного прогону моделі.
"""
from __future__ import annotations

import json
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
# NBU target: 5% point target (no tolerance band) within a policy horizon of up to three years.
# "Return to target" = first quarter from which inflation stays within 0.1 pp of 5% to the end of the forecast.
_qs = list(Q)
first_target_q = next(q for i, q in enumerate(_qs) if all(abs(Q[r]["cpi_yoy"] - 5) <= 0.1 for r in _qs[i:]))
dip28 = min(Q[f"2028Q{i}"]["cpi_yoy"] for i in range(1, 5))
# actual (model) depreciation of UAH vs EUR, average % a year over the horizon: the NBU target path allows up to
# 4% a year, but the high policy rate (UIP) keeps the hryvnia stronger
fx_yr = ((Q[f"{_qs[-1]}"]["uah_eur"] / Q[_qs[0]]["uah_eur"]) ** (4 / (len(_qs) - 1)) - 1) * 100
roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}


def qlabel(q):
    return f"{roman[q[-1]]} кв. {q[:4]}"


bt = table_csv("backtest_errors")
bt.columns = ["var", "model", "naive"]
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
    "res_sep": ("НБУ: резерви у вересні (USL $3,81 млрд)", "https://bank.gov.ua/ua/news/all/mijnarodni-rezervi-stanovili-471-mlrd-dol-ssha-za-pidsumkami-veresnya"),
    "pyshnyi": ("А. Пишний: три роки керованої гнучкості", "https://epravda.com.ua/finances/valyutniy-rinok-ukrajini-rezultati-troh-rokiv-rezhimu-kerovanoji-gnuchkosti-826509/"),
}.items()}

opt_lt = K["optimal_paths"]["λ = 1, без реакції на адмінціни"]
DATA_CUTOFF = "20.10.2026"
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
usd_now = float(pd.read_csv(ROOT / "data" / "overview" / "fx.csv", index_col=0, encoding="utf-8-sig")["грн/$"].dropna().iloc[-1])
RN = K["reserves_nbu"]
core = {y: A[y]["Базова інфляція, % р/р (IV кв.)"] for y in ("2026", "2027", "2028", "2029")}
nbu_cpi27 = nbu_val("ІСЦ (на кінець", "2027Q4")
nbu_core27, nbu_core28 = nbu_val("Базова інфляція", "2027Q4"), nbu_val("Базова інфляція", "2028Q4")
# Brent: monthly actual (EIA, then the front-month future; the last month is month-to-date) and the futures curve
_brent = pd.read_csv(ROOT / "data" / "raw" / "brent_monthly.csv", index_col=0)["brent_usd"]
_b26 = _brent.loc["2026-01":]
brent_peak_m, brent_peak = _mname[_b26.idxmax()[-2:]], float(_b26.max())
brent_last = float(_brent.iloc[-1])
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
# FX: frozen since June, but weaker a year earlier; risk if the hryvnia weakens as the market expects
_fx = pd.read_csv(ROOT / "data" / "overview" / "fx.csv", index_col=0, encoding="utf-8-sig")["грн/$"].dropna()
usd_yago = float(_fx.loc[str(pd.Period(_fx.index[-1], 'M') - 12)])
usd_dep_yr = (float(_fx.iloc[-1]) / usd_yago - 1) * 100
FXR = K["fx_risk"]
# wages: the whole first half of the year, not one month
_w = pd.read_csv(ROOT / "data" / "overview" / "wages.csv", index_col=0, encoding="utf-8-sig")["Номінальна"].dropna()
_w26 = _w.loc["2026-01":]
wages_rng = f"{n(_w26.min(), 0)}–{n(_w26.max(), 0)}"
BH = K["best_hold_by_lambda"]
_bh = sorted(set(BH.values()))
best_hold_rng = pr(_bh[0]) if len(_bh) == 1 else f"{pr(_bh[0])}–{pr(_bh[-1])}"
ADMIN = int(round(K["admin_reaction"] * 100))
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
         "text": f"утримувати щонайменше до середини 2027; далі — зниження, що повертає інфляцію до 5% у {first_target_q[:4]}"},
        {"label": "Курс гривні", "value": "Гнучкий", "delta": "",
         "text": f"з червня ≈{n(usd_now)} грн/$ без змін; допускати двосторонні коливання, інтервенції лише "
                 "згладжують; рівень не фіксувати"},
        {"label": "Валютні обмеження", "value": "Пауза", "delta": "етап III",
         "text": "серпневий пакет зберегти; нові кроки — після відновлення резервів і допомоги"},
    ],
    table={"header": ["", "IV кв. 2026", "IV кв. 2027", "IV кв. 2028", "IV кв. 2029"],
           "rows": [["ІСЦ, % р/р*"] + [n(Q[f"{y}Q4"]["cpi_yoy"]) for y in range(2026, 2030)],
                    ["Базова інфляція, % р/р*"] + [n(core[str(y)]) for y in range(2026, 2030)],
                    ["Реальний ВВП, % (рік)"] + [n(A[str(y)]["Реальний ВВП, % (рік)"]) for y in range(2026, 2030)],
                    ["Облікова ставка, %"] + [n(Q[f"{y}Q4"]["ir_pol"]) for y in range(2026, 2030)],
                    ["Курс, грн/€"] + [n(Q[f"{y}Q4"]["uah_eur"]) for y in range(2026, 2030)]]},
    footnote=f"* Середнє за квартал (SA); грудень 2026 — {n(K['nowcast_dec_yoy'])}% (наукаст). Ціль НБУ — 5% на горизонті "
             f"до 3 років; стабілізація на 5% — з {qlabel(first_target_q)}. Дані на {DATA_CUTOFF}.",
    notes="Три рішення: ставка, курс без заморожування, пауза в лібералізації (текст — у словнику SPEECH).")

# ----------------------------------------------------------------------------------------------- section 1
add(type="section", section="Огляд", number="01", title="Огляд економіки",
    subtitle="Інфляція прискорюється, резерви тануть, економіка сповільнюється")

add(type="chart", section="Огляд",
    title=f"Зовнішнє середовище стало проінфляційним: нафта ≈${n(brent_last, 0)}, ЄЦБ підвищує ставку",
    image=img("ov_external"), layout="below",
    bullets=[f"Війна на Близькому Сході (з 28.02.2026): Brent — пік ${n(brent_peak, 0)} у {brent_peak_m}, ${n(brent_sep, 0)} у вересні, "
             f"≈${n(brent_last, 0)} у жовтні (НБУ закладав $80–85); ф'ючерси — ${n(BP['2027Q4'], 0)} наприкінці 2027",
             "ЄЦБ підвищив ставку до 2,5% (червень, вересень); ринок закладає ще ≈+0,5 в. п. до кінця 2027",
             "Інфляція в єврозоні — пік ≈3,7% наприкінці 2026 (прогноз ЄЦБ: 3,0% / 2,5% / 2,1% у 2026–2028)"],
    notes="Зовнішній фон гірший, ніж у липневому прогнозі НБУ: дорожча нафта підживлює ціни на пальне в Україні, "
          "а підвищення ставок у світі зменшує простір для пом'якшення. У прогнозі ми беремо ф'ючерсну криву Brent: "
          f"ринок очікує поступового здешевлення нафти (до ${n(BP['2028Q4'], 0)} наприкінці 2028), і це дезінфляційний чинник.")

add(type="chart", section="Огляд",
    title="Інфляція у вересні — 10,0%: пальне, руйнування логістики, прискорення базової",
    image=img("ov_inflation"), layout="below",
    bullets=["+2,1% за місяць: пальне +46,2% р/р, адмінціни +13,6% (проїзд, вода, алкоголь), атаки на склади й логістику",
             "Базова інфляція 8,8% (з 8,1%): оброблені продукти +10,7%, послуги +13,7% (зарплати, оренда)",
             "Сирі продукти прискорилися до 6,7%: менші врожаї овочів, витрати на транспорт і зберігання"],
    notes="Вересень значно перевищив траєкторію НБУ: пальне, атаки на логістику, прискорення базової інфляції.")

add(type="chart", section="Огляд",
    title=f"Очікування підвищені; реальна ставка — {n(rr_post, 0)}–{n(rr_ante_an, 0)}% залежно від методу, і вона знижується",
    image=img("ov_rates"), layout="below",
    bullets=["Очікування домогосподарств 10–14% — вище фактичної інфляції; аналітики підвищили до 7,9% (липень)",
             f"Реальна ставка: від очікувань аналітиків ≈{n(rr_ante_an)}%, від нашого прогнозу на рік уперед ≈{n(rr_ante_fc)}%, "
             f"від фактичної інфляції ≈{n(rr_post)}% (місяцем раніше — ≈{n(rr_post_prev)}%); депозити реагують слабко",
             "ОВДП: 1 рік — 15,1%, 2,5 року — 16,5% (06.10): ринок не закладає швидкого зниження; гривневі кредити "
             "бізнесу +30% р/р — умови не надто жорсткі (КМП)"],
    notes="Ризик — розбалансування очікувань: домогосподарства очікують інфляцію вище фактичної, а члени КМП "
          "звертають увагу на зростання очікувань фінансових аналітиків.")

add(type="chart", section="Огляд",
    title=f"Економіка сповільнюється: ВВП III кв. гірший за прогноз, а зарплати +{wages_rng}%",
    image=img("ov_activity"), layout="below",
    bullets=["ВВП II кв.: +0,3% кв/кв, +0,4% р/р; у III кв. — «суттєво гірше прогнозу НБУ» (КМП)",
             "Атаки на енергетику, логістику та порти; внесок обстрілів у ВВП-2026 — −0,9 в. п. (НБУ)",
             f"Дефіцит кадрів: номінальні зарплати +{wages_rng}% р/р у січні–червні (червень — +{n(_w26.iloc[-1], 0)}%) — "
             "тиск на ціни послуг"],
    notes="Ринок праці перегрітий через дефіцит працівників, тому навіть за слабкого ВВП фундаментальний "
          "ціновий тиск зберігається.")

add(type="chart", section="Огляд",
    title=f"НБУ продає ≈${n(RR['sales_per_month'])} млрд на місяць — резерви впали до $47,1 млрд",
    image=img("ov_fx"), layout="below",
    bullets=[f"Чистий продаж валюти НБУ: $4,8 млрд у серпні, $5,5 млрд у вересні — рекорд року",
             f"Резерви: $51,2 млрд (липень) → $47,1 млрд (вересень) проти $53,8 млрд у прогнозі НБУ на кінець III кв.",
             f"Курс заморожений: ≈{n(usd_now)} грн/$ з червня (за рік до того — +{n(usd_dep_yr, 0)}%); продаж валюти "
             "здебільшого «доносить» допомогу: у вересні уряд конвертував $3,81 млрд оборонного траншу"],
    notes="Стабільність курсу зараз забезпечується інтервенціями, а надходження допомоги в липні–вересні були меншими "
          "за очікувані. Це ключовий аргумент для нашої курсової рекомендації.")

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
    notes="Локалізація оборонного виробництва коштом USL — це водночас бюджетний імпульс (інфляційний) і додатковий "
          "попит на валюту для імпорту компонентів.")

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
           {"value": matlab_diff, "label": "розбіжність Python і MATLAB/IRIS: фільтр і всі 5 сценаріїв"},
           {"value": f"{n(bt_cpi['model'].min())}–{n(bt_cpi['model'].max())} в. п.",
            "label": f"помилка прогнозу ІСЦ на рік уперед (наївний: {n(bt_cpi['naive'].min())}–{n(bt_cpi['naive'].max())})"}],
    chips=["Базова + небазова інфляція", "Канал нафти Brent", "Наукаст ІСЦ", "Судження з джерелами",
           "Віялові графіки", "Оптимальна ставка", "Бектест", "Резерви", "MATLAB/IRIS"],
    notes="Ми взяли шаблон QPM від НБУ, переписали його на Python і розширили: окремо базова й небазова інфляція "
          "та канал світових цін на нафту. Python дав автоматизацію даних, віяла, оптимальну політику й бектест. "
          "Той самий файл моделі ми проганяємо в MATLAB/IRIS: фільтр і всі сценарії збігаються до п'ятого знака, "
          "а графіки сценаріїв і функцій відгуку в презентації побудовані саме в MATLAB.")

add(type="chart", section="Прогноз",
    title="Наше розширення QPM: нафта змінює небазові ціни, ставка реагує лише на вторинні ефекти",
    image=ml_img("ml_irf_oil", "irf_res_dl_roil_beta"), layout="below",
    bullets=["ІСЦ = базова інфляція + зміна відносних цін небазових товарів; крива Філіпса НБУ описує базову",
             "Brent +20% → ІСЦ +0,3 в. п. упродовж року, ставка +0,2 в. п.; базова інфляція не прискорюється",
             "З вагою нафти 0 модель точно збігається з шаблоном НБУ — перевірено тестами і в MATLAB/IRIS"],
    notes="Ми розділили інфляцію на базову і небазову: крива Філіпса з шаблону НБУ тепер описує базову інфляцію "
          "(дані Держстату про базовий ІСЦ), а небазові ціни реагують на реальну ціну нафти в євро і на курс. "
          "Вагу 0,016 відкалібровано так, щоб +20% ціни нафти давали ≈+0,3 в. п. до ІСЦ: пальне ≈4% кошика, "
          "частка нафти в його ціні ≈40%, плюс непрямі ефекти. Графік побудовано в MATLAB/IRIS.")

judg_rows = [["Інфляція IV кв. 2026", f"Наукаст: тренд {n(nc_trend, 2)}%/міс + сезонність − 0,1 в. п. (разові ефекти вересня) → грудень {n(K['nowcast_dec_yoy'])}% р/р",
              {"text": "Держстат, API НБУ", "url": SRC["api"]["url"]}],
             ["ВВП III кв. 2026", "−0,3% кв/кв SA (КМП: «суттєво гірше прогнозу»)", {"text": "Підсумки КМП 28.09", "url": SRC["kmp"]["url"]}]]
for j in cfg.JUDGMENTS:
    label = {"res_dl_cpi_c": "Шок витрат 2027", "res_dl_rnc": "Адмінціни та акцизи", "res_l_gdp_gap": "Бюджетний імпульс",
             "res_prem_uip_gap": "Премія за ризик", "res_dl_gdp_tnd": "Потенційний ВВП"}[j["shock"]]
    why = j["why"].split(" (")[0]
    why = why[len(label) + 2:] if why.startswith(label + ":") else why
    judg_rows.append([label, why[0].upper() + why[1:], {"text": j["source"].split(";")[0].split(" (")[0], "url": j["url"]}])
judg_rows.append(["Курс гривні до €", f"Допустиме послаблення (цільовий темп): 4% у 2027, 3% у 2028; фактичний курс — з моделі (≈{n(fx_yr, 0)}% на рік)",
                  {"text": "Макропрогноз НБУ (EUR/USD)", "url": SRC["nbu_fc"]["url"]}])
judg_rows.append(["Нафта Brent", f"Ф'ючерсна крива ({DATA_CUTOFF[:5]}): ${n(BP['2026Q4'], 0)} (IV кв. 2026) → "
                  f"${n(BP['2027Q4'], 0)} (кінець 2027) → ${n(BP['2028Q4'], 0)} (кінець 2028)",
                  [SRC["eia"], {"text": ", "}, {"text": "NYMEX", "url": SRC["fut"]["url"]}]])
judg_rows.append(["Єврозона", "HICP 3,0 / 2,5 / 2,1%, ВВП 0,9 / 1,4 / 1,5%, ставка ЄЦБ до 3%", {"text": "ЄЦБ, вер. 2026", "url": SRC["ecb_proj"]["url"]}])
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
             f"Тренд {n(nc_trend, 2)}% на місяць (з урахуванням сезонності) — це ≈{n(((1 + nc_trend / 100) ** 12 - 1) * 100, 0)}% "
             "у річному вимірі; вересневий стрибок частково разовий (−0,1 в. п./міс.)",
             f"Грудень {n(K['nowcast_dec_yoy'])}% — вище липневого прогнозу НБУ (10%): вересень уже вивів інфляцію з його траєкторії"],
    notes="Для поточного кварталу беремо трендовий темп і сезонність; поправка −0,1 в. п. — разові ефекти вересня.")

add(type="chart", section="Прогноз",
    title=f"Інфляція досягне піку на початку 2027 і стабілізується на 5% у {first_target_q[:4]} — у межах горизонту політики",
    image=img("fc_fan"), layout="below",
    bullets=[f"Пік — I кв. 2027: ≈{n(SC['Базовий']['ІСЦ пік'])}% у середньому за квартал (у грудні — ≈{n(K['nowcast_dec_yoy'])}% за місяць); "
             f"{n(Q['2027Q4']['cpi_yoy'])}% у IV кв. 2027 (НБУ: {n(nbu_cpi27)}% у грудні); ≈5% уже в II кв. 2028, у 2028 — "
             f"тимчасово ≈{n(dip28)}%; стабільно 5% — з {qlabel(first_target_q)}",
             f"Ставка: {pr(REC['rate'])}% до середини 2027 → {n(Q['2027Q4']['ir_pol'])}% наприкінці 2027 → "
             f"{n(Q['2028Q4']['ir_pol'])}% — 2028 → {n(Q['2029Q4']['ir_pol'])}% — 2029",
             f"Невизначеність велика: з імовірністю 70% інфляція наприкінці 2027 — від {n(fan['2027Q4']['q15'])} до "
             f"{n(fan['2027Q4']['q85'])}%"],
    notes="Ціль НБУ — 5% без діапазону відхилень, горизонт політики — до трьох років (Основні засади ГКП, 2024). "
          "Тому після рішення ставка йде траєкторією, що повертає інфляцію до 5% на горизонті, а не за механічним "
          f"правилом: за правилом інфляція наприкінці 2029 була б лише {n(rule29)}%. Віяло — стохастичні симуляції з "
          "волатильністю шоків 2023–2026 років; широке віяло — чесне відображення воєнної невизначеності.")

add(type="chart", section="Прогноз",
    title=f"Базова інфляція в 2027 стійкіша, ніж у НБУ: {n(core['2027'])}% наприкінці року проти {n(nbu_core27)}%",
    image=img("fc_core"), layout="right",
    bullets=[f"Зарплати +{wages_rng}%, дорожчі послуги, наслідки атак — базова інфляція знижується повільніше, ніж очікує НБУ",
             f"Загальна: {n(Q['2027Q4']['cpi_yoy'])}% у IV кв. 2027 (НБУ {n(nbu_cpi27)}% у грудні) — тарифи й акцизи додають "
             "≈1,7 в. п. на рік, дешевша нафта (ф'ючерси) — віднімає",
             f"2028: базова {n(core['2028'])}% (НБУ {n(nbu_core28)}%) — слабкий попит → простір для зниження ставки з II пів. 2027",
             "Висновок: рішуче підвищення зараз, швидше пом'якшення пізніше"],
    notes="Наша базова інфляція наприкінці 2027 вища, ніж у НБУ, бо ринок праці перегрітий, а атаки на енергетику "
          "підвищують витрати. Загальна інфляція близька до НБУ, бо дешевша за ф'ючерсами нафта частково компенсує "
          "тарифи й акцизи. У 2028 базова інфляція опускається нижче цілі — як і в прогнозі НБУ, — тому орієнтир "
          "на зниження ставки з другого півріччя 2027 року.")

gap27 = sum(Q[f"2027Q{i}"]["l_gdp_gap"] for i in range(1, 5)) / 4
nbu_gap27 = float(read_ir_chart("2.18").iloc[:, 0].loc[2027])
add(type="chart", section="Прогноз",
    title=f"Ми бачимо слабший попит, ніж НБУ: розрив ВВП у 2027 ≈{n(gap27)}% проти {n(nbu_gap27)}%",
    image=img("fc_gap_vs_nbu"), layout="right", side_image=img("fc_trends"),
    bullets=[f"ВВП: {n(VS['2026']['ВВП, наш'])}% / {n(VS['2027']['ВВП, наш'])}% / {n(VS['2028']['ВВП, наш'])}% у 2026–2028 "
             f"(НБУ: {n(VS['2026']['ВВП, НБУ липень'])} / {n(VS['2027']['ВВП, НБУ липень'])} / {n(VS['2028']['ВВП, НБУ липень'])}%)",
             "Причини: слабкий III кв., атаки на логістику, блокада портів, дефіцит кадрів",
             f"У моделі реальна ставка зараз ≈{n(rir_now)}% — близько нейтральної (≈{n(rir_tnd_now)}%); за {pr(REC['rate'])}% вона зросте до "
             f"≈{n(rir_q2)}% у II кв. 2027: політика стає стримувальною в міру зниження інфляції"],
    notes="Наша оцінка розриву ВВП близька до НБУ в історії, але на 2027 рік ми консервативніші: бюджетний імпульс "
          "частково нівелюється атаками і нестачею працівників.")

scn = SC
fg, hw, oil, bs = (scn[k] for k in ("Дефіцит фінансування", "Важка зима", "Нафта $120", "Базовий"))
fx_dep = (fg["Курс IV кв. 2027, грн/€"] / bs["Курс IV кв. 2027, грн/€"] - 1) * 100
add(type="chart_table", section="Прогноз", title="Сценарії: найнебезпечніший — дефіцит фінансування, а не зима чи нафта",
    image=ml_img("ml_scenarios", "fc_scenarios"), layout="stack",
    table={"header": ["Сценарій", "ІСЦ пік", "ІСЦ IV кв. 27", "Ставка пік", "грн/€ IV кв. 27", "ВВП 2027"],
           "rows": [[k, n(v["ІСЦ пік"]), n(v["ІСЦ IV кв. 2027"]), n(v["Ставка пік"]), n(v["Курс IV кв. 2027, грн/€"]),
                     n(v["ВВП 2027, % (рік)"])] for k, v in scn.items()]},
    bullets=[f"Дефіцит фінансування: гривня на ≈{n(fx_dep, 0)}% слабша (≈{n(fg['Курс IV кв. 2027, грн/€'], 0)} грн/€) → "
             f"інфляція до {n(fg['ІСЦ пік'])}%, ставка до {n(fg['Ставка пік'])}%",
             f"Важка зима: інфляція до {n(hw['ІСЦ пік'])}%, ставка до {n(hw['Ставка пік'])}%, ВВП 2027 — {n(hw['ВВП 2027, % (рік)'])}%",
             f"Нафта $120: +{n(oil['ІСЦ пік'] - bs['ІСЦ пік'])} в. п. до піку інфляції, ставка майже не змінюється",
             "Сприятливий: нижча премія за ризик → швидше пом'якшення"],
    notes="Сценарії побудовано поверх базового: однакове рішення в жовтні, далі правило Тейлора реагує на шоки "
          "сценарію навколо базової траєкторії ставки. Графік "
          "розраховано в MATLAB/IRIS за тими самими планами, що й у Python. Висновок: головний ризик для інфляції — "
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
        "Ціль 5% без діапазону, горизонт — до 3 років",
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
                    n(v["ІСЦ IV кв. 2027"]), n(v["ВВП 2027, %"]), n(v[LOSS])])
opt = K["optimal_paths"]
_best = sorted({float(pr_opt(BEST[k]).replace(",", ".")) for k in BEST})
best_rng = pr(_best[0]) if len(_best) == 1 else f"{pr(_best[0])}–{pr(_best[-1])}"
add(type="chart_table", section="Рекомендації",
    title="Варіанти рішення 29 жовтня: утримати 16% — найгірше; між 16,5 і 17,5% різниця мала — крок обираємо за ризиками",
    image=img("fc_policy"), layout="stack",
    table={"header": ["Рішення (до середини 2027)", "Ставка IV кв. 26", "Ставка IV кв. 27", "ІСЦ IV кв. 27", "ВВП 2027", "Втрати"],
           "rows": po_rows},
    bullets=[f"Втрати: відхилення інфляції від 5%, розрив ВВП, різкі зміни ставки; адмінціни — з вагою {ADMIN}% (вони ростуть "
             "щороку, але це перший раунд) — той самий принцип для рішення й усієї траєкторії",
             f"Оптимальна траєкторія починається з {n(opt['λ = 1']['2026Q4'])}% ({n(opt['λ = 2']['2026Q4'])}–{n(opt['λ = 0.5']['2026Q4'])}% "
             f"залежно від згладжування); найменші втрати серед утримань — {best_hold_rng}%: таблиця не вибирає крок",
             f"+1 в. п. — через ризики для курсу й очікувань: якщо гривня слабшатиме, як чекає ринок (≈5% на рік), "
             f"інфляція в IV кв. 2027 — ≈{n(FXR['cpi_2027Q4'])}% замість {n(Q['2027Q4']['cpi_yoy'])}%"],
    notes="Кожен варіант: ставка утримується до середини 2027, далі — траєкторія, яка повертає інфляцію до 5% на "
          "горизонті політики. Втрати — та сама функція, що й в оптимізації: квадрати відхилень інфляції від цілі, "
          "половина квадрата розриву ВВП і квадрати змін ставки за IV кв. 2026 – 2029.")

add(type="reco", section="Рекомендації", title=f"Облікова ставка: підвищити до {pr(REC['rate'])}% і утримувати до середини 2027",
    big=f"{pr(REC['rate'])}%", big_label=f"{n(REC['change_pp'], 1, True)} в. п. з 30.10.2026",
    groups=[{"head": "Чому підвищити", "items": [
        f"Вересень — 10,0%, значно вище прогнозу НБУ; у грудні — ≈{n(K['nowcast_dec_yoy'], 0)}%; ризики зміщені вгору",
        f"Базова інфляція наприкінці 2027 — {n(core['2027'])}% (НБУ: {n(nbu_core27)}%): ринок праці перегрітий",
        f"Курс і очікування: якщо гривня слабшатиме, як чекає ринок, інфляція IV кв. 2027 — ≈{n(FXR['cpi_2027Q4'], 0)}%",
        "Гнучкіший курс потребує сильного якоря — ставка має утримати очікування"]},
        {"head": "Чому не більше", "items": [
            f"ВВП III кв. скоротився; за {pr(REC['rate'])}% реальна ставка сама зросте з ≈{n(rir_now)}% до ≈{n(rir_q2)}% "
            "у II кв. 2027 — у міру зниження інфляції",
            f"Оптимальна траєкторія моделі починається з {n(opt['λ = 1']['2026Q4'])}%; адмінціни враховуємо на {ADMIN}%",
            "Підвищення має дійти до депозитів: обмежити обсяги тендерів 3-міс. ДС"]},
        {"head": "Орієнтири (forward guidance)", "items": [
            f"Утримання {pr(REC['rate'])}% щонайменше до середини 2027; далі зниження до ≈{n(half(Q['2027Q4']['ir_pol']))}% наприкінці 2027 "
            f"і ≈{n(half(Q['2028Q4']['ir_pol']))}% — 2028: інфляція 5% у {first_target_q[:4]}",
            f"Подальше підвищення (до ≈{n(fg['Ставка пік'], 0)}%) — якщо тиск на курс загрожує очікуванням (зростають "
            "девальваційні й інфляційні очікування)",
            "Швидше пом'якшення — якщо базова інфляція < 7% і очікування знижуються"]}],
    notes="Рекомендація — рішуче, але одноразове підвищення на 1 в. п. з чіткими умовами подальших дій.")

add(type="chart", section="Рекомендації",
    title=f"Курс і резерви: без допомоги резерви наблизяться до 3 місяців імпорту",
    image=img("fc_reserves"), layout="right",
    bullets=[f"Продаж НБУ ≈${n(RR['sales_per_month'])} млрд/міс, надходження ≈${n(RR['inflows_per_month'])} млрд/міс. НБУ (липень) "
             f"чекав ${n(RN['end2026'])} млрд на кінець 2026 — для цього треба ≈${n(RN['inflow_needed_per_month'], 0)} млрд/міс",
             f"Наші сценарії на кінець 2026: ${n(RES['Надолуження допомоги'], 0)} / {n(RES['Як у липні–вересні'], 0)} / "
             f"{n(RES['Затримка допомоги'], 0)} млрд = {n(RESM['Надолуження допомоги'])} / {n(RESM['Як у липні–вересні'])} / "
             f"{n(RESM['Затримка допомоги'])} міс. імпорту 2027 р. (як рахує НБУ)",
             f"Ринок чекає ≈{n(fx_exp['Фінансові аналітики'], 0)} грн/$ через рік (≈{n((fx_exp['Фінансові аналітики'] / usd_now - 1) * 100, 0)}% "
             f"послаблення); за ставки {pr(REC['rate'])}% модель дає ≈{n(fx_yr, 0)}% на рік",
             f"Рекомендація: не заморожувати курс (≈{n(usd_now)} грн/$ з червня); інтервенції — лише згладжувати. Резерви "
             "залежать від ритму допомоги (продаж валюти її «доносить»), тому захищає їх пауза в лібералізації"],
    notes="Простий балансовий розрахунок: резерви = попередні + офіційні надходження − продаж валюти НБУ. "
          "Регресія інтервенцій на модельну змінну не дала значущого зв'язку, тому ми не використовували підхід «1% курсу = X млрд».")

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
        f"НБУ підвищує ставку на {n(REC['change_pp'], 0)} в. п., щоб інфляція повернулася до 5% у {first_target_q[:4]} році",
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
          "прискорення інфляції, зміщення ризиків угору та зниження міжнародних резервів. НБУ утримуватиме ставку "
          "щонайменше до середини 2027 року та допускатиме більшу гнучкість курсу, згладжуючи надмірні коливання».",
    notes="Комунікація має пояснити логіку пакета: ставка — якір очікувань, курс — амортизатор шоків.")

add(type="summary_end", section="Рекомендації", title="Підсумок",
    items=[f"Підвищити облікову ставку до {pr(REC['rate'])}% та утримувати щонайменше до середини 2027",
           "Не заморожувати курс; обмежити обсяги тендерів депсертифікатів, щоб підвищення дійшло до депозитів",
           "Пауза в лібералізації валютних обмежень до відновлення резервів і допомоги",
           f"Базовий прогноз: інфляція ≈{n(K['nowcast_dec_yoy'])}% у грудні 2026, {n(Q['2027Q4']['cpi_yoy'])}% у IV кв. 2027, "
           f"стабільно 5% — з {qlabel(first_target_q)}"],
    notes="Дякуємо! Готові до запитань.")

# ----------------------------------------------------------------------------------------------- appendix
add(type="section", section="Додатки", number="", title="Додатки", subtitle="")
add(type="equations", section="Додатки", title="Додаток 1. Модель: QPM НБУ + розширення команди",
    eqs=[("Попит (розрив ВВП)", "ŷₜ = 0,7·ŷₜ₋₁ − 0,4·MCIₜ + 0,3·ŷ*ₜ + εʸ;   MCI = −0,5·z̃ + 0,3·r̃ + 0,2·prem̃"),
         ("Базова інфляція (Філіпс)", "πᶜₜ = 0,4·πᶜₜ₋₁ + 0,6·Eₜπᶜₜ₊₁ + 0,3·rmcₜ + εᶜ;   rmc = 0,6·ŷ + 0,4·z̃,  z = s − pᶜ + p*"),
         ("Небазові ціни (наше)", "Δrncₜ = 0,3·Δrncₜ₋₁ + 0,016·(Δoilₜ + Δzₜ) + εⁿᶜ;   πₜ = πᶜₜ + Δrncₜ"),
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
          "Функції відгуку розраховано в MATLAB/IRIS.")
add(type="chart", section="Додатки",
    title="Додаток 3. Ставка має лишатися високою, доки прогноз інфляції вищий за ціль на 3–4 в. п.",
    image=img("fc_rate_drivers"), layout="right",
    bullets=["Головний чинник — прогноз інфляції на 3 квартали вперед вище цілі",
             "Розрив ВВП майже не тисне на ставку — це не «перегрів попиту», а шоки витрат",
             "З другого півріччя 2027 внесок інфляції зменшується → простір для зниження ставки",
             "Лінія вище стовпців у 2027–2028 — ставка тримається вище правила, щоб інфляція повернулася саме до 5%"],
    notes="Графік показує, на скільки ставка має бути вищою за нейтральну за правилом Тейлора і чому.")
if ML:
    add(type="chart", section="Додатки", title=f"Додаток 4. Python і MATLAB/IRIS дають той самий прогноз (розбіжність {matlab_diff})",
        image=img("fc_matlab_check"), layout="below",
        bullets=["Один файл моделі model/model.model, ті самі дані, параметри й плани всіх 5 сценаріїв",
                 "Фільтр Калмана 2016–2026 і прогнози до 2029 збігаються з точністю до округлення",
                 "Збірка однією командою: python build.py → MATLAB → звірка → графіки → презентація"],
        notes="Лінії — розрахунок у Python, кружки — у MATLAB R2026b з IRIS. Це підтверджує, що наш Python-порт і "
              "розширення моделі коректні, а графіки MATLAB у презентації відповідають тим самим цифрам.")
bt_tab = table_csv("backtest_2025Q3")
add(type="chart", section="Додатки", title=f"Додаток {5 if ML else 4}. Бектест: прогноз з даними до III кв. 2025",
    image=img("fc_backtest"), layout="below",
    bullets=[f"Помилка прогнозу ІСЦ на 4 квартали: {n(bt_cpi['model'].min())}–{n(bt_cpi['model'].max())} в. п. (наївний прогноз: "
             f"{n(bt_cpi['naive'].min())}–{n(bt_cpi['naive'].max())})",
             "Ставку краще прогнозує «без змін»: НБУ змінює її рідко",
             "Курс грн/€ модель не прогнозує краще за наївний — залежить від EUR/USD (обмеження моделі)"],
    notes="Бектест квазіреальний: зовнішні змінні — фактичні, судження не використовувалися.")
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
        f"Друге — не заморожувати курс: з червня гривня стоїть біля {n(usd_now, 0)} за долар, а курс має поглинати шоки. "
        "І обмежити обсяги тендерів депсертифікатів, щоб підвищення дійшло до депозитів. Третє — поставити "
        f"на паузу наступні кроки валютної лібералізації, доки не відновляться резерви. За такої політики інфляція "
        f"знизиться до {q27}% у четвертому кварталі 2027 року і стабілізується на 5% у {tq} — у межах трирічного горизонту НБУ.",
    "Зовнішнє середовище":
        f"Зовнішнє середовище стало помітно проінфляційним. Через війну на Близькому Сході нафта Brent у {brent_peak_m} "
        f"сягала {n(brent_peak, 0)} доларів за барель, а у вересні–жовтні знову перевищила 100 — тоді як НБУ в липні "
        f"закладав 80–85. Ринок очікує здешевлення: ф'ючерси вказують на {n(BP['2027Q4'], 0)} доларів наприкінці 2027 року, "
        "і саме цю криву ми беремо в прогноз. Водночас ЄЦБ підвищує ставку, тож простору для пом'якшення в Україні менше.",
    "Інфляція у вересні":
        "У вересні інфляція стрибнула до 10% — ціни за місяць зросли на 2,1%. Пальне подорожчало на 46% за рік, "
        "атаки на склади й логістику здорожчили доставку. Але більше нас турбує базова інфляція: вона прискорилася "
        "до 8,8%, послуги дорожчають на 14%. І навіть продовольство, яке досі стримувало ціни, почало дорожчати.",
    "Очікування підвищені":
        "Інфляційні очікування підвищені: домогосподарства чекають 10–14% — більше, ніж фактична інфляція, а "
        f"фінансові аналітики підвищили свої очікування до {n(exp_an)}%. Реальна ставка від очікувань аналітиків — близько "
        f"{n(rr_ante_an, 0)}%, але від фактичної інфляції вона знизилася з {n(rr_post_prev, 0)} до {n(rr_post, 0)}%. А великі банки "
        "майже не підняли депозитні ставки, тож трансмісія слабка, і ризик розбалансування очікувань реальний.",
    "Економіка сповільнюється":
        "Економіка тим часом сповільнюється. ВВП у другому кварталі зріс лише на 0,4% за рік, а у третьому, за "
        "оцінкою КМП, — суттєво гірше прогнозу НБУ. Атаки на енергетику, логістику й порти забирають близько "
        "0,9 пункта зростання. Водночас ринок праці перегрітий: через дефіцит кадрів номінальні зарплати цього року "
        f"зростають на {wages_rng.replace('–', '–')}%. Тож навіть за слабкого ВВП тиск на ціни послуг зберігається.",
    "НБУ продає":
        f"Найгостріша проблема — валютний ринок. НБУ продає в середньому близько {n(RR['sales_per_month'])} мільярда "
        "доларів на місяць, у вересні — рекордні 5,5 мільярда. Резерви за два місяці скоротилися з 51,2 до 47,1 "
        "мільярда, тоді як НБУ очікував 53,8. Але важливо: продаж валюти здебільшого «доносить» допомогу на ринок — у "
        "вересні уряд конвертував 3,81 мільярда оборонного траншу. Тож резерви падають через ритм допомоги. А курс "
        f"із червня фактично заморожений — близько {n(usd_now, 1)} гривні за долар.",
    "Платіжний баланс":
        f"Звідки тиск на резерви — видно з платіжного балансу. Імпорт цього року в {n(m26 / e26)} раза більший за "
        f"експорт, дефіцит — близько {n(m26 - e26, 0)} мільярдів доларів. Поточний рахунок фінансують позики партнерів. "
        f"Але офіційне фінансування скорочується з {n(of26, 0)} мільярдів у 2026 році до {n(of28, 0)} у 2028-му, і, за "
        f"прогнозом НБУ, поточний рахунок тоді погіршиться до мінус {n(-ca28, 0)} мільярдів. Тому резерви потрібні як "
        "буфер, а лібералізацію варто проводити поступово.",
    "Бюджет залежить від допомоги":
        "Причина — залежність бюджету від допомоги. Дефіцит без грантів — близько 35% ВВП, потреба у зовнішньому "
        "фінансуванні — 87 мільярдів доларів, а влітку надходження затрималися. Оборонний кредит USL — водночас "
        "бюджетний імпульс для попиту і додатковий попит на валюту. Уряд у Бюджетній декларації закладає інфляцію "
        "8,9% наприкінці 2027 року — вище, ніж НБУ і ми.",
    "Модель:":
        "Тепер — прогноз. Ми взяли квартальну прогнозну модель НБУ, переписали її на Python і розширили. Дані "
        "завантажуються автоматично, фільтр Калмана оцінює розриви й тренди, далі — прогноз із судженнями й аналіз "
        "політики. Той самий файл моделі ми проганяємо в MATLAB з IRIS: розбіжність — у п'ятому знаку, а графіки "
        "сценаріїв у презентації побудовані в MATLAB.",
    "Наше розширення QPM":
        "Що ми змінили в моделі. У шаблоні одна крива Філіпса для всієї інфляції, тож нафтовий шок дає хибні "
        "коливання через курс. Ми розділили інфляцію на базову і небазову: небазові ціни реагують на нафту та курс. "
        "Нафта на 20% дорожча — це плюс 0,3 пункта до інфляції впродовж року, ставка зростає лише на 0,2 пункта, а "
        "базова інфляція не прискорюється. Без цього каналу модель точно збігається з шаблоном НБУ.",
    "Припущення та судження":
        "Модель не описує все — енергетику, бюджет, допомогу, тарифи. Тому ці чинники входять через явні судження, "
        "і кожне має кількісне обґрунтування та джерело. Наприклад, вторинні ефекти атак в опалювальний сезон ми "
        "калібруємо за оцінкою НБУ. Окремо закладаємо адмінціни й акцизи: у 2016–2026 роках загальна інфляція в "
        "середньому перевищувала базову на 1,7 пункта на рік, і НБУ закладає таку саму різницю на 2027–2028 роки.",
    "Короткостроковий прогноз":
        "Для найближчих місяців ми будуємо короткостроковий прогноз: трендовий темп цін, сезонність і поправка на "
        f"разовість вересневого стрибка. Тренд — {n(nc_trend, 2)}% на місяць. До того ж діє ефект бази: у {base_span} "
        f"ціни зросли лише на {n(base_effect)}%. Тому річна інфляція підніметься до {dec}% у грудні — помітно вище, "
        "ніж НБУ прогнозував у липні.",
    "Інфляція досягне піку":
        "Базовий прогноз. Нагадаю: ціль НБУ — 5% без діапазону відхилень, і повернути інфляцію до неї треба на "
        f"горизонті до трьох років. У середньому за квартал інфляція досягне піку — близько {n(SC['Базовий']['ІСЦ пік'])}% — "
        f"на початку 2027 року; у місячному вимірі це близько {dec0}% у грудні. Далі вона знизиться до {q27}% у четвертому "
        f"кварталі 2027-го, у 2028-му коливатиметься біля 5% — до {n(dip28)}% у мінімумі — і з {tq} стабілізується на 5%. Ставка — {pr(REC['rate'])}% до середини 2027 року, далі поступово "
        f"знижується до {r28}% наприкінці 2028-го. Невизначеність велика — це показує віяло.",
    "Базова інфляція в 2027":
        f"Важлива відмінність від НБУ — базова інфляція. Ми вважаємо, що вона буде стійкішою: {n(core['2027'])}% "
        f"наприкінці 2027 року проти {n(nbu_core27)}% у НБУ. Причина — перегрітий ринок праці, дорожчі послуги й "
        "наслідки атак. Загальна інфляція при цьому близька до НБУ: тарифи й акцизи додають близько 1,7 пункта на "
        "рік, а дешевша нафта частково це компенсує. Висновок: підвищити ставку зараз, щоб швидше пом'якшити її пізніше.",
    "слабший попит":
        f"Попит ми бачимо слабшим, ніж НБУ: {g26s}, {n(VS['2027']['ВВП, наш'])}% у 2027-му і "
        f"{n(VS['2028']['ВВП, наш'])}% у 2028-му проти {n(VS['2026']['ВВП, НБУ липень'])}, "
        f"{n(VS['2027']['ВВП, НБУ липень'])} і {n(VS['2028']['ВВП, НБУ липень'])}% у НБУ. Причини — слабкий третій "
        f"квартал, атаки, блокада портів і дефіцит кадрів. У моделі реальна ставка зараз близька до нейтральної. "
        f"За {pr(REC['rate'])}% вона зросте до {n(rir_q2, 0)}% у другому кварталі 2027-го сама собою, бо інфляція "
        "знижуватиметься, — тому одного рішучого кроку достатньо, різкішого посилення не потрібно.",
    "Сценарії:":
        "Ми розглянули чотири ризикові сценарії, розраховані в MATLAB. Найнебезпечніший — дефіцит фінансування: "
        f"якщо допомога затримається, гривня буде приблизно на {n(fx_dep, 0)}% слабшою, інфляція зросте до "
        f"{n(fg['ІСЦ пік'])}%, а ставку доведеться підняти до {n(fg['Ставка пік'])}%. Важка зима з ударами по "
        f"енергетиці підніме інфляцію до {n(hw['ІСЦ пік'])}% і майже зупинить зростання ВВП. Натомість нафта по "
        f"120 доларів додає лише {n(oil['ІСЦ пік'] - bs['ІСЦ пік'])} пункта до піку інфляції, і ставка майже не "
        "реагує — це шок першого раунду. Висновок: головний ризик для інфляції — курс і резерви.",
    "Матриця ризиків":
        "Матриця ризиків підсумовує: більшість імовірних і сильних ризиків — проінфляційні. Це атаки на "
        "енергетику, затримки допомоги, розбалансування очікувань і зарплатна спіраль. Дезінфляційних менше — "
        "блокада портів, охолодження попиту, можливе перемир'я. Баланс зміщений угору.",
    "Рамка рішення":
        "Переходимо до рекомендацій. Спершу — рамка. Головна мета НБУ — цінова стабільність: ціль 5% без діапазону, "
        "і повернути до неї інфляцію треба на горизонті до трьох років. Інструменти — облікова ставка, депозитні "
        "сертифікати, які з серпня розміщуються на тендерах, валютні інтервенції та обмеження. У вересні КМП підвищив "
        "ставку до 16%, але думки розділилися: семеро вважають, що цього достатньо, двоє чекають ще одного "
        "підвищення, один — зниження. Ми — за підвищення, і ось чому.",
    "Варіанти рішення":
        "Ми порівняли чотири варіанти рішення — від утримання 16% до підвищення до 17,5%. У кожному ставка "
        "утримується до середини 2027 року, а далі знижується так, щоб інфляція повернулася саме до 5%. "
        "Критерій — втрати: відхилення інфляції від цілі, розрив ВВП і різкі зміни ставки. Адмінціни ми враховуємо "
        f"наполовину: вони ростуть щороку, але це перший раунд. Утримання 16% — найгірший варіант за будь-яких ваг. "
        f"Оптимальна траєкторія моделі починається з {n(opt['λ = 1']['2026Q4'])}%, але між 16,5 і 17,5% різниця втрат мала. "
        f"Тому крок у пункт ми обираємо за ризиками: якщо гривня слабшатиме, як чекає ринок, інфляція наприкінці 2027 "
        f"року буде близько {n(FXR['cpi_2027Q4'], 0)}%, а не {n(Q['2027Q4']['cpi_yoy'], 0)}.",
    "Облікова ставка: підвищити":
        f"Тому перша рекомендація — підвищити облікову ставку до {pr(REC['rate'])}%. Чому підвищити: інфляція в грудні "
        f"сягне близько {dec0}%, базова інфляція прискорюється, курсові ризики високі, а гнучкіший курс потребує "
        "сильного якоря для очікувань. Чому не більше: економіка слабка, а шоки здебільшого з боку пропозиції. "
        f"Орієнтир: утримувати {pr(REC['rate'])}% щонайменше до середини 2027 року, далі знижувати — до близько {r27h}% "
        f"наприкінці 2027-го і {n(half(Q['2028Q4']['ir_pol']))}% наприкінці 2028-го. Якщо тиск на курс почне розхитувати "
        "очікування — готові підвищувати далі; якщо базова інфляція опуститься нижче 7% — знижувати швидше.",
    "Курс і резерви":
        f"Друга рекомендація — щодо курсу. НБУ продає близько {n(RR['sales_per_month'])} мільярда доларів на місяць, а "
        f"надходить близько {n(RR['inflows_per_month'])}. Якщо так і залишиться, на кінець року резерви становитимуть {n(RES['Як у липні–вересні'], 0)} мільярди. Але продаж валюти "
        "здебільшого «доносить» допомогу до ринку, тож резерви визначає її ритм, а не курс. Наша рекомендація щодо курсу "
        f"інша: не заморожувати його. З червня гривня стоїть біля {n(usd_now, 1)} за долар, хоча за рік до того "
        f"послабилася на {n(usd_dep_yr, 0)}%. Курс має поглинати шоки, а НБУ — лише згладжувати коливання.",
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
        f"лібералізації валютних обмежень. За такої політики інфляція стабілізується на 5% у {tq}. Дякуємо за увагу! "
        "Будемо раді відповісти на ваші запитання.",
}
WPM = 120   # planning pace for a talk in Ukrainian, words per minute
SPEAKERS = {None: "Доповідач 1", "Огляд": "Доповідач 1", "Прогноз": "Доповідач 2", "Рекомендації": "Доповідач 3"}
used = set()
talk = []
for i, sl in enumerate(slides, 1):
    if sl["section"] == "Додатки" or sl["type"] == "section":
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
       "≈14 хв, тобто є запас до 15. Розподіл на трьох доповідачів — за розділами (якщо доповідачів інша кількість, "
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
    "Економіка сповільнюється": ["gdp_q2", "ir_data", "kmp"],
    "НБУ продає": ["api", "res_sep", "pyshnyi"],
    "Бюджет залежить": ["nbu_fc", "ir_data", "imf"],
    "Платіжний баланс": ["nbu_fc", "ir_data"],
    "Рамка рішення": ["law", "mpg", "kmp", "cd"],
    "Модель:": ["template", "api", "ecb", "eurostat"],
    "Наше розширення QPM": ["ccpi", "eia", "fut"],
    "Припущення та судження": ["ir", "nbu_fc", "kmp"],
    "Короткостроковий прогноз": ["api", "cpi_sep"],
    "Інфляція досягне піку": ["mpg", "nbu_fc"],
    "Базова інфляція в 2027": ["ccpi", "nbu_fc"],
    "слабший попит": ["ir_data", "nbu_fc", "gdp_q2"],
    "Ставка має лишатися високою": ["template"],
    "Сценарії:": ["kmp", "fut", "nbu_fc"],
    "Матриця ризиків": ["kmp", "ir"],
    "Варіанти рішення": ["mpg"],
    "Облікова ставка: підвищити": ["rate", "kmp"],
    "Курс і резерви": ["res_sep", "pyshnyi", "nbu_fc"],
    "Валютні обмеження": ["fx_pack", "fx_strat", "api"],
    "Комунікація": ["rate"],
    "Додаток 1.": ["template"],
    "Додаток 2.": ["template"],
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
