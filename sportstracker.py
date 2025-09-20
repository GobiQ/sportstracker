import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection

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
    return st.connection("gsheets", type=GSheetsConnection)

def ensure_sheets_exist(conn):
    """Ensure all required sheets exist in the Google Sheet"""
    try:
        # Try to read each sheet, create if doesn't exist
        sheets_to_create = {
            'players': pd.DataFrame(columns=['id', 'name', 'created_at']),
            'games': pd.DataFrame(columns=['id', 'week_number', 'game_date', 'team1', 'team2', 'actual_winner', 'season_year', 'created_at']),
            'predictions': pd.DataFrame(columns=['id', 'player_id', 'game_id', 'predicted_winner', 'is_correct', 'created_at'])
        }
        
        for sheet_name, default_df in sheets_to_create.items():
            try:
                conn.read(worksheet=sheet_name)
            except:
                # Sheet doesn't exist, create it
                conn.create(worksheet=sheet_name, data=default_df)
                
    except Exception as e:
        st.error(f"Error setting up sheets: {e}")
        st.info("Please make sure you have a Google Sheet set up and the connection is properly configured.")

def get_next_id(df):
    """Get the next available ID for a dataframe"""
    if df.empty or 'id' not in df.columns:
        return 1
    return df['id'].max() + 1 if not df['id'].isna().all() else 1

def add_player(conn, name):
    """Add a new player to the players sheet"""
    try:
        players_df = conn.read(worksheet="players")
        
        # Check if player already exists
        if not players_df.empty and name in players_df['name'].values:
            return False
        
        # Add new player
        new_id = get_next_id(players_df)
        new_player = pd.DataFrame({
            'id': [new_id],
            'name': [name],
            'created_at': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        
        if players_df.empty:
            updated_df = new_player
        else:
            updated_df = pd.concat([players_df, new_player], ignore_index=True)
        
        conn.update(worksheet="players", data=updated_df)
        return True
    except Exception as e:
        st.error(f"Error adding player: {e}")
        return False

def get_players(conn):
    """Get all players from the players sheet"""
    try:
        return conn.read(worksheet="players")
    except:
        return pd.DataFrame(columns=['id', 'name', 'created_at'])

def add_game(conn, week_number, game_date, team1, team2, season_year):
    """Add a new game to the games sheet"""
    try:
        games_df = conn.read(worksheet="games")
        
        new_id = get_next_id(games_df)
        new_game = pd.DataFrame({
            'id': [new_id],
            'week_number': [week_number],
            'game_date': [game_date.strftime('%Y-%m-%d')],
            'team1': [team1],
            'team2': [team2],
            'actual_winner': [None],
            'season_year': [season_year],
            'created_at': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        
        if games_df.empty:
            updated_df = new_game
        else:
            updated_df = pd.concat([games_df, new_game], ignore_index=True)
        
        conn.update(worksheet="games", data=updated_df)
        return True
    except Exception as e:
        st.error(f"Error adding game: {e}")
        return False

def get_games(conn, season_year=None, week_number=None):
    """Get games from the games sheet with optional filters"""
    try:
        games_df = conn.read(worksheet="games")
        
        if games_df.empty:
            return pd.DataFrame(columns=['id', 'week_number', 'game_date', 'team1', 'team2', 'actual_winner', 'season_year', 'created_at'])
        
        # Apply filters
        if season_year is not None:
            games_df = games_df[games_df['season_year'] == season_year]
        if week_number is not None:
            games_df = games_df[games_df['week_number'] == week_number]
        
        return games_df.sort_values(['week_number', 'game_date'])
    except:
        return pd.DataFrame(columns=['id', 'week_number', 'game_date', 'team1', 'team2', 'actual_winner', 'season_year', 'created_at'])

def update_game_result(conn, game_id, actual_winner):
    """Update the actual winner of a game and recalculate predictions"""
    try:
        # Update games sheet
        games_df = conn.read(worksheet="games")
        games_df.loc[games_df['id'] == game_id, 'actual_winner'] = actual_winner
        conn.update(worksheet="games", data=games_df)
        
        # Update predictions correctness
        predictions_df = conn.read(worksheet="predictions")
        if not predictions_df.empty:
            mask = predictions_df['game_id'] == game_id
            predictions_df.loc[mask, 'is_correct'] = (predictions_df.loc[mask, 'predicted_winner'] == actual_winner)
            conn.update(worksheet="predictions", data=predictions_df)
        
        return True
    except Exception as e:
        st.error(f"Error updating game result: {e}")
        return False

def add_prediction(conn, player_id, game_id, predicted_winner):
    """Add or update a player's prediction for a game"""
    try:
        predictions_df = conn.read(worksheet="predictions")
        
        # Check if prediction already exists
        if not predictions_df.empty:
            existing_mask = (predictions_df['player_id'] == player_id) & (predictions_df['game_id'] == game_id)
            if existing_mask.any():
                # Update existing prediction
                predictions_df.loc[existing_mask, 'predicted_winner'] = predicted_winner
                predictions_df.loc[existing_mask, 'is_correct'] = None  # Will be calculated when game result is entered
                conn.update(worksheet="predictions", data=predictions_df)
                return True
        
        # Add new prediction
        new_id = get_next_id(predictions_df)
        new_prediction = pd.DataFrame({
            'id': [new_id],
            'player_id': [player_id],
            'game_id': [game_id],
            'predicted_winner': [predicted_winner],
            'is_correct': [None],
            'created_at': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        
        if predictions_df.empty:
            updated_df = new_prediction
        else:
            updated_df = pd.concat([predictions_df, new_prediction], ignore_index=True)
        
        conn.update(worksheet="predictions", data=updated_df)
        return True
    except Exception as e:
        st.error(f"Error adding prediction: {e}")
        return False

def get_weekly_standings(conn, season_year, week_number):
    """Get weekly standings for a specific week"""
    try:
        players_df = conn.read(worksheet="players")
        games_df = conn.read(worksheet="games")
        predictions_df = conn.read(worksheet="predictions")
        
        if players_df.empty or games_df.empty:
            return pd.DataFrame()
        
        # Filter games for the specific week and season with results
        week_games = games_df[
            (games_df['season_year'] == season_year) & 
            (games_df['week_number'] == week_number) & 
            (games_df['actual_winner'].notna())
        ]
        
        if week_games.empty:
            return pd.DataFrame()
        
        # Calculate standings
        standings = []
        for _, player in players_df.iterrows():
            player_predictions = predictions_df[
                (predictions_df['player_id'] == player['id']) & 
                (predictions_df['game_id'].isin(week_games['id']))
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

def get_season_standings(conn, season_year):
    """Get season standings"""
    try:
        players_df = conn.read(worksheet="players")
        games_df = conn.read(worksheet="games")
        predictions_df = conn.read(worksheet="predictions")
        
        if players_df.empty or games_df.empty:
            return pd.DataFrame()
        
        # Filter games for the season with results
        season_games = games_df[
            (games_df['season_year'] == season_year) & 
            (games_df['actual_winner'].notna())
        ]
        
        if season_games.empty:
            return pd.DataFrame()
        
        # Calculate standings
        standings = []
        for _, player in players_df.iterrows():
            player_predictions = predictions_df[
                (predictions_df['player_id'] == player['id']) & 
                (predictions_df['game_id'].isin(season_games['id']))
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

def get_player_history(conn, player_name, season_year):
    """Get a player's prediction history"""
    try:
        players_df = conn.read(worksheet="players")
        games_df = conn.read(worksheet="games")
        predictions_df = conn.read(worksheet="predictions")
        
        if players_df.empty or games_df.empty:
            return pd.DataFrame()
        
        # Get player ID
        player_row = players_df[players_df['name'] == player_name]
        if player_row.empty:
            return pd.DataFrame()
        
        player_id = player_row.iloc[0]['id']
        
        # Get player's predictions for the season
        player_predictions = predictions_df[predictions_df['player_id'] == player_id]
        season_games = games_df[games_df['season_year'] == season_year]
        
        # Merge data
        history = player_predictions.merge(season_games, left_on='game_id', right_on='id', suffixes=('_pred', '_game'))
        
        if history.empty:
            return pd.DataFrame()
        
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
conn = init_connection()

# Initialize session state for better performance
if 'sheets_initialized' not in st.session_state:
    with st.spinner("Setting up Google Sheets..."):
        ensure_sheets_exist(conn)
    st.session_state.sheets_initialized = True

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
    games_df = get_games(conn, season_year=current_season)
    if not games_df.empty:
        available_weeks = sorted(games_df['week_number'].unique())
        selected_week = st.selectbox("Select Week:", available_weeks)
        
        # Get games for selected week
        week_games = games_df[games_df['week_number'] == selected_week]
        
        if not week_games.empty:
            players_df = get_players(conn)
            if not players_df.empty:
                selected_player = st.selectbox("Select Player:", players_df['name'].tolist())
                
                st.subheader(f"Week {selected_week} Games - {selected_player}")
                
                # Display games and collect predictions
                predictions = {}
                predictions_df = conn.read(worksheet="predictions")
                
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
                        if not add_prediction(conn, player_id, game_id, predicted_winner):
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
    
    games_df = get_games(conn, season_year=current_season)
    if not games_df.empty:
        # Filter games that don't have results yet
        pending_games = games_df[games_df['actual_winner'].isna()]
        
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
                            if update_game_result(conn, game['id'], winner):
                                st.success("Result saved!")
                                st.rerun()
                            else:
                                st.error("Error saving result. Please try again.")
        else:
            st.info("All games have results entered!")
        
        # Show completed games
        completed_games = games_df[games_df['actual_winner'].notna()]
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
    
    games_df = get_games(conn, season_year=current_season)
    if not games_df.empty:
        # Get weeks that have completed games
        completed_games = games_df[games_df['actual_winner'].notna()]
        if not completed_games.empty:
            available_weeks = sorted(completed_games['week_number'].unique())
            selected_week = st.selectbox("Select Week:", available_weeks, key="weekly_standings_week")
            
            standings_df = get_weekly_standings(conn, current_season, selected_week)
            
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
    
    standings_df = get_season_standings(conn, current_season)
    
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
    
    players_df = get_players(conn)
    if not players_df.empty:
        selected_player = st.selectbox("Select Player:", players_df['name'].tolist(), key="player_history")
        
        history_df = get_player_history(conn, selected_player, current_season)
        
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
                    if add_player(conn, new_player_name.strip()):
                        st.success(f"Player '{new_player_name}' added successfully!")
                        st.rerun()
                    else:
                        st.error("Player already exists or error occurred!")
                else:
                    st.error("Please enter a valid name.")
        
        # Show existing players
        players_df = get_players(conn)
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
                    if add_game(conn, week_number, game_date, team1.strip(), team2.strip(), current_season):
                        st.success("Game added successfully!")
                        st.rerun()
                    else:
                        st.error("Error adding game. Please try again.")
                else:
                    st.error("Please enter both team names.")
        
        # Show existing games
        games_df = get_games(conn, season_year=current_season)
        if not games_df.empty:
            st.subheader(f"Games for Season {current_season}")
            display_games = games_df[['week_number', 'game_date', 'team1', 'team2', 'actual_winner']].copy()
            display_games['status'] = display_games['actual_winner'].apply(
                lambda x: 'Completed' if pd.notna(x) else 'Pending'
            )
            st.dataframe(display_games, use_container_width=True, hide_index=True)
        else:
            st.info(f"No games found for season {current_season}.")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using Streamlit & Google Sheets | Youth Home Sports Prediction Tracker")
