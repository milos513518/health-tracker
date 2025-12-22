import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
import json

from streamlit_autorefresh import st_autorefresh

# -----------------------
# CONFIG (yours)
# -----------------------
SECRET_FILE_PATH = "/etc/secrets/gcp-key.pem"
SHEET_KEY = "1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc"
WORKSHEET_NAME = "daily_manual_entry"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_COLUMNS = ["date", "ahi", "leak", "coherence", "energy", "notes"]

# ✅ True auto refresh interval
AUTO_REFRESH_SECONDS = 10  # change to 5, 15, 30, etc.

st.set_page_config(page_title="Health Tracker", page_icon="💪", layout="wide")

# ✅ This forces Streamlit to rerun automatically every N seconds
st_autorefresh(interval=AUTO_REFRESH_SECONDS * 1000, key="app_autorefresh")


# -----------------------
# GOOGLE CONNECTOR
# -----------------------
@st.cache_resource
def get_worksheet():
    """Connect to Google Sheets using service-account JSON stored in Render Secret File."""
    if os.path.exists(SECRET_FILE_PATH):
        with open(SECRET_FILE_PATH, "r") as f:
            raw = f.read().strip()

        creds = json.loads(raw)

        pk = creds.get("private_key", "")
        if isinstance(pk, str):
            # Convert literal "\n" to real newlines (works whether needed or not)
            creds["private_key"] = pk.replace("\\n", "\n")

        credentials = Credentials.from_service_account_info(creds, scopes=SCOPES)

    elif os.path.exists("credentials.json"):
        credentials = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)

    else:
        raise FileNotFoundError(
            f"Credentials not found. Expected Render secret file at {SECRET_FILE_PATH} "
            f"or local credentials.json."
        )

    client = gspread.authorize(credentials)
    sheet = client.open_by_key(SHEET_KEY)
    return sheet.worksheet(WORKSHEET_NAME)


# -----------------------
# HEADER NORMALIZATION
# -----------------------
def _clean_header(h: str) -> str:
    # remove BOM/invisible char, strip whitespace, lowercase
    return str(h).replace("\ufeff", "").strip().lower()


def _normalize_headers(headers):
    return [_clean_header(h) for h in headers]


def _ensure_expected_cols(df: pd.DataFrame) -> pd.DataFrame:
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[EXPECTED_COLUMNS]


# -----------------------
# DATA FUNCTIONS
# -----------------------
def load_data_live() -> pd.DataFrame:
    ws = get_worksheet()
    data = ws.get_all_values()

    if not data:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    raw_headers = data[0]
    headers = _normalize_headers(raw_headers)

    if len(data) == 1:
        df = pd.DataFrame(columns=headers)
        return _ensure_expected_cols(df)

    df = pd.DataFrame(data[1:], columns=headers)

    # Accept common alternatives for date
    df.rename(columns={
        "day": "date",
        "datetime": "date",
        "timestamp": "date",
        "recorded_at": "date",
    }, inplace=True)

    if "date" not in df.columns:
        raise KeyError(
            "Missing required column 'date'.\n"
            f"Found headers (normalized): {headers}\n"
            f"Raw headers (row 1): {raw_headers}\n"
            f"Fix Row 1 to exactly: {', '.join(EXPECTED_COLUMNS)}"
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["ahi", "leak", "coherence", "energy"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = _ensure_expected_cols(df)
    df = df.sort_values("date", ascending=False)
    return df


# ✅ Cache the sheet read for exactly the refresh interval
@st.cache_data(ttl=AUTO_REFRESH_SECONDS)
def load_data_cached() -> pd.DataFrame:
    return load_data_live()


def calculate_correlations(df: pd.DataFrame):
    if df is None or df.empty or len(df) < 7:
        return None
    cols = ["ahi", "leak", "coherence", "energy"]
    if not all(c in df.columns for c in cols):
        return None
    return df[cols].corr()


# -----------------------
# UI
# -----------------------
st.title("💪 Personal Health Tracker")
st.caption(f"Auto-refreshing every {AUTO_REFRESH_SECONDS} seconds from Google Sheets.")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🔍 Correlations", "⚙️ Setup", "🧾 Raw Table"])

# Keep last-good df in session state so UI doesn't go blank on intermittent failures
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

# Pull fresh data automatically every refresh (cached at TTL)
try:
    st.session_state.df = load_data_cached()
except Exception as e:
    # Keep previous df if a refresh fails
    st.warning(f"Auto-refresh failed (showing last loaded data): {repr(e)}")

df = st.session_state.df


with tab4:
    st.subheader("🔌 Connection Status")
    try:
        ws = get_worksheet()
        st.success(f"✅ Connected! Worksheet: {ws.title}")
    except Exception as e:
        st.error(f"❌ Connection failed: {repr(e)}")

    st.divider()
    st.write("Secret file exists:")
    st.write(f"- {SECRET_FILE_PATH}: **{os.path.exists(SECRET_FILE_PATH)}**")


with tab1:
    st.subheader("📊 Dashboard")

    if df is None or df.empty:
        st.info("No data yet (or sheet empty). Add rows in Google Sheets and this will update automatically.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Avg AHI", f"{df['ahi'].mean():.1f}" if df["ahi"].notna().any() else "—")
        col2.metric("Avg Leak", f"{df['leak'].mean():.1f}" if df["leak"].notna().any() else "—")
        col3.metric("Avg Coherence", f"{df['coherence'].mean():.1f}" if df["coherence"].notna().any() else "—")
        col4.metric("Avg Energy", f"{df['energy'].mean():.1f}" if df["energy"].notna().any() else "—")

        st.divider()

        df_sorted = df.sort_values("date")
        if df_sorted["date"].notna().any():
            if df_sorted["ahi"].notna().any():
                st.plotly_chart(
                    px.line(df_sorted, x="date", y="ahi", title="AHI Trend", markers=True),
                    use_container_width=True
                )
            if df_sorted["energy"].notna().any():
                st.plotly_chart(
                    px.line(df_sorted, x="date", y="energy", title="Energy Trend", markers=True),
                    use_container_width=True
                )


with tab2:
    st.subheader("🔍 Correlations")
    corr = calculate_correlations(df)
    if corr is None:
        st.info("Need at least ~7 rows loaded to compute correlations.")
    else:
        fig = go.Figure(
            data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.columns,
                zmid=0,
            )
        )
        st.plotly_chart(fig, use_container_width=True)


with tab3:
    st.subheader("🧾 Raw Table (auto-updating)")
    if df is None or df.empty:
        st.info("No rows yet.")
    else:
        display_df = df.copy()
        display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(display_df, hide_index=True, use_container_width=True)
