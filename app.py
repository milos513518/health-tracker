import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import time

st.set_page_config(page_title="Health Tracker", page_icon="💪", layout="wide")

SECRET_FILE_PATH = "/etc/secrets/gcp-key.pem"
SHEET_KEY = "1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc"
WORKSHEET_NAME = "daily_manual_entry"

@st.cache_resource
def get_worksheet():
    """
    Connect to Google Sheets. This function:
    - Reads the Render Secret File as raw text
    - Parses JSON safely
    - Converts literal "\\n" to real newlines in the private_key
    """
    # Read raw file (helps avoid weird hidden characters / paste artifacts)
    if os.path.exists(SECRET_FILE_PATH):
        with open(SECRET_FILE_PATH, "r") as f:
            raw = f.read().strip()
        creds = json.loads(raw)

        # Fix literal backslash-n if present
        pk = creds.get("private_key", "")
        if isinstance(pk, str):
            creds["private_key"] = pk.replace("\\n", "\n")

        credentials = Credentials.from_service_account_info(
            creds,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
    elif os.path.exists("credentials.json"):
        credentials = Credentials.from_service_account_file(
            "credentials.json",
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
    else:
        raise FileNotFoundError("No credentials found (Render secret file or local credentials.json).")

    client = gspread.authorize(credentials)
    sheet = client.open_by_key(SHEET_KEY)
    return sheet.worksheet(WORKSHEET_NAME)

def load_data_live() -> pd.DataFrame:
    ws = get_worksheet()
    data = ws.get_all_values()

    if len(data) <= 1:
        return pd.DataFrame(columns=["date", "ahi", "leak", "coherence", "energy", "notes"])

    df = pd.DataFrame(data[1:], columns=data[0])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["ahi", "leak", "coherence", "energy"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values("date", ascending=False)

def save_entry(date, ahi, leak, coherence, energy, notes) -> bool:
    ws = get_worksheet()
    row = [
        date.strftime("%Y-%m-%d"),
        str(ahi),
        str(leak),
        str(coherence),
        str(energy),
        notes,
    ]
    ws.append_row(row)
    return True

st.title("💪 Personal Health Tracker")
st.caption("This version only connects to Google when you click a button (prevents Render from stopping the service).")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "✍️ Daily Entry", "🔍 Correlations", "⚙️ Setup"])

# Keep df in session state (so we don't auto-fetch on every rerun)
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

with tab4:
    st.subheader("🔌 Connection Status (On-demand)")
    if st.button("Test connection to Google Sheets"):
        try:
            ws = get_worksheet()
            st.success(f"✅ Connected! Worksheet: {ws.title}")
        except Exception as e:
            st.error(f"❌ Connection failed: {repr(e)}")

    st.divider()
    st.write("Secret file path check:")
    st.write(f"- {SECRET_FILE_PATH} exists? **{os.path.exists(SECRET_FILE_PATH)}**")

with tab1:
    st.subheader("📊 Dashboard (On-demand load)")
    colA, colB = st.columns([1, 2])
    with colA:
        if st.button("Load / Refresh data from Google Sheets"):
            try:
                st.session_state.df = load_data_live()
                st.success("Loaded!")
            except Exception as e:
                st.error(f"Load failed: {repr(e)}")

    df = st.session_state.df

    if df.empty:
        st.info("No data loaded yet. Click **Load / Refresh data**.")
    else:
        st.dataframe(df.head(20), hide_index=True, use_container_width=True)

        # Example chart
        df_sorted = df.sort_values("date")
        st.plotly_chart(px.line(df_sorted, x="date", y="ahi", title="AHI Trend", markers=True), use_container_width=True)

with tab2:
    st.subheader("✍️ Log Today's Metrics")
    with st.form("daily_entry_form"):
        col1, col2 = st.columns(2)

        with col1:
            entry_date = st.date_input("Date", value=datetime.now())
            ahi = st.number_input("AHI", min_value=0.0, step=0.1)
            leak = st.number_input("Leak Rate", min_value=0.0, step=0.1)

        with col2:
            coherence = st.number_input("Coherence", min_value=0.0, step=0.1)
            energy = st.slider("Energy", 1, 10, 5)
            notes = st.text_area("Notes")

        if st.form_submit_button("💾 Save Entry", use_container_width=True):
            try:
                save_entry(entry_date, ahi, leak, coherence, energy, notes)
                st.success("✅ Saved!")
                # Don’t auto-refresh from Google here (keeps things stable on Render)
            except Exception as e:
                st.error(f"Save failed: {repr(e)}")

with tab3:
    st.subheader("🔍 Correlations")
    df = st.session_state.df
    if df.empty or len(df) < 7:
        st.info("Load data first, and you need at least 7 rows for correlations.")
    else:
        corr = df[["ahi", "leak", "coherence", "energy"]].corr()
        fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns, y=corr.columns, zmid=0))
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("Built with ❤️")
