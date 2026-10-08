"""Download fresh data from official open-data APIs (NBU, ECB, Eurostat)."""
from __future__ import annotations

import io
import time

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
NBU = "https://bank.gov.ua/NBUStatService/v1/statdirectory"
ECB = "https://data-api.ecb.europa.eu/service/data"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _get(url, **kw):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2)


# ------------------------------------------------------------------ NBU
# Codes of the NBU inflation API (checked against Sept 2025: CPI 11.9% y/y, +0.3% m/m)
CPI_TZEP = {"PCPM_": "mom",   # to previous month
            "PCCM_": "yoy",   # to the same month of the previous year
            "DTPY_": "ytd",   # to December of the previous year
            "PCCP_": "ytd_yoy"}  # cumulative period to the same period of the previous year


def nbu_cpi(start: str, end: str) -> pd.DataFrame:
    """National CPI and core CPI by reference month: m-o-m, y-o-y, YTD % (NBU API, data from Derzhstat).

    The API `date` is the reporting date (1st day of the following month): dt=20251001 holds September 2025.
    """
    rows = []
    for p in pd.period_range(start, end, freq="M"):
        rep = p + 1
        data = _get(f"{NBU}/inflation?period=m&date={rep.year}{rep.month:02d}&json").json()
        rec = {"period": p}
        for r in data:
            if r["ku"] is None and r["mcrd081"] == "Total":
                key = {"prices_price_cpi_": "cpi", "prices_price_ci_": "core"}.get(r["id_api"])
                tz = CPI_TZEP.get(r["tzep"])
                if key and tz:
                    rec[f"{key}_{tz}"] = r["value"]
        if len(rec) > 1:
            rows.append(rec)
    return pd.DataFrame(rows).set_index("period")


def nbu_cpi_components(month: str) -> pd.DataFrame:
    """All CPI rows for one month (COICOP groups by region) — for the inflation overview slides."""
    rep = pd.Period(month, "M") + 1  # reporting date = next month
    return pd.DataFrame(_get(f"{NBU}/inflation?period=m&date={rep.year}{rep.month:02d}&json").json())


def nbu_key_rate() -> pd.Series:
    """NBU key policy rate, daily."""
    data = _get(f"{NBU}/key?json").json()
    s = pd.Series({pd.Timestamp(r["dt"]): r["value"] for r in data if r["id_api"] == "KEY_PolicyRate"})
    return s.sort_index()


def nbu_fx(valcode: str, start: str, end: str) -> pd.Series:
    """Official NBU exchange rate (UAH per unit), daily."""
    s, e = pd.Timestamp(start).strftime("%Y%m%d"), pd.Timestamp(end).strftime("%Y%m%d")
    data = _get(f"https://bank.gov.ua/NBU_Exchange/exchange_site?start={s}&end={e}"
                f"&valcode={valcode.lower()}&sort=exchangedate&order=asc&json").json()
    return pd.Series({pd.to_datetime(r["exchangedate"], dayfirst=True): r["rate_per_unit"] for r in data}).sort_index()


def nbu_reserves() -> pd.DataFrame:
    """International reserves (monthly, $ mn) — all components."""
    return pd.DataFrame(_get(f"{NBU}/res?json").json())


# ------------------------------------------------------------------ ECB / Eurostat
def ecb_series(key: str, start: str) -> pd.Series:
    txt = _get(f"{ECB}/{key}?startPeriod={start}&format=csvdata").text
    df = pd.read_csv(io.StringIO(txt))
    return pd.Series(df["OBS_VALUE"].values, index=df["TIME_PERIOD"].values, name=key)


def ecb_deposit_rate(start="1999-01-01") -> pd.Series:
    s = ecb_series("FM/D.U2.EUR.4F.KR.DFR.LEV", start)
    s.index = pd.to_datetime(s.index)
    return s


def ea_gdp(start="2024-Q1") -> pd.Series:
    """Euro-area real GDP, chain-linked volumes, SA (EA21 from 2026: ECB code I10)."""
    s = ecb_series("MNA/Q.Y.I10.W2.S1.S1.B.B1GQ._Z._Z._Z.EUR.LR.N", start)
    s.index = pd.PeriodIndex(s.index.str.replace("-", ""), freq="Q")
    return s


def ea_hicp(start="2024-01") -> pd.Series:
    """Euro-area HICP all-items index (Eurostat prc_hicp_minr, COICOP 2018, 2025=100)."""
    d = _get(f"{EUROSTAT}/prc_hicp_minr?format=JSON&geo=EA&unit=I25&coicop18=TOTAL&sinceTimePeriod={start}").json()
    tl = d["dimension"]["time"]["category"]["index"]
    inv = {v: k for k, v in tl.items()}
    s = pd.Series({pd.Period(inv[int(k)], "M"): v for k, v in d["value"].items()}).sort_index()
    return s


def fred(series_id: str, start: str = "2023-01-01") -> pd.Series:
    """FRED series (no API key needed for the CSV endpoint), e.g. DCOILBRENTEU = Brent, $/bbl."""
    txt = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}").text
    df = pd.read_csv(io.StringIO(txt))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


# ------------------------------------------------------------------ oil
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
FUTURES_MONTH = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}


def _yahoo_daily(symbol: str, rng: str = "2y") -> pd.Series:
    j = _get(f"{YAHOO}/{symbol}?range={rng}&interval=1d").json()["chart"]["result"][0]
    s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s"))
    return s.dropna()


def brent_monthly(start: str = "1999-01") -> pd.Series:
    """Brent, $/bbl, monthly average: EIA spot (via DBnomics) + front-month futures (Yahoo) for the latest months."""
    doc = _get("https://api.db.nomics.world/v22/series/EIA/PET/RBRTE.M?observations=1").json()["series"]["docs"][0]
    eia = pd.Series(doc["value"], index=pd.PeriodIndex(doc["period"], freq="M"), dtype=float)
    fut = _yahoo_daily("BZ=F", "2y").resample("ME").mean()
    fut.index = fut.index.to_period("M")
    out = eia.combine_first(fut[fut.index > eia.index.max()])
    out.attrs["eia_last"] = str(eia.index.max())
    return out.loc[start:]


def brent_futures(months: list[str]) -> pd.Series:
    """Last price of Brent futures for contract months 'YYYY-MM' (NYMEX BZ, Yahoo)."""
    out = {}
    for m in months:
        p = pd.Period(m, "M")
        sym = f"BZ{FUTURES_MONTH[p.month]}{str(p.year)[2:]}.NYM"
        try:
            s = _yahoo_daily(sym, "5d")
            if len(s):
                out[p] = float(s.iloc[-1])
        except Exception:
            pass
    return pd.Series(out, dtype=float)


def ecb_usd_per_eur(start: str = "1999-01") -> pd.Series:
    """ECB reference rate, USD per EUR, monthly average."""
    s = ecb_series("EXR/M.USD.EUR.SP00.A", start)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s
