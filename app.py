import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
import json

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

st.set_page_config(page_title="Health Tracker", page_icon="💪", layout="wide")


# -----------------------
# GOOGLE CONNECTOR
# -----------------------
@st.cache_resource
def get_worksheet():
    """
    Connect to Google Sheets using service-account JSON stored in Render Secret File.
    Robust steps:
      1) Read file as raw text
      2) json.loads
      3) Convert literal "\\n" in private_key into real newlines
      4) Credentials.from_service_account_info
      5) gspread authorize + open worksheet
    """
    try:
        if os.path.exists(SECRET_FILE_PATH):
            with open(SECRET_FILE_PATH, "r") as f:
                raw = f.read().strip()

            creds = json.loads(raw)

            pk = creds.get("private_key", "")
            if isinstance(pk, str):
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
        ws = sheet.worksheet(WORKSHEET_NAME)
        return ws

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("=== GOOGLE SHEETS CONNECT ERROR ===", flush=True)
        print(tb, flush=True)
        raise


def _normalize_headers(headers):
    # strip whitespace and lower-case
    return [h.strip().lower() for h in headers]


def load_data_live() -> pd.DataFrame:
    """
    Load data from sheet with header normalization to avoid KeyError('date').
    If headers are missing, raises a clear error explaining what was found.
    """
    ws = get_worksheet()
    data = ws.get_all_values()

    # empty sheet
    if not data:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    raw_headers = data[0]
    headers = _normalize_headers(raw_headers)

    # If sheet has only headers row
    if len(data) == 1:
        # return empty df with normalized headers, but ensure expected cols exist
        df = pd.DataFrame(columns=headers)
        for col in EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = pd.Series(dtype="object")
        return df[EXPECTED_COLUMNS]

    df = pd.DataFrame(data[1:], columns=headers)

    # Allow a few common variations
    rename_map = {
        "day": "date",
        "datetime": "date",
        "timestamp": "date",
    }
    df.rename(columns=rename_map, inplace=True)

    # Ensure required columns exist (create if missing, except date which we require)
    if "date" not in df.columns:
        raise KeyError(
            f"Missing required column 'date'. Found headers: {headers}. "
            f"Fix row 1 to exactly: {', '.join(EXPECTED_COLUMNS)}"
        )

    # Create optional columns if missing
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Parse date
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Parse numeric columns
    for col in ["ahi", "leak", "coherence", "energy"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort newest first
    df = df.sort_values("date", ascending=False)

    # Keep expected column order
    return df[EXPECTED_COLUMNS]


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
st.caption("Connects to Google Sheets only when you click a button (stable on Render).")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "✍️ Daily Entry", "🔍 Correlations", "⚙️ Setup"])

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

# ---- Setup tab
with tab4:
    st.subheader("🔌 Connection Status (On-demand)")

    if st.button("Test connection to Google Sheets", use_container_width=True):
        try:
            ws = get_worksheet()
            st.success(f"✅ Connected! Worksheet: {ws.title}")
        except Exception as e:
            st.error(f"❌ Connection failed: {repr(e)}")

    st.divider()
    st.write("Secret file path check:")
    st.write(f"- {SECRET_FILE_PATH} exists? **{os.path.exists(SECRET_FILE_PATH)}**")

# ---- Dashboard tab
with tab1:
    st.subheader("📊 Dashboard (On-demand load)")

    if st.button("Load / Refresh data from Google Sheets", use_container_width=True):
        try:
            st.session_state.df = load_data_live()
            st.success("Loaded!")
        except Exception as e:
            st.error(f"Load failed: {repr(e)}")

    df = st.session_state.df

    if df is None or df.empty:
        st.info("No data loaded yet. Click **Load / Refresh**.")
    else:
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Avg AHI", f"{df['ahi'].mean():.1f}" if df["ahi"].notna().any() else "—")
        col2.metric("Avg Leak", f"{df['leak'].mean():.1f}" if df["leak"].notna().any() else "—")
        col3.metric("Avg Coherence", f"{df['coherence'].mean():.1f}" if df["coherence"].notna().any() else "—")
        col4.metric("Avg Energy", f"{df['energy'].mean():.1f}" if df["energy"].notna().any() else "—")

        st.divider()

        df_sorted = df.sort_values("date")
        if df_sorted["date"].notna().any():
            if df_sorted["ahi"].notna().any():
                st.plotly_chart(px.line(df_sorted, x="date", y="ahi", title="AHI Trend", markers=True),
                                use_container_width=True)
            if df_sorted["energy"].notna().any():
                st.plotly_chart(px.line(df_sorted, x="date", y="energy", title="Energy Trend", markers=True),
                                use_container_width=True)

        st.subheader("Recent Entries")
        display_df = df.copy()
        display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(display_df.head(25), hide_index=True, use_container_width=True)

# ---- Daily Entry tab
with tab2:
    st.subheader("✍️ Log Today's Metrics")

    with st.form("daily_entry_form"):
        col1, col2 = st.columns(2)

        with col1:
            entry_date = st.date_input("Date", value=datetime.now())
            ahi = st.number_input("AHI", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
            leak = st.number_input("Leak Rate", min_value=0.0, max_value=100.0, value=0.0, step=0.1)

        with col2:
            coherence = st.number_input("Coherence", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
            energy = st.slider("Energy", 1, 10, 5)
            notes = st.text_area("Notes", placeholder="Anything about sleep, diet, stress, training...")

        submitted = st.form_submit_button("💾 Save Entry", use_container_width=True)

        if submitted:
            try:
                save_entry(entry_date, ahi, leak, coherence, energy, notes)
                st.success("✅ Saved!")
                st.info("Go to Dashboard and click **Load / Refresh** to see it.")
            except Exception as e:
                st.error(f"Save failed: {repr(e)}")

# ---- Correlations tab
with tab3:
    st.subheader("🔍 Correlations")

    df = st.session_state.df
    corr = calculate_correlations(df)

    if corr is None:
        st.info("Load data first (Dashboard tab). Need at least ~7 rows for correlations.")
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

st.divider()
st.caption("Built with ❤️")
