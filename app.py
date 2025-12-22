# Google Sheets connection
@st.cache_resource
def get_google_sheet():
    """Connect to Google Sheets using service account credentials file"""
    try:
        # The path where Render stores your secret file
        secret_file_path = "/etc/secrets/gcp-key.pem"
        
        # Check if the file exists (it will on Render, but maybe not on your laptop)
        if os.path.exists(secret_file_path):
            credentials = Credentials.from_service_account_file(
                secret_file_path,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        # Fallback for local testing (looking for a local .json file)
        elif os.path.exists("credentials.json"):
            credentials = Credentials.from_service_account_file(
                "credentials.json",
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        else:
            st.error(f"Credentials file not found at {secret_file_path}")
            return None

        # Connect to Google Sheets
        client = gspread.authorize(credentials)
        
        # Open the specific sheet
        sheet = client.open_by_key("1qc_8gnDFMkwnT3j2i_BFBWFqsLymroqVf-rrQuGzzOc")
        worksheet = sheet.worksheet("daily_manual_entry")
        
        return worksheet
        
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {str(e)}")
        return None
