import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import numpy as np

# Streamlit App Configuration
st.set_page_config(
    page_title="Pick'ems 2026",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Google Sheets connection
@st.cache_resource
def init_connection():
    """Initialize Google Sheets connection using gspread"""
    try:
        # Get credentials from Streamlit secrets
        credentials_info = {
            "type": st.secrets["connections"]["gsheets"]["type"],
            "project_id": st.secrets["connections"]["gsheets"]["project_id"],
            "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
            "private_key": st.secrets["connections"]["gsheets"]["private_key"],
            "client_email": st.secrets["connections"]["gsheets"]["client_email"],
            "client_id": st.secrets["connections"]["gsheets"]["client_id"],
            "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
            "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["connections"]["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["connections"]["gsheets"]["client_x509_cert_url"]
        }
        
        # Add universe_domain if it exists in secrets
        if "universe_domain" in st.secrets["connections"]["gsheets"]:
            credentials_info["universe_domain"] = st.secrets["connections"]["gsheets"]["universe_domain"]
        
        # Create credentials
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        
        # Create gspread client
        gc = gspread.authorize(credentials)
        
        # Open spreadsheet
        spreadsheet_id = st.secrets["connections"]["gsheets"]["spreadsheet"]
        spreadsheet = gc.open_by_key(spreadsheet_id)
        
        return spreadsheet
            
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        return None

@st.cache_data(ttl=300)  # Cache for 5 minutes to reduce API calls
def get_all_data(spreadsheet_id):
    """Get all data from all sheets in one batch operation"""
    try:
        spreadsheet = init_connection()
        if not spreadsheet:
            return {}
        
        # Get all sheets at once
        worksheets = spreadsheet.worksheets()
        sheet_names = [ws.title for ws in worksheets]
        
        data = {}
        
        # Find our required sheets (case-insensitive)
        sheet_mapping = {}
        for sheet_name in ['players', 'weeks', 'results']:
            for actual_name in sheet_names:
                if actual_name.lower() == sheet_name.lower():
                    sheet_mapping[sheet_name] = actual_name
                    break
        
        # Get data from each sheet
        for logical_name, actual_name in sheet_mapping.items():
            try:
                worksheet = spreadsheet.worksheet(actual_name)
                all_records = worksheet.get_all_records()
                data[logical_name] = pd.DataFrame(all_records)
            except Exception as e:
                st.warning(f"Could not load {logical_name} sheet: {e}")
                data[logical_name] = pd.DataFrame()
        
        # Ensure we have all required sheets
        for sheet_name in ['players', 'weeks', 'results']:
            if sheet_name not in data:
                data[sheet_name] = pd.DataFrame()
        
        return data
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return {'players': pd.DataFrame(), 'weeks': pd.DataFrame(), 'results': pd.DataFrame()}

def linear_regression(x, y):
    """Calculate linear regression without scipy dependency"""
    try:
        x = np.array(x)
        y = np.array(y)
        
        if len(x) < 2 or len(y) < 2 or len(x) != len(y):
            return 0, 0, 0, 1, 0
        
        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x * x)
        sum_y2 = np.sum(y * y)
        
        # Calculate slope (m) and intercept (b)
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0, np.mean(y), 0, 1, 0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        # Calculate correlation coefficient (r)
        numerator_r = n * sum_xy - sum_x * sum_y
        denominator_r = np.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
        
        if denominator_r == 0:
            r_value = 0
        else:
            r_value = numerator_r / denominator_r
        
        # Calculate p-value (simplified approximation)
        if n > 2:
            t_stat = r_value * np.sqrt((n - 2) / (1 - r_value**2)) if abs(r_value) < 1 else 0
            # Simplified p-value approximation
            p_value = 0.05 if abs(t_stat) > 2 else 0.2  # Very rough approximation
        else:
            p_value = 1
        
        # Calculate standard error (simplified)
        if n > 2:
            y_pred = slope * x + intercept
            residuals = y - y_pred
            mse = np.sum(residuals**2) / (n - 2)
            std_err = np.sqrt(mse / np.sum((x - np.mean(x))**2)) if np.sum((x - np.mean(x))**2) > 0 else 0
        else:
            std_err = 0
        
        return slope, intercept, r_value, p_value, std_err
        
    except Exception:
        return 0, 0, 0, 1, 0

def ensure_sheets_exist(spreadsheet):
    """Ensure all required sheets exist in the Google Sheet"""
    try:
        required_sheets = {
            'players': ['id', 'name', 'created_at'],
            'weeks': ['id', 'week_number', 'season_year', 'total_games', 'week_date', 'created_at'],
            'results': ['id', 'player_id', 'week_id', 'correct_guesses', 'status', 'created_at']
        }
        
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        
        # Create a case-insensitive mapping of existing sheets
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        
        for sheet_name, headers in required_sheets.items():
            if sheet_name.lower() in existing_sheets_lower:
                # Sheet exists, check headers
                actual_sheet_name = existing_sheets_lower[sheet_name.lower()]
                worksheet = spreadsheet.worksheet(actual_sheet_name)
                
                try:
                    existing_headers = worksheet.row_values(1)
                    if not existing_headers or existing_headers != headers:
                        # Update headers
                        if existing_headers:
                            worksheet.delete_rows(1, 1)
                        worksheet.insert_row(headers, 1)
                except:
                    try:
                        worksheet.insert_row(headers, 1)
                    except:
                        pass
            else:
                # Create sheet
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
                worksheet.append_row(headers)
        
        return True
        
    except Exception as e:
        st.error(f"Error setting up sheets: {e}")
        return False

def batch_update_sheet(spreadsheet, sheet_name, data_list, operation='append'):
    """Batch update a sheet with multiple rows at once"""
    try:
        # Find actual sheet name (case-insensitive)
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        actual_sheet_name = existing_sheets_lower.get(sheet_name.lower(), sheet_name)
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        if operation == 'append':
            # Get headers
            headers = worksheet.row_values(1)
            
            # Convert data to rows
            rows = []
            for data_dict in data_list:
                row = []
                for header in headers:
                    value = data_dict.get(header, '')
                    # Convert data types to native Python types
                    if hasattr(value, 'item'):
                        value = value.item()
                    elif hasattr(value, 'tolist'):
                        value = value.tolist()
                    elif str(type(value)).startswith('<class \'pandas'):
                        value = str(value)
                    row.append(value)
                rows.append(row)
            
            # Batch append all rows at once
            if rows:
                worksheet.append_rows(rows)
            
        return True
        
    except Exception as e:
        st.error(f"Error batch updating {sheet_name}: {e}")
        return False

def update_player_name(spreadsheet, player_id, new_name):
    """Update a player's name"""
    try:
        # Find actual sheet name (case-insensitive)
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        actual_sheet_name = existing_sheets_lower.get('players', 'players')
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        data = worksheet.get_all_records()
        
        # Find the row to update
        for i, row in enumerate(data, start=2):  # Start at 2 because row 1 is headers
            if str(row.get('id', '')) == str(player_id):
                # Update name cell
                headers = worksheet.row_values(1)
                if 'name' in headers:
                    col_index = headers.index('name') + 1
                    worksheet.update_cell(i, col_index, new_name)
                return True
        return False
    except Exception as e:
        st.error(f"Error updating player: {e}")
        return False

def delete_player(spreadsheet, player_id):
    """Delete a player and all their results"""
    try:
        # Delete from players sheet
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        
        # Delete from players sheet
        players_sheet_name = existing_sheets_lower.get('players', 'players')
        worksheet = spreadsheet.worksheet(players_sheet_name)
        data = worksheet.get_all_records()
        
        row_to_delete = None
        for i, row in enumerate(data, start=2):
            if str(row.get('id', '')) == str(player_id):
                row_to_delete = i
                break
        
        if row_to_delete:
            worksheet.delete_rows(row_to_delete)
        
        # Delete from results sheet
        results_sheet_name = existing_sheets_lower.get('results', 'results')
        results_worksheet = spreadsheet.worksheet(results_sheet_name)
        results_data = results_worksheet.get_all_records()
        
        # Find all rows to delete (in reverse order to avoid index issues)
        rows_to_delete = []
        for i, row in enumerate(results_data, start=2):
            if str(row.get('player_id', '')) == str(player_id):
                rows_to_delete.append(i)
        
        # Delete rows in reverse order
        for row_num in reversed(rows_to_delete):
            results_worksheet.delete_rows(row_num)
        
        return True
    except Exception as e:
        st.error(f"Error deleting player: {e}")
        return False

def update_result(spreadsheet, result_id, correct_guesses, status):
    """Update a specific result"""
    try:
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        actual_sheet_name = existing_sheets_lower.get('results', 'results')
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        data = worksheet.get_all_records()
        
        # Find the row to update
        for i, row in enumerate(data, start=2):
            if str(row.get('id', '')) == str(result_id):
                headers = worksheet.row_values(1)
                
                # Update correct_guesses
                if 'correct_guesses' in headers:
                    col_index = headers.index('correct_guesses') + 1
                    value = correct_guesses if status != 'omitted' else ''
                    worksheet.update_cell(i, col_index, value)
                
                # Update status
                if 'status' in headers:
                    col_index = headers.index('status') + 1
                    worksheet.update_cell(i, col_index, status)
                
                return True
        return False
    except Exception as e:
        st.error(f"Error updating result: {e}")
        return False

def get_next_id(df):
    """Get the next available ID for a dataframe"""
    if df.empty or 'id' not in df.columns:
        return 1
    try:
        max_id = int(df['id'].astype(int).max())
        return max_id + 1 if pd.notna(max_id) else 1
    except:
        return 1

def calculate_standings(data, season_year, week_number=None):
    """Calculate standings with both absolute and adjusted statistics"""
    try:
        players_df = data['players'].copy()
        weeks_df = data['weeks'].copy()
        results_df = data['results'].copy()
        
        if players_df.empty or weeks_df.empty:
            return pd.DataFrame()
        
        # Convert data types
        if not weeks_df.empty:
            weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
            weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
            weeks_df['id'] = pd.to_numeric(weeks_df['id'], errors='coerce')
            weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        if not results_df.empty:
            results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
            results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
            results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
        
        # Filter weeks
        weeks_df = weeks_df[weeks_df['season_year'] == season_year]
        if week_number is not None:
            weeks_df = weeks_df[weeks_df['week_number'] == week_number]
        
        if weeks_df.empty:
            return pd.DataFrame()
        
        week_ids = weeks_df['id'].tolist()
        
        # Calculate standings for each player
        standings = []
        for _, player in players_df.iterrows():
            player_id = int(player['id'])
            player_results = results_df[
                (results_df['player_id'] == player_id) & 
                (results_df['week_id'].isin(week_ids))
            ]
            
            # Absolute statistics (including omissions as zeros)
            total_weeks_absolute = len(weeks_df)
            total_correct_absolute = 0
            total_possible_absolute = 0
            
            # Adjusted statistics (excluding omissions)
            participated_results = player_results[player_results['status'] != 'omitted']
            total_weeks_adjusted = len(participated_results)
            total_correct_adjusted = 0
            total_possible_adjusted = 0
            
            # Calculate totals
            for _, week in weeks_df.iterrows():
                week_id = int(week['id'])
                week_result = player_results[player_results['week_id'] == week_id]
                
                if not week_result.empty:
                    result = week_result.iloc[0]
                    if result['status'] == 'omitted':
                        # For absolute stats, count as 0 correct out of total_games
                        total_possible_absolute += int(week['total_games'])
                    else:
                        # Count for both absolute and adjusted
                        correct = int(result['correct_guesses']) if pd.notna(result['correct_guesses']) else 0
                        total_correct_absolute += correct
                        total_possible_absolute += int(week['total_games'])
                        total_correct_adjusted += correct
                        total_possible_adjusted += int(week['total_games'])
                else:
                    # No result recorded - treat as 0 for absolute, skip for adjusted
                    total_possible_absolute += int(week['total_games'])
            
            # Calculate percentages
            accuracy_absolute = (total_correct_absolute / total_possible_absolute * 100) if total_possible_absolute > 0 else 0
            accuracy_adjusted = (total_correct_adjusted / total_possible_adjusted * 100) if total_possible_adjusted > 0 else 0
            
            standings.append({
                'player_name': player['name'],
                
                # Absolute statistics
                'weeks_absolute': total_weeks_absolute,
                'correct_absolute': total_correct_absolute,
                'possible_absolute': total_possible_absolute,
                'accuracy_absolute': round(accuracy_absolute, 1),
                
                # Adjusted statistics  
                'weeks_adjusted': total_weeks_adjusted,
                'correct_adjusted': total_correct_adjusted,
                'possible_adjusted': total_possible_adjusted,
                'accuracy_adjusted': round(accuracy_adjusted, 1),
                
                # Status info
                'omitted_weeks': total_weeks_absolute - total_weeks_adjusted
            })
        
        standings_df = pd.DataFrame(standings)
        
        # Sort by adjusted accuracy (primary), then absolute accuracy
        if not standings_df.empty:
            standings_df = standings_df.sort_values(['accuracy_adjusted', 'accuracy_absolute'], ascending=False)
        
        return standings_df
        
    except Exception as e:
        st.error(f"Error calculating standings: {e}")
        return pd.DataFrame()

def get_player_history(data, player_name, season_year):
    """Get a player's history for a season"""
    try:
        players_df = data['players'].copy()
        weeks_df = data['weeks'].copy()
        results_df = data['results'].copy()
        
        if players_df.empty or weeks_df.empty:
            return pd.DataFrame()
        
        # Convert data types
        if not weeks_df.empty:
            weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
            weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
            weeks_df['id'] = pd.to_numeric(weeks_df['id'], errors='coerce')
            weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        if not results_df.empty:
            results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
            results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
            results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
        
        # Get player ID
        player_row = players_df[players_df['name'] == player_name]
        if player_row.empty:
            return pd.DataFrame()
        
        player_id = int(player_row.iloc[0]['id'])
        
        # Filter weeks for season
        weeks_df = weeks_df[weeks_df['season_year'] == season_year]
        
        # Get player's results
        player_results = results_df[results_df['player_id'] == player_id]
        
        # Merge with weeks data
        history = weeks_df.merge(
            player_results, 
            left_on='id', 
            right_on='week_id', 
            how='left',
            suffixes=('_week', '_result')
        )
        
        if history.empty:
            return pd.DataFrame()
        
        # Calculate accuracy for each week
        history['accuracy'] = history.apply(
            lambda row: (row['correct_guesses'] / row['total_games'] * 100) 
            if pd.notna(row['correct_guesses']) and row['status'] != 'omitted' and row['total_games'] > 0
            else None, 
            axis=1
        )
        
        # Clean up status
        history['status'] = history['status'].fillna('no_result')
        history['correct_guesses'] = history['correct_guesses'].fillna(0)
        
        return history[['week_number', 'week_date', 'total_games', 'correct_guesses', 'accuracy', 'status']].sort_values('week_number')
        
    except Exception as e:
        st.error(f"Error getting player history: {e}")
        return pd.DataFrame()

def calculate_improvement_trends(data, season_year, min_weeks=3):
    """Calculate improvement trends for all players"""
    try:
        players_df = data['players'].copy()
        weeks_df = data['weeks'].copy()
        results_df = data['results'].copy()
        
        if players_df.empty or weeks_df.empty or results_df.empty:
            return pd.DataFrame()
        
        # Convert data types
        weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
        weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
        weeks_df['id'] = pd.to_numeric(weeks_df['id'], errors='coerce')
        weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
        results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
        results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
        
        # Filter for season
        season_weeks = weeks_df[weeks_df['season_year'] == season_year]
        if season_weeks.empty:
            return pd.DataFrame()
        
        trends = []
        
        for _, player in players_df.iterrows():
            player_id = int(player['id'])
            player_name = player['name']
            
            # Get player's participated results for the season
            player_results = results_df[
                (results_df['player_id'] == player_id) & 
                (results_df['week_id'].isin(season_weeks['id'])) &
                (results_df['status'] == 'participated')
            ]
            
            if len(player_results) < min_weeks:
                continue
            
            # Merge with weeks to get week numbers and calculate accuracy
            player_weeks = player_results.merge(
                season_weeks[['id', 'week_number', 'total_games']], 
                left_on='week_id', 
                right_on='id'
            ).sort_values('week_number')
            
            # Calculate accuracy for each week
            player_weeks['accuracy'] = (player_weeks['correct_guesses'] / player_weeks['total_games']) * 100
            
            if len(player_weeks) < min_weeks:
                continue
            
            # Calculate trend statistics
            weeks = player_weeks['week_number'].values
            accuracies = player_weeks['accuracy'].values
            
            # Linear regression to find trend
            slope, intercept, r_value, p_value, std_err = linear_regression(weeks, accuracies)
            
            # Calculate performance metrics
            early_avg = player_weeks.head(min_weeks)['accuracy'].mean()
            recent_avg = player_weeks.tail(min_weeks)['accuracy'].mean()
            overall_avg = player_weeks['accuracy'].mean()
            
            # Calculate volatility (standard deviation)
            volatility = player_weeks['accuracy'].std()
            
            # Determine trend category
            if abs(slope) < 0.5:
                trend_category = "Stable"
            elif slope > 0.5:
                trend_category = "Improving"
            else:
                trend_category = "Declining"
            
            trends.append({
                'player_name': player_name,
                'weeks_played': len(player_weeks),
                'overall_accuracy': round(overall_avg, 1),
                'early_avg': round(early_avg, 1),
                'recent_avg': round(recent_avg, 1),
                'improvement': round(recent_avg - early_avg, 1),
                'trend_slope': round(slope, 2),
                'trend_r_squared': round(r_value**2, 3),
                'volatility': round(volatility, 1),
                'trend_category': trend_category,
                'trend_significance': 'Significant' if p_value < 0.05 else 'Not Significant'
            })
        
        return pd.DataFrame(trends)
        
    except Exception as e:
        st.error(f"Error calculating improvement trends: {e}")
        return pd.DataFrame()

def get_rolling_averages(data, player_name, season_year, window=3):
    """Calculate rolling averages for a player"""
    try:
        history = get_player_history(data, player_name, season_year)
        if history.empty:
            return pd.DataFrame()
        
        # Filter participated weeks only
        participated = history[history['status'] == 'participated'].copy()
        if len(participated) < window:
            return pd.DataFrame()
        
        # Calculate rolling averages
        participated['rolling_avg'] = participated['accuracy'].rolling(window=window, min_periods=1).mean()
        participated['rolling_std'] = participated['accuracy'].rolling(window=window, min_periods=1).std()
        
        return participated
        
    except Exception as e:
        st.error(f"Error calculating rolling averages: {e}")
        return pd.DataFrame()

# Initialize connection
spreadsheet = init_connection()

if spreadsheet is None:
    st.error("Could not connect to Google Sheets. Please check your configuration.")
    st.stop()

# Initialize sheets
if 'sheets_initialized' not in st.session_state:
    with st.spinner("Setting up Google Sheets..."):
        if ensure_sheets_exist(spreadsheet):
            st.session_state.sheets_initialized = True
        else:
            st.error("Could not set up Google Sheets. Please check your permissions.")
            st.stop()

# Load all data once
if 'data_loaded_time' not in st.session_state or (datetime.now() - st.session_state.data_loaded_time).seconds > 300:
    with st.spinner("Loading data..."):
        st.session_state.data = get_all_data(st.secrets["connections"]["gsheets"]["spreadsheet"])
        st.session_state.data_loaded_time = datetime.now()

data = st.session_state.data

st.title("🏆 Pick'ems 2026")
st.markdown("Game Outcome Prediction Accuracy Metrics")

# Sidebar for navigation
st.sidebar.title("Navigation")
page = st.sidebar.selectbox("Choose a page:", [
    "Enter Results", 
    "Weekly Standings", 
    "Season Standings",
    "Player History",
    "Improvement Trends",  # New page added
    "Edit Players",
    "Edit Results", 
    "Manage Players & Weeks"
])

# Get current season year
current_season = st.sidebar.selectbox("Season Year:", [2024, 2025, 2026], index=1)

# Add refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.session_state.data = get_all_data(st.secrets["connections"]["gsheets"]["spreadsheet"])
    st.session_state.data_loaded_time = datetime.now()
    st.rerun()

if page == "Enter Results":
    st.header("Enter Weekly Results")
    
    weeks_df = data['weeks'].copy()
    if not weeks_df.empty:
        # Convert data types
        weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
        weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
        weeks_df['id'] = pd.to_numeric(weeks_df['id'], errors='coerce')
        weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        # Filter for current season
        season_weeks = weeks_df[weeks_df['season_year'] == current_season]
        
        if not season_weeks.empty:
            # Show week selector
            week_options = []
            for _, week in season_weeks.iterrows():
                week_options.append({
                    'label': f"Week {int(week['week_number'])} ({int(week['total_games'])} games) - {week['week_date']}",
                    'value': int(week['id']),
                    'week_number': int(week['week_number']),
                    'total_games': int(week['total_games'])
                })
            
            selected_week_option = st.selectbox(
                "Select Week:", 
                week_options,
                format_func=lambda x: x['label']
            )
            
            if selected_week_option:
                selected_week_id = selected_week_option['value']
                selected_week_number = selected_week_option['week_number']
                total_games = selected_week_option['total_games']
                
                st.subheader(f"Week {selected_week_number} Results ({total_games} total games)")
                
                # Get players and existing results
                players_df = data['players'].copy()
                results_df = data['results'].copy()
                
                if not players_df.empty:
                    # Convert data types for results
                    if not results_df.empty:
                        results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
                        results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
                        results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
                    
                    # Choose input method
                    input_method = st.radio(
                        "Choose input method:",
                        ["Individual Entry", "Bulk Text Entry"],
                        horizontal=True
                    )
                    
                    if input_method == "Individual Entry":
                        # Original individual entry method
                        results_to_save = {}
                        
                        st.write("Enter results for each player:")
                        
                        for _, player in players_df.iterrows():
                            player_id = int(player['id'])
                            
                            with st.container():
                                col1, col2, col3 = st.columns([2, 2, 1])
                                
                                with col1:
                                    st.write(f"**{player['name']}**")
                                
                                # Get existing result if any
                                existing_result = None
                                if not results_df.empty:
                                    existing_mask = (
                                        (results_df['player_id'] == player_id) & 
                                        (results_df['week_id'] == selected_week_id)
                                    )
                                    if existing_mask.any():
                                        existing_result = results_df[existing_mask].iloc[0]
                                
                                with col2:
                                    # Status selector
                                    status_options = ['participated', 'omitted']
                                    default_status = 0
                                    if existing_result is not None and existing_result['status'] == 'omitted':
                                        default_status = 1
                                    
                                    status = st.selectbox(
                                        "Status:",
                                        status_options,
                                        key=f"status_{player_id}",
                                        index=default_status,
                                        label_visibility="collapsed"
                                    )
                                
                                with col3:
                                    if status == 'participated':
                                        # Correct guesses input
                                        default_correct = 0
                                        if existing_result is not None and pd.notna(existing_result['correct_guesses']):
                                            default_correct = int(existing_result['correct_guesses'])
                                        
                                        correct_guesses = st.number_input(
                                            f"Correct guesses (0-{total_games}):",
                                            min_value=0,
                                            max_value=total_games,
                                            value=default_correct,
                                            key=f"correct_{player_id}",
                                            label_visibility="collapsed"
                                        )
                                        results_to_save[player_id] = (correct_guesses, status)
                                    else:
                                        st.write("—")
                                        results_to_save[player_id] = (0, status)
                                
                                st.divider()
                        
                        # Save button for individual entry
                        if st.button("Save All Results", type="primary"):
                            # Process individual entry results
                            batch_data = []
                            results_df_for_updates = data['results'].copy()
                            
                            if not results_df_for_updates.empty:
                                results_df_for_updates['player_id'] = pd.to_numeric(results_df_for_updates['player_id'], errors='coerce')
                                results_df_for_updates['week_id'] = pd.to_numeric(results_df_for_updates['week_id'], errors='coerce')
                            
                            next_id = get_next_id(data['results'])
                            
                            for player_id, (correct_guesses, status) in results_to_save.items():
                                # Check if result already exists
                                existing = False
                                if not results_df_for_updates.empty:
                                    existing_mask = (
                                        (results_df_for_updates['player_id'] == player_id) & 
                                        (results_df_for_updates['week_id'] == selected_week_id)
                                    )
                                    if existing_mask.any():
                                        existing = True
                                
                                if not existing:
                                    # Add new result
                                    result_data = {
                                        'id': next_id,
                                        'player_id': player_id,
                                        'week_id': selected_week_id,
                                        'correct_guesses': correct_guesses if status != 'omitted' else '',
                                        'status': status,
                                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    batch_data.append(result_data)
                                    next_id += 1
                            
                            # Batch save all new results
                            if batch_data:
                                if batch_update_sheet(spreadsheet, 'results', batch_data, 'append'):
                                    st.success(f"Saved {len(batch_data)} new results successfully!")
                                    # Clear cache to reload data
                                    st.cache_data.clear()
                                    time.sleep(1)  # Small delay to ensure data is saved
                                    st.rerun()
                                else:
                                    st.error("Error saving results. Please try again.")
                            else:
                                st.info("No new results to save. All players already have results for this week.")
                    
                    else:  # Bulk Text Entry
                        st.write("**Bulk Text Entry**")
                        st.write("Enter results in the format: `PlayerName: CorrectGuesses` or `PlayerName: omitted`")
                        st.write("Examples:")
                        st.code("""John Smith: 7
Jane Doe: omitted
Mike Johnson: 5
Sarah Wilson: 9""")
                        
                        # Get existing results for display
                        existing_results_text = ""
                        if not results_df.empty:
                            for _, player in players_df.iterrows():
                                player_id = int(player['id'])
                                existing_mask = (
                                    (results_df['player_id'] == player_id) & 
                                    (results_df['week_id'] == selected_week_id)
                                )
                                if existing_mask.any():
                                    result = results_df[existing_mask].iloc[0]
                                    if result['status'] == 'omitted':
                                        existing_results_text += f"{player['name']}: omitted\n"
                                    else:
                                        correct = int(result['correct_guesses']) if pd.notna(result['correct_guesses']) else 0
                                        existing_results_text += f"{player['name']}: {correct}\n"
                        
                        bulk_results_text = st.text_area(
                            "Enter results (one per line):",
                            height=200,
                            value=existing_results_text,
                            placeholder="PlayerName: CorrectGuesses\nPlayerName: omitted"
                        )
                        
                        # Parse and preview
                        if bulk_results_text.strip():
                            parsed_results = {}
                            parse_errors = []
                            
                            # Create name to ID mapping
                            name_to_id = {player['name']: int(player['id']) for _, player in players_df.iterrows()}
                            
                            for line_num, line in enumerate(bulk_results_text.strip().split('\n'), 1):
                                line = line.strip()
                                if not line:
                                    continue
                                
                                if ':' not in line:
                                    parse_errors.append(f"Line {line_num}: Missing ':' separator")
                                    continue
                                
                                parts = line.split(':', 1)
                                player_name = parts[0].strip()
                                result_str = parts[1].strip().lower()
                                
                                if player_name not in name_to_id:
                                    parse_errors.append(f"Line {line_num}: Player '{player_name}' not found")
                                    continue
                                
                                if result_str == 'omitted':
                                    parsed_results[name_to_id[player_name]] = (0, 'omitted')
                                else:
                                    try:
                                        correct_guesses = int(result_str)
                                        if correct_guesses < 0 or correct_guesses > total_games:
                                            parse_errors.append(f"Line {line_num}: Score {correct_guesses} out of range (0-{total_games})")
                                            continue
                                        parsed_results[name_to_id[player_name]] = (correct_guesses, 'participated')
                                    except ValueError:
                                        parse_errors.append(f"Line {line_num}: Invalid number '{result_str}'")
                            
                            # Show preview
                            if parsed_results:
                                st.write("**Preview:**")
                                preview_data = []
                                for player_id, (correct, status) in parsed_results.items():
                                    player_name = players_df[players_df['id'] == player_id]['name'].iloc[0]
                                    preview_data.append({
                                        'Player': player_name,
                                        'Result': f"{correct}/{total_games}" if status == 'participated' else 'Omitted',
                                        'Status': status.title()
                                    })
                                
                                preview_df = pd.DataFrame(preview_data)
                                st.dataframe(preview_df, use_container_width=True, hide_index=True)
                            
                            # Show errors
                            if parse_errors:
                                st.error("**Parse Errors:**")
                                for error in parse_errors:
                                    st.write(f"❌ {error}")
                            
                            # Save button for bulk entry
                            if parsed_results and not parse_errors:
                                if st.button("Save Bulk Results", type="primary"):
                                    # Process bulk entry results
                                    batch_data = []
                                    results_df_for_updates = data['results'].copy()
                                    
                                    if not results_df_for_updates.empty:
                                        results_df_for_updates['player_id'] = pd.to_numeric(results_df_for_updates['player_id'], errors='coerce')
                                        results_df_for_updates['week_id'] = pd.to_numeric(results_df_for_updates['week_id'], errors='coerce')
                                    
                                    next_id = get_next_id(data['results'])
                                    
                                    for player_id, (correct_guesses, status) in parsed_results.items():
                                        # Check if result already exists
                                        existing = False
                                        if not results_df_for_updates.empty:
                                            existing_mask = (
                                                (results_df_for_updates['player_id'] == player_id) & 
                                                (results_df_for_updates['week_id'] == selected_week_id)
                                            )
                                            if existing_mask.any():
                                                existing = True
                                        
                                        if not existing:
                                            # Add new result
                                            result_data = {
                                                'id': next_id,
                                                'player_id': player_id,
                                                'week_id': selected_week_id,
                                                'correct_guesses': correct_guesses if status != 'omitted' else '',
                                                'status': status,
                                                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                            }
                                            batch_data.append(result_data)
                                            next_id += 1
                                    
                                    # Batch save all new results
                                    if batch_data:
                                        if batch_update_sheet(spreadsheet, 'results', batch_data, 'append'):
                                            st.success(f"Saved {len(batch_data)} results successfully!")
                                            # Clear cache to reload data
                                            st.cache_data.clear()
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error("Error saving results. Please try again.")
                                    else:
                                        st.info("No new results to save. All specified players already have results for this week.")
                            
                            elif not parsed_results and not parse_errors:
                                st.info("Enter some results above to see the preview.")
                
                else:
                    st.warning("No players found. Please add players in the 'Manage Players & Weeks' section.")
        else:
            st.info("No weeks found for the current season. Please add weeks in the 'Manage Players & Weeks' section.")
    else:
        st.info("No weeks found. Please add weeks in the 'Manage Players & Weeks' section.")

elif page == "Weekly Standings":
    st.header("Weekly Standings")
    
    weeks_df = data['weeks'].copy()
    if not weeks_df.empty:
        # Convert data types
        weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
        weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
        
        # Filter for current season
        season_weeks = weeks_df[weeks_df['season_year'] == current_season]
        
        if not season_weeks.empty:
            # Get weeks that have results
            results_df = data['results'].copy()
            weeks_with_results = []
            
            if not results_df.empty:
                results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
                
                for _, week in season_weeks.iterrows():
                    week_id = int(week['id'])
                    week_results = results_df[results_df['week_id'] == week_id]
                    if not week_results.empty:
                        weeks_with_results.append(int(week['week_number']))
            
            if weeks_with_results:
                selected_week = st.selectbox("Select Week:", sorted(weeks_with_results))
                
                standings_df = calculate_standings(data, current_season, week_number=selected_week)
                
                if not standings_df.empty:
                    st.subheader(f"Week {selected_week} Standings")
                    
                    # Show both absolute and adjusted statistics
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**📊 Absolute Statistics** (including omissions as 0)")
                        abs_display = standings_df.copy()
                        abs_display['rank'] = range(1, len(abs_display) + 1)
                        abs_display = abs_display[['rank', 'player_name', 'correct_absolute', 'possible_absolute', 'accuracy_absolute']]
                        abs_display.columns = ['Rank', 'Player', 'Correct', 'Possible', 'Accuracy %']
                        st.dataframe(abs_display, use_container_width=True, hide_index=True)
                    
                    with col2:
                        st.write("**🎯 Adjusted Statistics** (excluding omissions)")
                        adj_display = standings_df.copy()
                        adj_display['rank'] = range(1, len(adj_display) + 1)
                        adj_display = adj_display[['rank', 'player_name', 'correct_adjusted', 'possible_adjusted', 'accuracy_adjusted']]
                        adj_display.columns = ['Rank', 'Player', 'Correct', 'Possible', 'Accuracy %']
                        st.dataframe(adj_display, use_container_width=True, hide_index=True)
                    
                    # Visualization
                    fig = px.bar(
                        standings_df.head(10), 
                        x='player_name', 
                        y=['accuracy_absolute', 'accuracy_adjusted'],
                        title=f'Week {selected_week} - Accuracy Comparison',
                        barmode='group',
                        color_discrete_map={'accuracy_absolute': '#ff7f7f', 'accuracy_adjusted': '#7fbf7f'}
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    fig.update_traces(name='Absolute', selector=dict(name='accuracy_absolute'))
                    fig.update_traces(name='Adjusted', selector=dict(name='accuracy_adjusted'))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info(f"No results found for week {selected_week}")
            else:
                st.info("No weeks with results found for the current season.")
        else:
            st.info("No weeks found for the current season.")
    else:
        st.info("No weeks found.")

elif page == "Season Standings":
    st.header("Season Standings")
    
    standings_df = calculate_standings(data, current_season)
    
    if not standings_df.empty:
        st.subheader(f"Season {current_season} Overall Standings")
        
        # Show both statistics side by side
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📊 Absolute Statistics** (including omissions as 0)")
            abs_display = standings_df.copy()
            abs_display['rank'] = range(1, len(abs_display) + 1)
            abs_display = abs_display[['rank', 'player_name', 'weeks_absolute', 'correct_absolute', 'possible_absolute', 'accuracy_absolute']]
            abs_display.columns = ['Rank', 'Player', 'Weeks', 'Correct', 'Possible', 'Accuracy %']
            st.dataframe(abs_display, use_container_width=True, hide_index=True)
        
        with col2:
            st.write("**🎯 Adjusted Statistics** (excluding omissions)")
            adj_display = standings_df.copy()
            adj_display['rank'] = range(1, len(adj_display) + 1)
            adj_display = adj_display[['rank', 'player_name', 'weeks_adjusted', 'correct_adjusted', 'possible_adjusted', 'accuracy_adjusted', 'omitted_weeks']]
            adj_display.columns = ['Rank', 'Player', 'Weeks', 'Correct', 'Possible', 'Accuracy %', 'Omitted']
            st.dataframe(adj_display, use_container_width=True, hide_index=True)
        
        # Visualizations
        col1, col2 = st.columns(2)
        
        with col1:
            fig1 = px.bar(
                standings_df.head(10), 
                x='player_name', 
                y='accuracy_absolute',
                title='Season Absolute Accuracy',
                color='accuracy_absolute',
                color_continuous_scale='Blues'
            )
            fig1.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            fig2 = px.bar(
                standings_df.head(10), 
                x='player_name', 
                y='accuracy_adjusted',
                title='Season Adjusted Accuracy',
                color='accuracy_adjusted',
                color_continuous_scale='Greens'
            )
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, use_container_width=True)
        
        # Comparison scatter plot
        fig3 = px.scatter(
            standings_df, 
            x='accuracy_absolute', 
            y='accuracy_adjusted',
            size='weeks_adjusted',
            hover_name='player_name',
            title='Absolute vs Adjusted Accuracy',
            color='omitted_weeks',
            color_continuous_scale='Reds'
        )
        fig3.add_shape(
            type="line",
            x0=0, y0=0, x1=100, y1=100,
            line=dict(color="gray", width=2, dash="dash")
        )
        fig3.update_layout(
            xaxis_title="Absolute Accuracy (%)",
            yaxis_title="Adjusted Accuracy (%)"
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No season data available yet.")

elif page == "Player History":
    st.header("Player History")
    
    players_df = data['players'].copy()
    if not players_df.empty:
        selected_player = st.selectbox("Select Player:", players_df['name'].tolist(), key="player_history")
        
        history_df = get_player_history(data, selected_player, current_season)
        
        if not history_df.empty:
            st.subheader(f"{selected_player}'s Season {current_season} History")
            
            # Calculate summary statistics
            participated_weeks = history_df[history_df['status'] == 'participated']
            
            if not participated_weeks.empty:
                total_correct = participated_weeks['correct_guesses'].sum()
                total_possible = participated_weeks['total_games'].sum()
                overall_accuracy = (total_correct / total_possible * 100) if total_possible > 0 else 0
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Weeks Participated", len(participated_weeks))
                with col2:
                    st.metric("Total Correct", int(total_correct))
                with col3:
                    st.metric("Total Possible", int(total_possible))
                with col4:
                    st.metric("Overall Accuracy", f"{overall_accuracy:.1f}%")
                
                # Weekly performance chart
                chart_data = participated_weeks[participated_weeks['accuracy'].notna()]
                if not chart_data.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=chart_data['week_number'],
                        y=chart_data['accuracy'],
                        mode='lines+markers',
                        name='Weekly Accuracy %',
                        line=dict(color='blue', width=3),
                        marker=dict(size=8)
                    ))
                    
                    # Add horizontal line for overall average
                    fig.add_hline(
                        y=overall_accuracy, 
                        line_dash="dash", 
                        line_color="red",
                        annotation_text=f"Overall Average: {overall_accuracy:.1f}%"
                    )
                    
                    fig.update_layout(
                        title=f"{selected_player}'s Weekly Performance",
                        xaxis_title="Week Number",
                        yaxis_title="Accuracy (%)",
                        yaxis=dict(range=[0, 100])
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            # Show detailed history
            st.subheader("Detailed Weekly History")
            history_display = history_df.copy()
            
            # Format the display
            history_display['status_display'] = history_display['status'].map({
                'participated': '✅ Participated',
                'omitted': '⏸️ Omitted',
                'no_result': '❓ No Result'
            })
            
            history_display['accuracy_display'] = history_display['accuracy'].apply(
                lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
            )
            
            history_display['correct_display'] = history_display.apply(
                lambda row: f"{int(row['correct_guesses'])}/{int(row['total_games'])}" 
                if row['status'] == 'participated' else "—", 
                axis=1
            )
            
            display_df = history_display[['week_number', 'week_date', 'correct_display', 'accuracy_display', 'status_display']]
            display_df.columns = ['Week', 'Date', 'Correct/Total', 'Accuracy', 'Status']
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No history found for {selected_player} in season {current_season}.")
    else:
        st.info("No players found. Please add players first.")

elif page == "Improvement Trends":
    st.header("📈 Improvement Trends & Performance Analysis")
    
    # Calculate improvement trends
    trends_df = calculate_improvement_trends(data, current_season, min_weeks=3)
    
    if not trends_df.empty:
        st.subheader(f"Season {current_season} Performance Trends")
        
        # Overview metrics
        col1, col2, col3, col4 = st.columns(4)
        
        improving_players = len(trends_df[trends_df['trend_category'] == 'Improving'])
        stable_players = len(trends_df[trends_df['trend_category'] == 'Stable'])
        declining_players = len(trends_df[trends_df['trend_category'] == 'Declining'])
        avg_improvement = trends_df['improvement'].mean()
        
        with col1:
            st.metric("📈 Improving Players", improving_players)
        with col2:
            st.metric("📊 Stable Players", stable_players)
        with col3:
            st.metric("📉 Declining Players", declining_players)
        with col4:
            st.metric("🎯 Avg Improvement", f"{avg_improvement:+.1f}%")
        
        # Trends summary table
        st.subheader("Player Trends Summary")
        
        # Sort by improvement
        trends_display = trends_df.sort_values('improvement', ascending=False).copy()
        
        # Add trend indicators
        trends_display['trend_indicator'] = trends_display['trend_category'].map({
            'Improving': '📈',
            'Stable': '📊', 
            'Declining': '📉'
        })
        
        # Format for display
        display_cols = [
            'trend_indicator', 'player_name', 'weeks_played', 'overall_accuracy',
            'early_avg', 'recent_avg', 'improvement', 'volatility', 'trend_significance'
        ]
        trends_display_formatted = trends_display[display_cols].copy()
        trends_display_formatted.columns = [
            '📊', 'Player', 'Weeks', 'Overall %', 'Early %', 'Recent %', 'Change', 'Volatility', 'Significance'
        ]
        
        st.dataframe(trends_display_formatted, use_container_width=True, hide_index=True)
        
        # Visualizations
        col1, col2 = st.columns(2)
        
        with col1:
            # Improvement scatter plot
            fig1 = px.scatter(
                trends_df,
                x='early_avg',
                y='recent_avg',
                size='weeks_played',
                color='trend_category',
                hover_name='player_name',
                title='Early vs Recent Performance',
                color_discrete_map={
                    'Improving': '#2ecc71',
                    'Stable': '#f39c12', 
                    'Declining': '#e74c3c'
                }
            )
            
            # Add diagonal line (no change)
            fig1.add_shape(
                type="line",
                x0=0, y0=0, x1=100, y1=100,
                line=dict(color="gray", width=2, dash="dash")
            )
            
            fig1.update_layout(
                xaxis_title="Early Season Average (%)",
                yaxis_title="Recent Performance Average (%)"
            )
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # Trend slope distribution
            fig2 = px.histogram(
                trends_df,
                x='trend_slope',
                color='trend_category',
                title='Distribution of Trend Slopes',
                color_discrete_map={
                    'Improving': '#2ecc71',
                    'Stable': '#f39c12',
                    'Declining': '#e74c3c'
                }
            )
            fig2.update_layout(xaxis_title="Trend Slope (% per week)")
            st.plotly_chart(fig2, use_container_width=True)
        
        # Individual player trend analysis
        st.subheader("Individual Player Trend Analysis")
        
        # Player selector for detailed view
        selected_trend_player = st.selectbox(
            "Select Player for Detailed Analysis:",
            trends_df['player_name'].tolist(),
            key="trend_player_selector"
        )
        
        if selected_trend_player:
            # Get rolling averages
            rolling_data = get_rolling_averages(data, selected_trend_player, current_season, window=3)
            
            if not rolling_data.empty:
                # Player trend details
                player_trend = trends_df[trends_df['player_name'] == selected_trend_player].iloc[0]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Trend Category", 
                        player_trend['trend_category'],
                        delta=f"{player_trend['improvement']:+.1f}% change"
                    )
                with col2:
                    st.metric(
                        "Trend Slope", 
                        f"{player_trend['trend_slope']:+.2f}%/week",
                        delta=f"R² = {player_trend['trend_r_squared']:.3f}"
                    )
                with col3:
                    st.metric(
                        "Performance Volatility",
                        f"{player_trend['volatility']:.1f}%",
                        delta=player_trend['trend_significance']
                    )
                
                # Detailed performance chart with rolling averages
                fig = make_subplots(
                    rows=2, cols=1,
                    subplot_titles=(
                        f"{selected_trend_player}'s Weekly Performance with Trend",
                        "3-Week Rolling Average"
                    ),
                    vertical_spacing=0.12,
                    row_heights=[0.7, 0.3]
                )
                
                # Main performance chart
                fig.add_trace(
                    go.Scatter(
                        x=rolling_data['week_number'],
                        y=rolling_data['accuracy'],
                        mode='lines+markers',
                        name='Weekly Accuracy',
                        line=dict(color='lightblue', width=2),
                        marker=dict(size=8)
                    ),
                    row=1, col=1
                )
                
                # Trend line
                x_trend = rolling_data['week_number']
                y_trend = player_trend['trend_slope'] * x_trend + (player_trend['overall_accuracy'] - player_trend['trend_slope'] * x_trend.mean())
                
                fig.add_trace(
                    go.Scatter(
                        x=x_trend,
                        y=y_trend,
                        mode='lines',
                        name='Trend Line',
                        line=dict(color='red', width=3, dash='dash')
                    ),
                    row=1, col=1
                )
                
                # Rolling average
                fig.add_trace(
                    go.Scatter(
                        x=rolling_data['week_number'],
                        y=rolling_data['rolling_avg'],
                        mode='lines',
                        name='3-Week Rolling Avg',
                        line=dict(color='orange', width=3),
                        fill='tonexty',
                        fillcolor='rgba(255,165,0,0.1)'
                    ),
                    row=2, col=1
                )
                
                # Confidence bands for rolling average
                upper_band = rolling_data['rolling_avg'] + rolling_data['rolling_std']
                lower_band = rolling_data['rolling_avg'] - rolling_data['rolling_std']
                
                fig.add_trace(
                    go.Scatter(
                        x=rolling_data['week_number'],
                        y=upper_band,
                        mode='lines',
                        line=dict(width=0),
                        showlegend=False,
                        hoverinfo='skip'
                    ),
                    row=2, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=rolling_data['week_number'],
                        y=lower_band,
                        mode='lines',
                        line=dict(width=0),
                        fill='tonexty',
                        fillcolor='rgba(255,165,0,0.2)',
                        name='±1 Std Dev',
                        hoverinfo='skip'
                    ),
                    row=2, col=1
                )
                
                fig.update_layout(
                    height=600,
                    title_text=f"{selected_trend_player} - Performance Trend Analysis",
                    showlegend=True
                )
                
                fig.update_xaxes(title_text="Week Number", row=2, col=1)
                fig.update_yaxes(title_text="Accuracy (%)", row=1, col=1)
                fig.update_yaxes(title_text="Accuracy (%)", row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Performance insights
                st.subheader("Performance Insights")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**🎯 Key Statistics:**")
                    st.write(f"• Best Week: {rolling_data['accuracy'].max():.1f}% (Week {rolling_data.loc[rolling_data['accuracy'].idxmax(), 'week_number']})")
                    st.write(f"• Worst Week: {rolling_data['accuracy'].min():.1f}% (Week {rolling_data.loc[rolling_data['accuracy'].idxmin(), 'week_number']})")
                    st.write(f"• Performance Range: {rolling_data['accuracy'].max() - rolling_data['accuracy'].min():.1f}%")
                    st.write(f"• Consistency Score: {100 - player_trend['volatility']:.1f}/100")
                
                with col2:
                    st.write("**📈 Trend Analysis:**")
                    
                    if player_trend['trend_category'] == 'Improving':
                        st.write("🟢 **Positive Trend:** Performance is improving over time")
                        st.write(f"• Gaining {player_trend['trend_slope']:.2f}% per week on average")
                    elif player_trend['trend_category'] == 'Declining':
                        st.write("🔴 **Negative Trend:** Performance is declining over time")
                        st.write(f"• Losing {abs(player_trend['trend_slope']):.2f}% per week on average")
                    else:
                        st.write("🟡 **Stable Performance:** Consistent performance level")
                        st.write(f"• Minimal change ({player_trend['trend_slope']:+.2f}% per week)")
                    
                    if player_trend['trend_significance'] == 'Significant':
                        st.write("• Trend is statistically significant")
                    else:
                        st.write("• Trend may be due to random variation")
        
        # League-wide trend analysis
        st.subheader("League-Wide Trend Patterns")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Volatility vs Performance
            fig_vol = px.scatter(
                trends_df,
                x='overall_accuracy',
                y='volatility',
                size='weeks_played',
                color='trend_category',
                hover_name='player_name',
                title='Performance vs Consistency',
                color_discrete_map={
                    'Improving': '#2ecc71',
                    'Stable': '#f39c12',
                    'Declining': '#e74c3c'
                }
            )
            fig_vol.update_layout(
                xaxis_title="Overall Accuracy (%)",
                yaxis_title="Performance Volatility (%)"
            )
            st.plotly_chart(fig_vol, use_container_width=True)
        
        with col2:
            # Improvement distribution
            fig_imp = px.box(
                trends_df,
                x='trend_category',
                y='improvement',
                color='trend_category',
                title='Improvement Distribution by Category',
                color_discrete_map={
                    'Improving': '#2ecc71',
                    'Stable': '#f39c12',
                    'Declining': '#e74c3c'
                }
            )
            fig_imp.update_layout(
                xaxis_title="Trend Category",
                yaxis_title="Performance Change (%)"
            )
            st.plotly_chart(fig_imp, use_container_width=True)
        
        # Multi-player comparison
        st.subheader("Multi-Player Performance Comparison")
        
        # Allow selection of multiple players for comparison
        comparison_players = st.multiselect(
            "Select players to compare:",
            trends_df['player_name'].tolist(),
            default=trends_df.head(3)['player_name'].tolist(),
            key="multi_player_comparison"
        )
        
        if comparison_players:
            # Create comparison chart
            fig_comp = go.Figure()
            
            colors = px.colors.qualitative.Set1
            
            for i, player in enumerate(comparison_players):
                player_history = get_player_history(data, player, current_season)
                participated = player_history[player_history['status'] == 'participated']
                
                if not participated.empty:
                    fig_comp.add_trace(
                        go.Scatter(
                            x=participated['week_number'],
                            y=participated['accuracy'],
                            mode='lines+markers',
                            name=player,
                            line=dict(color=colors[i % len(colors)], width=3),
                            marker=dict(size=6)
                        )
                    )
            
            fig_comp.update_layout(
                title="Multi-Player Performance Comparison",
                xaxis_title="Week Number",
                yaxis_title="Accuracy (%)",
                hovermode='x unified'
            )
            
            st.plotly_chart(fig_comp, use_container_width=True)
            
            # Comparison statistics table
            comparison_stats = []
            for player in comparison_players:
                player_trend = trends_df[trends_df['player_name'] == player]
                if not player_trend.empty:
                    stats = player_trend.iloc[0]
                    comparison_stats.append({
                        'Player': player,
                        'Overall %': f"{stats['overall_accuracy']:.1f}%",
                        'Trend': f"{stats['trend_slope']:+.2f}%/week",
                        'Change': f"{stats['improvement']:+.1f}%",
                        'Category': stats['trend_category'],
                        'Volatility': f"{stats['volatility']:.1f}%"
                    })
            
            if comparison_stats:
                st.write("**Comparison Summary:**")
                comparison_df = pd.DataFrame(comparison_stats)
                st.dataframe(comparison_df, use_container_width=True, hide_index=True)
    
    else:
        st.info(f"Not enough data for trend analysis. Need at least 3 weeks of participation per player.")
        st.write("Add more weekly results to see improvement trends and performance analysis.")

elif page == "Edit Players":
    st.header("Edit Players")
    
    players_df = data['players'].copy()
    if not players_df.empty:
        st.subheader("Current Players")
        
        # Initialize session state for editing if not exists
        if 'editing_player' not in st.session_state:
            st.session_state.editing_player = None
        
        # Create editable interface
        for _, player in players_df.iterrows():
            player_id = int(player['id'])
            
            with st.expander(f"Player: {player['name']}", expanded=False):
                # Create unique keys using timestamp or counter
                unique_suffix = f"{player_id}_{hash(str(player['name']))}"
                
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    new_name = st.text_input(
                        "Name:",
                        value=player['name'],
                        key=f"edit_name_{unique_suffix}"
                    )
                
                with col2:
                    if st.button("Update", key=f"update_{unique_suffix}", type="secondary"):
                        if new_name.strip() and new_name != player['name']:
                            # Check if new name already exists
                            if new_name in players_df['name'].values:
                                st.error("A player with this name already exists!")
                            else:
                                if update_player_name(spreadsheet, player_id, new_name.strip()):
                                    st.success("Player updated successfully!")
                                    st.cache_data.clear()
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Error updating player.")
                        elif new_name == player['name']:
                            st.info("No changes made.")
                        else:
                            st.error("Please enter a valid name.")
                
                with col3:
                    delete_key = f"delete_{unique_suffix}"
                    confirm_key = f"confirm_delete_{player_id}"
                    
                    if st.button("Delete", key=delete_key, type="secondary"):
                        # Confirm deletion
                        if confirm_key not in st.session_state:
                            st.session_state[confirm_key] = True
                            st.warning("⚠️ Click Delete again to confirm. This will delete the player and ALL their results!")
                            st.rerun()
                        else:
                            if delete_player(spreadsheet, player_id):
                                st.success("Player and all their results deleted successfully!")
                                if confirm_key in st.session_state:
                                    del st.session_state[confirm_key]
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Error deleting player.")
                
                # Clear confirmation if user clicks away
                if confirm_key in st.session_state:
                    if st.button("Cancel Delete", key=f"cancel_{unique_suffix}"):
                        del st.session_state[confirm_key]
                        st.rerun()
                
                # Show player statistics
                results_df = data['results'].copy()
                if not results_df.empty:
                    results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
                    player_results = results_df[results_df['player_id'] == player_id]
                    
                    if not player_results.empty:
                        total_weeks = len(player_results)
                        participated = len(player_results[player_results['status'] == 'participated'])
                        omitted = len(player_results[player_results['status'] == 'omitted'])
                        
                        st.write(f"**Statistics:** {total_weeks} weeks total | {participated} participated | {omitted} omitted")
    else:
        st.info("No players found. Add players in the 'Manage Players & Weeks' section.")

elif page == "Edit Results":
    st.header("Edit Results")
    
    # Initialize session state for editing if not exists
    if 'editing_result' not in st.session_state:
        st.session_state.editing_result = None
    
    # Week selector
    weeks_df = data['weeks'].copy()
    if not weeks_df.empty:
        weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
        weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
        
        season_weeks = weeks_df[weeks_df['season_year'] == current_season]
        
        if not season_weeks.empty:
            # Get weeks with results
            results_df = data['results'].copy()
            weeks_with_results = []
            
            if not results_df.empty:
                results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
                
                for _, week in season_weeks.iterrows():
                    week_id = int(week['id'])
                    week_results = results_df[results_df['week_id'] == week_id]
                    if not week_results.empty:
                        weeks_with_results.append({
                            'label': f"Week {int(week['week_number'])} ({int(week['total_games'])} games) - {week['week_date']}",
                            'value': week_id,
                            'week_number': int(week['week_number']),
                            'total_games': int(week['total_games'])
                        })
            
            if weeks_with_results:
                selected_week_option = st.selectbox(
                    "Select Week to Edit:",
                    weeks_with_results,
                    format_func=lambda x: x['label'],
                    key="edit_results_week_selector"
                )
                
                if selected_week_option:
                    selected_week_id = selected_week_option['value']
                    selected_week_number = selected_week_option['week_number']
                    total_games = selected_week_option['total_games']
                    
                    st.subheader(f"Edit Week {selected_week_number} Results")
                    
                    # Get players and results for this week
                    players_df = data['players'].copy()
                    
                    if not players_df.empty and not results_df.empty:
                        # Convert data types
                        results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
                        results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
                        
                        # Get results for this week
                        week_results = results_df[results_df['week_id'] == selected_week_id]
                        
                        if not week_results.empty:
                            # Merge with player names
                            week_results_with_names = week_results.merge(
                                players_df[['id', 'name']], 
                                left_on='player_id', 
                                right_on='id',
                                suffixes=('_result', '_player')
                            )
                            
                            st.write("Click on a result to edit or delete it:")
                            
                            for _, result in week_results_with_names.iterrows():
                                result_id = int(result['id_result'])
                                player_name = result['name']
                                current_status = result['status']
                                current_correct = int(result['correct_guesses']) if pd.notna(result['correct_guesses']) else 0
                                
                                # Create unique keys
                                unique_suffix = f"{result_id}_{selected_week_id}_{hash(player_name)}"
                                
                                with st.expander(f"{player_name}: {current_correct if current_status == 'participated' else 'Omitted'}", expanded=False):
                                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                                    
                                    with col1:
                                        st.write(f"**Player:** {player_name}")
                                    
                                    with col2:
                                        new_status = st.selectbox(
                                            "Status:",
                                            ['participated', 'omitted'],
                                            index=0 if current_status == 'participated' else 1,
                                            key=f"status_edit_{unique_suffix}"
                                        )
                                    
                                    with col3:
                                        if new_status == 'participated':
                                            new_correct = st.number_input(
                                                f"Correct (0-{total_games}):",
                                                min_value=0,
                                                max_value=total_games,
                                                value=current_correct,
                                                key=f"correct_edit_{unique_suffix}"
                                            )
                                        else:
                                            new_correct = 0
                                            st.write("—")
                                    
                                    with col4:
                                        col4a, col4b = st.columns(2)
                                        
                                        with col4a:
                                            if st.button("Update", key=f"update_result_{unique_suffix}", type="secondary"):
                                                if (new_status != current_status or 
                                                    (new_status == 'participated' and new_correct != current_correct)):
                                                    
                                                    if update_result(spreadsheet, result_id, new_correct, new_status):
                                                        st.success("Result updated!")
                                                        st.cache_data.clear()
                                                        time.sleep(1)
                                                        st.rerun()
                                                    else:
                                                        st.error("Error updating result.")
                                                else:
                                                    st.info("No changes made.")
                                        
                                        with col4b:
                                            delete_key = f"delete_result_{unique_suffix}"
                                            confirm_key = f"confirm_delete_result_{result_id}"
                                            
                                            if st.button("Delete", key=delete_key, type="secondary"):
                                                if confirm_key not in st.session_state:
                                                    st.session_state[confirm_key] = True
                                                    st.warning("Click Delete again to confirm!")
                                                    st.rerun()
                                                else:
                                                    # Note: delete_result function needs to be implemented
                                                    st.error("Delete result function not implemented yet.")
                                            
                                            # Cancel delete option
                                            if confirm_key in st.session_state:
                                                if st.button("Cancel", key=f"cancel_delete_{unique_suffix}"):
                                                    del st.session_state[confirm_key]
                                                    st.rerun()
                        else:
                            st.info("No results found for this week.")
                    else:
                        st.info("No players or results found.")
            else:
                st.info("No weeks with results found for the current season.")
        else:
            st.info("No weeks found for the current season.")
    else:
        st.info("No weeks found.")

elif page == "Manage Players & Weeks":
    st.header("Manage Players & Weeks")
    
    tab1, tab2 = st.tabs(["Players", "Weeks"])
    
    with tab1:
        st.subheader("Manage Players")
        
        # Add multiple players at once
        with st.expander("Add Players"):
            st.write("Add one or multiple players (one per line):")
            player_names_text = st.text_area("Player Names:", height=100, placeholder="Enter player names, one per line")
            
            if st.button("Add Players"):
                if player_names_text.strip():
                    player_names = [name.strip() for name in player_names_text.strip().split('\n') if name.strip()]
                    
                    if player_names:
                        # Prepare batch data
                        existing_players = set(data['players']['name'].tolist()) if not data['players'].empty else set()
                        batch_data = []
                        next_id = get_next_id(data['players'])
                        
                        new_players = []
                        duplicate_players = []
                        
                        for name in player_names:
                            if name not in existing_players:
                                player_data = {
                                    'id': next_id,
                                    'name': name,
                                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                batch_data.append(player_data)
                                new_players.append(name)
                                next_id += 1
                            else:
                                duplicate_players.append(name)
                        
                        # Batch save all new players
                        if batch_data:
                            if batch_update_sheet(spreadsheet, 'players', batch_data, 'append'):
                                st.success(f"Added {len(new_players)} players successfully!")
                                if duplicate_players:
                                    st.warning(f"Skipped duplicates: {', '.join(duplicate_players)}")
                                # Clear cache to reload data
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Error adding players. Please try again.")
                        else:
                            st.warning("All players already exist!")
                else:
                    st.error("Please enter at least one player name.")
        
        # Show existing players
        players_df = data['players']
        if not players_df.empty:
            st.subheader("Current Players")
            st.dataframe(players_df[['name', 'created_at']], use_container_width=True, hide_index=True)
        else:
            st.info("No players found.")
    
    with tab2:
        st.subheader("Manage Weeks")
        
        # Add new week
        with st.expander("Add New Week"):
            col1, col2 = st.columns(2)
            
            with col1:
                week_number = st.number_input("Week Number:", min_value=1, value=1)
                total_games = st.number_input("Total Games:", min_value=1, value=10)
            
            with col2:
                week_date = st.date_input("Week Date:", value=date.today())
            
            if st.button("Add Week"):
                # Check if week already exists
                weeks_df = data['weeks'].copy()
                if not weeks_df.empty:
                    weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
                    weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
                    existing = weeks_df[
                        (weeks_df['season_year'] == current_season) & 
                        (weeks_df['week_number'] == week_number)
                    ]
                    if not existing.empty:
                        st.error("Week already exists for this season!")
                    else:
                        # Add new week
                        next_id = get_next_id(data['weeks'])
                        week_data = [{
                            'id': next_id,
                            'week_number': week_number,
                            'season_year': current_season,
                            'total_games': total_games,
                            'week_date': week_date.strftime('%Y-%m-%d'),
                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }]
                        
                        if batch_update_sheet(spreadsheet, 'weeks', week_data, 'append'):
                            st.success("Week added successfully!")
                            # Clear cache to reload data
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Error adding week. Please try again.")
                else:
                    # First week
                    next_id = 1
                    week_data = [{
                        'id': next_id,
                        'week_number': week_number,
                        'season_year': current_season,
                        'total_games': total_games,
                        'week_date': week_date.strftime('%Y-%m-%d'),
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }]
                    
                    if batch_update_sheet(spreadsheet, 'weeks', week_data, 'append'):
                        st.success("Week added successfully!")
                        # Clear cache to reload data
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Error adding week. Please try again.")
        
        # Show existing weeks
        weeks_df = data['weeks'].copy()
        if not weeks_df.empty:
            # Convert data types
            weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
            weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
            
            season_weeks = weeks_df[weeks_df['season_year'] == current_season]
            
            if not season_weeks.empty:
                st.subheader(f"Weeks for Season {current_season}")
                
                # Get results count for each week
                results_df = data['results'].copy()
                weeks_display = season_weeks.copy()
                
                if not results_df.empty:
                    results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
                    weeks_display['results_count'] = weeks_display['id'].apply(
                        lambda week_id: len(results_df[results_df['week_id'] == week_id])
                    )
                else:
                    weeks_display['results_count'] = 0
                
                display_cols = ['week_number', 'week_date', 'total_games', 'results_count']
                weeks_display = weeks_display[display_cols]
                weeks_display.columns = ['Week #', 'Date', 'Total Games', 'Results Entered']
                
                st.dataframe(weeks_display, use_container_width=True, hide_index=True)
            else:
                st.info(f"No weeks found for season {current_season}.")
        else:
            st.info("No weeks found.")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using Streamlit & Google Sheets | Youth Home Sports Prediction Tracker")
