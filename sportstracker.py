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
            'games': ['id', 'week_number', 'game_date', 'team1', 'team2', 'actual_winner', 'season_year', 'created_at'],
            'predictions': ['id', 'player_id', 'game_id', 'predicted_winner', 'is_correct', 'created_at']
        }
        
        existing_sheets = [sheet.title for sheet in spreadsheet.worksheets()]
        st.write(f"📋 Existing sheets: {existing_sheets}")
        
        # Create a case-insensitive mapping of existing sheets
        existing_sheets_lower = {sheet.lower(): sheet for sheet in existing_sheets}
        st.write(f"🔍 Case-insensitive mapping: {existing_sheets_lower}")
        
        for sheet_name, headers in required_sheets.items():
            if sheet_name.lower() in existing_sheets_lower:
                # Sheet exists (possibly with different case), use the actual name
                actual_sheet_name = existing_sheets_lower[sheet_name.lower()]
                st.write(f"📝 Found existing sheet: '{actual_sheet_name}' (looking for '{sheet_name}')")
                
                worksheet = spreadsheet.worksheet(actual_sheet_name)
                
                try:
                    existing_headers = worksheet.row_values(1)
                    if not existing_headers or existing_headers != headers:
                        st.write(f"🔧 Adding/updating headers for {actual_sheet_name}")
                        # Clear first row and add correct headers
                        if existing_headers:
                            worksheet.delete_rows(1, 1)
                        worksheet.insert_row(headers, 1)
                        st.write(f"✅ Updated headers for {actual_sheet_name}")
                    else:
                        st.write(f"✅ Headers already correct for {actual_sheet_name}")
                except Exception as header_error:
                    st.write(f"⚠️ Could not check headers for {actual_sheet_name}: {header_error}")
                    # Try to add headers anyway
                    try:
                        worksheet.insert_row(headers, 1)
                        st.write(f"✅ Added headers to {actual_sheet_name}")
                    except:
                        st.write(f"⚠️ Could not add headers to {actual_sheet_name}")
            else:
                # Sheet doesn't exist, create it
                st.write(f"➕ Creating sheet: {sheet_name}")
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
                worksheet.append_row(headers)
                st.write(f"✅ Created sheet: {sheet_name}")
        
        st.write("🎉 All sheets are ready!")
        return True
        
    except Exception as e:
        st.error(f"Error setting up sheets: {e}")
        st.write(f"🔍 Error type: {type(e).__name__}")
        import traceback
        st.code(traceback.format_exc())
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
        st.error(f"Error getting data from {sheet_name}: {e}")
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
        
        # Create row in correct order
        row = [data_dict.get(header, '') for header in headers]
        
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
        max_id = df['id'].astype(int).max()
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

def add_game(spreadsheet, week_number, game_date, team1, team2, season_year):
    """Add a new game to the games sheet"""
    try:
        games_df = get_worksheet_data(spreadsheet, 'games')
        
        new_id = get_next_id(games_df)
        game_data = {
            'id': new_id,
            'week_number': week_number,
            'game_date': game_date.strftime('%Y-%m-%d'),
            'team1': team1,
            'team2': team2,
            'actual_winner': '',
            'season_year': season_year,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return append_to_worksheet(spreadsheet, 'games', game_data)
    except Exception as e:
        st.error(f"Error adding game: {e}")
        return False

def get_games(spreadsheet, season_year=None, week_number=None):
    """Get games from the games sheet with optional filters"""
    try:
        games_df = get_worksheet_data(spreadsheet, 'games')
        
        if games_df.empty:
            return pd.DataFrame()
        
        # Convert data types
        if 'season_year' in games_df.columns:
            games_df['season_year'] = pd.to_numeric(games_df['season_year'], errors='coerce')
        if 'week_number' in games_df.columns:
            games_df['week_number'] = pd.to_numeric(games_df['week_number'], errors='coerce')
        if 'id' in games_df.columns:
            games_df['id'] = pd.to_numeric(games_df['id'], errors='coerce')
        
        # Apply filters
        if season_year is not None:
            games_df = games_df[games_df['season_year'] == season_year]
        if week_number is not None:
            games_df = games_df[games_df['week_number'] == week_number]
        
        return games_df.sort_values(['week_number', 'game_date'])
    except Exception as e:
        st.error(f"Error getting games: {e}")
        return pd.DataFrame()

def update_game_result(spreadsheet, game_id, actual_winner):
    """Update the actual winner of a game and recalculate predictions"""
    try:
        # Update games sheet
        success = update_worksheet_row(spreadsheet, 'games', game_id, {'actual_winner': actual_winner})
        
        if success:
            # Update predictions correctness
            predictions_df = get_worksheet_data(spreadsheet, 'predictions')
            if not predictions_df.empty:
                # Convert game_id to proper type for comparison
                predictions_df['game_id'] = pd.to_numeric(predictions_df['game_id'], errors='coerce')
                game_predictions = predictions_df[predictions_df['game_id'] == game_id]
                
                for _, prediction in game_predictions.iterrows():
                    is_correct = prediction['predicted_winner'] == actual_winner
                    update_worksheet_row(spreadsheet, 'predictions', prediction['id'], {'is_correct': is_correct})
        
        return success
    except Exception as e:
        st.error(f"Error updating game result: {e}")
        return False

def add_prediction(spreadsheet, player_id, game_id, predicted_winner):
    """Add or update a player's prediction for a game"""
    try:
        predictions_df = get_worksheet_data(spreadsheet, 'predictions')
        
        # Check if prediction already exists
        if not predictions_df.empty:
            predictions_df['player_id'] = pd.to_numeric(predictions_df['player_id'], errors='coerce')
            predictions_df['game_id'] = pd.to_numeric(predictions_df['game_id'], errors='coerce')
            
            existing_mask = (predictions_df['player_id'] == player_id) & (predictions_df['game_id'] == game_id)
            if existing_mask.any():
                # Update existing prediction
                existing_prediction = predictions_df[existing_mask].iloc[0]
                return update_worksheet_row(spreadsheet, 'predictions', existing_prediction['id'], 
                                          {'predicted_winner': predicted_winner, 'is_correct': ''})
        
        # Add new prediction
        new_id = get_next_id(predictions_df)
        prediction_data = {
            'id': new_id,
            'player_id': player_id,
            'game_id': game_id,
            'predicted_winner': predicted_winner,
            'is_correct': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return append_to_worksheet(spreadsheet, 'predictions', prediction_data)
    except Exception as e:
        st.error(f"Error adding prediction: {e}")
        return False

def get_weekly_standings(spreadsheet, season_year, week_number):
    """Get weekly standings for a specific week"""
    try:
        players_df = get_players(spreadsheet)
        games_df = get_games(spreadsheet, season_year=season_year, week_number=week_number)
        predictions_df = get_worksheet_data(spreadsheet, 'predictions')
        
        if players_df.empty or games_df.empty:
            return pd.DataFrame()
        
        # Filter games with results
        games_with_results = games_df[games_df['actual_winner'].notna() & (games_df['actual_winner'] != '')]
        
        if games_with_results.empty:
            return pd.DataFrame()
        
        # Convert data types
        if not predictions_df.empty:
            predictions_df['player_id'] = pd.to_numeric(predictions_df['player_id'], errors='coerce')
            predictions_df['game_id'] = pd.to_numeric(predictions_df['game_id'], errors='coerce')
            predictions_df['is_correct'] = predictions_df['is_correct'].astype(str).map({'True': True, 'False': False})
        
        # Calculate standings
        standings = []
        for _, player in players_df.iterrows():
            if not predictions_df.empty:
                player_predictions = predictions_df[
                    (predictions_df['player_id'] == player['id']) & 
                    (predictions_df['game_id'].isin(games_with_results['id']))
                ]
                
                total_predictions = len(player_predictions)
                if total_predictions > 0:
                    correct_predictions = player_predictions['is_correct'].sum()
                    incorrect_predictions = total_predictions - correct_predictions
                    accuracy_percentage = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
                else:
                    correct_predictions = 0
                    incorrect_predictions = 0
                    accuracy_percentage = 0
            else:
                total_predictions = 0
                correct_predictions = 0
                incorrect_predictions = 0
                accuracy_percentage = 0
            
            standings.append({
                'player_name': player['name'],
                'total_predictions': total_predictions,
                'correct_predictions': correct_predictions,
                'incorrect_predictions': incorrect_predictions,
                'accuracy_percentage': round(accuracy_percentage, 1)
            })
        
        standings_df = pd.DataFrame(standings)
        return standings_df.sort_values(['correct_predictions', 'accuracy_percentage'], ascending=False)
    except Exception as e:
        st.error(f"Error getting weekly standings: {e}")
        return pd.DataFrame()

def get_season_standings(spreadsheet, season_year):
    """Get season standings"""
    try:
        players_df = get_players(spreadsheet)
        games_df = get_games(spreadsheet, season_year=season_year)
        predictions_df = get_worksheet_data(spreadsheet, 'predictions')
        
        if players_df.empty or games_df.empty:
            return pd.DataFrame()
        
        # Filter games with results
        games_with_results = games_df[games_df['actual_winner'].notna() & (games_df['actual_winner'] != '')]
        
        if games_with_results.empty:
            return pd.DataFrame()
        
        # Convert data types
        if not predictions_df.empty:
            predictions_df['player_id'] = pd.to_numeric(predictions_df['player_id'], errors='coerce')
            predictions_df['game_id'] = pd.to_numeric(predictions_df['game_id'], errors='coerce')
            predictions_df['is_correct'] = predictions_df['is_correct'].astype(str).map({'True': True, 'False': False})
        
        # Calculate standings
        standings = []
        for _, player in players_df.iterrows():
            if not predictions_df.empty:
                player_predictions = predictions_df[
                    (predictions_df['player_id'] == player['id']) & 
                    (predictions_df['game_id'].isin(games_with_results['id']))
                ]
                
                total_predictions = len(player_predictions)
                if total_predictions > 0:
                    correct_predictions = player_predictions['is_correct'].sum()
                    incorrect_predictions = total_predictions - correct_predictions
                    accuracy_percentage = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
                else:
                    correct_predictions = 0
                    incorrect_predictions = 0
                    accuracy_percentage = 0
            else:
                total_predictions = 0
                correct_predictions = 0
                incorrect_predictions = 0
                accuracy_percentage = 0
            
            standings.append({
                'player_name': player['name'],
                'total_predictions': total_predictions,
                'correct_predictions': correct_predictions,
                'incorrect_predictions': incorrect_predictions,
                'accuracy_percentage': round(accuracy_percentage, 1)
            })
        
        standings_df = pd.DataFrame(standings)
        return standings_df.sort_values(['correct_predictions', 'accuracy_percentage'], ascending=False)
    except Exception as e:
        st.error(f"Error getting season standings: {e}")
        return pd.DataFrame()

def get_player_history(spreadsheet, player_name, season_year):
    """Get a player's prediction history"""
    try:
        players_df = get_players(spreadsheet)
        games_df = get_games(spreadsheet, season_year=season_year)
        predictions_df = get_worksheet_data(spreadsheet, 'predictions')
        
        if players_df.empty or games_df.empty:
            return pd.DataFrame()
        
        # Get player ID
        player_row = players_df[players_df['name'] == player_name]
        if player_row.empty:
            return pd.DataFrame()
        
        player_id = player_row.iloc[0]['id']
        
        if predictions_df.empty:
            return pd.DataFrame()
        
        # Convert data types
        predictions_df['player_id'] = pd.to_numeric(predictions_df['player_id'], errors='coerce')
        predictions_df['game_id'] = pd.to_numeric(predictions_df['game_id'], errors='coerce')
        games_df['id'] = pd.to_numeric(games_df['id'], errors='coerce')
        
        # Get player's predictions for the season
        player_predictions = predictions_df[predictions_df['player_id'] == player_id]
        
        # Merge with games data
        history = player_predictions.merge(games_df, left_on='game_id', right_on='id', suffixes=('_pred', '_game'))
        
        if history.empty:
            return pd.DataFrame()
        
        # Convert is_correct to proper boolean
        history['is_correct'] = history['is_correct'].astype(str).map({'True': True, 'False': False, '': None})
        
        # Select and rename columns
        history = history[[
            'week_number', 'game_date', 'team1', 'team2', 
            'predicted_winner', 'actual_winner', 'is_correct'
        ]].sort_values(['week_number', 'game_date'])
        
        return history
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
st.markdown("Track weekly sports predictions and maintain season-long leaderboards")

# Sidebar for navigation
st.sidebar.title("Navigation")
page = st.sidebar.selectbox("Choose a page:", [
    "Weekly Predictions", 
    "Game Results", 
    "Weekly Standings", 
    "Season Standings",
    "Player History",
    "Manage Players & Games"
])

# Get current season year
current_season = st.sidebar.selectbox("Season Year:", [2024, 2025, 2026], index=1)

if page == "Weekly Predictions":
    st.header("Weekly Predictions")
    
    # Get available weeks for current season
    games_df = get_games(spreadsheet, season_year=current_season)
    if not games_df.empty:
        available_weeks = sorted(games_df['week_number'].unique())
        selected_week = st.selectbox("Select Week:", available_weeks)
        
        # Get games for selected week
        week_games = games_df[games_df['week_number'] == selected_week]
        
        if not week_games.empty:
            players_df = get_players(spreadsheet)
            if not players_df.empty:
                selected_player = st.selectbox("Select Player:", players_df['name'].tolist())
                
                st.subheader(f"Week {selected_week} Games - {selected_player}")
                
                # Display games and collect predictions
                predictions = {}
                predictions_df = get_worksheet_data(spreadsheet, 'predictions')
                
                for idx, game in week_games.iterrows():
                    game_key = f"game_{game['id']}"
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**{game['team1']} vs {game['team2']}** - {game['game_date']}")
                    
                    with col2:
                        # Get existing prediction if any
                        player_id = players_df[players_df['name'] == selected_player]['id'].iloc[0]
                        existing_prediction = None
                        
                        if not predictions_df.empty:
                            predictions_df['player_id'] = pd.to_numeric(predictions_df['player_id'], errors='coerce')
                            predictions_df['game_id'] = pd.to_numeric(predictions_df['game_id'], errors='coerce')
                            existing_mask = (predictions_df['player_id'] == player_id) & (predictions_df['game_id'] == game['id'])
                            if existing_mask.any():
                                existing_prediction = predictions_df.loc[existing_mask, 'predicted_winner'].iloc[0]
                        
                        choice_index = 0
                        if existing_prediction == game['team2']:
                            choice_index = 1
                        
                        predicted_winner = st.radio(
                            f"Pick winner:",
                            [game['team1'], game['team2']],
                            key=game_key,
                            index=choice_index
                        )
                        predictions[game['id']] = predicted_winner
                
                if st.button("Save Predictions"):
                    # Get player ID
                    player_id = players_df[players_df['name'] == selected_player]['id'].iloc[0]
                    
                    # Save all predictions
                    success = True
                    for game_id, predicted_winner in predictions.items():
                        if not add_prediction(spreadsheet, player_id, game_id, predicted_winner):
                            success = False
                    
                    if success:
                        st.success("Predictions saved successfully!")
                        st.rerun()
                    else:
                        st.error("Error saving predictions. Please try again.")
            else:
                st.warning("No players found. Please add players in the 'Manage Players & Games' section.")
        else:
            st.info(f"No games scheduled for week {selected_week}")
    else:
        st.info("No games found for the current season. Please add games in the 'Manage Players & Games' section.")

elif page == "Game Results":
    st.header("Enter Game Results")
    
    games_df = get_games(spreadsheet, season_year=current_season)
    if not games_df.empty:
        # Filter games that don't have results yet
        pending_games = games_df[(games_df['actual_winner'].isna()) | (games_df['actual_winner'] == '')]
        
        if not pending_games.empty:
            st.subheader("Games Pending Results")
            
            for idx, game in pending_games.iterrows():
                with st.expander(f"Week {game['week_number']}: {game['team1']} vs {game['team2']} ({game['game_date']})"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        winner = st.radio(
                            "Actual Winner:",
                            [game['team1'], game['team2']],
                            key=f"result_{game['id']}"
                        )
                    
                    with col2:
                        if st.button("Save Result", key=f"save_{game['id']}"):
                            if update_game_result(spreadsheet, game['id'], winner):
                                st.success("Result saved!")
                                st.rerun()
                            else:
                                st.error("Error saving result. Please try again.")
        else:
            st.info("All games have results entered!")
        
        # Show completed games
        completed_games = games_df[(games_df['actual_winner'].notna()) & (games_df['actual_winner'] != '')]
        if not completed_games.empty:
            st.subheader("Completed Games")
            st.dataframe(
                completed_games[['week_number', 'game_date', 'team1', 'team2', 'actual_winner']],
                use_container_width=True
            )
    else:
        st.info("No games found for the current season.")

elif page == "Weekly Standings":
    st.header("Weekly Standings")
    
    games_df = get_games(spreadsheet, season_year=current_season)
    if not games_df.empty:
        # Get weeks that have completed games
        completed_games = games_df[(games_df['actual_winner'].notna()) & (games_df['actual_winner'] != '')]
        if not completed_games.empty:
            available_weeks = sorted(completed_games['week_number'].unique())
            selected_week = st.selectbox("Select Week:", available_weeks, key="weekly_standings_week")
            
            standings_df = get_weekly_standings(spreadsheet, current_season, selected_week)
            
            if not standings_df.empty:
                st.subheader(f"Week {selected_week} Standings")
                
                # Add rank column
                standings_df['rank'] = range(1, len(standings_df) + 1)
                standings_df = standings_df[['rank', 'player_name', 'correct_predictions', 
                                           'incorrect_predictions', 'total_predictions', 'accuracy_percentage']]
                
                # Display dataframe
                st.dataframe(standings_df, use_container_width=True, hide_index=True)
                
                # Create visualization
                if len(standings_df) > 0:
                    fig = px.bar(
                        standings_df.head(10), 
                        x='player_name', 
                        y='correct_predictions',
                        title=f'Week {selected_week} - Correct Predictions',
                        color='accuracy_percentage',
                        color_continuous_scale='RdYlGn'
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No predictions found for week {selected_week}")
        else:
            st.info("No completed games found for the current season.")
    else:
        st.info("No games found for the current season.")

elif page == "Season Standings":
    st.header("Season Standings")
    
    standings_df = get_season_standings(spreadsheet, current_season)
    
    if not standings_df.empty:
        st.subheader(f"Season {current_season} Overall Standings")
        
        # Add rank column
        standings_df['rank'] = range(1, len(standings_df) + 1)
        standings_df = standings_df[['rank', 'player_name', 'correct_predictions', 
                                   'incorrect_predictions', 'total_predictions', 'accuracy_percentage']]
        
        # Display dataframe
        st.dataframe(standings_df, use_container_width=True, hide_index=True)
        
        # Create visualizations
        if len(standings_df) > 0:
            col1, col2 = st.columns(2)
            
            with col1:
                fig1 = px.bar(
                    standings_df.head(10), 
                    x='player_name', 
                    y='correct_predictions',
                    title='Total Correct Predictions',
                    color='correct_predictions',
                    color_continuous_scale='Blues'
                )
                fig1.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                fig2 = px.scatter(
                    standings_df, 
                    x='total_predictions', 
                    y='accuracy_percentage',
                    size='correct_predictions',
                    hover_name='player_name',
                    title='Accuracy vs Total Predictions',
                    color='correct_predictions',
                    color_continuous_scale='RdYlGn'
                )
                st.plotly_chart(fig2, use_container_width=True)
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
            
            # Calculate weekly performance
            weekly_stats = history_df.groupby('week_number').agg({
                'is_correct': ['sum', 'count']
            }).reset_index()
            weekly_stats.columns = ['week_number', 'correct', 'total']
            weekly_stats['accuracy'] = (weekly_stats['correct'] / weekly_stats['total'] * 100).round(1)
            
            # Show weekly performance chart
            if len(weekly_stats) > 0:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=weekly_stats['week_number'],
                    y=weekly_stats['accuracy'],
                    mode='lines+markers',
                    name='Weekly Accuracy %',
                    line=dict(color='blue', width=3)
                ))
                fig.update_layout(
                    title=f"{selected_player}'s Weekly Performance",
                    xaxis_title="Week Number",
                    yaxis_title="Accuracy (%)",
                    yaxis=dict(range=[0, 100])
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Show detailed history
            st.subheader("Detailed Prediction History")
            history_display = history_df.copy()
            history_display['result'] = history_display['is_correct'].map({
                True: '✅ Correct', 
                False: '❌ Wrong', 
                None: '⏳ Pending'
            })
            
            st.dataframe(
                history_display[['week_number', 'game_date', 'team1', 'team2', 
                               'predicted_winner', 'actual_winner', 'result']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(f"No prediction history found for {selected_player} in season {current_season}.")
    else:
        st.info("No players found. Please add players first.")

elif page == "Manage Players & Games":
    st.header("Manage Players & Games")
    
    tab1, tab2 = st.tabs(["Players", "Games"])
    
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
        st.subheader("Manage Games")
        
        # Add new game
        with st.expander("Add New Game"):
            col1, col2 = st.columns(2)
            
            with col1:
                week_number = st.number_input("Week Number:", min_value=1, value=1)
                game_date = st.date_input("Game Date:", value=date.today())
            
            with col2:
                team1 = st.text_input("Team 1:")
                team2 = st.text_input("Team 2:")
            
            if st.button("Add Game"):
                if team1.strip() and team2.strip():
                    if add_game(spreadsheet, week_number, game_date, team1.strip(), team2.strip(), current_season):
                        st.success("Game added successfully!")
                        st.rerun()
                    else:
                        st.error("Error adding game. Please try again.")
                else:
                    st.error("Please enter both team names.")
        
        # Show existing games
        games_df = get_games(spreadsheet, season_year=current_season)
        if not games_df.empty:
            st.subheader(f"Games for Season {current_season}")
            display_games = games_df[['week_number', 'game_date', 'team1', 'team2', 'actual_winner']].copy()
            display_games['status'] = display_games['actual_winner'].apply(
                lambda x: 'Completed' if pd.notna(x) and x != '' else 'Pending'
            )
            st.dataframe(display_games, use_container_width=True, hide_index=True)
        else:
            st.info(f"No games found for season {current_season}.")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using Streamlit & Google Sheets | Youth Home Sports Prediction Tracker")
