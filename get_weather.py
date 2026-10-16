
import requests
import pandas as pd

# Chennai location
latitude = 13.0827
longitude = 80.2707

url = "https://api.open-meteo.com/v1/forecast"

parameters = {
    "latitude": latitude,
    "longitude": longitude,
    "hourly": [
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "shortwave_radiation",
        "direct_radiation",
        "direct_normal_irradiance",
        "diffuse_radiation",
        "soil_temperature_0cm",
        "soil_temperature_6cm",
        "cloud_cover"
    ],
    "forecast_days": 2,
    "timezone": "Asia/Kolkata",
    "wind_speed_unit": "ms"
}

response = requests.get(
    url,
    params=parameters,
    timeout=30
)

response.raise_for_status()
weather = response.json()

df = pd.DataFrame(weather["hourly"])

df = df.rename(columns={
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
    "cloud_cover": "cloud_cover_percent"
})

df.to_csv("chennai_hourly_weather_extended.csv", index=False)

print("Weather data retrieved successfully!")
print("Number of hourly records:", len(df))
print(df.head(5).to_string(index=False))
print("\nSaved as chennai_hourly_weather_extended.csv")
