"""Soil intelligence, crop recommendation, fertiliser & irrigation planning, crop statistics, weather and market data."""
import csv
import io
import json
import time
from datetime import date, datetime
from functools import lru_cache

import httpx
import joblib
import numpy as np
import pandas as pd

from .core import DATA, MODELS, execute, get_setting, rows

# ------------------------------------------------------------------ soil test interpretation
RATINGS = {  # commonly used Indian soil-test ratings (Soil Health Card)
    "N": (280, 560, "kg/ha"), "P": (10, 25, "kg/ha"), "K": (110, 280, "kg/ha"), "OC": (0.5, 0.75, "%"),
}

# pH range, water need, ECe salinity threshold (Maas & Hoffman, dS/m), season
CROP_REQ = {
    "Rice": (5.0, 7.5, "high", 3.0, "Kharif / summer"), "Maize": (5.5, 7.5, "medium", 1.7, "Kharif / Rabi"),
    "Finger millet (ragi)": (5.0, 8.0, "low", None, "Kharif"), "Sorghum (jowar)": (5.5, 8.5, "low", 6.8, "Kharif / Rabi"),
    "Wheat": (6.0, 7.5, "medium", 6.0, "Rabi"), "Cotton": (5.8, 8.0, "medium", 7.7, "Kharif"),
    "Groundnut": (6.0, 7.5, "low", 3.2, "Kharif / summer"), "Chickpea": (6.0, 8.0, "low", None, "Rabi"),
    "Pigeon pea (tur)": (5.0, 7.5, "low", None, "Kharif"), "Sugarcane": (6.0, 7.5, "high", 1.7, "Annual"),
    "Tomato": (6.0, 7.0, "medium", 2.5, "All seasons"), "Potato": (5.0, 6.5, "medium", 1.7, "Rabi"),
    "Onion": (6.0, 7.0, "medium", 1.2, "Kharif / Rabi"), "Banana": (6.0, 7.5, "high", None, "Annual"),
    "Coffee": (5.0, 6.5, "high", None, "Perennial"), "Barley": (6.0, 8.5, "low", 8.0, "Rabi"),
}


def rate(param, value):
    lo, hi, unit = RATINGS[param]
    return {"value": value, "unit": unit, "rating": "Low" if value < lo else "Medium" if value <= hi else "High",
            "low_below": lo, "high_above": hi}


def ph_class(ph):
    for lim, cls, note in [(5.5, "Strongly acidic", "Apply agricultural lime based on a lime-requirement test; phosphorus gets fixed."),
                           (6.5, "Moderately to slightly acidic", "Suitable for most crops; acid-tolerant crops do well."),
                           (7.5, "Neutral", "Ideal range; most nutrients are readily available."),
                           (8.5, "Alkaline", "Zinc, iron and phosphorus availability falls; add organic manure, use acid-forming fertilisers."),
                           (99, "Strongly alkaline / sodic", "Needs gypsum reclamation (gypsum-requirement test) and drainage.")]:
        if ph < lim:
            return {"class": cls, "advice": note}


def ec_class(ec):
    if ec is None:
        return None
    if ec < 1:
        return {"class": "Normal", "advice": "No salinity problem."}
    if ec < 2:
        return {"class": "Critical for sensitive crops", "advice": "Avoid salt-sensitive crops (beans, onion); improve drainage."}
    if ec < 3:
        return {"class": "Injurious to sensitive crops", "advice": "Grow tolerant crops; leach salts with good-quality water."}
    return {"class": "Injurious to most crops", "advice": "Reclaim by leaching and drainage; choose highly tolerant crops (barley, cotton)."}


def soil_analysis(N, P, K, ph, oc=None, ec=None, rainfall=None, irrigated=False):
    r = {"N": rate("N", N), "P": rate("P", P), "K": rate("K", K)}
    if oc is not None:
        r["OC"] = rate("OC", oc)
    ph_info = ph_class(ph)
    ec_info = ec_class(ec)
    suit = []
    for crop, (lo, hi, water, ece, season) in CROP_REQ.items():
        score, reasons = 100, []
        if ph < lo:
            score -= min(60, (lo - ph) * 40); reasons.append(f"pH below preferred {lo}–{hi}")
        elif ph > hi:
            score -= min(60, (ph - hi) * 40); reasons.append(f"pH above preferred {lo}–{hi}")
        else:
            reasons.append(f"pH within preferred {lo}–{hi}")
        if water == "high" and not irrigated and rainfall is not None and rainfall < 1000:
            score -= 35; reasons.append("needs assured water (low rainfall, no irrigation)")
        if ec is not None and ece is not None and ec * 2 > ece:  # EC(1:2) roughly ×2 → ECe (approximation)
            score -= 30; reasons.append(f"salinity may exceed tolerance (~{ece} dS/m ECe)")
        suit.append({"crop": crop, "score": int(max(0, round(score))), "water_need": water, "season": season,
                     "reasons": reasons})
    suit.sort(key=lambda s: -s["score"])
    fert_adj = {k: {"Low": "+25%", "Medium": "as recommended", "High": "−25%"}[v["rating"]] for k, v in r.items() if k in "NPK"}
    tips = []
    if r["N"]["rating"] == "Low":
        tips.append("Nitrogen is low: split nitrogen into 2–3 doses, add FYM/compost and grow legumes in rotation.")
    if r["P"]["rating"] == "Low":
        tips.append("Phosphorus is low: apply the full phosphorus dose at sowing (DAP/SSP) placed near the seed row; use phosphate-solubilising bacteria.")
    if r["K"]["rating"] == "Low":
        tips.append("Potassium is low: apply muriate of potash (MOP); important for grain filling and disease resistance.")
    if oc is not None and oc < 0.5:
        tips.append("Organic carbon is low: add 5–10 t/ha FYM/compost, green manure (sunhemp/dhaincha) and retain crop residue.")
    tips.append(ph_info["advice"])
    if ec_info and ec_info["class"] != "Normal":
        tips.append(ec_info["advice"])
    return {"ratings": r, "ph": {"value": ph, **ph_info}, "ec": ({"value": ec, **ec_info} if ec_info else None),
            "fertiliser_adjustment": fert_adj, "suitability": suit, "tips": tips,
            "method": "Soil Health Card fertility ratings + crop pH / water / salinity tolerance tables (FAO, Maas & Hoffman)."}


def soil_summary_template(a):
    r = a["ratings"]
    best = ", ".join(s["crop"] for s in a["suitability"][:4])
    return (f"Your soil is {a['ph']['class'].lower()} (pH {a['ph']['value']}). Nitrogen is {r['N']['rating'].lower()}, "
            f"phosphorus is {r['P']['rating'].lower()} and potassium is {r['K']['rating'].lower()}. "
            f"Crops best matched to this soil include {best}. " + " ".join(a["tips"][:3]))


# ------------------------------------------------------------------ crop recommendation (ML)
@lru_cache
def _crop_model():
    return joblib.load(MODELS / "crop_model.joblib")


@lru_cache
def _crop_profiles():
    return json.loads((MODELS / "crop_profiles.json").read_text())


@lru_cache
def _crop_ranges():
    df = pd.read_csv(DATA / "crop_recommendation.csv")
    return {c: (float(df[c].min()), float(df[c].max())) for c in ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]}


def recommend_crops(features: dict, top=5):
    m = _crop_model()
    x = np.array([[features[f] for f in m["features"]]], dtype=float)
    proba = m["model"].predict_proba(x)[0]
    classes = m["model"].classes_
    order = np.argsort(-proba)[:top]
    prof = _crop_profiles()
    out = []
    for i in order:
        c = classes[i]
        cmp_ = {f: {"you": features[f], **prof[c][f],
                    "status": "low" if features[f] < prof[c][f]["p10"] else "high" if features[f] > prof[c][f]["p90"] else "typical"}
                for f in m["features"]}
        out.append({"crop": c, "probability": round(float(proba[i]), 4), "comparison": cmp_})
    rng = _crop_ranges()
    oor = [f"{f} = {features[f]} is outside the training range {lo:g}–{hi:g}" for f, (lo, hi) in rng.items()
           if not lo <= features[f] <= hi]
    return {"recommendations": out, "out_of_range": oor, "model": type(m["model"]).__name__,
            "metrics": json.loads((MODELS / "crop_metrics.json").read_text())}


# ------------------------------------------------------------------ fertiliser calculator
def fertiliser_plan(n, p2o5, k2o, area_ha=1.0, adjust=None):
    adjust = adjust or {}
    f = {"Low": 1.25, "Medium": 1.0, "High": 0.75}
    n, p2o5, k2o = n * f.get(adjust.get("N"), 1), p2o5 * f.get(adjust.get("P"), 1), k2o * f.get(adjust.get("K"), 1)
    dap = p2o5 / 0.46
    n_from_dap = dap * 0.18
    urea = max(0.0, (n - n_from_dap) / 0.46)
    mop = k2o / 0.60
    per_ha = {"DAP": dap, "Urea": urea, "MOP": mop}
    return {"target_per_ha": {"N": round(n, 1), "P2O5": round(p2o5, 1), "K2O": round(k2o, 1)},
            "products_per_ha_kg": {k: round(v, 1) for k, v in per_ha.items()},
            "products_total_kg": {k: round(v * area_ha, 1) for k, v in per_ha.items()},
            "bags_50kg_total": {k: round(v * area_ha / 50, 1) for k, v in per_ha.items()},
            "schedule": ["Apply all DAP and MOP plus about one third of the urea as basal dose at sowing/transplanting.",
                         "Top-dress the remaining urea in two equal splits at active vegetative growth and before flowering.",
                         "Apply fertiliser to moist soil and incorporate; avoid application just before heavy rain."],
            "basis": "DAP 18-46-0, Urea 46% N, MOP 60% K2O; soil rating adjustment Low +25%, High −25%."}


# ------------------------------------------------------------------ irrigation (FAO-56)
KC = {  # ini, mid, end (FAO-56 Table 12)
    "Rice": (1.05, 1.20, 0.75), "Maize": (0.30, 1.20, 0.45), "Tomato": (0.60, 1.15, 0.80), "Potato": (0.50, 1.15, 0.75),
    "Capsicum": (0.60, 1.05, 0.90), "Finger millet (ragi)": (0.30, 1.00, 0.30), "Groundnut": (0.40, 1.15, 0.60),
    "Cotton": (0.35, 1.18, 0.60), "Sugarcane": (0.40, 1.25, 0.75), "Onion": (0.70, 1.05, 0.75), "Chickpea": (0.40, 1.00, 0.35),
    "Wheat": (0.30, 1.15, 0.30), "Banana": (0.50, 1.10, 1.00),
}
EFF = {"drip": 0.90, "sprinkler": 0.75, "surface": 0.55}


def irrigation_plan(crop, stage, et0_days: list[float], rain_days: list[float], method="drip", area_ha=1.0, dates=None):
    kc = KC[crop][{"initial": 0, "development": None, "mid": 1, "late": 2}[stage]] if stage != "development" \
        else round((KC[crop][0] + KC[crop][1]) / 2, 2)
    days = []
    for i, (e, r) in enumerate(zip(et0_days, rain_days)):
        etc = kc * e
        eff_rain = max(0.0, 0.8 * r - 2) if r > 2 else 0.0  # simple effective-rain approximation (small showers lost)
        net = max(0.0, etc - eff_rain)
        days.append({"date": dates[i] if dates else i + 1, "et0": round(e, 2), "rain": round(r, 1), "etc": round(etc, 2),
                     "effective_rain": round(eff_rain, 2), "net_mm": round(net, 2)})
    net_total = sum(d["net_mm"] for d in days)
    gross = net_total / EFF[method]
    return {"crop": crop, "stage": stage, "kc": kc, "method": method, "efficiency": EFF[method], "days": days,
            "net_total_mm": round(net_total, 1), "gross_total_mm": round(gross, 1),
            "litres_total": round(gross * 10000 * area_ha), "litres_per_day": round(gross * 10000 * area_ha / max(1, len(days))),
            "note": "ETc = Kc × ET0 (FAO-56). 1 mm over 1 ha = 10,000 litres. Effective rain approximated as 80% of rain above 2 mm/day."}


# ------------------------------------------------------------------ district crop statistics
@lru_cache
def _production():
    # Categorical text columns: ~6 MB in memory instead of ~58 MB.
    cats = {c: "category" for c in ("State_Name", "District_Name", "Season", "Crop")}
    d = pd.read_csv(DATA / "district_crop_production.csv.gz", dtype=cats)
    d["Season"] = d["Season"].cat.rename_categories(lambda x: str(x).strip())
    return d


def crop_stats_options():
    d = _production()
    states = sorted(d.State_Name.unique())
    return {"states": states, "seasons": sorted(d.Season.unique()), "years": [int(d.Crop_Year.min()), int(d.Crop_Year.max())]}


def districts(state):
    d = _production()
    return sorted(d[d.State_Name == state].District_Name.unique())


def crop_stats(state, district=None, season=None):
    d = _production()
    d = d[d.State_Name == state]
    if district:
        d = d[d.District_Name == district]
    if season and season != "All":
        d = d[d.Season == season]
    if d.empty:
        return {"top_crops": [], "trend": [], "seasons": []}
    last = int(d.Crop_Year.max())
    recent = d[d.Crop_Year >= last - 4]
    g = recent.groupby("Crop", observed=True).agg(area=("Area", "sum"), production=("Production", "sum"), years=("Crop_Year", "nunique")).reset_index()
    g["avg_area_ha"] = g.area / g.years
    g["yield_t_per_ha"] = np.where(g.area > 0, g.production / g.area, np.nan)
    g = g.sort_values("avg_area_ha", ascending=False).head(12)
    top_names = list(g.Crop.head(5))
    trend = d[d.Crop.isin(top_names)].groupby(["Crop_Year", "Crop"], observed=True).Area.sum().unstack(fill_value=0).reset_index()
    seas = recent.groupby("Season", observed=True).Area.sum().sort_values(ascending=False)
    return {"period": f"{last - 4}–{last}",
            "top_crops": [{"crop": r.Crop, "avg_area_ha": round(float(r.avg_area_ha), 1),
                           "yield": None if np.isnan(r.yield_t_per_ha) else round(float(r.yield_t_per_ha), 2)}
                          for r in g.itertuples()],
            "trend": json.loads(trend.rename(columns={"Crop_Year": "year"}).to_json(orient="records")),
            "trend_crops": top_names,
            "seasons": [{"season": s, "area_ha": round(float(a), 1)} for s, a in seas.items()],
            "source": "District-wise season-wise crop production statistics (DES, Ministry of Agriculture, via data.gov.in), 1997–2015. "
                      "Yield = production ÷ area; units for coconut (nuts) and cotton (bales) differ."}


def current_season(month=None):
    m = month or date.today().month
    if m in (6, 7, 8, 9):
        return "Kharif"
    if m in (10, 11, 12, 1):
        return "Rabi"
    return "Zaid (summer)"


# ------------------------------------------------------------------ weather (Open-Meteo, no key)
_wcache: dict = {}


def geocode(q):
    r = httpx.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": q, "count": 6, "language": "en"}, timeout=15)
    r.raise_for_status()
    return [{"name": x["name"], "admin1": x.get("admin1"), "country": x.get("country"), "lat": x["latitude"], "lon": x["longitude"]}
            for x in r.json().get("results", [])]


def weather(lat, lon):
    key = (round(lat, 2), round(lon, 2))
    if key in _wcache and time.time() - _wcache[key][0] < 1800:
        return _wcache[key][1]
    r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7, "past_days": 7,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration,"
                 "relative_humidity_2m_mean,wind_speed_10m_max,weather_code"})
    r.raise_for_status()
    j = r.json()
    dly = j["daily"]
    days = [{"date": dly["time"][i], "tmax": dly["temperature_2m_max"][i], "tmin": dly["temperature_2m_min"][i],
             "rain": dly["precipitation_sum"][i], "et0": dly["et0_fao_evapotranspiration"][i],
             "rh": dly["relative_humidity_2m_mean"][i], "wind": dly["wind_speed_10m_max"][i], "code": dly["weather_code"][i]}
            for i in range(len(dly["time"]))]
    today = date.today().isoformat()
    out = {"current": j.get("current", {}), "past": [d for d in days if d["date"] < today],
           "forecast": [d for d in days if d["date"] >= today], "timezone": j.get("timezone"),
           "source": "Open-Meteo (open-meteo.com)"}
    out["advisories"] = agro_advisories(out["forecast"])
    _wcache[key] = (time.time(), out)
    return out


def agro_advisories(fc):
    adv = []
    for d in fc[:5]:
        tmean = ((d["tmax"] or 0) + (d["tmin"] or 0)) / 2
        if (d["rh"] or 0) >= 85 and 15 <= tmean <= 25:
            adv.append({"date": d["date"], "level": "warning", "type": "disease",
                        "text": "Cool and humid: high risk of late blight and other fungal diseases. Scout tomato/potato; prefer protective sprays before rain."})
        if (d["rain"] or 0) >= 20:
            adv.append({"date": d["date"], "level": "warning", "type": "rain",
                        "text": f"Heavy rain expected ({d['rain']} mm): postpone fertiliser and pesticide application, clear field drains."})
        if (d["tmax"] or 0) >= 38:
            adv.append({"date": d["date"], "level": "warning", "type": "heat",
                        "text": "Heat stress: irrigate in the evening, mulch, avoid spraying in the afternoon."})
        if (d["wind"] or 0) < 15 and (d["rain"] or 0) < 1:
            adv.append({"date": d["date"], "level": "info", "type": "spray",
                        "text": "Good spraying window (low wind, no rain) in early morning or evening."})
    return adv


# ------------------------------------------------------------------ market prices (Agmarknet / data.gov.in)
AGMARK_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _date(v):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def store_prices(records, source):
    n = 0
    for r in records:
        d = _date(r.get("arrival_date"))
        if not d or not r.get("commodity"):
            continue
        execute("INSERT OR REPLACE INTO market_prices(state,district,market,commodity,variety,grade,arrival_date,min_price,"
                "max_price,modal_price,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (r.get("state"), r.get("district"), r.get("market"), r["commodity"].strip(), r.get("variety") or "",
                 r.get("grade") or "", d, _num(r.get("min_price")), _num(r.get("max_price")), _num(r.get("modal_price")), source))
        n += 1
    return n


def fetch_live_prices(state=None, commodity=None, limit=500):
    key = get_setting("data_gov_api_key")
    if not key:
        raise ValueError("A free data.gov.in API key is required for live Agmarknet prices. Add it in Admin → Model configuration.")
    base = {"api-key": key, "format": "json", "limit": limit}
    recs = []
    for style in ("{}.keyword", "{}"):
        params = dict(base)
        if state:
            params[f"filters[{style.format('state')}]"] = state
        if commodity:
            params[f"filters[{style.format('commodity')}]"] = commodity
        r = httpx.get(f"https://api.data.gov.in/resource/{AGMARK_RESOURCE}", params=params, timeout=30)
        r.raise_for_status()
        recs = r.json().get("records", [])
        if recs or not (state or commodity):
            break
    n = store_prices(recs, "data.gov.in (Agmarknet daily prices)")
    return {"fetched": len(recs), "stored": n}


def import_price_csv(raw: bytes):
    text = raw.decode("utf-8-sig", errors="replace")
    rdr = csv.DictReader(io.StringIO(text))
    cols = {c: c.lower().replace("_x0020_", " ").replace("_", " ").strip() for c in (rdr.fieldnames or [])}

    def find(*keys):
        for c, lc in cols.items():
            if any(k in lc for k in keys):
                return c
    m = {"state": find("state"), "district": find("district"), "market": find("market"), "commodity": find("commodity"),
         "variety": find("variety"), "grade": find("grade"), "arrival_date": find("arrival", "date"),
         "min_price": find("min"), "max_price": find("max"), "modal_price": find("modal")}
    if not m["commodity"] or not m["arrival_date"] or not m["modal_price"]:
        raise ValueError("CSV must have commodity, arrival date and modal price columns (Agmarknet export format).")
    recs = [{k: (r.get(c) if c else None) for k, c in m.items()} for r in rdr]
    return {"rows": len(recs), "stored": store_prices(recs, "CSV import")}


def price_overview():
    com = rows("SELECT commodity, COUNT(*) n, MIN(arrival_date) first, MAX(arrival_date) last FROM market_prices "
               "GROUP BY commodity ORDER BY n DESC")
    latest = rows("SELECT * FROM market_prices WHERE arrival_date=(SELECT MAX(arrival_date) FROM market_prices) "
                  "ORDER BY commodity LIMIT 200")
    return {"commodities": com, "latest": latest, "total": sum(c["n"] for c in com)}


def price_trend(commodity, market=None, state=None):
    q, p = "SELECT arrival_date d, AVG(modal_price) modal, MIN(min_price) min, MAX(max_price) max, COUNT(*) n FROM market_prices WHERE commodity=?", [commodity]
    if market:
        q += " AND market=?"; p.append(market)
    if state:
        q += " AND state=?"; p.append(state)
    series = rows(q + " GROUP BY arrival_date ORDER BY arrival_date", p)
    markets = rows("SELECT market, state, COUNT(*) n, AVG(modal_price) avg_modal FROM market_prices WHERE commodity=? "
                   "GROUP BY market, state ORDER BY n DESC LIMIT 50", (commodity,))
    stats = None
    if series:
        vals = [s["modal"] for s in series if s["modal"] is not None]
        if vals:
            stats = {"latest": round(vals[-1], 1), "mean": round(float(np.mean(vals)), 1), "min": round(min(vals), 1),
                     "max": round(max(vals), 1), "change_pct": round((vals[-1] - vals[0]) / vals[0] * 100, 1) if vals[0] else None}
    return {"series": series, "markets": markets, "stats": stats, "unit": "₹ per quintal"}
