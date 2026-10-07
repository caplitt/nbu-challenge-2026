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
