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
    """Connect to Google Sheets and automatically fix key formatting"""
    try:
        secret_file_path = "/etc/secrets/gcp-key.pem"
        
        # Check if the file exists on Render
        if os.path.exists(secret_file_path):
            with open(secret_file_path, 'r') as f:
                creds_data = json.load(f)
            
            # THE AUTOMATIC FIX:
            # This line finds those "\n" text characters and turns them into 
            # the real hidden line breaks Google needs.
            if "private_key" in creds_data:
                creds_data["private_key"] = creds_data["private_key"].replace("\\n", "\n")
            
            credentials = Credentials.from_service_account_info(
                creds_data,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        # Fallback for local testing
        elif os.path.exists("credentials.json"):
            credentials = Credentials.from_service_account_file(
                "credentials.json",
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        else:
            st.error("Credentials file not found in Render Secret Files.")
            return None

        # Connect to Google Sheets
        client = gspread.authorize(credentials)
        
        # Open your specific sheet
        sheet = client.open_by_key("1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc")
        worksheet = sheet.worksheet("daily_manual_entry")
        
        return worksheet
        
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=60)
def load_data():
    """Load data from Google Sheets"""
    worksheet = get_google_sheet()
    if worksheet is None:
        return pd.DataFrame()
    
    try:
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame(columns=['date', 'ahi', 'leak', 'coherence', 'energy', 'notes'])
        
        df = pd.DataFrame(data[1:], columns=data[0])
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
        numeric_cols = ['ahi', 'leak', 'coherence', 'energy']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.sort_values('date', ascending=False)
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

def save_entry(date, ahi, leak, coherence, energy, notes):
    """Save a new entry to Google Sheets"""
    worksheet = get_google_sheet()
    if worksheet is None:
        return False
    
    try:
        row = [date.strftime('%Y-%m-%d'), str(ahi), str(leak), str(coherence), str(energy), notes]
        worksheet.append_row(row)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving entry: {str(e)}")
        return False

def calculate_correlations(df):
    """Calculate correlations between metrics"""
    if len(df) < 7:
        return None
    numeric_cols = ['ahi', 'leak', 'coherence', 'energy']
    return df[numeric_cols].corr()

# --- APP UI ---
st.title("💪 Personal Health Tracker")
st.caption("Track your daily health metrics and discover patterns")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "✍️ Daily Entry", "🔍 Correlations", "⚙️ Setup"])
df = load_data()

# TAB 1: DASHBOARD
with tab1:
    if df.empty:
        st.info("👋 No data yet! Go to the **Daily Entry** tab to log your first day.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Avg AHI", f"{df['ahi'].mean():.1f}")
        with col2:
            st.metric("Avg Leak", f"{df['leak'].mean():.1f}")
        with col3:
            st.metric("Avg Coherence", f"{df['coherence'].mean():.1f}")
        with col4:
            st.metric("Avg Energy", f"{df['energy'].mean():.1f}")
        
        st.divider()
        days_to_show = st.selectbox("Show last:", [7, 14, 30, "All"], index=1)
        df_filtered = df.head(days_to_show if days_to_show != "All" else len(df)).sort_values('date')
        
        st.plotly_chart(px.line(df_filtered, x='date', y='ahi', title='AHI Trend', markers=True), use_container_width=True)
        st.plotly_chart(px.line(df_filtered, x='date', y='energy', title='Energy Level Trend', markers=True), use_container_width=True)
        
        st.subheader("📋 Recent Entries")
        st.dataframe(df.head(10), hide_index=True, use_container_width=True)

# TAB 2: DAILY ENTRY
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
            if save_entry(entry_date, ahi, leak, coherence, energy, notes):
                st.success("✅ Entry saved!")
                st.rerun()

# TAB 3: CORRELATIONS
with tab3:
    st.subheader("🔍 Discover Patterns")
    corr = calculate_correlations(df)
    if corr is not None:
        fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns, y=corr.columns, colorscale='RdBu', zmid=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Log 7 days of data to see correlations.")

# TAB 4: SETUP (Status Check)
with tab4:
    st.subheader("🔌 Connection Status")
    if get_google_sheet():
        st.success("✅ Connected to Google Sheets successfully!")
    else:
        st.error("❌ Not connected. Check Render Secret Files.")

st.divider()
st.caption("Built with ❤️")
