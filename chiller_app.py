# User input and create chillers dictionaries
import sys
import pandas as pd
from itertools import combinations 
import numpy as np
import streamlit as st
import openmeteo_requests
import requests_cache
from retry_requests import retry
import math
st.title("Chiller Plant Optimizer")
city_coords = {
    "Grand Rapids": (42.9634, -85.6681),
    "Chicago": (41.8781, -87.6298),
    "New York": (40.7128, -74.0060),
    "Miami": (25.7617, -80.1918),
    "Oymyakon": (63.4608,142.7858),
    "Detroit": (42.3314, -83.0458),
    "Los Angeles": (34.0522, -118.2437),
    "Dallas": (32.7767, -96.7970),
    "Houston": (29.7604, -95.3698),
    "Phoenix": (33.4484, -112.0740),
    "Atlanta": (33.7490, -84.3880),
    "Seattle": (47.6062, -122.3321),
    "Denver": (39.7392, -104.9903),
    "Minneapolis": (44.9778, -93.2650),
    "Boston": (42.3601, -71.0589),
    "Washington DC": (38.9072, -77.0369),
    "Las Vegas": (36.1699, -115.1398),
    "San Francisco": (37.7749, -122.4194),
    "San Diego": (32.7157, -117.1611),
    "Charlotte": (35.2271, -80.8431),
    "Nashville": (36.1627, -86.7816),
    "London": (51.5074, -0.1278),
    "Paris": (48.8566, 2.3522),
    "Berlin": (52.5200, 13.4050),
    "Rome": (41.9028, 12.4964),
    "Madrid": (40.4168, -3.7038),
    "Amsterdam": (52.3676, 4.9041),
    "Tokyo": (35.6762, 139.6503),
    "Seoul": (37.5665, 126.9780),
    "Beijing": (39.9042, 116.4074),
    "Singapore": (1.3521, 103.8198),
    "Sydney": (-33.8688, 151.2093),
    "Melbourne": (-37.8136, 144.9631),
    "Toronto": (43.6532, -79.3832),
    "Vancouver": (49.2827, -123.1207),
    "Mexico City": (19.4326, -99.1332),
    "São Paulo": (-23.5505, -46.6333),
    "Dubai": (25.2048, 55.2708),
    "Mumbai": (19.0760, 72.8777),
    "Cape Town": (-33.9249, 18.4241)
}

city = st.selectbox("Select Location", list(city_coords.keys()))

lat,long = city_coords[city]
start_date = st.date_input("Start date")
end_date = st.date_input("End date")
costperkwh = st.number_input("Cost per kWh?")
cost_of_economizer = st.number_input("Cost of Economizer Upgrade?")



def room_maker():
    num_rooms = st.number_input("Number of rooms?", min_value=1, step=1)

    rooms = []

    for i in range(int(num_rooms)):
        st.subheader(f"Room {i+1}")

        room_name = st.text_input(f"Room name {i+1}", key=f"name_{i}")
        room_cfm = st.number_input(f"Room cfm {i+1}", key=f"cfm_{i}")
        room_t_supply = st.number_input(f"Room t_supply {i+1}", key=f"supply_{i}")
        room_t_return = st.number_input(f"Room t_return {i+1}", key=f"return_{i}")
        room_sqft = st.number_input(f"Room sqft {i+1}", key=f"sq_ft_{i}")

        rooms.append({
            "name": room_name,
            "cfm": room_cfm,
            "t_supply": room_t_supply,
            "t_return": room_t_return,
            "sq_ft": room_sqft
        })

    return rooms


# Setup Open-Meteo API client
cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

url = "https://archive-api.open-meteo.com/v1/archive"
params = {
    "latitude": lat,
    "longitude": long,
    "start_date": start_date.strftime("%Y-%m-%d"),
    "end_date":  end_date.strftime("%Y-%m-%d"),
    "hourly": ["temperature_2m", "relative_humidity_2m"],
    "temperature_unit": "fahrenheit",
}

responses = openmeteo.weather_api(url, params=params)
response = responses[0]

hourly = response.Hourly()
hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
hourly_relative_humidity_2m = hourly.Variables(1).ValuesAsNumpy()

hourly_data = {
    "date": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left"
    )
}

hourly_data["temperature_2m"] = hourly_temperature_2m
hourly_data["relative_humidity_2m"] = hourly_relative_humidity_2m

hourly_dataframe = pd.DataFrame(data=hourly_data)

building_load_constant = []
for i in range(len(hourly_dataframe)):
    building_load_constant.append(18)
hourly_dataframe["building_enthalpy"] = building_load_constant

def calculate_enthalpy(dry_bulb, relative_h):
    p_ws = 0.6108 * math.exp((17.27 * (dry_bulb - 32) * 5/9) / ((dry_bulb - 32) * 5/9 + 237.3))
    p_w = (relative_h / 100) * p_ws
    w = 0.62198 * p_w / (101.325 - p_w)
    enthalpy = 0.24 * dry_bulb + w * (1061 + 0.444 * dry_bulb)
    
    return enthalpy

def room_loads(cfm, t_supply, t_return, sq_ft):
    delta_t = t_return - t_supply
    btu = delta_t * 1.085 * cfm
    tons = btu / 12000
    btu_sqft = btu / sq_ft if sq_ft > 0 else 0
    return btu, tons, btu_sqft


def building_load_calc(rooms):
    room_btu_list = []

    for room in rooms:
        btu, tons, btu_sqft = room_loads(
            room["cfm"],
            room["t_supply"],
            room["t_return"],
            room["sq_ft"]
        )

        room_btu_list.append({
            "name": room["name"],
            "btu": btu,
            "tons": tons,
            "btu_sqft": round(btu_sqft, 2)
        })

    building_load_tons = sum(room["tons"] for room in room_btu_list)

    for room in room_btu_list:
        room["room_percent_load"] = (
            room["tons"] / building_load_tons if building_load_tons > 0 else 0
        )

    return building_load_tons, room_btu_list

def hourly_df_enthalpy_columns(dataframe):
    enthalpy_list = []
    for i in range(len(dataframe)):
        db = dataframe.loc[i, "temperature_2m"]
        rh = dataframe.loc[i, "relative_humidity_2m"]
        
        h = calculate_enthalpy(db, rh)
        enthalpy_list.append(h)

    dataframe["outside_enthalpy"] = enthalpy_list
    building_load_constant = []
    for i in range(len(dataframe)):
        building_load_constant.append(18)
    dataframe["building_enthalpy"] = building_load_constant
    economizer_runtime_list = []
    economizer_key = []
    for i in range(len(dataframe)):
        out_h = dataframe.loc[i, "outside_enthalpy"]
        in_h = dataframe.loc[i, "building_enthalpy"]
        if in_h > out_h:
            economizer_key.append(0)
            economizer_runtime_list.append(1)
        else:
            economizer_key.append(1)
    dataframe["economizer_key"] = economizer_key
    economizer_runtime = sum(economizer_runtime_list)
    economizer_runtime_percent = (economizer_runtime / len(hourly_dataframe)) * 100
    return economizer_runtime,economizer_runtime_percent

def optimize_chillers(building_load_tons, chillers):
    best_kw = 10000000
    best_group = None

    for r in range(1, len(chillers) + 1):
        for group in combinations(chillers, r):

            total_tons = sum(chiller["tons"] for chiller in group)

            if total_tons >= building_load_tons:
                percent_load = building_load_tons / total_tons
                total_kw = 0

                for chiller in group:
                    actual_kw_per_ton = chiller["kw_per_ton"] * iplv_lookup(percent_load)
                    load_chiller = chiller["tons"] * percent_load
                    kw_chiller = load_chiller * actual_kw_per_ton
                    total_kw += kw_chiller

                if total_kw < best_kw:
                    best_kw = total_kw
                    best_group = group

    return best_kw, best_group


def redundancy_check(best_group, building_load):
    max_chiller = max(chiller["tons"] for chiller in best_group)
    installed_capacity = sum(chiller["tons"] for chiller in best_group)
    n_minus_1_capacity = installed_capacity - max_chiller

    if n_minus_1_capacity >= building_load:
        st.success("N+1 REDUNDANCY CHECK PASSED")
    else:
        st.warning("N+1 REDUNDANCY CHECK FAILED")


def calculate(best_group, best_kw, costperkwh, building_load_tons):
    total_tons = sum(chiller["tons"] for chiller in best_group)
    daily_cost = best_kw * costperkwh * 24
    monthly_cost = daily_cost * 30
    utilization = (building_load_tons / total_tons) * 100
    return total_tons, daily_cost, monthly_cost, utilization

def system_flags(total_tons, building_load):
    if total_tons > building_load:
        st.info("Cooling capacity exceeds building load")
    elif total_tons < building_load:
        st.warning("Building load exceeds cooling capacity")
    else:
        st.info("Building load perfectly matched")


def iplv_lookup(load_pct):
    iplv_table = {
        0.25: 0.72,
        0.50: 0.60,
        0.75: 0.52,
        1.00: 1.00
    }

    closest_load = min(
        iplv_table.keys(),
        key=lambda x: abs(x - load_pct)
    )

    return iplv_table[closest_load]
def calculate_costs_dataframe(dataframe, best_kw, costperkwh, cost_of_economizer):
    cooling_fraction = .65
    non_cooling_fraction = .35
    dataframe["kw_cooling"] = best_kw * cooling_fraction
    dataframe["kw_non_cooling"] = best_kw * non_cooling_fraction
    
    dataframe["kw_cooling_econ"] = dataframe["kw_cooling"] * dataframe["economizer_key"]
    
    dataframe["total_kw_econ"] = dataframe["kw_cooling_econ"] + dataframe["kw_non_cooling"]
    dataframe["total_kw_base"] = dataframe["kw_cooling"] + dataframe["kw_non_cooling"]
    
    dataframe["total_cost_econ"] = dataframe["total_kw_econ"] * costperkwh
    dataframe["total_cost_base"] = dataframe["total_kw_base"] * costperkwh
    
    cost_w_economizer = hourly_dataframe["total_cost_econ"].sum()
    cost_wo_economizer = hourly_dataframe["total_cost_base"].sum()
    annual_savings = sum(hourly_dataframe["total_cost_base"]) - sum(hourly_dataframe["total_cost_econ"])
    payback = cost_of_economizer / annual_savings if annual_savings > 0 else 0
    payback_months = payback * 12
    return dataframe, cost_w_economizer, cost_wo_economizer,annual_savings,payback_months


def print_all(best_group,total_tons,daily_cost, monthly_cost, utilization, building_load_tons,cost_w_economizer,cost_wo_economizer,payback_months,economizer_runtime,economizer_runtime_percent):
    st.write("Building Load -->", round(building_load_tons, 2), "tons")

    for chiller in best_group:
        st.write(
            "Running:", chiller["name"],
            "-->", chiller["tons"], "tons ,",
            chiller["kw_per_ton"], "kW/ton"
        )

    st.write(len(best_group), "Chillers Running")
    st.write("Chiller Load -->", total_tons, "Tons")
    st.write("Daily Cost --> $", round(daily_cost, 2))
    st.write("Monthly Cost --> $", round(monthly_cost, 2))
    st.write("Utilization (%) -->", round(utilization, 2), "%")
    st.write("Annual Power Cost without Economizer", round(cost_wo_economizer, 2), "$")
    st.write("Annual Power Cost with Economizer", round(cost_w_economizer, 2), "$")
    st.write("Annual Power Cost Savings with Economizer",round(annual_savings,2), "$")
    st.write("Economizer Runtime",round(economizer_runtime,2), "hours")
    st.write("Percent Time Economizer On",round(economizer_runtime_percent,4), "%")
    st.write("Pay Period",round(payback_months,2), "months")
df_chillers = pd.read_csv("Chiller_06_22.csv")
df_chillers.columns = df_chillers.columns.str.strip()
chillers = df_chillers.to_dict(orient="records")

st.subheader("Chiller Data")
st.dataframe(df_chillers)
rooms = room_maker()
if st.button("Print Rooms"):
    st.write(rooms)

building_load_tons, room_btu_list = building_load_calc(rooms)
economizer_runtime,economizer_runtime_percent = hourly_df_enthalpy_columns(hourly_dataframe)
best_kw, best_group = optimize_chillers(building_load_tons, chillers)
hourly_dataframe,cost_w_economizer,cost_wo_economizer,annual_savings,payback_months = calculate_costs_dataframe(hourly_dataframe,best_kw,costperkwh,cost_of_economizer)

if best_group is None:
    st.error("COOLING REQUIREMENT EXCEEDS CHILLER CAPACITY")
else:
    total_tons, daily_cost, monthly_cost, utilization = calculate(
        best_group, best_kw, costperkwh, building_load_tons
    )

    redundancy_check(best_group, building_load_tons)
    system_flags(total_tons, building_load_tons)

    print_all(best_group, total_tons, daily_cost, monthly_cost, utilization, building_load_tons,
              cost_w_economizer,cost_wo_economizer,payback_months,
              economizer_runtime,economizer_runtime_percent)
    
     hourly_dataframe["date_only"] = hourly_dataframe["date"].dt.date

    # count hours per day when economizer is ON
    daily_runtime = (
        hourly_dataframe.groupby("date_only")["economizer_key"]
        .apply(lambda x: (x == 0).sum())
        .reset_index()
    )

    daily_runtime.columns = ["date", "economizer_hours"]

    st.subheader("Economizer Runtime by Day")
    st.bar_chart(daily_runtime.set_index("date")["economizer_hours"])

    # percent of day economizer runs
    daily_runtime["percent_on"] = daily_runtime["economizer_hours"] / 24 * 100

    st.subheader("Economizer % Runtime")
    st.line_chart(daily_runtime.set_index("date")["percent_on"])
    
    st.subheader("Weather")
    st.dataframe(hourly_dataframe)
