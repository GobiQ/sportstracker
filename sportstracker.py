import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go

# Database setup and functions
def init_db():
    """Initialize the SQLite database with required tables"""
    conn = sqlite3.connect('sports_predictions.db')
    cursor = conn.cursor()
    
    # Players table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Games table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_number INTEGER NOT NULL,
            game_date DATE NOT NULL,
            team1 TEXT NOT NULL,
            team2 TEXT NOT NULL,
            actual_winner TEXT,
            season_year INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Predictions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            game_id INTEGER,
            predicted_winner TEXT NOT NULL,
            is_correct BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players (id),
            FOREIGN KEY (game_id) REFERENCES games (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_player(name):
    """Add a new player to the database"""
    conn = sqlite3.connect('sports_predictions.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO players (name) VALUES (?)', (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_players():
    """Get all players from the database"""
    conn = sqlite3.connect('sports_predictions.db')
    df = pd.read_sql_query('SELECT * FROM players ORDER BY name', conn)
    conn.close()
    return df

def add_game(week_number, game_date, team1, team2, season_year):
    """Add a new game to the database"""
    conn = sqlite3.connect('sports_predictions.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO games (week_number, game_date, team1, team2, season_year)
        VALUES (?, ?, ?, ?, ?)
    ''', (week_number, game_date, team1, team2, season_year))
    conn.commit()
    conn.close()

def get_games(season_year=None, week_number=None):
    """Get games from the database with optional filters"""
    conn = sqlite3.connect('sports_predictions.db')
    query = 'SELECT * FROM games'
    params = []
    
    if season_year or week_number:
        query += ' WHERE'
        conditions = []
        if season_year:
            conditions.append(' season_year = ?')
            params.append(season_year)
        if week_number:
            conditions.append(' week_number = ?')
            params.append(week_number)
        query += ' AND'.join(conditions)
    
    query += ' ORDER BY week_number, game_date'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def update_game_result(game_id, actual_winner):
    """Update the actual winner of a game and recalculate predictions"""
    conn = sqlite3.connect('sports_predictions.db')
    cursor = conn.cursor()
    
    # Update the game result
    cursor.execute('UPDATE games SET actual_winner = ? WHERE id = ?', (actual_winner, game_id))
    
    # Update prediction correctness
    cursor.execute('''
        UPDATE predictions 
        SET is_correct = (predicted_winner = ?)
        WHERE game_id = ?
    ''', (actual_winner, game_id))
    
    conn.commit()
    conn.close()

def add_prediction(player_id, game_id, predicted_winner):
    """Add or update a player's prediction for a game"""
    conn = sqlite3.connect('sports_predictions.db')
    cursor = conn.cursor()
    
    # Check if prediction already exists
    cursor.execute('SELECT id FROM predictions WHERE player_id = ? AND game_id = ?', 
                   (player_id, game_id))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute('''
            UPDATE predictions 
            SET predicted_winner = ?, is_correct = NULL
            WHERE player_id = ? AND game_id = ?
        ''', (predicted_winner, player_id, game_id))
    else:
        cursor.execute('''
            INSERT INTO predictions (player_id, game_id, predicted_winner)
            VALUES (?, ?, ?)
        ''', (player_id, game_id, predicted_winner))
    
    conn.commit()
    conn.close()

def get_weekly_standings(season_year, week_number):
    """Get weekly standings for a specific week"""
    conn = sqlite3.connect('sports_predictions.db')
    query = '''
        SELECT 
            p.name as player_name,
            COUNT(pr.id) as total_predictions,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) as correct_predictions,
            SUM(CASE WHEN pr.is_correct = 0 THEN 1 ELSE 0 END) as incorrect_predictions,
            CASE 
                WHEN COUNT(pr.id) > 0 
                THEN ROUND(SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(pr.id), 1)
                ELSE 0 
            END as accuracy_percentage
        FROM players p
        LEFT JOIN predictions pr ON p.id = pr.player_id
        LEFT JOIN games g ON pr.game_id = g.id
        WHERE g.season_year = ? AND g.week_number = ? AND g.actual_winner IS NOT NULL
        GROUP BY p.id, p.name
        ORDER BY correct_predictions DESC, accuracy_percentage DESC
    '''
    df = pd.read_sql_query(query, conn, params=(season_year, week_number))
    conn.close()
    return df

def get_season_standings(season_year):
    """Get season standings"""
    conn = sqlite3.connect('sports_predictions.db')
    query = '''
        SELECT 
            p.name as player_name,
            COUNT(pr.id) as total_predictions,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) as correct_predictions,
            SUM(CASE WHEN pr.is_correct = 0 THEN 1 ELSE 0 END) as incorrect_predictions,
            CASE 
                WHEN COUNT(pr.id) > 0 
                THEN ROUND(SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(pr.id), 1)
                ELSE 0 
            END as accuracy_percentage
        FROM players p
        LEFT JOIN predictions pr ON p.id = pr.player_id
        LEFT JOIN games g ON pr.game_id = g.id
        WHERE g.season_year = ? AND g.actual_winner IS NOT NULL
        GROUP BY p.id, p.name
        ORDER BY correct_predictions DESC, accuracy_percentage DESC
    '''
    df = pd.read_sql_query(query, conn, params=(season_year,))
    conn.close()
    return df

def get_player_history(player_name, season_year):
    """Get a player's prediction history"""
    conn = sqlite3.connect('sports_predictions.db')
    query = '''
        SELECT 
            g.week_number,
            g.game_date,
            g.team1,
            g.team2,
            pr.predicted_winner,
            g.actual_winner,
            pr.is_correct
        FROM predictions pr
        JOIN players p ON pr.player_id = p.id
        JOIN games g ON pr.game_id = g.id
        WHERE p.name = ? AND g.season_year = ?
        ORDER BY g.week_number, g.game_date
    '''
    df = pd.read_sql_query(query, conn, params=(player_name, season_year))
    conn.close()
    return df

# Initialize database
if not st.session_state.db_initialized:
    init_db()
    st.session_state.db_initialized = True

# Streamlit App Configuration
st.set_page_config(
    page_title="Sports Prediction Tracker",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state for better performance on Streamlit Cloud
if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False

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

# Get current season year (you can modify this logic)
current_season = st.sidebar.selectbox("Season Year:", [2024, 2025, 2026], index=1)

if page == "Weekly Predictions":
    st.header("Weekly Predictions")
    
    # Get available weeks for current season
    games_df = get_games(season_year=current_season)
    if not games_df.empty:
        available_weeks = sorted(games_df['week_number'].unique())
        selected_week = st.selectbox("Select Week:", available_weeks)
        
        # Get games for selected week
        week_games = games_df[games_df['week_number'] == selected_week]
        
        if not week_games.empty:
            players_df = get_players()
            if not players_df.empty:
                selected_player = st.selectbox("Select Player:", players_df['name'].tolist())
                
                st.subheader(f"Week {selected_week} Games - {selected_player}")
                
                # Display games and collect predictions
                predictions = {}
                for idx, game in week_games.iterrows():
                    game_key = f"game_{game['id']}"
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**{game['team1']} vs {game['team2']}** - {game['game_date']}")
                    
                    with col2:
                        # Get existing prediction if any
                        conn = sqlite3.connect('sports_predictions.db')
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT predicted_winner FROM predictions pr
                            JOIN players p ON pr.player_id = p.id
                            WHERE p.name = ? AND pr.game_id = ?
                        ''', (selected_player, game['id']))
                        existing_prediction = cursor.fetchone()
                        conn.close()
                        
                        default_choice = existing_prediction[0] if existing_prediction else None
                        choice_index = 0
                        if default_choice == game['team2']:
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
                    for game_id, predicted_winner in predictions.items():
                        add_prediction(player_id, game_id, predicted_winner)
                    
                    st.success("Predictions saved successfully!")
                    st.rerun()
            else:
                st.warning("No players found. Please add players in the 'Manage Players & Games' section.")
        else:
            st.info(f"No games scheduled for week {selected_week}")
    else:
        st.info("No games found for the current season. Please add games in the 'Manage Players & Games' section.")

elif page == "Game Results":
    st.header("Enter Game Results")
    
    games_df = get_games(season_year=current_season)
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
                            update_game_result(game['id'], winner)
                            st.success("Result saved!")
                            st.rerun()
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
    
    games_df = get_games(season_year=current_season)
    if not games_df.empty:
        # Get weeks that have completed games
        completed_games = games_df[games_df['actual_winner'].notna()]
        if not completed_games.empty:
            available_weeks = sorted(completed_games['week_number'].unique())
            selected_week = st.selectbox("Select Week:", available_weeks, key="weekly_standings_week")
            
            standings_df = get_weekly_standings(current_season, selected_week)
            
            if not standings_df.empty:
                st.subheader(f"Week {selected_week} Standings")
                
                # Add rank column
                standings_df['rank'] = range(1, len(standings_df) + 1)
                standings_df = standings_df[['rank', 'player_name', 'correct_predictions', 
                                           'incorrect_predictions', 'total_predictions', 'accuracy_percentage']]
                
                # Style the dataframe
                st.dataframe(
                    standings_df.style.format({'accuracy_percentage': '{:.1f}%'}),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Create visualization
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
    
    standings_df = get_season_standings(current_season)
    
    if not standings_df.empty:
        st.subheader(f"Season {current_season} Overall Standings")
        
        # Add rank column
        standings_df['rank'] = range(1, len(standings_df) + 1)
        standings_df = standings_df[['rank', 'player_name', 'correct_predictions', 
                                   'incorrect_predictions', 'total_predictions', 'accuracy_percentage']]
        
        # Style the dataframe
        st.dataframe(
            standings_df.style.format({'accuracy_percentage': '{:.1f}%'}),
            use_container_width=True,
            hide_index=True
        )
        
        # Create visualizations
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
    
    players_df = get_players()
    if not players_df.empty:
        selected_player = st.selectbox("Select Player:", players_df['name'].tolist(), key="player_history")
        
        history_df = get_player_history(selected_player, current_season)
        
        if not history_df.empty:
            st.subheader(f"{selected_player}'s Season {current_season} History")
            
            # Calculate weekly performance
            weekly_stats = history_df.groupby('week_number').agg({
                'is_correct': ['sum', 'count']
            }).reset_index()
            weekly_stats.columns = ['week_number', 'correct', 'total']
            weekly_stats['accuracy'] = (weekly_stats['correct'] / weekly_stats['total'] * 100).round(1)
            
            # Show weekly performance chart
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
                    if add_player(new_player_name.strip()):
                        st.success(f"Player '{new_player_name}' added successfully!")
                        st.rerun()
                    else:
                        st.error("Player already exists!")
                else:
                    st.error("Please enter a valid name.")
        
        # Show existing players
        players_df = get_players()
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
                    add_game(week_number, game_date, team1.strip(), team2.strip(), current_season)
                    st.success("Game added successfully!")
                    st.rerun()
                else:
                    st.error("Please enter both team names.")
        
        # Show existing games
        games_df = get_games(season_year=current_season)
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
st.markdown("Built with ❤️ using Streamlit | Youth Home Sports Prediction Tracker")
