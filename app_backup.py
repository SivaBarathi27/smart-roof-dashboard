"""Smart Retractable Roof — operations dashboard (Chennai site).

Run locally:  python -m streamlit run app.py
Model details and assumptions are documented in METHODOLOGY.md.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pvlib
import requests
import streamlit as st
import streamlit.components.v1 as components
from pythermalcomfort.models import utci

st.set_page_config(page_title="Smart Roof · Operations", page_icon="🏟️",
                   layout="wide", initial_sidebar_state="expanded")

# --------------------------------------------------------------------------- config
ROOT = Path(__file__).parent
SNAPSHOT = ROOT / "data" / "latest_weather.csv"
FALLBACK = ROOT / "chennai_hourly_weather_extended.csv"
SITE_NAME = "Playground Roof · Chennai"
LAT, LON, TZ = 13.0827, 80.2707, "Asia/Kolkata"

SIGMA = 5.670374419e-8
EMISSIVITY_PERSON = 0.95
SOLAR_ABSORPTIVITY_PERSON = 0.70
PERSON_DIRECT_PROJECTION = 0.25
SOIL_PROBE_DEPTH_M = 0.06
UTCI_BAND = (9.0, 26.0)
DEADBAND = 0.5

API_FIELDS = {
    "time": "timestamp",
    "temperature_2m": "air_temperature_C",
    "relative_humidity_2m": "relative_humidity_percent",
    "wind_speed_10m": "wind_speed_10m_ms",
    "shortwave_radiation": "solar_radiation_W_m2",
    "direct_radiation": "direct_radiation_W_m2",
    "direct_normal_irradiance": "direct_normal_irradiance_W_m2",
    "diffuse_radiation": "diffuse_radiation_W_m2",
    "soil_temperature_0cm": "soil_surface_temperature_C",
    "soil_temperature_6cm": "soil_temperature_6cm_C",
    "cloud_cover": "cloud_cover_percent",
}
CHART_SERIES = ["air_temperature_C", "relative_humidity_percent", "wind_speed_10m_ms",
                "solar_radiation_W_m2", "direct_normal_irradiance_W_m2", "diffuse_radiation_W_m2",
                "cloud_cover_percent", "mrt_open_C", "mrt_closed_C", "utci_open_C", "utci_closed_C",
                "heat_flux_open_W_m2", "heat_flux_closed_W_m2"]
OPEN_COLOR, CLOSED_COLOR = "#F5A524", "#4C8DF6"

roof_canvas = components.declare_component("roof_canvas", path=str(ROOT / "roof_canvas"))

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 1rem; max-width: 1600px;}
.topbar {display:flex; flex-wrap:wrap; align-items:center; gap:.6rem 1.2rem;}
.topbar h1 {font-size:1.55rem !important; margin:0; padding:0;}
.chip {font-size:.78rem; padding:.18rem .6rem; border-radius:999px; border:1px solid rgba(150,160,175,.35); white-space:nowrap;}
.chip .dot {display:inline-block; width:.5rem; height:.5rem; border-radius:50%; margin-right:.35rem;}
.stAppDeployButton {display:none;}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- data
def _finalise(df):
    df = df.rename(columns=API_FIELDS)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(TZ)
    for col in API_FIELDS.values():
        if col == "timestamp":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df else np.nan
    return df.sort_values("timestamp").reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def load_weather():
    """Live Open-Meteo feed; falls back to the last snapshot or bundled CSV."""
    try:
        params = {"latitude": LAT, "longitude": LON, "hourly": list(API_FIELDS)[1:],
                  "past_days": 1, "forecast_days": 2, "timezone": TZ, "wind_speed_unit": "ms"}
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
        response.raise_for_status()
        raw = pd.DataFrame(response.json()["hourly"])
        try:
            SNAPSHOT.parent.mkdir(exist_ok=True)
            raw.rename(columns=API_FIELDS).to_csv(SNAPSHOT, index=False)
        except OSError:
            pass  # read-only filesystem — snapshot is optional
        return _finalise(raw), "online", datetime.now(ZoneInfo(TZ))
    except (requests.RequestException, KeyError, ValueError):
        path = SNAPSHOT if SNAPSHOT.exists() else FALLBACK
        fetched = datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(TZ))
        return _finalise(pd.read_csv(path)), "offline", fetched


def band_distance(u):
    return np.maximum.reduce([UTCI_BAND[0] - u, np.zeros_like(u), u - UTCI_BAND[1]])


def decide(u_open, u_closed, current):
    """Thermal controller: target the 9–26 °C UTCI band with a deadband."""
    if not (np.isfinite(u_open) and np.isfinite(u_closed)):
        return current, "Comfort data unavailable — holding position."
    d_open, d_closed = band_distance(np.array([u_open, u_closed]))
    if d_closed + DEADBAND < d_open:
        return "CLOSED", f"Closing improves comfort (UTCI {u_closed:.1f} °C vs {u_open:.1f} °C open)."
    if d_open + DEADBAND < d_closed:
        return "OPEN", f"Open roof is more comfortable (UTCI {u_open:.1f} °C vs {u_closed:.1f} °C closed)."
    if u_open > UTCI_BAND[1] and u_closed > UTCI_BAND[1] and u_open - u_closed >= 1.0:
        return "CLOSED", f"Heat stress in both positions; closing lowers UTCI by {u_open - u_closed:.1f} °C."
    return current, None  # no meaningful benefit from moving — hold


@st.cache_data(show_spinner=False)
def compute(df, roof_offset, albedo, k_soil):
    df = df.copy()
    solar = pvlib.location.Location(LAT, LON, tz=TZ, altitude=6).get_solarposition(
        df["timestamp"] - pd.Timedelta(minutes=30))  # radiation = preceding-hour mean
    elev = solar["apparent_elevation"].to_numpy()
    df["solar_elevation_deg"] = elev

    ta = df["air_temperature_C"].to_numpy(float)
    rh = df["relative_humidity_percent"].to_numpy(float)
    wind = df["wind_speed_10m_ms"].to_numpy(float)
    soil = df["soil_surface_temperature_C"].to_numpy(float)
    soil6 = df["soil_temperature_6cm_C"].to_numpy(float)
    ghi = np.maximum(df["solar_radiation_W_m2"].to_numpy(float), 0)
    dhi = np.maximum(df["diffuse_radiation_W_m2"].to_numpy(float), 0)
    dni = np.maximum(df["direct_normal_irradiance_W_m2"].to_numpy(float), 0)
    cloud = np.clip(df["cloud_cover_percent"].to_numpy(float) / 100, 0, 1)
    tk = ta + 273.15

    # Mean radiant temperature — roof open
    vapour_hpa = (rh / 100) * 6.112 * np.exp(17.67 * ta / (ta + 243.5))
    eps_sky = np.clip(1.24 * (vapour_hpa / tk) ** (1 / 7) * (1 + 0.22 * cloud ** 2), 0.55, 1.0)
    lw_sky = eps_sky * SIGMA * tk ** 4
    lw_ground = SIGMA * (soil + 273.15) ** 4
    sun_scale = np.clip(np.sin(np.radians(elev)) / np.sin(np.radians(25)), 0, 1)
    sw_open = np.where(elev > 0, SOLAR_ABSORPTIVITY_PERSON * (
        PERSON_DIRECT_PROJECTION * sun_scale * dni + 0.5 * dhi + 0.5 * albedo * ghi), 0.0)
    lw_open = EMISSIVITY_PERSON * 0.5 * (lw_sky + lw_ground)
    df["mrt_open_C"] = ((lw_open + sw_open) / (EMISSIVITY_PERSON * SIGMA)) ** 0.25 - 273.15

    # Mean radiant temperature — roof closed (full shade)
    roof_t = ta + roof_offset * np.minimum(1.0, ghi / 800.0)
    ground_shaded = ta + 0.25 * (soil - ta)
    lw_closed = EMISSIVITY_PERSON * 0.5 * SIGMA * ((roof_t + 273.15) ** 4 + (ground_shaded + 273.15) ** 4)
    df["mrt_closed_C"] = (lw_closed / (EMISSIVITY_PERSON * SIGMA)) ** 0.25 - 273.15
    df["roof_underside_C"] = roof_t

    # UTCI (wind kept inside the model's 0.5–17 m/s validity range)
    v = np.clip(wind, 0.51, 16.9)
    for pos in ("open", "closed"):
        res = utci(tdb=ta, tr=df[f"mrt_{pos}_C"].to_numpy(), v=v, rh=rh)
        df[f"utci_{pos}_C"] = np.asarray(res.utci, dtype=float)
        df[f"category_{pos}"] = pd.Series(res.stress_category).fillna("unavailable").astype(str).to_numpy()

    # Ground surface heat flux (Fourier's law over the 0–6 cm soil layer), + = into ground
    df["heat_flux_open_W_m2"] = k_soil * (soil - soil6) / SOIL_PROBE_DEPTH_M
    df["heat_flux_closed_W_m2"] = k_soil * (ground_shaded - soil6) / SOIL_PROBE_DEPTH_M

    # Automatic controller run over the whole horizon
    state, states, reasons = "OPEN", [], []
    for uo, uc in zip(df["utci_open_C"], df["utci_closed_C"]):
        state, why = decide(uo, uc, state)
        states.append(state)
        reasons.append(why)
    df["auto_state"], df["auto_reason"] = states, reasons
    return df


# --------------------------------------------------------------------------- controller helpers
def next_change(df, i, state):
    """Run the controller forward from hour i, starting in `state`; first hour it moves."""
    current = state
    for j in range(i + 1, len(df)):
        current, _ = decide(df["utci_open_C"].iat[j], df["utci_closed_C"].iat[j], current)
        if current != state:
            return f"{current} at {df['timestamp'].iat[j].strftime('%a %H:%M')}"
    return "None in forecast"


def series(values):
    return [None if pd.isna(v) else round(float(v), 2) for v in values]


def manual_command(target):
    ss = st.session_state
    if target not in ("OPEN", "CLOSED") or target == ss.manual_state:
        return
    stamp = datetime.now(ZoneInfo(TZ))
    ss.manual_log.append({"Time": stamp.strftime("%d %b %H:%M"), "Event": f"Roof → {target}",
                          "Source": "Operator", "Detail": f"Manual command (was {ss.manual_state})"})
    ss.manual_state, ss.manual_since = target, stamp.strftime("%a %H:%M")


# --------------------------------------------------------------------------- page
st.session_state.setdefault("manual_state", "OPEN")
st.session_state.setdefault("manual_since", "—")
st.session_state.setdefault("manual_log", [])
st.session_state.setdefault("last_nonce", None)

df_raw, feed_status, fetched_at = load_weather()

with st.sidebar:
    st.markdown(f"### 🏟️ {SITE_NAME}")
    st.caption(f"{LAT:.4f}° N · {LON:.4f}° E · 60 × 80 ft · roof height 15 ft")
    st.divider()
    mode = st.radio("Control mode", ["Automatic", "Manual"], horizontal=True, key="mode",
                    help="Automatic: the controller moves the roof. Manual: you issue commands from the Roof control panel.")
    follow_live = st.toggle("Follow live", value=True, key="follow_live",
                            help="Track the current hour. Turn off to play back any hour of the forecast.")
    with st.expander("System calibration"):
        roof_offset = st.slider("Roof underside rise at full sun (°C)", 0.0, 15.0, 6.0, 0.5,
                                help="How much warmer than the air the roof underside gets at 800 W/m² of sunshine.")
        albedo = st.slider("Ground reflectance", 0.10, 0.40, 0.22, 0.01,
                           help="Fraction of sunlight reflected by the playground surface.")
        k_soil = st.slider("Soil thermal conductivity (W/m·K)", 0.3, 2.5, 1.0, 0.1,
                           help="How easily heat conducts through the ground; used for surface heat flux.")

df = compute(df_raw, roof_offset, albedo, k_soil)
now = pd.Timestamp.now(tz=TZ)
past = np.flatnonzero((df["timestamp"] <= now).to_numpy())
live_idx = int(past[-1]) if len(past) else 0

if follow_live:
    i = live_idx
else:
    if st.session_state.get("sel_idx", 0) >= len(df):
        del st.session_state["sel_idx"]
    with st.sidebar:
        i = st.select_slider("Playback time", options=list(range(len(df))), value=live_idx, key="sel_idx",
                             format_func=lambda k: df["timestamp"].iloc[k].strftime("%a %d %b %H:%M"))
with st.sidebar:
    st.divider()
    st.download_button("⬇ Export data (CSV)", df.to_csv(index=False).encode("utf-8"),
                       "roof_operations.csv", "text/csv", width="stretch")

row = df.iloc[i]
moves = df[df["auto_state"].ne(df["auto_state"].shift()) & (df.index <= i)]
if mode == "Automatic":
    state = recommended = row["auto_state"]
    last_move = moves.iloc[-1] if len(moves) else None
    since = last_move["timestamp"].strftime("%a %H:%M") if last_move is not None else "—"
    reason = (last_move["auto_reason"] or None) if last_move is not None else None
    events = [{"Time": t.strftime("%d %b %H:%M"), "Event": f"Roof → {s}", "Source": "Controller", "Detail": why}
              for t, s, why in zip(moves["timestamp"], moves["auto_state"], moves["auto_reason"]) if why]
else:
    state, since = st.session_state.manual_state, st.session_state.manual_since
    recommended, reason = decide(row["utci_open_C"], row["utci_closed_C"], state)
    events = []
events = (events + st.session_state.manual_log)[::-1]
upcoming = ("Now — apply recommendation" if mode == "Manual" and recommended != state
            else next_change(df, i, state))

# Top bar
dot = "#2EA043" if feed_status == "online" else "#D29922"
status_txt = "Feed online" if feed_status == "online" else "Feed offline · cached data"
view_txt = "LIVE" if follow_live else "PLAYBACK"
state_color = OPEN_COLOR if state == "OPEN" else CLOSED_COLOR
bar, btn = st.columns([6, 1], vertical_alignment="center")
bar.markdown(f"""<div class='topbar'><h1>Smart Retractable Roof</h1>
  <span class='chip'><span class='dot' style='background:{dot}'></span>{status_txt}</span>
  <span class='chip'>Updated {fetched_at.strftime('%H:%M')} IST</span>
  <span class='chip'><b>{view_txt}</b> · {row['timestamp'].strftime('%a %d %b, %H:%M')}</span>
  <span class='chip' style='border-color:{state_color}; color:{state_color}'>Roof {state} · {mode}</span>
</div>""", unsafe_allow_html=True)
if btn.button("↻ Refresh", width="stretch"):
    load_weather.clear()
    st.rerun()

payload = {
    "times": df["timestamp"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
    "now": i, "live": follow_live,
    "s": {k: series(df[k]) for k in CHART_SERIES},
    "auto_state": df["auto_state"].tolist(), "auto_reason": df["auto_reason"].fillna("").tolist(),
    "state": state, "mode": mode, "recommended": recommended, "reason": reason,
    "next_change": upcoming, "since": since, "events": events,
}
action = roof_canvas(data=payload, key="canvas", default=None)
if action and action.get("nonce") != st.session_state.last_nonce:
    st.session_state.last_nonce = action.get("nonce")
    if mode == "Manual":
        manual_command(action.get("cmd"))
        st.rerun()

st.caption("Weather feed: Open-Meteo · Comfort index: UTCI · Solar geometry: pvlib · "
           "Drag panels by their title bar; resize from edges and corners.")
