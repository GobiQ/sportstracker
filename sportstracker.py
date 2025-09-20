# Google Sheets Setup Instructions

## 🔧 Setup Steps for Streamlit Cloud Deployment

### 1. Create a Google Sheet
1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new blank spreadsheet
3. Name it something like "Sports Prediction Tracker"
4. Note the Sheet ID from the URL (the long string between `/d/` and `/edit`)

### 2. Set up Google Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing one
3. Enable the Google Sheets API:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click and enable it

### 3. Create Service Account Credentials
1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the details and create
4. Click on the created service account
5. Go to "Keys" tab > "Add Key" > "Create New Key" > "JSON"
6. Download the JSON file

### 4. Share Google Sheet with Service Account
1. Open your Google Sheet
2. Click "Share"
3. Add the service account email (found in the JSON file as `client_email`)
4. Give it "Editor" permissions

### 5. Configure Streamlit Secrets
In your Streamlit Cloud app settings, add these secrets:

```toml
[connections.gsheets]
spreadsheet = "YOUR_GOOGLE_SHEET_ID_HERE"
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

**Important Notes:**
- Replace all `your-*` placeholders with actual values from your downloaded JSON file
- The `spreadsheet` value is the Google Sheet ID from the URL
- For the `private_key`, make sure to include the full key with `\n` for line breaks
- Keep the quotes around the private key

### 6. Alternative: Using .streamlit/secrets.toml (Local Development)
For local testing, create a `.streamlit/secrets.toml` file in your project root:

```toml
[connections.gsheets]
spreadsheet = "YOUR_GOOGLE_SHEET_ID_HERE"
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

**⚠️ Important: Add `.streamlit/` to your `.gitignore` file to avoid committing secrets!**

### 7. Repository Structure
```
your-repo/
├── app.py                     # Main Streamlit app
├── requirements.txt           # Dependencies
├── .streamlit/
│   └── secrets.toml          # Local secrets (add to .gitignore)
├── .gitignore                # Include .streamlit/ here
└── README.md                 # Setup instructions
```

### 8. Deploy to Streamlit Cloud
1. Push your repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repository
4. In the advanced settings, add your secrets from step 5
5. Deploy!

## 🔍 Troubleshooting

### Common Issues:

1. **"Sheet not found" error**
   - Check that the spreadsheet ID is correct
   - Ensure the service account has access to the sheet

2. **Authentication errors**
   - Verify all credentials in secrets are correct
   - Check that Google Sheets API is enabled
   - Confirm service account has proper permissions

3. **Permission denied**
   - Make sure you shared the Google Sheet with the service account email
   - Service account needs "Editor" permissions

4. **Local vs Cloud differences**
   - Secrets format must be identical between local `.streamlit/secrets.toml` and Streamlit Cloud secrets
   - Test locally first before deploying

### Testing Your Setup:
1. Run the app locally first to test the Google Sheets connection
2. Add a test player to verify write permissions
3. Create a test game to confirm all sheets are working
4. Only deploy to Streamlit Cloud after local testing succeeds

## 🎯 What the App Will Do:
- Automatically create 3 sheets in your Google Sheet: `players`, `games`, `predictions`
- Store all data persistently in Google Sheets
- Handle concurrent access safely
- Provide real-time updates across all users
- Maintain data integrity across app restarts

## 🚀 Next Steps:
1. Complete the Google Sheets setup above
2. Test locally with `streamlit run app.py`
3. Deploy to Streamlit Cloud
4. Start tracking your youth home predictions!

Your data will be safely stored in Google Sheets and accessible from anywhere! 🏆
