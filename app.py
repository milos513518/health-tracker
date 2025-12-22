import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# Page config
st.set_page_config(
    page_title="Health Tracker",
    page_icon="💪",
    layout="wide"
)

# Google Sheets connection
@st.cache_resource
def get_google_sheet():
    """Connect to Google Sheets with automated formatting fixes"""
    try:
        secret_file_path = "/etc/secrets/gcp-key.pem"
        
        if os.path.exists(secret_file_path):
            # FIX 1: Read as raw text to prevent the app from hanging
            with open(secret_file_path, 'r') as f:
                raw_content = f.read().strip()
            
            # FIX 2: Parse string to JSON
            creds_data = json.loads(raw_content)
            
            # FIX 3: Convert literal "\n" text into real line breaks
            if "private_key" in creds_data:
                creds_data["private_key"] = creds_data["private_key"].replace("\\n", "\n")
            
            credentials = Credentials.from_service_account_info(
                creds_data,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        elif os.path.exists("credentials.json"):
            credentials = Credentials.from_service_account_file(
                "credentials.json",
                scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            )
        else:
            st.error("Credentials file not found.")
            return None

        client = gspread.authorize(credentials)
        # Use your verified Sheet ID and Tab Name
        sheet = client.open_by_key("1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc")
        return sheet.worksheet("daily_manual_entry")
        
    except Exception as e:
        # This will now show the REAL error message instead of a blank box
        st.error(f"Error connecting to Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=60)
def load_data():
    worksheet = get_google_sheet()
    if worksheet is None: return pd.DataFrame()
    try:
        data = worksheet.get_all_values()
        if len(data) <= 1: return pd.DataFrame(columns=['date', 'ahi', 'leak', 'coherence', 'energy', 'notes'])
        df = pd.DataFrame(data[1:], columns=data[0])
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        for col in ['ahi', 'leak', 'coherence', 'energy']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.sort_values('date', ascending=False)
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

def save_entry(date, ahi, leak, coherence, energy, notes):
    worksheet = get_google_sheet()
    if worksheet is None: return False
    try:
        row = [date.strftime('%Y-%m-%d'), str(ahi), str(leak), str(coherence), str(energy), notes]
        worksheet.append_row(row)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving entry: {str(e)}")
        return False

# --- APP UI ---
st.title("💪 Personal Health Tracker")
df = load_data()

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "✍️ Daily Entry", "🔍 Correlations", "⚙️ Setup"])

with tab1:
    if df.empty:
        st.info("👋 No data yet! Go to the Daily Entry tab.")
    else:
        st.dataframe(df.head(10), hide_index=True, use_container_width=True)

with tab2:
    with st.form("entry_form"):
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("Date", value=datetime.now())
            ahi = st.number_input("AHI", min_value=0.0, step=0.1)
        with col2:
            energy = st.slider("Energy", 1, 10, 5)
            notes = st.text_area("Notes")
        if st.form_submit_button("Save"):
            if save_entry(entry_date, ahi, 0, 0, energy, notes):
                st.success("Saved!")
                st.rerun()

with tab4:
    st.subheader("🔌 Connection Status")
    if get_google_sheet():
        st.success("✅ Connected to Google Sheets successfully!")
    else:
        st.error("❌ Not connected. Check Render Secret Files.")
