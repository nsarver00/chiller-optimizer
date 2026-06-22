# User input and create chillers dictionaries
import sys
import pandas as pd
from itertools import combinations 
import numpy as np
import streamlit as st

st.title("Chiller Plant Optimizer")

costperkwh = st.number_input("Cost per kWh?")

# Room cooling load calculator
def room_loads(cfm, t_supply, t_return):
    delta_t = t_return - t_supply
    btu = delta_t * 1.085 * cfm
    tons = btu / 12000
    return btu, tons


def building_load_calc(rooms):
    room_btu_list = []

    for room in rooms:
        btu, tons = room_loads(room["cfm"], room["t_supply"], room["t_return"])
        room_btu_list.append({
            "name": room["name"],
            "btu": btu,
            "tons": tons
        })

    building_load_tons = sum(room["tons"] for room in room_btu_list)
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
                kw_per_ton = iplv_lookup(percent_load)

                total_kw = 0
                for chiller in group:
                    load_chiller = chiller["tons"] * percent_load
                    kw_chiller = load_chiller * kw_per_ton
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
        1.00: 0.58
    }

    closest_load = min(
        iplv_table.keys(),
        key=lambda x: abs(x - load_pct)
    )

    return iplv_table[closest_load]


def print_all(best_group, best_kw, total_tons, daily_cost, monthly_cost, utilization, building_load_tons):
    st.write("Building Load -->", round(building_load_tons, 2), "tons")

    for chiller in best_group:
        st.write("Running:", chiller["name"], "-->", chiller["tons"], "tons ,", chiller["eff"], "kW/ton")

    st.write(len(best_group), "Chillers Running")
    st.write("Total kW -->", round(best_kw, 2), "kW")
    st.write("Chiller Load -->", total_tons, "Tons")
    st.write("Daily Cost --> $", round(daily_cost, 2))
    st.write("Monthly Cost --> $", round(monthly_cost, 2))
    st.write("Utilization (%) -->", round(utilization, 2), "%")


# ---------------- MAIN ----------------

df_chillers = pd.read_csv("Chiller_csv_1.csv")
df_rooms = pd.read_csv("data_center_rooms.csv") 

df_chillers.columns = df_chillers.columns.str.strip()
df_rooms.columns = df_rooms.columns.str.strip()

chillers = df_chillers.to_dict(orient="records")
rooms = df_rooms.to_dict(orient="records")

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

    results = []

    for chiller in best_group:
        kw_chiller = chiller["tons"] * chiller["eff"]
        percent_of_load = chiller["tons"] / total_tons
        cost_chiller = kw_chiller * 24 * costperkwh

        results.append({
            "name": chiller["name"],
            "eff": chiller["eff"],
            "tons": chiller["tons"],
            "kw_usage": kw_chiller,
            "percent_load": percent_of_load,
            "daily_cost": cost_chiller
        })

    total_kw = sum(r["kw_usage"] for r in results)
    total_cost = sum(r["daily_cost"] for r in results)
    total_percent = sum(r["percent_load"] for r in results)

    results.append({
        "name": "Total",
        "eff": np.mean([chiller["eff"] for chiller in best_group]),
        "tons": np.mean([chiller["tons"] for chiller in best_group]),
        "total_kw_usage": total_kw,
        "total_percent": total_percent,
        "total_daily_cost": total_cost
    })

    df_results = pd.DataFrame(results)
    st.dataframe(df_results)

    csv = df_results.to_csv(index=False)
    st.download_button("Download Results CSV", csv, "chiller_results.csv")
