import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import json

# Streamlit App Configuration
st.set_page_config(
    page_title="Sports Prediction Tracker",
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
                # Sheet exists (possibly with different case), use the actual name
                actual_sheet_name = existing_sheets_lower[sheet_name.lower()]
                
                worksheet = spreadsheet.worksheet(actual_sheet_name)
                
                try:
                    existing_headers = worksheet.row_values(1)
                    if not existing_headers or existing_headers != headers:
                        # Clear first row and add correct headers
                        if existing_headers:
                            worksheet.delete_rows(1, 1)
                        worksheet.insert_row(headers, 1)
                except Exception as header_error:
                    # Try to add headers anyway
                    try:
                        worksheet.insert_row(headers, 1)
                    except:
                        pass
            else:
                # Sheet doesn't exist, create it
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
                worksheet.append_row(headers)
        
        return True
        
    except Exception as e:
        st.error(f"Error setting up sheets: {e}")
        return False

def get_worksheet_data(spreadsheet, sheet_name):
    """Get data from a specific worksheet"""
    try:
        # Try to find the sheet with case-insensitive matching
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        
        actual_sheet_name = existing_sheets_lower.get(sheet_name.lower(), sheet_name)
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        return pd.DataFrame()

def append_to_worksheet(spreadsheet, sheet_name, data_dict):
    """Append a row to a worksheet"""
    try:
        # Try to find the sheet with case-insensitive matching
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        
        actual_sheet_name = existing_sheets_lower.get(sheet_name.lower(), sheet_name)
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        
        # Get headers to ensure correct order
        headers = worksheet.row_values(1)
        
        # Create row in correct order, converting data types to native Python types
        row = []
        for header in headers:
            value = data_dict.get(header, '')
            # Convert numpy/pandas types to native Python types
            if hasattr(value, 'item'):  # numpy scalar
                value = value.item()
            elif hasattr(value, 'tolist'):  # numpy array
                value = value.tolist()
            elif str(type(value)).startswith('<class \'pandas'):  # pandas types
                value = str(value)
            row.append(value)
        
        worksheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Error adding data to {sheet_name}: {e}")
        return False

def update_worksheet_row(spreadsheet, sheet_name, row_id, updates):
    """Update a specific row in a worksheet"""
    try:
        # Try to find the sheet with case-insensitive matching
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        
        actual_sheet_name = existing_sheets_lower.get(sheet_name.lower(), sheet_name)
        
        worksheet = spreadsheet.worksheet(actual_sheet_name)
        data = worksheet.get_all_records()
        
        # Find the row to update
        for i, row in enumerate(data, start=2):  # Start at 2 because row 1 is headers
            if str(row.get('id', '')) == str(row_id):
                # Update specific cells
                for column, value in updates.items():
                    # Convert data types to native Python types
                    if hasattr(value, 'item'):  # numpy scalar
                        value = value.item()
                    elif hasattr(value, 'tolist'):  # numpy array
                        value = value.tolist()
                    elif str(type(value)).startswith('<class \'pandas'):  # pandas types
                        value = str(value)
                    
                    # Find column index
                    headers = worksheet.row_values(1)
                    if column in headers:
                        col_index = headers.index(column) + 1
                        worksheet.update_cell(i, col_index, value)
                return True
        return False
    except Exception as e:
        st.error(f"Error updating {sheet_name}: {e}")
        return False

def get_next_id(df):
    """Get the next available ID for a dataframe"""
    if df.empty or 'id' not in df.columns:
        return 1
    try:
        # Convert to native Python int to avoid serialization issues
        max_id = int(df['id'].astype(int).max())
        return max_id + 1 if pd.notna(max_id) else 1
    except:
        return 1

def add_player(spreadsheet, name):
    """Add a new player to the players sheet"""
    try:
        players_df = get_worksheet_data(spreadsheet, 'players')
        
        # Check if player already exists
        if not players_df.empty and name in players_df['name'].values:
            return False
        
        # Add new player
        new_id = get_next_id(players_df)
        player_data = {
            'id': new_id,
            'name': name,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return append_to_worksheet(spreadsheet, 'players', player_data)
    except Exception as e:
        st.error(f"Error adding player: {e}")
        return False

def get_players(spreadsheet):
    """Get all players from the players sheet"""
    return get_worksheet_data(spreadsheet, 'players')

def add_week(spreadsheet, week_number, season_year, total_games, week_date):
    """Add a new week to the weeks sheet"""
    try:
        weeks_df = get_worksheet_data(spreadsheet, 'weeks')
        
        # Check if week already exists for this season
        if not weeks_df.empty:
            weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
            weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
            existing = weeks_df[
                (weeks_df['season_year'] == season_year) & 
                (weeks_df['week_number'] == week_number)
            ]
            if not existing.empty:
                return False
        
        new_id = get_next_id(weeks_df)
        week_data = {
            'id': new_id,
            'week_number': week_number,
            'season_year': season_year,
            'total_games': total_games,
            'week_date': week_date.strftime('%Y-%m-%d'),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return append_to_worksheet(spreadsheet, 'weeks', week_data)
    except Exception as e:
        st.error(f"Error adding week: {e}")
        return False

def get_weeks(spreadsheet, season_year=None):
    """Get weeks from the weeks sheet with optional filters"""
    try:
        weeks_df = get_worksheet_data(spreadsheet, 'weeks')
        
        if weeks_df.empty:
            return pd.DataFrame()
        
        # Convert data types
        if 'season_year' in weeks_df.columns:
            weeks_df['season_year'] = pd.to_numeric(weeks_df['season_year'], errors='coerce')
        if 'week_number' in weeks_df.columns:
            weeks_df['week_number'] = pd.to_numeric(weeks_df['week_number'], errors='coerce')
        if 'id' in weeks_df.columns:
            weeks_df['id'] = pd.to_numeric(weeks_df['id'], errors='coerce')
        if 'total_games' in weeks_df.columns:
            weeks_df['total_games'] = pd.to_numeric(weeks_df['total_games'], errors='coerce')
        
        # Apply filters
        if season_year is not None:
            weeks_df = weeks_df[weeks_df['season_year'] == season_year]
        
        return weeks_df.sort_values(['season_year', 'week_number'])
    except Exception as e:
        st.error(f"Error getting weeks: {e}")
        return pd.DataFrame()

def add_or_update_result(spreadsheet, player_id, week_id, correct_guesses, status):
    """Add or update a player's result for a week"""
    try:
        results_df = get_worksheet_data(spreadsheet, 'results')
        
        # Check if result already exists
        if not results_df.empty:
            results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
            results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
            
            existing_mask = (results_df['player_id'] == player_id) & (results_df['week_id'] == week_id)
            if existing_mask.any():
                # Update existing result
                existing_result = results_df[existing_mask].iloc[0]
                updates = {
                    'correct_guesses': correct_guesses if status != 'omitted' else '',
                    'status': status
                }
                return update_worksheet_row(spreadsheet, 'results', existing_result['id'], updates)
        
        # Add new result
        new_id = get_next_id(results_df)
        result_data = {
            'id': new_id,
            'player_id': player_id,
            'week_id': week_id,
            'correct_guesses': correct_guesses if status != 'omitted' else '',
            'status': status,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return append_to_worksheet(spreadsheet, 'results', result_data)
    except Exception as e:
        st.error(f"Error adding result: {e}")
        return False

def get_results(spreadsheet):
    """Get all results from the results sheet"""
    try:
        results_df = get_worksheet_data(spreadsheet, 'results')
        
        if not results_df.empty:
            # Convert data types
            results_df['player_id'] = pd.to_numeric(results_df['player_id'], errors='coerce')
            results_df['week_id'] = pd.to_numeric(results_df['week_id'], errors='coerce')
            results_df['correct_guesses'] = pd.to_numeric(results_df['correct_guesses'], errors='coerce')
        
        return results_df
    except:
        return pd.DataFrame()

def calculate_standings(spreadsheet, season_year, week_number=None):
    """Calculate standings with both absolute and adjusted statistics"""
    try:
        players_df = get_players(spreadsheet)
        weeks_df = get_weeks(spreadsheet, season_year=season_year)
        results_df = get_results(spreadsheet)
        
        if players_df.empty or weeks_df.empty:
            return pd.DataFrame()
        
        # Filter weeks
        if week_number is not None:
            weeks_df = weeks_df[weeks_df['week_number'] == week_number]
        
        if weeks_df.empty:
            return pd.DataFrame()
        
        week_ids = weeks_df['id'].tolist()
        
        # Calculate standings for each player
        standings = []
        for _, player in players_df.iterrows():
            player_results = results_df[
                (results_df['player_id'] == player['id']) & 
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
                week_result = player_results[player_results['week_id'] == week['id']]
                
                if not week_result.empty:
                    result = week_result.iloc[0]
                    if result['status'] == 'omitted':
                        # For absolute stats, count as 0 correct out of total_games
                        total_possible_absolute += week['total_games']
                        # For adjusted stats, don't count this week
                    else:
                        # Count for both absolute and adjusted
                        correct = result['correct_guesses'] if pd.notna(result['correct_guesses']) else 0
                        total_correct_absolute += correct
                        total_possible_absolute += week['total_games']
                        total_correct_adjusted += correct
                        total_possible_adjusted += week['total_games']
                else:
                    # No result recorded - treat as 0 for absolute, skip for adjusted
                    total_possible_absolute += week['total_games']
            
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

def get_player_history(spreadsheet, player_name, season_year):
    """Get a player's history for a season"""
    try:
        players_df = get_players(spreadsheet)
        weeks_df = get_weeks(spreadsheet, season_year=season_year)
        results_df = get_results(spreadsheet)
        
        if players_df.empty or weeks_df.empty:
            return pd.DataFrame()
        
        # Get player ID
        player_row = players_df[players_df['name'] == player_name]
        if player_row.empty:
            return pd.DataFrame()
        
        player_id = player_row.iloc[0]['id']
        
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

st.title("🏆 Youth Home Sports Prediction Tracker")
st.markdown("Track weekly sports prediction results with omission handling")

# Sidebar for navigation
st.sidebar.title("Navigation")
page = st.sidebar.selectbox("Choose a page:", [
    "Enter Results", 
    "Weekly Standings", 
    "Season Standings",
    "Player History",
    "Manage Players & Weeks"
])

# Get current season year
current_season = st.sidebar.selectbox("Season Year:", [2024, 2025, 2026], index=1)

if page == "Enter Results":
    st.header("Enter Weekly Results")
    
    # Get available weeks for current season
    weeks_df = get_weeks(spreadsheet, season_year=current_season)
    if not weeks_df.empty:
        # Show week selector
        week_options = []
        for _, week in weeks_df.iterrows():
            week_options.append({
                'label': f"Week {week['week_number']} ({week['total_games']} games) - {week['week_date']}",
                'value': week['id'],
                'week_number': week['week_number'],
                'total_games': week['total_games']
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
            players_df = get_players(spreadsheet)
            results_df = get_results(spreadsheet)
            
            if not players_df.empty:
                # Create input form for each player
                results_to_save = {}
                
                st.write("Enter results for each player:")
                
                for _, player in players_df.iterrows():
                    with st.container():
                        col1, col2, col3 = st.columns([2, 2, 1])
                        
                        with col1:
                            st.write(f"**{player['name']}**")
                        
                        # Get existing result if any
                        existing_result = None
                        if not results_df.empty:
                            existing_mask = (
                                (results_df['player_id'] == player['id']) & 
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
                                key=f"status_{player['id']}",
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
                                    max_value=int(total_games),
                                    value=default_correct,
                                    key=f"correct_{player['id']}",
                                    label_visibility="collapsed"
                                )
                                results_to_save[player['id']] = (correct_guesses, status)
                            else:
                                st.write("—")
                                results_to_save[player['id']] = (0, status)
                        
                        st.divider()
                
                # Save button
                if st.button("Save All Results", type="primary"):
                    success_count = 0
                    total_count = len(results_to_save)
                    
                    for player_id, (correct_guesses, status) in results_to_save.items():
                        if add_or_update_result(spreadsheet, player_id, selected_week_id, correct_guesses, status):
                            success_count += 1
                    
                    if success_count == total_count:
                        st.success("All results saved successfully!")
                        st.rerun()
                    else:
                        st.warning(f"Saved {success_count} out of {total_count} results. Some may have failed.")
            else:
                st.warning("No players found. Please add players in the 'Manage Players & Weeks' section.")
    else:
        st.info("No weeks found for the current season. Please add weeks in the 'Manage Players & Weeks' section.")

elif page == "Weekly Standings":
    st.header("Weekly Standings")
    
    weeks_df = get_weeks(spreadsheet, season_year=current_season)
    if not weeks_df.empty:
        # Get weeks that have at least some results
        results_df = get_results(spreadsheet)
        weeks_with_results = []
        
        for _, week in weeks_df.iterrows():
            week_results = results_df[results_df['week_id'] == week['id']]
            if not week_results.empty:
                weeks_with_results.append(week['week_number'])
        
        if weeks_with_results:
            selected_week = st.selectbox("Select Week:", sorted(weeks_with_results))
            
            standings_df = calculate_standings(spreadsheet, current_season, week_number=selected_week)
            
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

elif page == "Season Standings":
    st.header("Season Standings")
    
    standings_df = calculate_standings(spreadsheet, current_season)
    
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
    
    players_df = get_players(spreadsheet)
    if not players_df.empty:
        selected_player = st.selectbox("Select Player:", players_df['name'].tolist(), key="player_history")
        
        history_df = get_player_history(spreadsheet, selected_player, current_season)
        
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

elif page == "Manage Players & Weeks":
    st.header("Manage Players & Weeks")
    
    tab1, tab2 = st.tabs(["Players", "Weeks"])
    
    with tab1:
        st.subheader("Manage Players")
        
        # Add new player
        with st.expander("Add New Player"):
            new_player_name = st.text_input("Player Name:")
            if st.button("Add Player"):
                if new_player_name.strip():
                    if add_player(spreadsheet, new_player_name.strip()):
                        st.success(f"Player '{new_player_name}' added successfully!")
                        st.rerun()
                    else:
                        st.error("Player already exists or error occurred!")
                else:
                    st.error("Please enter a valid name.")
        
        # Show existing players
        players_df = get_players(spreadsheet)
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
                if add_week(spreadsheet, week_number, current_season, total_games, week_date):
                    st.success("Week added successfully!")
                    st.rerun()
                else:
                    st.error("Week already exists for this season or error occurred!")
        
        # Show existing weeks
        weeks_df = get_weeks(spreadsheet, season_year=current_season)
        if not weeks_df.empty:
            st.subheader(f"Weeks for Season {current_season}")
            
            # Get results count for each week
            results_df = get_results(spreadsheet)
            weeks_display = weeks_df.copy()
            
            weeks_display['results_count'] = weeks_display['id'].apply(
                lambda week_id: len(results_df[results_df['week_id'] == week_id]) if not results_df.empty else 0
            )
            
            display_cols = ['week_number', 'week_date', 'total_games', 'results_count']
            weeks_display = weeks_display[display_cols]
            weeks_display.columns = ['Week #', 'Date', 'Total Games', 'Results Entered']
            
            st.dataframe(weeks_display, use_container_width=True, hide_index=True)
        else:
            st.info(f"No weeks found for season {current_season}.")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using Streamlit & Google Sheets | Youth Home Sports Prediction Tracker")
