# Smart Retractable Roof — Operations Dashboard

Streamlit dashboard for monitoring and controlling a retractable playground roof in Chennai. It shows site conditions, mean radiant temperature, UTCI thermal comfort, and surface heat flux for the open and closed positions, plus the controller schedule and an event log.

## Run locally
```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

## Using the canvas
The dashboard is a freely arrangeable canvas:
- **Move** a panel by dragging its title bar.
- **Resize** a panel by dragging its edges or bottom corners.
- Hide a panel with **×**, and bring it back with **+ Add panel**.
- **✎ Editing layout / 🔒 Layout locked** toggles whether panels can be moved. **Reset layout** restores the default arrangement.
- The layout is remembered in your browser.
- **Time window** (6 h / 12 h / 24 h / 48 h / All) sets every chart's time range around the selected hour. You can also drag across a chart to zoom, scroll to zoom, or double-click to reset. All charts follow the same zoom.
- Hover any **ⓘ** icon to see what a value means.

## Deploy to Streamlit Community Cloud
1. Push this folder to a GitHub repository. Include `app.py`, the `roof_canvas/` folder, `requirements.txt`, `.streamlit/config.toml`, the CSV files and `data/`.
2. Go to https://share.streamlit.io, then **Create app** → choose the repo and branch.
3. Set the main file to `app.py`. Under *Advanced settings*, choose Python 3.11 or 3.12. Then deploy.

## Files
| File | Purpose |
|---|---|
| `app.py` | Data, models and controller (Streamlit) |
| `roof_canvas/index.html` | Drag-and-resize dashboard canvas (custom Streamlit component: gridstack.js + Plotly, loaded from CDN) |
| `get_weather.py` | Stand-alone download of the Open-Meteo data → `chennai_hourly_weather_extended.csv` |
| `calculate_mrt.py` | Stand-alone solar-position check |
| `METHODOLOGY.md` | Models, assumptions and limitations |
