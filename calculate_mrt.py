
import pandas as pd
import pvlib

# Load the Chennai weather data
weather = pd.read_csv("chennai_hourly_weather.csv")

# Convert timestamps to Chennai local time
weather["timestamp"] = pd.to_datetime(
    weather["timestamp"]
).dt.tz_localize("Asia/Kolkata")

# Define the approximate location of Chennai
location = pvlib.location.Location(
    latitude=13.0827,
    longitude=80.2707,
    tz="Asia/Kolkata",
    altitude=6,
    name="Chennai"
)

# Calculate the sun's position at each timestamp
solar_position = location.get_solarposition(
    weather["timestamp"]
)

# Add solar position to the weather dataset
weather["solar_elevation_deg"] = (
    solar_position["apparent_elevation"].values
)

weather["solar_azimuth_deg"] = (
    solar_position["azimuth"].values
)

# Display the results
print("Number of hourly records:", len(weather))
print("\nSolar position preview:")

print(
    weather[
        [
            "timestamp",
            "solar_radiation_W_m2",
            "solar_elevation_deg",
            "solar_azimuth_deg"
        ]
    ].head(10).to_string(index=False)
)

print("\nSolar position calculated successfully.")
