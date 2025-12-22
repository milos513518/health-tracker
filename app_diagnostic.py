import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# Page config
st.set_page_config(
    page_title="Health Tracker",
    page_icon="💪",
    layout="wide"
)

# Google Sheets connection
@st.cache_resource
def get_google_sheet():
    """Connect to Google Sheets using service account credentials"""
    try:
        import os
        import json
        
        # Debug: Show which environment variables are present
        st.sidebar.write("🔍 Debug Info:")
        st.sidebar.write(f"GOOGLE_APPLICATION_CREDENTIALS_JSON present: {bool(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))}")
        st.sidebar.write(f"GCP_CLIENT_EMAIL present: {bool(os.environ.get('GCP_CLIENT_EMAIL'))}")
        st.sidebar.write(f"Streamlit secrets present: {'gcp_service_account' in st.secrets}")
        
        # Try to get credentials from environment variables first (for Render)
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
            st.sidebar.success("✓ Found GOOGLE_APPLICATION_CREDENTIALS_JSON")
            try:
                # Parse the JSON string from environment variable
                credentials_dict = json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
                st.sidebar.write(f"Project ID: {credentials_dict.get('project_id', 'N/A')}")
                st.sidebar.write(f"Client Email: {credentials_dict.get('client_email', 'N/A')[:50]}...")
                
                credentials = Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive"
                    ]
                )
                st.sidebar.success("✓ Credentials parsed successfully")
            except json.JSONDecodeError as e:
                st.sidebar.error(f"❌ JSON parsing error: {str(e)}")
                raise
            except Exception as e:
                st.sidebar.error(f"❌ Credentials creation error: {str(e)}")
                raise
                
        # Try individual environment variables (alternative method)
        elif os.environ.get("GCP_CLIENT_EMAIL"):
            st.sidebar.success("✓ Found individual GCP variables")
            credentials_dict = {
                "type": os.environ.get("GCP_TYPE", "service_account"),
                "project_id": os.environ.get("GCP_PROJECT_ID"),
                "private_key_id": os.environ.get("GCP_PRIVATE_KEY_ID"),
                "private_key": os.environ.get("GCP_PRIVATE_KEY"),
                "client_email": os.environ.get("GCP_CLIENT_EMAIL"),
                "client_id": os.environ.get("GCP_CLIENT_ID"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.environ.get('GCP_CLIENT_EMAIL')}",
                "universe_domain": "googleapis.com"
            }
            credentials = Credentials.from_service_account_info(
                credentials_dict,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        # Fall back to Streamlit secrets (for Streamlit Cloud)
        elif "gcp_service_account" in st.secrets:
            st.sidebar.success("✓ Found Streamlit secrets")
            credentials = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        else:
            st.sidebar.error("❌ No credentials found anywhere")
            st.error("No credentials found. Please set up environment variables or Streamlit secrets.")
            return None
        
        # Connect to Google Sheets
        st.sidebar.write("Attempting to authorize with gspread...")
        client = gspread.authorize(credentials)
        st.sidebar.success("✓ Authorized with gspread")
        
        # Open the specific sheet
        st.sidebar.write("Opening spreadsheet...")
        sheet = client.open_by_key("1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc")
        st.sidebar.success("✓ Spreadsheet opened")
        
        st.sidebar.write("Getting worksheet...")
        worksheet = sheet.worksheet("daily_manual_entry")
        st.sidebar.success("✓ Worksheet retrieved")
        
        return worksheet
    except Exception as e:
        error_msg = str(e)
        st.error(f"Error connecting to Google Sheets: {error_msg}")
        st.sidebar.error(f"❌ Full error: {error_msg}")
        
        # Additional troubleshooting info
        import traceback
        st.sidebar.text("Full traceback:")
        st.sidebar.code(traceback.format_exc())
        
        st.info("Make sure you've added the secrets in Streamlit Cloud and shared the sheet with the service account email.")
        return None

@st.cache_data(ttl=60)
def load_data():
    """Load data from Google Sheets"""
    worksheet = get_google_sheet()
    if worksheet is None:
        return pd.DataFrame()
    
    try:
        # Get all values
        data = worksheet.get_all_values()
        
        if len(data) <= 1:
            # Only headers or empty
            return pd.DataFrame(columns=['date', 'ahi', 'leak', 'coherence', 'energy', 'notes'])
        
        # Convert to DataFrame
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # Convert date column to datetime
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
        # Convert numeric columns
        numeric_cols = ['ahi', 'leak', 'coherence', 'energy']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Sort by date
        df = df.sort_values('date', ascending=False)
        
        return df
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

def save_entry(date, ahi, leak, coherence, energy, notes):
    """Save a new entry to Google Sheets"""
    worksheet = get_google_sheet()
    if worksheet is None:
        return False
    
    try:
        # Format the row
        row = [
            date.strftime('%Y-%m-%d'),
            str(ahi),
            str(leak),
            str(coherence),
            str(energy),
            notes
        ]
        
        # Append to sheet
        worksheet.append_row(row)
        
        # Clear cache to refresh data
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
    correlations = df[numeric_cols].corr()
    
    return correlations

# App Title
st.title("💪 Personal Health Tracker")
st.caption("Track your daily health metrics and discover patterns")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "✍️ Daily Entry", "🔍 Correlations", "⚙️ Setup"])

# Load data once for all tabs
df = load_data()

# TAB 1: DASHBOARD
with tab1:
    if df.empty:
        st.info("👋 No data yet! Go to the **Daily Entry** tab to log your first day.")
    else:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            avg_ahi = df['ahi'].mean()
            st.metric("Avg AHI", f"{avg_ahi:.1f}", 
                     delta=f"{df['ahi'].iloc[0] - avg_ahi:.1f}" if len(df) > 1 else None,
                     delta_color="inverse")
        
        with col2:
            avg_leak = df['leak'].mean()
            st.metric("Avg Leak", f"{avg_leak:.1f}", 
                     delta=f"{df['leak'].iloc[0] - avg_leak:.1f}" if len(df) > 1 else None,
                     delta_color="inverse")
        
        with col3:
            avg_coherence = df['coherence'].mean()
            st.metric("Avg Coherence", f"{avg_coherence:.1f}", 
                     delta=f"{df['coherence'].iloc[0] - avg_coherence:.1f}" if len(df) > 1 else None)
        
        with col4:
            avg_energy = df['energy'].mean()
            st.metric("Avg Energy", f"{avg_energy:.1f}", 
                     delta=f"{df['energy'].iloc[0] - avg_energy:.1f}" if len(df) > 1 else None)
        
        st.divider()
        
        # Time range selector
        days_to_show = st.selectbox("Show last:", [7, 14, 30, 60, 90, "All"], index=1)
        
        if days_to_show != "All":
            df_filtered = df.head(days_to_show).sort_values('date')
        else:
            df_filtered = df.sort_values('date')
        
        # Charts
        st.subheader("📈 Trends Over Time")
        
        # AHI Chart
        fig_ahi = px.line(df_filtered, x='date', y='ahi', 
                         title='AHI (Apnea-Hypopnea Index)',
                         markers=True)
        fig_ahi.add_hline(y=5, line_dash="dash", line_color="orange", 
                         annotation_text="Target: < 5")
        fig_ahi.update_layout(height=300)
        st.plotly_chart(fig_ahi, use_container_width=True)
        
        # Leak Chart
        fig_leak = px.line(df_filtered, x='date', y='leak', 
                          title='Leak Rate (L/min)',
                          markers=True)
        fig_leak.add_hline(y=24, line_dash="dash", line_color="orange", 
                          annotation_text="Target: < 24")
        fig_leak.update_layout(height=300)
        st.plotly_chart(fig_leak, use_container_width=True)
        
        # Coherence Chart
        fig_coherence = px.line(df_filtered, x='date', y='coherence', 
                               title='HeartMath Coherence Score',
                               markers=True)
        fig_coherence.update_layout(height=300)
        st.plotly_chart(fig_coherence, use_container_width=True)
        
        # Energy Chart
        fig_energy = px.line(df_filtered, x='date', y='energy', 
                            title='Energy Level (1-10)',
                            markers=True)
        fig_energy.update_layout(height=300)
        st.plotly_chart(fig_energy, use_container_width=True)
        
        st.divider()
        
        # Recent entries table
        st.subheader("📋 Recent Entries")
        display_df = df.head(10).copy()
        display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
        st.dataframe(display_df, hide_index=True, use_container_width=True)

# TAB 2: DAILY ENTRY
with tab2:
    st.subheader("✍️ Log Today's Metrics")
    
    with st.form("daily_entry_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            entry_date = st.date_input("Date", value=datetime.now())
            ahi = st.number_input("AHI (Apnea-Hypopnea Index)", 
                                 min_value=0.0, max_value=100.0, value=0.0, step=0.1,
                                 help="From myAir app - lower is better")
            leak = st.number_input("Leak Rate (L/min)", 
                                  min_value=0.0, max_value=100.0, value=0.0, step=0.1,
                                  help="From myAir app - lower is better")
        
        with col2:
            coherence = st.number_input("Coherence Score", 
                                       min_value=0.0, max_value=100.0, value=0.0, step=0.1,
                                       help="From HeartMath app - higher is better")
            energy = st.slider("Energy Level", 
                              min_value=1, max_value=10, value=5,
                              help="Rate your energy: 1 = exhausted, 10 = amazing")
            notes = st.text_area("Notes (optional)", 
                                help="Any observations about your day, sleep, etc.")
        
        submit_button = st.form_submit_button("💾 Save Entry", use_container_width=True)
        
        if submit_button:
            if ahi == 0 and leak == 0 and coherence == 0:
                st.warning("⚠️ Please enter at least some metrics before saving.")
            else:
                with st.spinner("Saving..."):
                    if save_entry(entry_date, ahi, leak, coherence, energy, notes):
                        st.success("✅ Entry saved successfully!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("❌ Failed to save entry. Check the Setup tab for troubleshooting.")

# TAB 3: CORRELATIONS
with tab3:
    st.subheader("🔍 Discover Patterns in Your Data")
    
    if len(df) < 7:
        st.info(f"📊 You have {len(df)} entries. You need at least 7 days of data to see meaningful correlations. Keep logging!")
    else:
        st.write(f"Analyzing {len(df)} days of data...")
        
        # Calculate correlations
        corr = calculate_correlations(df)
        
        if corr is not None:
            # Correlation heatmap
            fig_corr = go.Figure(data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.columns,
                colorscale='RdBu',
                zmid=0,
                text=corr.values.round(2),
                texttemplate='%{text}',
                textfont={"size": 14},
            ))
            fig_corr.update_layout(
                title="Correlation Matrix",
                height=400,
                xaxis_title="",
                yaxis_title=""
            )
            st.plotly_chart(fig_corr, use_container_width=True)
            
            st.divider()
            
            # Key insights
            st.subheader("💡 Key Insights")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**AHI Impact:**")
                ahi_energy = corr.loc['ahi', 'energy']
                if ahi_energy < -0.3:
                    st.error(f"🔴 Strong negative correlation with energy ({ahi_energy:.2f})")
                    st.write("Higher AHI → Lower energy. Focus on improving your CPAP therapy.")
                elif ahi_energy < -0.1:
                    st.warning(f"🟡 Moderate negative correlation with energy ({ahi_energy:.2f})")
                else:
                    st.success(f"🟢 Weak/no correlation with energy ({ahi_energy:.2f})")
                
                st.markdown("**Leak Impact:**")
                leak_energy = corr.loc['leak', 'energy']
                if leak_energy < -0.3:
                    st.error(f"🔴 Strong negative correlation with energy ({leak_energy:.2f})")
                    st.write("High leak rates → Lower energy. Check your mask fit.")
                elif leak_energy < -0.1:
                    st.warning(f"🟡 Moderate negative correlation with energy ({leak_energy:.2f})")
                else:
                    st.success(f"🟢 Weak/no correlation with energy ({leak_energy:.2f})")
            
            with col2:
                st.markdown("**Coherence Impact:**")
                coherence_energy = corr.loc['coherence', 'energy']
                if coherence_energy > 0.3:
                    st.success(f"🟢 Strong positive correlation with energy ({coherence_energy:.2f})")
                    st.write("Higher coherence → Higher energy. Your breathwork is paying off!")
                elif coherence_energy > 0.1:
                    st.info(f"🔵 Moderate positive correlation with energy ({coherence_energy:.2f})")
                else:
                    st.info(f"⚪ Weak/no correlation with energy ({coherence_energy:.2f})")
                
                st.markdown("**AHI vs Leak:**")
                ahi_leak = corr.loc['ahi', 'leak']
                if ahi_leak > 0.3:
                    st.warning(f"🟡 High leak often coincides with high AHI ({ahi_leak:.2f})")
                    st.write("Poor mask seal may be causing apneas. Try adjusting your mask.")
            
            st.divider()
            
            # Scatter plots
            st.subheader("📊 Detailed Comparisons")
            
            scatter_x = st.selectbox("X-axis", ['ahi', 'leak', 'coherence'], key='scatter_x')
            scatter_y = st.selectbox("Y-axis", ['energy', 'coherence', 'ahi'], key='scatter_y')
            
            if scatter_x != scatter_y:
                fig_scatter = px.scatter(df, x=scatter_x, y=scatter_y,
                                        trendline="ols",
                                        title=f"{scatter_x.upper()} vs {scatter_y.upper()}",
                                        hover_data=['date'])
                fig_scatter.update_layout(height=400)
                st.plotly_chart(fig_scatter, use_container_width=True)

# TAB 4: SETUP
with tab4:
    st.subheader("⚙️ Setup Instructions")
    
    st.markdown("""
    ### ✅ Quick Checklist
    
    Make sure you've completed these steps:
    
    1. ✓ Created Google Sheet named "Health Data"
    2. ✓ Created worksheet named "daily_manual_entry"
    3. ✓ Added headers: `date | ahi | leak | coherence | energy | notes`
    4. ✓ Created Google Cloud service account
    5. ✓ Downloaded JSON credentials
    6. ✓ Shared sheet with: `health-tracker-bot@health-tracker-481311.iam.gserviceaccount.com`
    7. ✓ Added secrets to Streamlit Cloud (or environment variable to Render)
    8. ✓ Rebooted app
    
    ---
    
    ### 🔧 Troubleshooting
    
    **"Error connecting to Google Sheets"**
    - Check that you shared the sheet with the service account email (see step 6 above)
    - Verify the secrets in Streamlit Settings → Secrets (or environment variables in Render)
    - Make sure the sheet name is exactly "Health Data"
    - Make sure the worksheet name is exactly "daily_manual_entry"
    
    **"Error loading data"**
    - Check that your sheet has the correct headers in row 1
    - Verify there's no extra worksheets with similar names
    
    **Private key formatting issues**
    - Make sure the private_key in secrets is wrapped in quotes
    - Include the entire key including `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----`
    
    ---
    
    ### 📱 Bookmark This App
    
    **iPhone:**
    1. Open this app in Safari
    2. Tap the Share icon
    3. Select "Add to Home Screen"
    4. Name it "Health Log"
    
    **Android:**
    1. Open this app in Chrome
    2. Tap the ⋮ menu
    3. Select "Add to Home screen"
    4. Name it "Health Log"
    
    ---
    
    ### 📊 Your Google Sheet
    
    View your data directly:
    [Open Google Sheet](https://docs.google.com/spreadsheets/d/1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc/edit)
    
    ---
    
    ### 📚 What the Metrics Mean
    
    **AHI (Apnea-Hypopnea Index)**
    - Measures breathing interruptions per hour
    - < 5: Normal/Mild
    - 5-15: Moderate
    - 15-30: Severe
    - > 30: Very Severe
    - *Lower is better*
    
    **Leak Rate**
    - Measures mask seal quality in L/min
    - < 24: Good seal
    - 24-40: Acceptable
    - > 40: Poor seal (adjust mask)
    - *Lower is better*
    
    **Coherence Score**
    - HeartMath HRV coherence measure
    - Reflects stress/relaxation state
    - Higher scores = better regulation
    - *Higher is better*
    
    **Energy Level**
    - Subjective rating 1-10
    - Track how you actually feel
    - Watch for patterns with other metrics
    - *Higher is better*
    """)
    
    st.divider()
    
    # Connection status
    st.subheader("🔌 Connection Status")
    
    with st.spinner("Checking connection..."):
        worksheet = get_google_sheet()
        if worksheet:
            st.success("✅ Connected to Google Sheets successfully!")
            try:
                row_count = len(worksheet.get_all_values())
                st.info(f"📊 Found {row_count - 1} entries in your sheet (excluding header)")
            except:
                st.warning("⚠️ Connected but couldn't count rows")
        else:
            st.error("❌ Not connected to Google Sheets. Check troubleshooting steps above.")

# Footer
st.divider()
st.caption("Built with ❤️ using 100% free tools • [View on GitHub](https://github.com)")
