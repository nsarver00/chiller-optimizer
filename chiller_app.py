import sys
import pandas as pd
from itertools import combinations
import numpy as np
import streamlit as st

st.title("Chiller Plant Optimizer")

building_load = st.number_input("Building Load in Tons?")
costperkwh = st.number_input("Cost per kWh?")

def optimize_chillers(building_load, chillers):
    best_kw = 10000000
    best_group = None
    for r in range(1, len(chillers) + 1):
        for group in combinations(chillers, r):
            total_tons = 0
            total_kw = 0
            for chiller in group:
                total_tons = total_tons + chiller["tons"]
                kw = chiller["tons"] * chiller["eff"]
                total_kw = kw + total_kw
            if total_tons >= building_load:
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

def calculate(best_group, best_kw, costperkwh, building_load):
    total_tons = sum(chiller["tons"] for chiller in best_group)
    daily_cost = best_kw * costperkwh * 24
    monthly_cost = daily_cost * 30
    utilization = (building_load / total_tons) * 100
    return total_tons, daily_cost, monthly_cost, utilization

def system_flags(total_tons, building_load):
    if total_tons > building_load:
        st.info("Cooling capacity exceeds building load")
    elif total_tons < building_load:
        st.warning("Building load exceeds cooling capacity")
    else:
        st.info("Building load perfectly matched")

def print_all(best_group, best_kw, total_tons, daily_cost, monthly_cost, utilization):
    for chiller in best_group:
        st.write("Running:", chiller["name"], "-->", chiller["tons"], "tons ,", chiller["eff"], "kW/ton")
    st.write(len(best_group), "Chillers Running")
    st.write("Total kW -->", round(best_kw, 2), "kW")
    st.write("Chiller Load -->", total_tons, "Tons")
    st.write("Daily Cost --> $", round(daily_cost, 2))
    st.write("Monthly Cost --> $", round(monthly_cost, 2))
    st.write("Utilization (%) -->", round(utilization, 2), "%")

# Load CSV
df = pd.read_csv("Chiller_csv_1.csv")
df.columns = df.columns.str.strip()
chillers = df.to_dict(orient="records")

best_kw, best_group = optimize_chillers(building_load, chillers)

if best_group is None:
    st.error("COOLING REQUIREMENT EXCEEDS CHILLER CAPACITY")
else:
    total_tons, daily_cost, monthly_cost, utilization = calculate(best_group, best_kw, costperkwh, building_load)
    redundancy_check(best_group, building_load)
    system_flags(total_tons, building_load)
    print_all(best_group, best_kw, total_tons, daily_cost, monthly_cost, utilization)

    results = []
    for chiller in best_group:
        kw_chiller = chiller["tons"] * chiller["eff"]
        percent_load = chiller["tons"] / total_tons
        cost_chiller = kw_chiller * 24 * costperkwh
        results.append({"name": chiller["name"],
                        "eff": chiller["eff"],
                        "tons": chiller["tons"],
                        "kw_usage": kw_chiller,
                        "percent_load": percent_load,
                        "daily_cost": cost_chiller})

    results.append({"name": "Total",
                    "eff": round(np.mean([chiller["eff"] for chiller in best_group]),2),
                    "tons": round(np.mean([chiller["tons"] for chiller in best_group]),2),
                    "kw_usage": sum(r["kw_usage"] for r in results),
                    "percent_load": round(np.mean([r["percent_load"] for r in results]), 2),
                    "daily_cost": sum(r["daily_cost"] for r in results)})

    df_results = pd.DataFrame(results)
    st.dataframe(df_results)
    csv = df_results.to_csv(index=False)
    st.download_button("Download Results CSV", csv, "chiller_results.csv")
