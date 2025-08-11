import os
import streamlit as st
import pandas as pd
from analysis import analyze_universe, HORIZONS_MONTHS
from firebase_utils import get_secret

st.set_page_config(page_title="Top-10 Doublers", layout="wide")

st.title("Top-10 Stocks — Likely to 200% (Research Tool)")
st.markdown("Click **Refresh** to run the analysis using historical + live data (Dhan) and save results to Excel.")

# Sidebar / settings
st.sidebar.header("Settings / Secrets")
st.sidebar.write("Dhan token is read from Firestore (config/keys -> DHAN_TOKEN)")
st.sidebar.write("News API key is read from Firestore as NEWSAPI_KEY (optional)")

# Universe upload
uploaded = st.sidebar.file_uploader("Upload CSV with column 'symbol' for universe (optional)", type=["csv"])
if uploaded:
    try:
        universe_df = pd.read_csv(uploaded)
        universe = universe_df["symbol"].astype(str).tolist()
    except Exception:
        st.sidebar.error("Invalid CSV. Ensure a column named 'symbol' exists.")
        universe = None
else:
    sample = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "KOTAKBANK", "SBIN", "BAJFINANCE", "LT"]
    if os.path.exists("nifty500.csv"):
        df = pd.read_csv("nifty500.csv")
        universe = df["symbol"].astype(str).tolist()
    else:
        universe = sample

st.sidebar.write(f"Universe size: {len(universe)}")

min_vol = st.sidebar.number_input("Minimum avg daily volume", value=30000, step=1000)
use_news = st.sidebar.checkbox("Use News Sentiment (if key in Firebase)", value=False)

if st.button("Refresh (run analysis)"):
    with st.spinner("Running analysis — this may take a few minutes..."):
        out_file, counts = analyze_universe(universe, use_dhan=True, use_news=use_news, min_avg_vol=min_vol)

    st.subheader("Candidates scanned per horizon")
    cols = st.columns(len(counts))
    for idx, (horizon, count) in enumerate(sorted(counts.items())):
        cols[idx].metric(label=f"{horizon} months", value=count)

    st.success(f"Analysis complete. Excel saved: {out_file}")

    # Show top 10 tables for each horizon
    st.header("Top 10 Stocks by Horizon")
    try:
        xls = pd.ExcelFile(out_file, engine="openpyxl")
        for horizon in HORIZONS_MONTHS:
            sheet_name = f"{horizon}m"
            if sheet_name in xls.sheet_names:
                df_top = pd.read_excel(xls, sheet_name=sheet_name)
                if not df_top.empty:
                    st.subheader(f"Top 10 for {horizon} months")
                    st.dataframe(df_top)
                else:
                    st.write(f"No data for {horizon} months horizon.")
            else:
                st.write(f"Sheet {sheet_name} not found in Excel.")
    except Exception as e:
        st.error(f"Failed to read Excel file for display: {e}")

    # Provide download button
    try:
        with open(out_file, "rb") as f:
            st.download_button(
                "Download Excel with Top-10 stocks per horizon",
                data=f,
                file_name=out_file,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    except Exception as e:
        st.error("Unable to provide download link: " + str(e))
