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
import uuid
import hashlib

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

# Cache sheet name mapping to avoid repeated lookups
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_sheet_name_mapping(spreadsheet_id):
    """Get case-insensitive sheet name mapping"""
    try:
        spreadsheet = init_connection()
        if not spreadsheet:
            return {}
        
        worksheets = spreadsheet.worksheets()
        sheet_names = [ws.title for ws in worksheets]
        return {name.lower(): name for name in sheet_names}
    except Exception as e:
        st.error(f"Error getting sheet mapping: {e}")
        return {}

def get_actual_sheet_name(logical_name, spreadsheet_id):
    """Get actual sheet name from logical name using cached mapping"""
    mapping = get_sheet_name_mapping(spreadsheet_id)
    return mapping.get(logical_name.lower(), logical_name)

def generate_id():
    """Generate unique ID using UUID4"""
    return uuid.uuid4().hex

def create_deterministic_key(*parts):
    """Create deterministic key for Streamlit widgets"""
    combined = "_".join(str(part) for part in parts)
    return hashlib.md5(combined.encode()).hexdigest()[:12]

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

def update_week(spreadsheet, week_id, week_number, total_games, week_date):
    """Update a week's data"""
    try:
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        actual_sheet_name = existing_sheets_lower.get('weeks', 'weeks')
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        data = worksheet.get_all_records()
        
        # Find the row to update
        for i, row in enumerate(data, start=2):  # Start at 2 because row 1 is headers
            if str(row.get('id', '')) == str(week_id):
                headers = worksheet.row_values(1)
                
                # Update week_number
                if 'week_number' in headers:
                    col_index = headers.index('week_number') + 1
                    worksheet.update_cell(i, col_index, week_number)
                
                # Update total_games
                if 'total_games' in headers:
                    col_index = headers.index('total_games') + 1
                    worksheet.update_cell(i, col_index, total_games)
                
                # Update week_date
                if 'week_date' in headers:
                    col_index = headers.index('week_date') + 1
                    worksheet.update_cell(i, col_index, week_date)
                
                return True
        return False
    except Exception as e:
        st.error(f"Error updating week: {e}")
        return False

def delete_week(spreadsheet, week_id):
    """Delete a week and all its results"""
    try:
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        
        # Delete from weeks sheet
        weeks_sheet_name = existing_sheets_lower.get('weeks', 'weeks')
        worksheet = spreadsheet.worksheet(weeks_sheet_name)
        data = worksheet.get_all_records()
        
        row_to_delete = None
        for i, row in enumerate(data, start=2):
            if str(row.get('id', '')) == str(week_id):
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
            if str(row.get('week_id', '')) == str(week_id):
                rows_to_delete.append(i)
        
        # Delete rows in reverse order
        for row_num in reversed(rows_to_delete):
            results_worksheet.delete_rows(row_num)
        
        return True
    except Exception as e:
        st.error(f"Error deleting week: {e}")
        return False

def update_player_name_batch(spreadsheet, player_id, new_name, spreadsheet_id=None):
    """Update player name using batch operation"""
    try:
        actual_sheet_name = get_actual_sheet_name('players', spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        data = worksheet.get_all_records()
        headers = worksheet.row_values(1)
        
        # Find the row to update
        for i, row in enumerate(data, start=2):
            if str(row.get('id', '')) == str(player_id):
                if 'name' in headers:
                    col_letter = chr(ord('A') + headers.index('name'))
                    worksheet.batch_update([{
                        'range': f'{col_letter}{i}',
                        'values': [[new_name]]
                    }])
                return True
        return False
    except Exception as e:
        st.error(f"Error updating player: {e}")
        return False

def delete_player_batch(spreadsheet, player_id, spreadsheet_id=None):
    """Delete player and all results using batch operations"""
    try:
        sheet_id = spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"]
        
        # Get sheet references
        players_sheet_name = get_actual_sheet_name('players', sheet_id)
        results_sheet_name = get_actual_sheet_name('results', sheet_id)
        
        players_worksheet = spreadsheet.worksheet(players_sheet_name)
        results_worksheet = spreadsheet.worksheet(results_sheet_name)
        
        # Find player row to delete
        players_data = players_worksheet.get_all_records()
        player_row_to_delete = None
        for i, row in enumerate(players_data, start=2):
            if str(row.get('id', '')) == str(player_id):
                player_row_to_delete = i
                break
        
        # Find all result rows to delete
        results_data = results_worksheet.get_all_records()
        result_rows_to_delete = []
        for i, row in enumerate(results_data, start=2):
            if str(row.get('player_id', '')) == str(player_id):
                result_rows_to_delete.append(i)
        
        # Batch delete all rows
        rows_to_delete = []
        if player_row_to_delete:
            rows_to_delete.append((players_worksheet, player_row_to_delete))
        
        for row_num in result_rows_to_delete:
            rows_to_delete.append((results_worksheet, row_num))
        
        # Execute batch deletes
        if rows_to_delete:
            # Group by worksheet for efficiency
            players_rows = [row for ws, row in rows_to_delete if ws == players_worksheet]
            results_rows = [row for ws, row in rows_to_delete if ws == results_worksheet]
            
            if players_rows:
                delete_rows_batch(spreadsheet, 'players', players_rows, sheet_id)
            if results_rows:
                delete_rows_batch(spreadsheet, 'results', results_rows, sheet_id)
        
        return True
    except Exception as e:
        st.error(f"Error deleting player: {e}")
        return False

def normalize_dates(df, date_columns):
    """Normalize date columns to consistent format"""
    df = df.copy()
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
    return df

def linear_regression_improved(x, y):
    """Improved linear regression with better trend classification"""
    try:
        x = np.array(x)
        y = np.array(y)
        
        if len(x) < 3 or len(y) < 3 or len(x) != len(y):
            return 0, 0, 0, False, 0
        
        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x * x)
        sum_y2 = np.sum(y * y)
        
        # Calculate slope (m) and intercept (b)
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0, np.mean(y), 0, False, 0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        # Calculate correlation coefficient (r)
        numerator_r = n * sum_xy - sum_x * sum_y
        denominator_r = np.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
        
        if denominator_r == 0:
            r_value = 0
        else:
            r_value = numerator_r / denominator_r
        
        # Use interpretable thresholds instead of fake p-values
        r_squared = r_value ** 2
        is_significant = abs(slope) >= 0.75 and r_squared >= 0.25
        
        # Calculate standard error
        if n > 2:
            y_pred = slope * x + intercept
            residuals = y - y_pred
            mse = np.sum(residuals**2) / (n - 2)
            std_err = np.sqrt(mse / np.sum((x - np.mean(x))**2)) if np.sum((x - np.mean(x))**2) > 0 else 0
        else:
            std_err = 0
        
        return slope, intercept, r_value, is_significant, std_err
        
    except Exception:
        return 0, 0, 0, False, 0

def linear_regression(x, y):
    """Wrapper to maintain compatibility"""
    slope, intercept, r_value, is_significant, std_err = linear_regression_improved(x, y)
    # Return old format with fake p_value for compatibility
    p_value = 0.02 if is_significant else 0.3
    return slope, intercept, r_value, p_value, std_err
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

# Update player data adding to use new methods
def add_players_batch(spreadsheet, player_names, spreadsheet_id=None):
    """Add multiple players efficiently with duplicate checking"""
    try:
        # Check for duplicates against fresh data
        existing_data = spreadsheet.worksheet(get_actual_sheet_name('players', spreadsheet_id)).get_all_records()
        existing_names = {row.get('name', '') for row in existing_data}
        
        # Prepare batch data
        batch_data = []
        new_players = []
        duplicate_players = []
        
        for name in player_names:
            name = name.strip()
            if name and name not in existing_names:
                player_data = {
                    'id': generate_id(),
                    'name': name,
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                batch_data.append(player_data)
                new_players.append(name)
                existing_names.add(name)  # Prevent duplicates within this batch
            elif name:
                duplicate_players.append(name)
        
        # Batch save all new players
        if batch_data:
            if batch_update_sheet_optimized(spreadsheet, 'players', batch_data, 'append', spreadsheet_id):
                return True, new_players, duplicate_players
        
        return False, [], duplicate_players
        
    except Exception as e:
        st.error(f"Error adding players: {e}")
        return False, [], []

def add_week_batch(spreadsheet, week_data, spreadsheet_id=None):
    """Add week with duplicate checking"""
    try:
        # Check for existing week number in season
        existing_data = spreadsheet.worksheet(get_actual_sheet_name('weeks', spreadsheet_id)).get_all_records()
        existing_weeks = {(row.get('season_year'), row.get('week_number')) for row in existing_data}
        
        check_key = (week_data['season_year'], week_data['week_number'])
        if check_key in existing_weeks:
            return False, "Week already exists for this season"
        
        # Add unique ID
        week_data['id'] = generate_id()
        week_data['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if batch_update_sheet_optimized(spreadsheet, 'weeks', [week_data], 'append', spreadsheet_id):
            return True, "Week added successfully"
        
        return False, "Error saving week"
        
    except Exception as e:
        return False, f"Error adding week: {e}"

def update_result_batch(spreadsheet, result_id, correct_guesses, status, spreadsheet_id=None):
    """Update result using batch operation"""
    try:
        actual_sheet_name = get_actual_sheet_name('results', spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        data = worksheet.get_all_records()
        headers = worksheet.row_values(1)
        
        # Find the row to update
        for i, row in enumerate(data, start=2):
            if str(row.get('id', '')) == str(result_id):
                # Prepare batch update
                updates = []
                
                if 'correct_guesses' in headers:
                    col_letter = chr(ord('A') + headers.index('correct_guesses'))
                    value = correct_guesses if status != 'omitted' else ''
                    updates.append({
                        'range': f'{col_letter}{i}',
                        'values': [[value]]
                    })
                
                if 'status' in headers:
                    col_letter = chr(ord('A') + headers.index('status'))
                    updates.append({
                        'range': f'{col_letter}{i}',
                        'values': [[status]]
                    })
                
                # Single batch update call
                if updates:
                    worksheet.batch_update(updates)
                
                return True
        return False
    except Exception as e:
        st.error(f"Error updating result: {e}")
        return False

def normalize_data_types(data):
    """Normalize data types for consistency"""
    if data.empty:
        return data
    
    data = data.copy()
    
    # Normalize ID columns as strings (UUID4 hex)
    id_cols = ['id', 'player_id', 'week_id']
    for col in id_cols:
        if col in data.columns:
            data[col] = data[col].astype(str)
    
    # Normalize numeric columns
    numeric_cols = ['week_number', 'season_year', 'total_games', 'correct_guesses']
    for col in numeric_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors='coerce')
    
    # Normalize date columns
    date_cols = ['week_date', 'created_at']
    for col in date_cols:
        if col in data.columns:
            data[col] = pd.to_datetime(data[col], errors='coerce').dt.strftime('%Y-%m-%d')
    
    return data

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

def batch_update_sheet_optimized(spreadsheet, sheet_name, data_list, operation='append', spreadsheet_id=None):
    """Optimized batch update with single API call"""
    try:
        actual_sheet_name = get_actual_sheet_name(sheet_name, spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        if operation == 'append':
            # Get headers once
            headers = worksheet.row_values(1)
            
            # Convert all data to rows in one pass
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
            
            # Single batch append
            if rows:
                worksheet.append_rows(rows)
            
        return True
        
    except Exception as e:
        st.error(f"Error batch updating {sheet_name}: {e}")
        return False

def check_and_prevent_duplicates(spreadsheet, sheet_name, new_data, unique_columns, spreadsheet_id=None):
    """Check for duplicates before inserting to prevent race conditions"""
    try:
        actual_sheet_name = get_actual_sheet_name(sheet_name, spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        # Fresh read of just the target sheet
        existing_data = worksheet.get_all_records()
        existing_df = pd.DataFrame(existing_data)
        
        if existing_df.empty:
            return new_data  # No existing data, all new records are safe
        
        # Create composite keys for duplicate checking
        safe_records = []
        for record in new_data:
            composite_key = "|".join(str(record.get(col, '')) for col in unique_columns)
            
            # Check if this combination already exists
            existing_composites = existing_df.apply(
                lambda row: "|".join(str(row.get(col, '')) for col in unique_columns), 
                axis=1
            ).tolist()
            
            if composite_key not in existing_composites:
                safe_records.append(record)
        
        return safe_records
        
    except Exception as e:
        st.error(f"Error checking duplicates: {e}")
        return new_data

def update_week_batch(spreadsheet, week_id, week_number, total_games, week_date, spreadsheet_id=None):
    """Update week using batch operations"""
    try:
        actual_sheet_name = get_actual_sheet_name('weeks', spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        # Get all data to find the row
        data = worksheet.get_all_records()
        headers = worksheet.row_values(1)
        
        # Find the row to update
        for i, row in enumerate(data, start=2):
            if str(row.get('id', '')) == str(week_id):
                # Prepare batch update
                updates = []
                
                if 'week_number' in headers:
                    col_letter = chr(ord('A') + headers.index('week_number'))
                    updates.append({
                        'range': f'{col_letter}{i}',
                        'values': [[week_number]]
                    })
                
                if 'total_games' in headers:
                    col_letter = chr(ord('A') + headers.index('total_games'))
                    updates.append({
                        'range': f'{col_letter}{i}',
                        'values': [[total_games]]
                    })
                
                if 'week_date' in headers:
                    col_letter = chr(ord('A') + headers.index('week_date'))
                    updates.append({
                        'range': f'{col_letter}{i}',
                        'values': [[week_date]]
                    })
                
                # Single batch update call
                if updates:
                    worksheet.batch_update(updates)
                
                return True
        return False
    except Exception as e:
        st.error(f"Error updating week: {e}")
        return False

def delete_rows_batch(spreadsheet, sheet_name, row_numbers, spreadsheet_id=None):
    """Delete multiple rows in a single batch operation"""
    try:
        actual_sheet_name = get_actual_sheet_name(sheet_name, spreadsheet_id or st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        if not row_numbers:
            return True
        
        # Sort in reverse order to avoid index shifting
        sorted_rows = sorted(row_numbers, reverse=True)
        
        # Group consecutive rows for efficient deletion
        requests = []
        for row_num in sorted_rows:
            requests.append({
                "deleteDimension": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": row_num - 1,  # 0-indexed
                        "endIndex": row_num
                    }
                }
            })
        
        # Single batch delete
        if requests:
            worksheet.spreadsheet.batch_update({"requests": requests})
        
        return True
        
    except Exception as e:
        st.error(f"Error batch deleting rows: {e}")
        return False

def update_player_name_batch(spreadsheet, player_id, new_name, spreadsheet_id=None):
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

def delete_result(spreadsheet, result_id):
    """Delete a specific result"""
    try:
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        actual_sheet_name = existing_sheets_lower.get('results', 'results')
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        data = worksheet.get_all_records()
        
        # Find the row to delete
        for i, row in enumerate(data, start=2):  # Start at 2 because row 1 is headers
            if str(row.get('id', '')) == str(result_id):
                worksheet.delete_rows(i)
                return True
        return False
    except Exception as e:
        st.error(f"Error deleting result: {e}")
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
    """Get the next available ID for a dataframe - now returns UUID4 hex string"""
    return generate_id()

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
            weeks_df['id'] = weeks_df['id'].astype(str)
            weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        if not results_df.empty:
            # Keep player_id as string since it's a UUID4 hex
            results_df['player_id'] = results_df['player_id'].astype(str)
            results_df['week_id'] = results_df['week_id'].astype(str)
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
            player_id = str(player['id'])  # Keep as string since it's a UUID4 hex
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
                week_id = str(week['id'])
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
        
        # No need to sort here since each display will sort by its own criteria
        # standings_df remains unsorted to allow proper individual ranking
        
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
            weeks_df['id'] = weeks_df['id'].astype(str)
            weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        if not results_df.empty:
            # Keep player_id as string since it's a UUID4 hex
            results_df['player_id'] = results_df['player_id'].astype(str)
            results_df['week_id'] = results_df['week_id'].astype(str)
            results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
        
        # Get player ID
        player_row = players_df[players_df['name'] == player_name]
        if player_row.empty:
            return pd.DataFrame()
        
        player_id = str(player_row.iloc[0]['id'])  # Keep as string since it's a UUID4 hex
        
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
        weeks_df['id'] = weeks_df['id'].astype(str)
        weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        results_df['player_id'] = results_df['player_id'].astype(str)
        results_df['week_id'] = results_df['week_id'].astype(str)
        results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
        
        # Filter for season
        season_weeks = weeks_df[weeks_df['season_year'] == season_year]
        if season_weeks.empty:
            return pd.DataFrame()
        
        trends = []
        
        for _, player in players_df.iterrows():
            player_id = str(player['id'])  # Keep as string since it's a UUID4 hex
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
            slope, intercept, r_value, p_value, std_err = linear_regression_improved(weeks, accuracies)
            r_squared = r_value ** 2
            
            # Use improved significance determination
            is_significant = abs(slope) >= 0.75 and r_squared >= 0.25
            
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
                'trend_r_squared': round(r_squared, 3),
                'volatility': round(volatility, 1),
                'trend_category': trend_category,
                'trend_significance': 'Meaningful' if is_significant else 'Inconclusive'
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
    "Improvement Trends",
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
    st.header("Enter/Edit Weekly Results")
    st.write("💡 **Tip:** This page allows you to both enter new results and edit existing ones. Simply adjust the numbers or status and save to override current data.")
    
    weeks_df = data['weeks'].copy()
    if not weeks_df.empty:
        # Convert data types
        weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
        weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
        weeks_df['id'] = weeks_df['id'].astype(str)
        weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        # Filter for current season
        season_weeks = weeks_df[weeks_df['season_year'] == current_season]
        
        if not season_weeks.empty:
            # Show week selector
            week_options = []
            for _, week in season_weeks.iterrows():
                week_options.append({
                    'label': f"Week {int(week['week_number'])} ({int(week['total_games'])} games) - {week['week_date']}",
                    'value': str(week['id']),
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
                        # Keep player_id as string since it's a UUID4 hex
                        results_df['player_id'] = results_df['player_id'].astype(str)
                        results_df['week_id'] = results_df['week_id'].astype(str)
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
                            player_id = str(player['id'])
                            
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
                        if st.button("Save/Update All Results", type="primary"):
                            # Process individual entry results - update existing or create new
                            results_df_for_updates = data['results'].copy()
                            
                            if not results_df_for_updates.empty:
                                results_df_for_updates['player_id'] = results_df_for_updates['player_id'].astype(str)
                                results_df_for_updates['week_id'] = results_df_for_updates['week_id'].astype(str)
                            
                            new_results = []
                            updated_count = 0
                            created_count = 0
                            
                            for player_id, (correct_guesses, status) in results_to_save.items():
                                # Check if result already exists
                                existing_mask = (
                                    (results_df_for_updates['player_id'] == player_id) & 
                                    (results_df_for_updates['week_id'] == selected_week_id)
                                )
                                
                                if existing_mask.any():
                                    # Update existing result
                                    existing_result = results_df_for_updates[existing_mask].iloc[0]
                                    result_id = str(existing_result['id'])
                                    
                                    if update_result_batch(spreadsheet, result_id, correct_guesses, status):
                                        updated_count += 1
                                    else:
                                        st.error(f"Failed to update result for player {player_id}")
                                else:
                                    # Create new result
                                    result_data = {
                                        'id': generate_id(),
                                        'player_id': player_id,
                                        'week_id': selected_week_id,
                                        'correct_guesses': correct_guesses if status != 'omitted' else '',
                                        'status': status,
                                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    new_results.append(result_data)
                            
                            # Save new results if any
                            if new_results:
                                if batch_update_sheet_optimized(spreadsheet, 'results', new_results, 'append'):
                                    created_count = len(new_results)
                                else:
                                    st.error("Error saving new results. Please try again.")
                            
                            # Show success message
                            if updated_count > 0 or created_count > 0:
                                message_parts = []
                                if updated_count > 0:
                                    message_parts.append(f"Updated {updated_count} existing results")
                                if created_count > 0:
                                    message_parts.append(f"Created {created_count} new results")
                                
                                st.success(" ".join(message_parts) + "!")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.info("No changes made to any results.")
                    
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
                                player_id = str(player['id'])
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
                            name_to_id = {player['name']: str(player['id']) for _, player in players_df.iterrows()}
                            
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
                                if st.button("Save/Update Bulk Results", type="primary"):
                                    # Process bulk entry results - update existing or create new
                                    results_df_for_updates = data['results'].copy()
                                    
                                    if not results_df_for_updates.empty:
                                        # Keep player_id as string since it's a UUID4 hex
                                        results_df_for_updates['player_id'] = results_df_for_updates['player_id'].astype(str)
                                        results_df_for_updates['week_id'] = results_df_for_updates['week_id'].astype(str)
                                    
                                    new_results = []
                                    updated_count = 0
                                    created_count = 0
                                    
                                    for player_id, (correct_guesses, status) in parsed_results.items():
                                        # Check if result already exists
                                        existing_mask = (
                                            (results_df_for_updates['player_id'] == player_id) & 
                                            (results_df_for_updates['week_id'] == selected_week_id)
                                        )
                                        
                                        if existing_mask.any():
                                            # Update existing result
                                            existing_result = results_df_for_updates[existing_mask].iloc[0]
                                            result_id = str(existing_result['id'])
                                            
                                            if update_result_batch(spreadsheet, result_id, correct_guesses, status):
                                                updated_count += 1
                                            else:
                                                st.error(f"Failed to update result for player {player_id}")
                                        else:
                                            # Create new result
                                            result_data = {
                                                'id': generate_id(),
                                                'player_id': player_id,
                                                'week_id': selected_week_id,
                                                'correct_guesses': correct_guesses if status != 'omitted' else '',
                                                'status': status,
                                                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                            }
                                            new_results.append(result_data)
                                    
                                    # Save new results if any
                                    if new_results:
                                        if batch_update_sheet_optimized(spreadsheet, 'results', new_results, 'append'):
                                            created_count = len(new_results)
                                        else:
                                            st.error("Error saving new results. Please try again.")
                                    
                                    # Show success message
                                    if updated_count > 0 or created_count > 0:
                                        message_parts = []
                                        if updated_count > 0:
                                            message_parts.append(f"Updated {updated_count} existing results")
                                        if created_count > 0:
                                            message_parts.append(f"Created {created_count} new results")
                                        
                                        st.success(" ".join(message_parts) + "!")
                                        st.cache_data.clear()
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.info("No changes made to any results.")
                            
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
                results_df['week_id'] = results_df['week_id'].astype(str)
                
                for _, week in season_weeks.iterrows():
                    week_id = str(week['id'])
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
                        # Sort by absolute accuracy for proper ranking
                        abs_display = abs_display.sort_values('accuracy_absolute', ascending=False)
                        abs_display['rank'] = range(1, len(abs_display) + 1)
                        abs_display = abs_display[['rank', 'player_name', 'correct_absolute', 'possible_absolute', 'accuracy_absolute']]
                        abs_display.columns = ['Rank', 'Player', 'Correct', 'Possible', 'Accuracy %']
                        st.dataframe(abs_display, use_container_width=True, hide_index=True)
                    
                    with col2:
                        st.write("**🎯 Adjusted Statistics** (excluding omissions)")
                        adj_display = standings_df.copy()
                        # Sort by adjusted accuracy for proper ranking
                        adj_display = adj_display.sort_values('accuracy_adjusted', ascending=False)
                        adj_display['rank'] = range(1, len(adj_display) + 1)
                        adj_display = adj_display[['rank', 'player_name', 'correct_adjusted', 'possible_adjusted', 'accuracy_adjusted']]
                        adj_display.columns = ['Rank', 'Player', 'Correct', 'Possible', 'Accuracy %']
                        st.dataframe(adj_display, use_container_width=True, hide_index=True)
                    
                    # Visualization
                    fig = px.bar(
                        standings_df, 
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
            # Sort by absolute accuracy for proper ranking
            abs_display = abs_display.sort_values('accuracy_absolute', ascending=False)
            abs_display['rank'] = range(1, len(abs_display) + 1)
            abs_display = abs_display[['rank', 'player_name', 'weeks_absolute', 'correct_absolute', 'possible_absolute', 'accuracy_absolute']]
            abs_display.columns = ['Rank', 'Player', 'Weeks', 'Correct', 'Possible', 'Accuracy %']
            st.dataframe(abs_display, use_container_width=True, hide_index=True)
        
        with col2:
            st.write("**🎯 Adjusted Statistics** (excluding omissions)")
            adj_display = standings_df.copy()
            # Sort by adjusted accuracy for proper ranking
            adj_display = adj_display.sort_values('accuracy_adjusted', ascending=False)
            adj_display['rank'] = range(1, len(adj_display) + 1)
            adj_display = adj_display[['rank', 'player_name', 'weeks_adjusted', 'correct_adjusted', 'possible_adjusted', 'accuracy_adjusted', 'omitted_weeks']]
            adj_display.columns = ['Rank', 'Player', 'Weeks', 'Correct', 'Possible', 'Accuracy %', 'Omitted']
            st.dataframe(adj_display, use_container_width=True, hide_index=True)
        
        # Visualizations
        col1, col2 = st.columns(2)
        
        with col1:
            fig1 = px.bar(
                standings_df, 
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
                standings_df, 
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
                        # Use optimized batch add
                        success, new_players, duplicate_players = add_players_batch(
                            spreadsheet, 
                            player_names, 
                            st.secrets["connections"]["gsheets"]["spreadsheet"]
                        )
                        
                        if success and new_players:
                            st.success(f"Added {len(new_players)} players successfully!")
                            if duplicate_players:
                                st.warning(f"Skipped duplicates: {', '.join(duplicate_players)}")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        elif not new_players and duplicate_players:
                            st.warning("All players already exist!")
                        else:
                            st.error("Error adding players. Please try again.")
                else:
                    st.error("Please enter at least one player name.")
        
        # Show existing players with edit functionality
        players_df = data['players'].copy()
        if not players_df.empty:
            st.subheader("Current Players")
            
            # Get results data for statistics
            results_df = data['results'].copy()
            
            # Create editable interface for players
            for _, player in players_df.iterrows():
                player_id = str(player['id'])  # Keep as string since it's a UUID4 hex
                
                # Calculate player statistics
                player_stats = {'total_weeks': 0, 'participated': 0, 'omitted': 0}
                if not results_df.empty:
                    # Convert player_id to string for comparison
                    results_df['player_id'] = results_df['player_id'].astype(str)
                    player_results = results_df[results_df['player_id'] == player_id]
                    
                    if not player_results.empty:
                        player_stats['total_weeks'] = len(player_results)
                        player_stats['participated'] = len(player_results[player_results['status'] == 'participated'])
                        player_stats['omitted'] = len(player_results[player_results['status'] == 'omitted'])
                
                # Create expandable card
                stats_text = f"{player_stats['total_weeks']} weeks total, {player_stats['participated']} participated"
                with st.expander(f"{player['name']} ({stats_text})", expanded=False):
                    # Create unique keys
                    unique_suffix = f"{player_id}_{hash(str(player['name']))}"
                    
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        new_name = st.text_input(
                            "Player Name:",
                            value=player['name'],
                            key=f"edit_player_name_{unique_suffix}"
                        )
                    
                    with col2:
                        st.write("**Statistics:**")
                        st.write(f"Total weeks: {player_stats['total_weeks']}")
                        st.write(f"Participated: {player_stats['participated']}")
                        st.write(f"Omitted: {player_stats['omitted']}")
                    
                    with col3:
                        if player_stats['total_weeks'] > 0:
                            st.write(f"**Activity Level:**")
                            participation_rate = (player_stats['participated'] / player_stats['total_weeks']) * 100
                            st.write(f"{participation_rate:.0f}% participation")
                        else:
                            st.write("**Status:**")
                            st.write("No results yet")
                    
                    # Action buttons
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        if st.button("Update Player", key=f"update_player_{unique_suffix}", type="secondary"):
                            if new_name.strip() and new_name != player['name']:
                                # Check if new name already exists
                                if new_name in players_df['name'].values:
                                    st.error("A player with this name already exists!")
                                else:
                                    if update_player_name_batch(spreadsheet, player_id, new_name.strip()):
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
                    
                    with col2:
                        delete_key = f"delete_player_{unique_suffix}"
                        confirm_key = f"confirm_delete_player_{player_id}"
                        
                        # Check if we're in confirmation mode
                        in_confirmation = st.session_state.get(confirm_key, False)
                        
                        if not in_confirmation:
                            if st.button("Delete Player", key=delete_key, type="secondary"):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            col2a, col2b = st.columns(2)
                            with col2a:
                                if st.button("Confirm", key=f"confirm_player_{unique_suffix}", type="secondary"):
                                    if delete_player_batch(spreadsheet, player_id):
                                        st.success("Player and all results deleted successfully!")
                                        if confirm_key in st.session_state:
                                            del st.session_state[confirm_key]
                                        st.cache_data.clear()
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Error deleting player.")
                                        if confirm_key in st.session_state:
                                            del st.session_state[confirm_key]
                            
                            with col2b:
                                if st.button("Cancel", key=f"cancel_player_{unique_suffix}", type="secondary"):
                                    if confirm_key in st.session_state:
                                        del st.session_state[confirm_key]
                                    st.rerun()
                    
                    with col3:
                        if player_stats['total_weeks'] > 0:
                            st.write(f"⚠️ Has {player_stats['total_weeks']} results")
                        else:
                            st.write("✅ No results yet")
                    
                    # Show confirmation warning
                    if st.session_state.get(confirm_key, False):
                        if player_stats['total_weeks'] > 0:
                            st.warning(f"⚠️ This will delete {player['name']} AND all {player_stats['total_weeks']} results!")
                        else:
                            st.warning(f"⚠️ Confirm deletion of {player['name']}?")
        else:
            st.info("No players found. Add players using the form above.")
    
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
                # Use optimized batch add with duplicate checking
                week_data = {
                    'week_number': week_number,
                    'season_year': current_season,
                    'total_games': total_games,
                    'week_date': week_date.strftime('%Y-%m-%d')
                }
                
                success, message = add_week_batch(
                    spreadsheet, 
                    week_data, 
                    st.secrets["connections"]["gsheets"]["spreadsheet"]
                )
                
                if success:
                    st.success(message)
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(message)
        
        # Show existing weeks with edit functionality
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
                
                # Create editable interface for weeks
                for _, week in season_weeks.iterrows():
                    week_id = str(week['id'])
                    
                    # Count results for this week
                    week_results_count = 0
                    if not results_df.empty:
                        results_df['week_id'] = results_df['week_id'].astype(str)
                        week_results_count = len(results_df[results_df['week_id'] == week_id])
                    
                    with st.expander(f"Week {int(week['week_number'])} - {week['week_date']} ({week_results_count} results)", expanded=False):
                        # Create unique keys
                        unique_suffix = create_deterministic_key(week_id, "week_edit")
                        
                        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                        
                        with col1:
                            new_week_number = st.number_input(
                                "Week Number:",
                                min_value=1,
                                value=int(week['week_number']),
                                key=f"edit_week_num_{unique_suffix}"
                            )
                        
                        with col2:
                            new_total_games = st.number_input(
                                "Total Games:",
                                min_value=1,
                                value=int(week['total_games']),
                                key=f"edit_total_games_{unique_suffix}"
                            )
                        
                        with col3:
                            # Parse the existing date
                            try:
                                if isinstance(week['week_date'], str):
                                    existing_date = datetime.strptime(week['week_date'], '%Y-%m-%d').date()
                                else:
                                    existing_date = date.today()
                            except:
                                existing_date = date.today()
                            
                            new_week_date = st.date_input(
                                "Week Date:",
                                value=existing_date,
                                key=f"edit_week_date_{unique_suffix}"
                            )
                        
                        with col4:
                            st.write(f"**Results:** {week_results_count}")
                        
                        # Action buttons
                        col1, col2, col3 = st.columns([1, 1, 1])
                        
                        with col1:
                            if st.button("Update Week", key=f"update_week_{unique_suffix}", type="secondary"):
                                # Check if week number already exists (only if changed)
                                if new_week_number != int(week['week_number']):
                                    existing_week = season_weeks[
                                        (season_weeks['week_number'] == new_week_number) &
                                        (season_weeks['id'] != week_id)
                                    ]
                                    if not existing_week.empty:
                                        st.error(f"Week {new_week_number} already exists for this season!")
                                        continue
                                
                                # Check if any changes were made
                                changes_made = (
                                    new_week_number != int(week['week_number']) or
                                    new_total_games != int(week['total_games']) or
                                    new_week_date.strftime('%Y-%m-%d') != week['week_date']
                                )
                                
                                if changes_made:
                                    if update_week_batch(spreadsheet, week_id, new_week_number, new_total_games, new_week_date.strftime('%Y-%m-%d')):
                                        st.success("Week updated successfully!")
                                        st.cache_data.clear()
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Error updating week.")
                                else:
                                    st.info("No changes made.")
                        
                        with col2:
                            delete_key = f"delete_week_{unique_suffix}"
                            confirm_key = f"confirm_delete_week_{week_id}"
                            
                            # Check if we're in confirmation mode
                            in_confirmation = st.session_state.get(confirm_key, False)
                            
                            if not in_confirmation:
                                if st.button("Delete Week", key=delete_key, type="secondary"):
                                    st.session_state[confirm_key] = True
                                    st.rerun()
                            else:
                                col2a, col2b = st.columns(2)
                                with col2a:
                                    if st.button("Confirm", key=f"confirm_week_{unique_suffix}", type="secondary"):
                                        if delete_week(spreadsheet, week_id):
                                            st.success("Week and all results deleted successfully!")
                                            if confirm_key in st.session_state:
                                                del st.session_state[confirm_key]
                                            st.cache_data.clear()
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error("Error deleting week.")
                                            if confirm_key in st.session_state:
                                                del st.session_state[confirm_key]
                                
                                with col2b:
                                    if st.button("Cancel", key=f"cancel_week_{unique_suffix}", type="secondary"):
                                        if confirm_key in st.session_state:
                                            del st.session_state[confirm_key]
                                        st.rerun()
                        
                        with col3:
                            if week_results_count > 0:
                                st.write(f"⚠️ Has {week_results_count} results")
                            else:
                                st.write("✅ No results yet")
                        
                        # Show confirmation warning
                        if st.session_state.get(confirm_key, False):
                            if week_results_count > 0:
                                st.warning(f"⚠️ This will delete the week AND all {week_results_count} results!")
                            else:
                                st.warning("⚠️ Confirm week deletion?")
            else:
                st.info(f"No weeks found for season {current_season}.")
        else:
            st.info("No weeks found.")

# Footer
st.markdown("---")
st.markdown("Built for Bradley-san 2026 | Pick'ems")
