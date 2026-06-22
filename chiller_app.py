# User input and create chillers dictionaries
import sys
import pandas as pd
from itertools import combinations 
import numpy as np
import streamlit as st

st.title("Chiller Plant Optimizer")
def room_maker():
    num_rooms = st.number_input("Number of rooms?", min_value=1, step=1)

    rooms = []

    for i in range(int(num_rooms)):
        st.subheader(f"Room {i+1}")

        room_name = st.text_input(f"Room name {i}", key=f"name_{i}")
        room_cfm = st.number_input(f"Room cfm {i}", key=f"cfm_{i}")
        room_t_supply = st.number_input(f"Room t_supply {i}", key=f"supply_{i}")
        room_t_return = st.number_input(f"Room t_return {i}", key=f"return_{i}")
        room_sqft = st.number_input(f"Room sqft {i}", key=f"sq_ft_{i}")
        rooms.append({
            "name": room_name,
            "cfm": room_cfm,
            "t_supply": room_t_supply,
            "t_return": room_t_return,
            "sq_ft": room_sqft
        })

    return rooms


costperkwh = st.number_input("Cost per kWh?")

# Room cooling load calculator
def room_loads(cfm,t_supply,t_return,sq_ft):
    delta_t = t_return - t_supply
    btu = delta_t * 1.085 * cfm
    tons = btu / 12000
    btu_sqft = btu / sq_ft if sq_ft > 0 else 0
    return btu,tons,btu_sqft

def building_load_calc(rooms):
    room_btu_list = []
    for room in rooms:
        btu,tons,btu_sqft = room_loads(room["cfm"],room["t_supply"],room["t_return"],room["sq_ft"])
        room_btu_list.append({
            "name":room["name"],
            "btu":btu,
            "tons":tons,
            "btu_sqft": btu_sqft
        })
    building_load_tons = sum(room["tons"] for room in room_btu_list)
    for room in room_btu_list:
        room_percent_load = room["tons"] / building_load_tons if building_load_tons > 0 else 0
        room["room_percent_load"] = room_percent_load
    return building_load_tons, room_btu_list

# Chiller Optimizer
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


def print_all(best_group, best_kw, total_tons, daily_cost, monthly_cost, utilization, building_load_tons):
    st.write("Building Load -->", round(building_load_tons, 2), "tons")

    for chiller in best_group:
        st.write("Running:", chiller["name"], "-->", chiller["tons"], "tons ,", chiller["kw_per_ton"], "kW/ton")

    st.write(len(best_group), "Chillers Running")
    st.write("Total kW -->", round(best_kw, 2), "kW")
    st.write("Chiller Load -->", total_tons, "Tons")
    st.write("Daily Cost --> $", round(daily_cost, 2))
    st.write("Monthly Cost --> $", round(monthly_cost, 2))
    st.write("Utilization (%) -->", round(utilization, 2), "%")


df_chillers = pd.read_csv("Chiller_06_22.csv")

df_chillers.columns = df_chillers.columns.str.strip()

chillers = df_chillers.to_dict(orient="records")

st.subheader("Chiller Data")
st.dataframe(df_chillers)

rooms = room_maker()

if st.button("Print Rooms"):
    st.write(rooms)

building_load_tons, room_btu_list = building_load_calc(rooms)

best_kw, best_group = optimize_chillers(building_load_tons, chillers)

if best_group is None:
    st.error("COOLING REQUIREMENT EXCEEDS CHILLER CAPACITY")
else:
    total_tons, daily_cost, monthly_cost, utilization = calculate(
        best_group, best_kw, costperkwh, building_load_tons
    )

    redundancy_check(best_group, building_load_tons)
    system_flags(total_tons, building_load_tons)
    print_all(best_group, best_kw, total_tons, daily_cost, monthly_cost, utilization, building_load_tons)

    results_chillers = []
    
    for chiller in best_group:
        percent_of_load = chiller["tons"] / total_tons
        kw_chiller_day = best_kw * percent_of_load
        cost_chiller_day = kw_chiller_day * 24 * costperkwh
        cost_chiller_month = cost_chiller_day * 30
        results_chillers.append({
            "name": chiller["name"],
            "tons": chiller["tons"],
            "kw_usage_day": round(kw_chiller_day,2),
            "percent_load": round(percent_of_load,2),
            "daily_cost": round(cost_chiller_day,2),
            "monthly_cost": round(cost_chiller_month,2)
        })

    total_kw = sum(r["kw_usage_day"] for r in results_chillers)
    total_day_cost = sum(r["daily_cost"] for r in results_chillers)
    total_percent = sum(r["percent_load"] for r in results_chillers)
    total_month_cost = sum(r["monthly_cost"] for r in results_chillers)
    avg_kw_per_ton =  np.mean([chiller["kw_per_ton"] for chiller in best_group])
    total_btu = sum(room["btu"] for room in room_btu_list)
    avg_btu_sqft =  np.mean([room["btu_sqft"] for room in room_btu_list])
    results_chillers.append({
        "name": "Total",
        "tons": total_tons,
        "kw_usage_day": round(total_kw,2),
        "percent_load": round(total_percent,2),
        "daily_cost": round(total_day_cost,2),
        "monthly_cost":round(total_month_cost,2)
    })
    room_btu_list.append({
        "name": "Total",
        "tons": total_tons,
        "btu": total_btu,
        "btu_sqft": avg_btu_sqft,
        "room_percent_load":"100%"
    })
    df_results_chillers = pd.DataFrame(results_chillers)
    df_room_btu_list = pd.DataFrame(room_btu_list)
    
    st.dataframe(df_results_chillers)
    st.dataframe(df_room_btu_list)
    
    csv = df_results_chillers.to_csv(index=False)
    st.download_button("Download Results CSV", csv, "results_chillers.csv")

    csv = df_room_btu_list.to_csv(index=False)
    st.download_button("Download Results CSV", csv, "room_loads.csv")
