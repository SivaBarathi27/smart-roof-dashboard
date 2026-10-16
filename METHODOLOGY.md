# Methodology & assumptions

The dashboard runs on Open-Meteo modelled weather for Chennai (13.0827° N, 80.2707° E), not on physical sensors. The roof is simulated; no actuator is connected. All MRT, UTCI and heat-flux values are model estimates and have not been validated against measurements.

## Data
- Open-Meteo hourly forecast API (`past_days=1`, `forecast_days=2`). The app caches it for 10 min and falls back to `data/latest_weather.csv`, then to `chennai_hourly_weather_extended.csv`.
- Radiation values are preceding-hour means, so solar position (pvlib) is evaluated 30 min before each timestamp.
- Wind is the 10 m reference wind, not wind at occupied height.

## Mean radiant temperature (MRT)
- Person: emissivity 0.95, shortwave absorptivity 0.70. View factors are 0.5 sky/roof and 0.5 ground.
- Sky longwave: Brutsaert clear-sky emissivity with an assumed cloud correction `(1 + 0.22·c²)`, clipped to 0.55–1.0.
- Ground temperature uses the forecast soil temperature at 0 cm as a proxy.
- **Open roof:** absorbed shortwave = 0.70 × [f·DNI + 0.5·DHI + 0.5·albedo·GHI]. The projected direct factor f ramps from 0 to 0.25 as the sun rises to 25° elevation.
- **Closed roof:** opaque full shade, so no shortwave reaches the person. Roof underside temperature = T_air + offset × min(1, GHI/800). Shaded ground temperature = T_air + 0.25·(T_soil − T_air).
- MRT = [(absorbed LW + SW) / (ε·σ)]^¼ − 273.15

## UTCI
`pythermalcomfort.models.utci` is fed air temperature, MRT, RH and wind. Wind is clipped to 0.51–16.9 m/s to stay inside the model's validity range. The no-thermal-stress band is 9–26 °C.

## Surface heat flux
Conductive ground heat flux follows Fourier's law across the 0–6 cm soil layer. This is the quantity an HFP01 heat-flux plate would measure.

`G = k · (T_0cm − T_6cm) / 0.06 m`. The default k is 1.0 W/m·K (moist sandy soil) and can be adjusted in *System calibration*. Positive G means heat is flowing into the ground.

- **Open:** uses the forecast soil temperatures directly.
- **Closed:** replaces T_0cm with the shaded ground temperature estimate above. This is an instantaneous estimate, so the 6 cm temperature is assumed unchanged.

## Controller
- The controller compares each position's distance from the 9–26 °C UTCI band, with a 0.5 °C deadband.
- If both positions show heat stress, it closes only when closing lowers UTCI by at least 1 °C. Otherwise it holds the current position; a hold is not shown as a message.
- Automatic mode runs this rule over the whole forecast horizon, starting OPEN. *Next scheduled change* is the first later hour at which this simulation moves the roof. In Manual mode, *Next recommended change* runs the same simulation starting from the operator's chosen position. Manual mode shows the recommendation, and the operator issues commands.

## Limitations
- Air temperature and wind are the same in both positions, so no roof-induced air cooling is modelled.
- Not modelled: roof size and material, shading by neighbouring buildings, soil thermal inertia under shade, occupancy, rain, and wind safety interlocks.
- Not for operating a real roof.
