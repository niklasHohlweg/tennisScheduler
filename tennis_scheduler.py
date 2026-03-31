import streamlit as st
import itertools
from collections import Counter, defaultdict
import random
import math
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
from datetime import datetime
import time
import uuid
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import os
import io
import logging
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -------------- POSTGRESQL DATABASE CLASS --------------
class TennisDatabase:
    def __init__(self):
        # Initialize PostgreSQL connection from environment variables
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'tennis_scheduler'),
            'user': os.getenv('DB_USER', 'tennis_user'),
            'password': os.getenv('DB_PASSWORD', 'tennis_password')
        }

    def get_connection(self):
        """Create a new database connection"""
        return psycopg2.connect(**self.db_config)

    def init_database(self):
        """Check if tables exist and database is accessible"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM tournaments LIMIT 1")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            st.error(f"Database connection error: {e}")
            st.info("Please ensure the database is running and properly configured.")
            return False
    
    def get_or_create_user(self, email):
        """Get user by email or create if doesn't exist. Returns (user_dict, is_new_user)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if user exists
            cursor.execute("""
                SELECT id, email, created_at, last_login
                FROM users
                WHERE email = %s
            """, (email.lower(),))
            
            user = cursor.fetchone()
            is_new_user = False
            
            if user:
                # Update last login
                cursor.execute("""
                    UPDATE users SET last_login = NOW()
                    WHERE email = %s
                """, (email.lower(),))
                conn.commit()
                user_dict = dict(user)
                user_dict['id'] = str(user_dict['id'])
                logging.info(f"User logged in: {email}")
            else:
                # Create new user
                cursor.execute("""
                    INSERT INTO users (email, created_at, last_login)
                    VALUES (%s, NOW(), NOW())
                    RETURNING id, email, created_at, last_login
                """, (email.lower(),))
                user = cursor.fetchone()
                conn.commit()
                user_dict = dict(user)
                user_dict['id'] = str(user_dict['id'])
                is_new_user = True
                logging.info(f"New user created: {email}")
            
            cursor.close()
            conn.close()
            return user_dict, is_new_user
            
        except Exception as e:
            st.error(f"Error managing user: {e}")
            logging.error(f"Error in get_or_create_user: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            return None, False
    
    def get_user_stats(self, user_id):
        """Get statistics for a user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get tournament count
            cursor.execute("""
                SELECT COUNT(*) as tournament_count
                FROM tournaments
                WHERE owner_id = %s
            """, (user_id,))
            stats = cursor.fetchone()
            
            cursor.close()
            conn.close()
            return dict(stats) if stats else {'tournament_count': 0}
            
        except Exception as e:
            logging.error(f"Error in get_user_stats: {e}")
            if 'conn' in locals():
                conn.close()
            return {'tournament_count': 0}

    def create_tournament(self, name, teams, num_courts, players_per_team, mode, owner_id, owner_email):
        """Create a tournament for the logged-in user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Insert tournament
            cursor.execute("""
                INSERT INTO tournaments (name, teams, num_courts, players_per_team, mode, owner_id, owner_email)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (name, Json(teams), num_courts, players_per_team, mode, owner_id, owner_email))

            tournament_id = cursor.fetchone()['id']

            # Initialize team stats
            for team in teams:
                cursor.execute("""
                    INSERT INTO team_stats (tournament_id, team_name, matches_played, matches_won, 
                                          matches_lost, points_for, points_against, ranking_points)
                    VALUES (%s, %s, 0, 0, 0, 0, 0, 0)
                """, (tournament_id, team))

            conn.commit()
            cursor.close()
            conn.close()
            return str(tournament_id)

        except Exception as e:
            st.error(f"Error creating tournament: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            return None

    def save_matches(self, tournament_id, schedule):
        """Save the match schedule"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Clear existing matches for this tournament
            cursor.execute("DELETE FROM matches WHERE tournament_id = %s", (tournament_id,))

            # Insert new matches
            for round_num, round_data in enumerate(schedule, 1):
                if isinstance(round_data, dict):  # Time-based
                    matches = round_data['matches']
                    start_time = round_data.get('start_time', 0)
                    end_time = round_data.get('end_time', 0)
                else:
                    matches = round_data
                    start_time = (round_num - 1) * 20
                    end_time = start_time + 15

                for court_num, match in enumerate(matches, 1):
                    team1, team2 = match
                    cursor.execute("""
                        INSERT INTO matches (tournament_id, round_number, court_number, team1, team2,
                                           start_time_minutes, end_time_minutes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (tournament_id, round_num, court_num, team1, team2, start_time, end_time))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            st.error(f"Error saving matches: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()

    def get_tournaments(self, owner_id):
        """Get all tournaments for the current user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, name, teams, num_courts, players_per_team, mode, 
                       owner_id, owner_email, created_at
                FROM tournaments
                WHERE owner_id = %s
                ORDER BY created_at DESC
            """, (owner_id,))
            tournaments = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Convert to list of dicts and stringify UUIDs
            result = []
            for t in tournaments:
                t_dict = dict(t)
                t_dict['id'] = str(t_dict['id'])
                result.append(t_dict)
            return result
        except Exception as e:
            st.error(f"Error fetching tournaments: {e}")
            if 'conn' in locals():
                conn.close()
            return []

    def get_matches(self, tournament_id, owner_id):
        """Get all matches for a tournament (with owner check)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # First check if tournament belongs to user
            cursor.execute("""
                SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
            """, (tournament_id, owner_id))
            if not cursor.fetchone():
                cursor.close()
                conn.close()
                return []

            # Get matches
            cursor.execute("""
                SELECT id, tournament_id, round_number, court_number, team1, team2, 
                       winner, team1_score, team2_score, played_at, 
                       start_time_minutes, end_time_minutes
                FROM matches
                WHERE tournament_id = %s
                ORDER BY round_number, court_number
            """, (tournament_id,))
            matches = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Convert to list of dicts and stringify UUIDs
            result = []
            for m in matches:
                m_dict = dict(m)
                m_dict['id'] = str(m_dict['id'])
                m_dict['tournament_id'] = str(m_dict['tournament_id'])
                result.append(m_dict)
            return result
        except Exception as e:
            st.error(f"Error fetching matches: {e}")
            if 'conn' in locals():
                conn.close()
            return []

    def update_match_result(self, match_id, winner, team1_score, team2_score):
        """Update match result"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Update match
            cursor.execute("""
                UPDATE matches
                SET winner = %s, team1_score = %s, team2_score = %s, played_at = NOW()
                WHERE id = %s
                RETURNING tournament_id, team1, team2
            """, (winner, team1_score, team2_score, match_id))

            match_info = cursor.fetchone()
            if match_info:
                self._update_team_stats(
                    cursor,
                    match_info['tournament_id'],
                    match_info['team1'],
                    match_info['team2'],
                    winner,
                    team1_score,
                    team2_score
                )

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            st.error(f"Error updating match result: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()

    def _update_team_stats(self, cursor, tournament_id, team1, team2, winner, team1_score, team2_score):
        """Update team statistics"""
        # Update team1 stats
        cursor.execute("""
            SELECT * FROM team_stats 
            WHERE tournament_id = %s AND team_name = %s
        """, (tournament_id, team1))
        
        stats = cursor.fetchone()
        if stats:
            cursor.execute("""
                UPDATE team_stats
                SET matches_played = matches_played + 1,
                    points_for = points_for + %s,
                    points_against = points_against + %s,
                    matches_won = matches_won + %s,
                    matches_lost = matches_lost + %s,
                    ranking_points = ranking_points + %s
                WHERE tournament_id = %s AND team_name = %s
            """, (
                team1_score, 
                team2_score,
                1 if winner == team1 else 0,
                1 if winner == team2 else 0,
                3 if winner == team1 else (1 if winner == "Draw" else 0),
                tournament_id,
                team1
            ))

        # Update team2 stats
        cursor.execute("""
            SELECT * FROM team_stats 
            WHERE tournament_id = %s AND team_name = %s
        """, (tournament_id, team2))
        
        stats = cursor.fetchone()
        if stats:
            cursor.execute("""
                UPDATE team_stats
                SET matches_played = matches_played + 1,
                    points_for = points_for + %s,
                    points_against = points_against + %s,
                    matches_won = matches_won + %s,
                    matches_lost = matches_lost + %s,
                    ranking_points = ranking_points + %s
                WHERE tournament_id = %s AND team_name = %s
            """, (
                team2_score,
                team1_score,
                1 if winner == team2 else 0,
                1 if winner == team1 else 0,
                3 if winner == team2 else (1 if winner == "Draw" else 0),
                tournament_id,
                team2
            ))

    def get_ranking(self, tournament_id, owner_id):
        """Get tournament ranking"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Check if tournament belongs to user
            cursor.execute("""
                SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
            """, (tournament_id, owner_id))
            if not cursor.fetchone():
                cursor.close()
                conn.close()
                return []

            # Get team stats
            cursor.execute("""
                SELECT team_name, matches_played, matches_won, matches_lost,
                       points_for, points_against, ranking_points
                FROM team_stats
                WHERE tournament_id = %s
                ORDER BY ranking_points DESC, matches_won DESC
            """, (tournament_id,))
            
            stats_list = cursor.fetchall()
            cursor.close()
            conn.close()

            ranking = []
            for i, stats in enumerate(stats_list, 1):
                win_rate = (stats['matches_won'] / stats['matches_played'] * 100) if stats['matches_played'] > 0 else 0
                goal_diff = stats['points_for'] - stats['points_against']
                
                ranking.append({
                    "position": i,
                    "team": stats['team_name'],
                    "matches_played": stats['matches_played'],
                    "matches_won": stats['matches_won'],
                    "matches_lost": stats['matches_lost'],
                    "win_rate": win_rate,
                    "points_for": stats['points_for'],
                    "points_against": stats['points_against'],
                    "goal_difference": goal_diff,
                    "ranking_points": stats['ranking_points']
                })
            
            return ranking

        except Exception as e:
            st.error(f"Error fetching ranking: {e}")
            logging.error(f"Error in get_ranking: {e}")
            if 'conn' in locals():
                conn.close()
            return []
    
    def delete_tournament(self, tournament_id, owner_id):
        """Delete a tournament (with ownership check)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Verify ownership
            cursor.execute("""
                SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
            """, (tournament_id, owner_id))
            
            if not cursor.fetchone():
                cursor.close()
                conn.close()
                return False
            
            # Delete tournament (cascades to matches and team_stats)
            cursor.execute("DELETE FROM tournaments WHERE id = %s", (tournament_id,))
            conn.commit()
            cursor.close()
            conn.close()
            logging.info(f"Tournament {tournament_id} deleted by {owner_id}")
            return True
            
        except Exception as e:
            st.error(f"Error deleting tournament: {e}")
            logging.error(f"Error in delete_tournament: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            return False
    
    def update_tournament(self, tournament_id, owner_id, name):
        """Update tournament name"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE tournaments SET name = %s
                WHERE id = %s AND owner_id = %s
            """, (name, tournament_id, owner_id))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            st.error(f"Error updating tournament: {e}")
            logging.error(f"Error in update_tournament: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            return False
    
    def search_tournaments(self, owner_id, search_term=None, status=None, date_from=None, date_to=None):
        """Search tournaments with filters"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT id, name, teams, num_courts, players_per_team, mode, 
                       owner_id, owner_email, created_at
                FROM tournaments
                WHERE owner_id = %s
            """
            params = [owner_id]
            
            if search_term:
                query += " AND LOWER(name) LIKE LOWER(%s)"
                params.append(f"%{search_term}%")
            
            if date_from:
                query += " AND created_at >= %s"
                params.append(date_from)
            
            if date_to:
                query += " AND created_at <= %s"
                params.append(date_to)
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            tournaments = cursor.fetchall()
            cursor.close()
            conn.close()
            
            result = []
            for t in tournaments:
                t_dict = dict(t)
                t_dict['id'] = str(t_dict['id'])
                
                # Apply status filter if provided
                if status:
                    matches = self.get_matches(t_dict['id'], owner_id)
                    if matches:
                        played = len([m for m in matches if m['winner']])
                        total = len(matches)
                        
                        if status == "completed" and played == total:
                            result.append(t_dict)
                        elif status == "active" and 0 < played < total:
                            result.append(t_dict)
                        elif status == "not_started" and played == 0:
                            result.append(t_dict)
                    elif status == "not_started":
                        result.append(t_dict)
                else:
                    result.append(t_dict)
            
            return result
            
        except Exception as e:
            st.error(f"Error searching tournaments: {e}")
            logging.error(f"Error in search_tournaments: {e}")
            if 'conn' in locals():
                conn.close()
            return []
    
    def get_match_history(self, tournament_id, owner_id, team_name=None):
        """Get detailed match history"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Verify ownership
            cursor.execute("""
                SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
            """, (tournament_id, owner_id))
            
            if not cursor.fetchone():
                cursor.close()
                conn.close()
                return []
            
            query = """
                SELECT id, round_number, court_number, team1, team2,
                       winner, team1_score, team2_score, played_at,
                       start_time_minutes, end_time_minutes
                FROM matches
                WHERE tournament_id = %s
            """
            params = [tournament_id]
            
            if team_name:
                query += " AND (team1 = %s OR team2 = %s)"
                params.extend([team_name, team_name])
            
            query += " ORDER BY played_at DESC NULLS LAST, round_number, court_number"
            
            cursor.execute(query, params)
            matches = cursor.fetchall()
            cursor.close()
            conn.close()
            
            result = []
            for m in matches:
                m_dict = dict(m)
                m_dict['id'] = str(m_dict['id'])
                result.append(m_dict)
            return result
            
        except Exception as e:
            st.error(f"Error fetching match history: {e}")
            logging.error(f"Error in get_match_history: {e}")
            if 'conn' in locals():
                conn.close()
            return []
    
    def get_tournament_statistics(self, tournament_id, owner_id):
        """Get detailed tournament statistics"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Verify ownership
            cursor.execute("""
                SELECT * FROM tournaments WHERE id = %s AND owner_id = %s
            """, (tournament_id, owner_id))
            
            tournament = cursor.fetchone()
            if not tournament:
                cursor.close()
                conn.close()
                return None
            
            # Get match statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_matches,
                    COUNT(CASE WHEN winner IS NOT NULL THEN 1 END) as played_matches,
                    AVG(CASE WHEN winner IS NOT NULL THEN team1_score + team2_score END) as avg_total_score,
                    MAX(team1_score + team2_score) as highest_score,
                    MIN(CASE WHEN winner IS NOT NULL THEN team1_score + team2_score END) as lowest_score
                FROM matches
                WHERE tournament_id = %s
            """, (tournament_id,))
            
            match_stats = cursor.fetchone()
            
            # Get team statistics
            cursor.execute("""
                SELECT 
                    team_name,
                    matches_played,
                    matches_won,
                    matches_lost,
                    points_for,
                    points_against,
                    ranking_points,
                    CASE 
                        WHEN matches_played > 0 THEN CAST(matches_won AS FLOAT) / matches_played * 100 
                        ELSE 0 
                    END as win_percentage
                FROM team_stats
                WHERE tournament_id = %s
                ORDER BY ranking_points DESC
            """, (tournament_id,))
            
            team_stats = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return {
                'tournament': dict(tournament),
                'match_stats': dict(match_stats) if match_stats else {},
                'team_stats': [dict(ts) for ts in team_stats]
            }
            
        except Exception as e:
            st.error(f"Error fetching tournament statistics: {e}")
            logging.error(f"Error in get_tournament_statistics: {e}")
            if 'conn' in locals():
                conn.close()
            return None

# -------------- USER MANAGEMENT --------------
def init_user_session():
    """Initialize user session management"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
        st.session_state.user_email = None

def require_login():
    """Improved login system - email only"""
    st.title("🎾 Tennis Turnier System")
    
    if st.session_state.user_id is None:
        st.info("Bitte geben Sie Ihre E-Mail-Adresse ein, um fortzufahren.")
        
        with st.form("login_form"):
            email = st.text_input(
                "E-Mail Adresse", 
                placeholder="ihre.email@beispiel.de",
                help="Wenn Sie neu sind, wird automatisch ein Konto erstellt."
            )
            
            submitted = st.form_submit_button("Anmelden", type="primary", use_container_width=True)
            
            if submitted and email.strip():
                # Validate email format
                if '@' not in email or '.' not in email.split('@')[1]:
                    st.error("Bitte geben Sie eine gültige E-Mail-Adresse ein.")
                    st.stop()
                
                with st.spinner("Anmeldung läuft..."):
                    db = TennisDatabase()
                    user, is_new_user = db.get_or_create_user(email.strip())
                    
                    if user:
                        st.session_state.user_id = user['id']
                        st.session_state.user_email = user['email']
                        
                        # Show welcome message
                        if is_new_user:
                            st.success(f"Willkommen! Ihr Konto wurde erstellt.")
                        else:
                            st.success(f"Willkommen zurück!")
                        
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Fehler bei der Anmeldung. Bitte versuchen Sie es erneut.")
            elif submitted:
                st.error("Bitte geben Sie eine E-Mail-Adresse ein.")
        
        # Add some info text
        st.markdown("---")
        st.markdown("""
        ### Wie funktioniert die Anmeldung?
        - **Neue Benutzer**: Geben Sie Ihre E-Mail ein - Ihr Konto wird automatisch erstellt
        - **Bestehende Benutzer**: Geben Sie Ihre E-Mail ein - Sie werden automatisch eingeloggt
        - **Datenschutz**: Wir speichern nur Ihre E-Mail-Adresse
        
        Ihre Turniere sind mit Ihrer E-Mail-Adresse verknüpft und bleiben zwischen den Sitzungen erhalten.
        """)
        
        st.stop()

# -------------- TENNIS SCHEDULER --------------
class TennisScheduler:
    def __init__(self, num_courts, teams, players_per_team=4):
        self.num_courts = num_courts
        self.teams = teams if isinstance(teams, list) else [f"Team {i+1}" for i in range(teams)]
        self.num_teams = len(self.teams)
        self.matches_per_round = num_courts
        self.max_players_per_round = num_courts * 2
        self.players_per_team = players_per_team
        self.max_simultaneous_matches_per_team = players_per_team // 2

    def create_time_based_schedule(self, total_duration_minutes):
        minutes_per_round = 20
        max_rounds = total_duration_minutes // minutes_per_round
        if max_rounds == 0:
            return [], {"error": "Zu wenig Zeit für mindestens eine Runde"}

        schedule = []
        team_game_counts = Counter({team: 0 for team in self.teams})

        for round_num in range(1, max_rounds + 1):
            round_matches = self.create_optimal_time_round(team_game_counts, round_num)
            schedule.append({
                'round': round_num,
                'matches': round_matches,
                'start_time': (round_num - 1) * minutes_per_round,
                'end_time': (round_num - 1) * minutes_per_round + 15
            })
            for t1, t2 in round_matches:
                team_game_counts[t1] += 1
                team_game_counts[t2] += 1

        stats = self.get_time_based_stats(schedule, team_game_counts, total_duration_minutes)
        return schedule, stats

    def create_optimal_time_round(self, current_counts, round_num):
        round_matches = []
        team_matches_this_round = Counter()
        teams_by_count = sorted(self.teams, key=lambda t: current_counts[t])

        possible_matches = []
        for t1 in teams_by_count:
            for t2 in teams_by_count:
                if t1 != t2 and (t1, t2) not in possible_matches and (t2, t1) not in possible_matches:
                    possible_matches.append((t1, t2))
        possible_matches.sort(key=lambda m: current_counts[m[0]] + current_counts[m[1]])

        for match in possible_matches:
            if len(round_matches) >= self.num_courts:
                break
            t1, t2 = match
            if (team_matches_this_round[t1] < self.max_simultaneous_matches_per_team and
                team_matches_this_round[t2] < self.max_simultaneous_matches_per_team):
                round_matches.append(match)
                team_matches_this_round[t1] += 1
                team_matches_this_round[t2] += 1

        return round_matches

    def get_time_based_stats(self, schedule, team_counts, total_duration):
        total_matches = sum(len(r['matches']) for r in schedule)
        actual_duration = len(schedule) * 20
        stats = {
            'total_rounds': len(schedule),
            'total_matches': total_matches,
            'planned_duration': total_duration,
            'actual_duration': actual_duration,
            'efficiency': (actual_duration / total_duration * 100) if total_duration > 0 else 0,
            'team_counts': dict(team_counts),
            'avg_games_per_team': sum(team_counts.values()) / len(self.teams) if self.teams else 0,
            'min_games': min(team_counts.values()) if team_counts else 0,
            'max_games': max(team_counts.values()) if team_counts else 0,
        }
        stats['games_difference'] = stats['max_games'] - stats['min_games']
        stats['court_utilization'] = (total_matches / (len(schedule) * self.num_courts) * 100) if len(schedule) > 0 else 0
        return stats

    def create_round_robin_schedule(self):
        all_matches = list(itertools.combinations(self.teams, 2))
        total_matches = len(all_matches)
        rounds_needed = math.ceil(total_matches / self.matches_per_round)
        schedule = []
        remaining = all_matches.copy()
        random.shuffle(remaining)
        
        for round_num in range(1, rounds_needed + 1):
            round_matches = self.create_optimal_round(remaining, round_num)
            schedule.append(round_matches)
            for match in round_matches:
                if match in remaining:
                    remaining.remove(match)
        return schedule

    def create_optimal_round(self, available_matches, round_num):
        round_matches = []
        used = set()
        for match in available_matches.copy():
            a, b = match
            if a not in used and b not in used:
                if len(round_matches) < self.matches_per_round:
                    round_matches.append(match)
                    used.add(a)
                    used.add(b)
        return round_matches

    def create_single_round_distribution(self):
        if self.num_teams < 2:
            return []
        matches = []
        available = self.teams.copy()
        while len(available) >= 2 and len(matches) < self.matches_per_round:
            t1 = available.pop(0)
            t2 = available.pop(0)
            matches.append((t1, t2))
        return matches

# -------------- VIEW HELPER FUNCTIONS --------------
def show_match_distribution_preview(teams, schedule, mode_type):
    team_match_count = Counter()
    for round_data in schedule:
        matches = round_data['matches'] if isinstance(round_data, dict) else round_data
        for t1, t2 in matches:
            team_match_count[t1] += 1
            team_match_count[t2] += 1

    max_matches = max(team_match_count.values()) if team_match_count else 0
    min_matches = min(team_match_count.values()) if team_match_count else 0
    difference = max_matches - min_matches

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Gesamte Matches", sum(team_match_count.values()) // 2)
    with col2:
        st.metric("Durchschnitt Matches/Team", f"{sum(team_match_count.values()) / len(teams):.1f}")
    with col3:
        st.metric("Max-Min Differenz", difference)
    with col4:
        if difference <= 1:
            st.success("Sehr fair")
        elif difference <= 2:
            st.warning("Akzeptabel")
        else:
            st.error("Ungleich")

def show_team_match_overview(tournament_id, matches, teams):
    st.subheader("Match-Verteilung pro Team")
    team_match_count = Counter()
    team_played_count = Counter()
    
    for m in matches:
        team_match_count[m['team1']] += 1
        team_match_count[m['team2']] += 1
        if m['winner']:
            team_played_count[m['team1']] += 1
            team_played_count[m['team2']] += 1

    max_matches = max(team_match_count.values()) if team_match_count else 0
    min_matches = min(team_match_count.values()) if team_match_count else 0
    difference = max_matches - min_matches

    col1, col2, col3, col4 = st.columns(4)
    with col1: 
        st.metric("Max Matches/Team", max_matches)
    with col2: 
        st.metric("Min Matches/Team", min_matches)
    with col3: 
        st.metric("Differenz", difference)
    with col4:
        if difference <= 1: 
            st.success("Faire Verteilung")
        elif difference <= 2: 
            st.warning("Akzeptabel")
        else: 
            st.error("Ungleiche Verteilung")

def show_detailed_team_overview(tournament_id, matches, teams):
    st.subheader("Detaillierte Team-Übersicht")
    team_stats = {t: {'total_matches':0,'played_matches':0,'pending_matches':0,
                      'opponents':[],'upcoming_opponents':[],'next_match_round':None}
                  for t in teams}
    
    for m in matches:
        t1, t2 = m['team1'], m['team2']
        for t, opp in [(t1,t2),(t2,t1)]:
            team_stats[t]['total_matches'] += 1
            team_stats[t]['opponents'].append(opp)
            if m['winner']:
                team_stats[t]['played_matches'] += 1
            else:
                team_stats[t]['pending_matches'] += 1
                team_stats[t]['upcoming_opponents'].append(opp)
                if team_stats[t]['next_match_round'] is None:
                    team_stats[t]['next_match_round'] = m['round_number']

    overview = []
    for team in sorted(teams):
        s = team_stats[team]
        next_opps = ", ".join(s['upcoming_opponents'][:3])
        if len(s['upcoming_opponents']) > 3:
            next_opps += f" (+{len(s['upcoming_opponents'])-3} weitere)"
        overview.append({
            "Team": team,
            "Gesamt Matches": s['total_matches'],
            "Gespielt": s['played_matches'],
            "Ausstehend": s['pending_matches'],
            "Fortschritt %": f"{(s['played_matches']/s['total_matches']*100):.0f}%" if s['total_matches']>0 else "0%",
            "Nächste Runde": s['next_match_round'] if s['next_match_round'] else "Fertig",
            "Nächste Gegner": next_opps if next_opps else "Keine ausstehenden Matches"
        })
    
    df_overview = pd.DataFrame(overview)
    st.dataframe(df_overview, hide_index=True, use_container_width=True)

# -------------- EXPORT AND VISUALIZATION FUNCTIONS --------------
def export_tournament_to_csv(tournament_id, user_id, tournament_name):
    """Export tournament data to CSV"""
    db = TennisDatabase()
    
    # Get all data
    matches = db.get_matches(tournament_id, user_id)
    ranking = db.get_ranking(tournament_id, user_id)
    
    # Create CSV buffer
    output = io.StringIO()
    
    # Write tournament info
    output.write(f"Tournament: {tournament_name}\n")
    output.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # Write matches
    output.write("MATCHES\n")
    if matches:
        df_matches = pd.DataFrame(matches)
        df_matches.to_csv(output, index=False)
    output.write("\n\n")
    
    # Write rankings
    output.write("RANKINGS\n")
    if ranking:
        df_ranking = pd.DataFrame(ranking)
        df_ranking.to_csv(output, index=False)
    
    return output.getvalue()

def export_tournament_to_excel(tournament_id, user_id, tournament_name):
    """Export tournament data to Excel"""
    db = TennisDatabase()
    
    # Get all data
    matches = db.get_matches(tournament_id, user_id)
    ranking = db.get_ranking(tournament_id, user_id)
    
    # Create Excel file in memory
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Write matches
        if matches:
            df_matches = pd.DataFrame(matches)
            df_matches.to_excel(writer, sheet_name='Matches', index=False)
        
        # Write rankings
        if ranking:
            df_ranking = pd.DataFrame(ranking)
            df_ranking.to_excel(writer, sheet_name='Rankings', index=False)
        
        # Write summary
        summary_data = {
            'Tournament Name': [tournament_name],
            'Export Date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            'Total Matches': [len(matches) if matches else 0],
            'Played Matches': [len([m for m in matches if m['winner']]) if matches else 0],
            'Teams': [len(ranking) if ranking else 0]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
    
    output.seek(0)
    return output.getvalue()

def export_tournament_to_pdf(tournament_id, user_id, tournament_name):
    """Export tournament data to PDF"""
    db = TennisDatabase()
    matches = db.get_matches(tournament_id, user_id)
    ranking = db.get_ranking(tournament_id, user_id)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph(f"<b>{tournament_name}</b>", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 0.2*inch))
    
    # Date
    date_text = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
    story.append(date_text)
    story.append(Spacer(1, 0.3*inch))
    
    # Rankings Table
    if ranking:
        story.append(Paragraph("<b>Rankings</b>", styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        
        rank_data = [['Pos', 'Team', 'Played', 'Won', 'Lost', 'Points']]
        for r in ranking[:10]:  # Top 10
            rank_data.append([
                str(r['position']),
                r['team'][:20],
                str(r['matches_played']),
                str(r['matches_won']),
                str(r['matches_lost']),
                str(r['ranking_points'])
            ])
        
        rank_table = Table(rank_data)
        rank_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(rank_table)
        story.append(Spacer(1, 0.3*inch))
    
    # Matches Table
    if matches:
        story.append(Paragraph("<b>Recent Matches</b>", styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        
        match_data = [['Rnd', 'Court', 'Team 1', 'Team 2', 'Score', 'Winner']]
        for m in matches[:20]:  # First 20 matches
            score = f"{m['team1_score']}:{m['team2_score']}" if m['winner'] else "TBD"
            winner = m['winner'][:15] if m['winner'] else "-"
            match_data.append([
                str(m['round_number']),
                str(m['court_number']),
                m['team1'][:15],
                m['team2'][:15],
                score,
                winner
            ])
        
        match_table = Table(match_data)
        match_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(match_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def show_advanced_analytics(tournament_id, user_id):
    """Show advanced analytics with charts"""
    db = TennisDatabase()
    stats = db.get_tournament_statistics(tournament_id, user_id)
    
    if not stats:
        st.info("No statistics available.")
        return
    
    st.subheader("📊 Advanced Analytics")
    
    team_stats = stats['team_stats']
    match_stats = stats['match_stats']
    
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Matches", match_stats.get('total_matches', 0))
    with col2:
        st.metric("Played", match_stats.get('played_matches', 0))
    with col3:
        avg_score = match_stats.get('avg_total_score', 0)
        st.metric("Avg Total Score", f"{avg_score:.1f}" if avg_score else "0")
    with col4:
        st.metric("Highest Score", match_stats.get('highest_score', 0) or 0)
    
    # Charts
    if team_stats:
        col1, col2 = st.columns(2)
        
        with col1:
            # Win percentage chart
            df_wins = pd.DataFrame(team_stats)
            fig_wins = px.bar(
                df_wins,
                x='team_name',
                y='win_percentage',
                title='Win Percentage by Team',
                labels={'team_name': 'Team', 'win_percentage': 'Win %'},
                color='win_percentage',
                color_continuous_scale='RdYlGn'
            )
            fig_wins.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_wins, use_container_width=True)
        
        with col2:
            # Points scored vs conceded
            df_points = pd.DataFrame(team_stats)
            fig_points = go.Figure()
            fig_points.add_trace(go.Bar(
                name='Points For',
                x=df_points['team_name'],
                y=df_points['points_for'],
                marker_color='lightblue'
            ))
            fig_points.add_trace(go.Bar(
                name='Points Against',
                x=df_points['team_name'],
                y=df_points['points_against'],
                marker_color='lightcoral'
            ))
            fig_points.update_layout(
                title='Points For vs Against',
                xaxis_tickangle=-45,
                barmode='group',
                xaxis_title='Team',
                yaxis_title='Points'
            )
            st.plotly_chart(fig_points, use_container_width=True)
        
        # Ranking points distribution
        fig_rank = px.pie(
            df_points,
            values='ranking_points',
            names='team_name',
            title='Ranking Points Distribution'
        )
        st.plotly_chart(fig_rank, use_container_width=True)
        
        # Performance table
        st.subheader("Detailed Performance Metrics")
        perf_data = []
        for ts in team_stats:
            goal_diff = ts['points_for'] - ts['points_against']
            perf_data.append({
                'Team': ts['team_name'],
                'Win %': f"{ts['win_percentage']:.1f}%",
                'Matches': ts['matches_played'],
                'W-L': f"{ts['matches_won']}-{ts['matches_lost']}",
                'Goals': f"{ts['points_for']}-{ts['points_against']}",
                'Goal Diff': f"{goal_diff:+d}",
                'Rank Points': ts['ranking_points']
            })
        
        df_perf = pd.DataFrame(perf_data)
        st.dataframe(df_perf, hide_index=True, use_container_width=True)

# -------------- MAIN APPLICATION FUNCTIONS --------------
def show_user_dashboard(user_id):
    """Show user dashboard with tournament overview"""
    st.header("Mein Dashboard")
    db = TennisDatabase()
    tournaments = db.get_tournaments(user_id)
    
    if not tournaments:
        st.info("Sie haben noch keine Turniere erstellt. Erstellen Sie Ihr erstes Turnier!")
        return

    # Overview metrics
    total_tournaments = len(tournaments)
    total_matches = sum(len(db.get_matches(t['id'], user_id)) for t in tournaments)
    completed_tournaments = 0
    active_tournaments = 0
    
    for t in tournaments:
        matches = db.get_matches(t['id'], user_id)
        if matches:
            played_matches = len([m for m in matches if m['winner']])
            if played_matches == len(matches):
                completed_tournaments += 1
            elif played_matches > 0:
                active_tournaments += 1

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Gesamt Turniere", total_tournaments)
    with col2:
        st.metric("Aktive Turniere", active_tournaments)
    with col3:
        st.metric("Abgeschlossen", completed_tournaments)
    with col4:
        st.metric("Gesamt Matches", total_matches)

    # Recent tournaments
    st.subheader("Ihre Turniere")
    for t in tournaments[:5]:  # Show last 5 tournaments
        created_date = t['created_at'].strftime('%Y-%m-%d') if hasattr(t['created_at'], 'strftime') else str(t['created_at'])[:10]
        with st.expander(f"{t['name']} ({created_date})", expanded=False):
            matches = db.get_matches(t['id'], user_id)
            played_matches = len([m for m in matches if m['winner']]) if matches else 0
            total_matches = len(matches) if matches else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Teams", len(t['teams']))
            with col2:
                st.metric("Modus", t['mode'].split()[0])
            with col3:
                st.metric("Matches", f"{played_matches}/{total_matches}")
            with col4:
                progress = (played_matches / total_matches * 100) if total_matches > 0 else 0
                if progress == 100:
                    st.success("Abgeschlossen")
                elif progress > 0:
                    st.info(f"{progress:.0f}% gespielt")
                else:
                    st.warning("Nicht gestartet")
            
            # Show current ranking leader if tournament has started
            if played_matches > 0:
                ranking = db.get_ranking(t['id'], user_id)
                if ranking and ranking[0]['matches_played'] > 0:
                    st.markdown(f"**Führend:** {ranking[0]['team']} ({ranking[0]['ranking_points']} Punkte)")

def create_new_tournament(user_id, user_email):
    st.header("Neues Turnier erstellen")
    
    # Teams configuration
    with st.container():
        st.markdown("### Schritt 1: Teams konfigurieren")
        col1, col2 = st.columns([1, 2])
        with col1:
            input_method = st.radio("", ["Anzahl Teams", "Team-Namen eingeben"])
        with col2:
            if input_method == "Anzahl Teams":
                num_teams = st.slider("Wie viele Teams nehmen teil?", 2, 20, 8, 1)
                teams = [f"Team {i+1}" for i in range(num_teams)]
            else:
                team_names = st.text_area("Team-Namen (eine Zeile pro Team):",
                                          value="Team A\nTeam B\nTeam C\nTeam D\nTeam E\nTeam F\nTeam G\nTeam H",
                                          height=180)
                teams = [x.strip() for x in team_names.splitlines() if x.strip()]

    st.markdown("---")

    with st.container():
        st.markdown("### Schritt 2: Turnier-Details")
        with st.form("tournament_config_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                tournament_name = st.text_input("Turnier Name",
                                                value=f"Tennis Turnier {datetime.now().strftime('%d.%m.%Y')}")
                num_courts = st.select_slider("Anzahl Tennisplätze", options=list(range(1, 11)), value=4)
                players_per_team = st.select_slider("Spieler pro Team", options=[2,3,4,5,6,7,8], value=4)
            with col2:
                mode = st.selectbox("Modus", ["Zeitbasierte Planung", "Vollständiges Turnier (Round-Robin)", "Einzelne Runde"])
                if mode == "Zeitbasierte Planung":
                    time_mode = st.radio("Zeit-Eingabe:", ["Stunden/Minuten", "Minuten"], horizontal=True)
                    if time_mode == "Stunden/Minuten":
                        c1, c2 = st.columns(2)
                        with c1: hours = st.number_input("Stunden", 0, 12, 2, 1)
                        with c2: minutes = st.number_input("Minuten", 0, 59, 0, 15)
                        total_minutes = hours*60 + minutes
                    else:
                        total_minutes = st.slider("Gesamtdauer (Minuten)", 20, 480, 120, 20)

            submitted = st.form_submit_button("Turnier erstellen und starten!", type="primary", use_container_width=True)

        if submitted:
            if len(teams) < 2 or not tournament_name.strip():
                st.error("Mindestens 2 Teams und ein Turnier-Name sind erforderlich")
                return

            with st.spinner("Turnier wird erstellt..."):
                db = TennisDatabase()
                tid = db.create_tournament(
                    tournament_name.strip(), teams, num_courts, players_per_team, mode, owner_id=user_id, owner_email=user_email
                )
                
                if tid:
                    scheduler = TennisScheduler(num_courts, teams, players_per_team)

                    if mode == "Zeitbasierte Planung":
                        schedule, stats = scheduler.create_time_based_schedule(total_minutes)
                        if "error" not in stats:
                            db.save_matches(tid, schedule)
                            st.success(f"Turnier '{tournament_name}' erstellt!")
                            st.balloons()
                            show_match_distribution_preview(teams, schedule, "time_based")
                    elif mode == "Vollständiges Turnier (Round-Robin)":
                        schedule = scheduler.create_round_robin_schedule()
                        db.save_matches(tid, schedule)
                        st.success(f"Turnier '{tournament_name}' erstellt!")
                        st.balloons()
                        show_match_distribution_preview(teams, schedule, "round_robin")
                    else:
                        matches = scheduler.create_single_round_distribution()
                        schedule = [matches]
                        db.save_matches(tid, schedule)
                        st.success("Einzelrunde erstellt!")

def manage_tournaments(user_id):
    st.header("Turnier Verwaltung")
    db = TennisDatabase()
    
    # Search and filter section
    with st.expander("🔍 Suchen & Filtern", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            search_term = st.text_input("Turnier suchen", placeholder="Name eingeben...")
        with col2:
            status_filter = st.selectbox("Status", ["Alle", "Nicht gestartet", "Aktiv", "Abgeschlossen"])
        with col3:
            date_from = st.date_input("Von Datum", value=None)
        
        status_map = {
            "Alle": None,
            "Nicht gestartet": "not_started",
            "Aktiv": "active",
            "Abgeschlossen": "completed"
        }
        
        tournaments = db.search_tournaments(
            user_id,
            search_term if search_term else None,
            status_map[status_filter],
            date_from if date_from else None,
            None
        )
    
    if not tournaments:
        tournaments = db.get_tournaments(user_id)
    
    if not tournaments:
        st.info("Noch keine Turniere erstellt. Gehe zu 'Neues Turnier'.")
        return

    # Show user's tournament summary
    col1, col2 = st.columns([2, 1])
    with col2:
        st.metric("Gefundene Turniere", len(tournaments))
        active_count = 0
        for t in tournaments:
            matches = db.get_matches(t['id'], user_id)
            if matches:
                played = len([m for m in matches if m['winner']])
                if 0 < played < len(matches):
                    active_count += 1
        st.metric("Aktive Turniere", active_count)

    with col1:
        tournament_options = {f"{t['name']} ({t['created_at'].strftime('%Y-%m-%d') if hasattr(t['created_at'], 'strftime') else str(t['created_at'])[:10]})": t['id'] for t in tournaments}
        selected_name = st.selectbox("Turnier auswählen:", list(tournament_options.keys()))
    
    if selected_name:
        tournament_id = tournament_options[selected_name]
        tournament = next(t for t in tournaments if t['id'] == tournament_id)
        
        # Tournament header with actions
        col_name, col_actions = st.columns([2, 1])
        with col_name:
            st.subheader(f"{tournament['name']}")
        with col_actions:
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("✏️ Umbenennen", key="rename_btn"):
                    st.session_state.show_rename = True
            with col_btn2:
                if st.button("🗑️ Löschen", key="delete_btn", type="secondary"):
                    st.session_state.show_delete_confirm = True
        
        # Rename dialog
        if st.session_state.get('show_rename', False):
            with st.form("rename_form"):
                new_name = st.text_input("Neuer Name", value=tournament['name'])
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Speichern", type="primary"):
                        if db.update_tournament(tournament_id, user_id, new_name):
                            st.success("Turnier umbenannt!")
                            st.session_state.show_rename = False
                            st.rerun()
                with col2:
                    if st.form_submit_button("Abbrechen"):
                        st.session_state.show_rename = False
                        st.rerun()
        
        # Delete confirmation dialog
        if st.session_state.get('show_delete_confirm', False):
            st.warning("⚠️ Warnung: Diese Aktion kann nicht rückgängig gemacht werden!")
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Ja, Turnier löschen", type="primary", key="confirm_delete"):
                    if db.delete_tournament(tournament_id, user_id):
                        st.success("Turnier gelöscht!")
                        st.session_state.show_delete_confirm = False
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Fehler beim Löschen.")
            with col2:
                if st.button("Abbrechen", key="cancel_delete"):
                    st.session_state.show_delete_confirm = False
                    st.rerun()
        
        st.markdown("---")
        
        # Tournament info
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Teams", len(tournament['teams']))
        with col2: st.metric("Plätze", tournament['num_courts'])
        with col3: st.metric("Spieler/Team", tournament['players_per_team'])
        with col4: st.metric("Modus", tournament['mode'])

        matches = db.get_matches(tournament_id, user_id)
        
        if matches:
            # Progress indicator
            played_matches = len([m for m in matches if m['winner']])
            total_matches = len(matches)
            progress = played_matches / total_matches if total_matches > 0 else 0
            
            st.progress(progress)
            st.caption(f"Fortschritt: {played_matches}/{total_matches} Matches gespielt ({progress*100:.0f}%)")
            
            # Export buttons
            st.markdown("### 📥 Export")
            col1, col2, col3 = st.columns(3)
            with col1:
                csv_data = export_tournament_to_csv(tournament_id, user_id, tournament['name'])
                st.download_button(
                    label="📄 Export CSV",
                    data=csv_data,
                    file_name=f"{tournament['name']}_export.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col2:
                excel_data = export_tournament_to_excel(tournament_id, user_id, tournament['name'])
                st.download_button(
                    label="📊 Export Excel",
                    data=excel_data,
                    file_name=f"{tournament['name']}_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            with col3:
                pdf_data = export_tournament_to_pdf(tournament_id, user_id, tournament['name'])
                st.download_button(
                    label="📑 Export PDF",
                    data=pdf_data,
                    file_name=f"{tournament['name']}_export.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            
            st.markdown("---")
            
            show_team_match_overview(tournament_id, matches, tournament['teams'])
            st.markdown("---")
            
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["Ergebnisse eintragen", "Spielplan", "Aktuelles Ranking", "Team-Übersicht", "Analytics"])
            with tab1: 
                enter_match_results(tournament_id, matches, user_id)
            with tab2: 
                show_match_schedule(matches, tournament)
            with tab3: 
                show_tournament_ranking(tournament_id, user_id)
            with tab4: 
                show_detailed_team_overview(tournament_id, matches, tournament['teams'])
            with tab5:
                show_advanced_analytics(tournament_id, user_id)
        else:
            st.info("Keine Matches gefunden.")

def enter_match_results(tournament_id, matches, user_id):
    st.subheader("Match-Ergebnisse eintragen")
    db = TennisDatabase()
    
    unplayed = [m for m in matches if not m['winner']]
    played = [m for m in matches if m['winner']]

    col1, col2 = st.columns([2, 1])
    with col2:
        st.metric("Offene Matches", len(unplayed))
        st.metric("Gespielte Matches", len(played))

    with col1:
        if not unplayed:
            st.success("Alle Matches wurden gespielt!")
            return

        for m in unplayed[:5]:  # Show first 5 unplayed matches
            st.markdown(f"**Platz {m['court_number']}:** {m['team1']} vs {m['team2']}")
            c1, c_vs, c2, c3 = st.columns([2, 0.5, 2, 2])
            with c1:
                s1 = st.number_input(f"Punkte {m['team1']}", 0, 100, 0, key=f"s1_{m['id']}")
            with c_vs:
                st.markdown("**:**")
            with c2:
                s2 = st.number_input(f"Punkte {m['team2']}", 0, 100, 0, key=f"s2_{m['id']}")
            with c3:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button(f"{m['team1'][:8]} gewinnt", key=f"w1_{m['id']}"):
                        db.update_match_result(m['id'], m['team1'], s1, s2)
                        st.success(f"{m['team1']} gewinnt!")
                        st.rerun()
                with b2:
                    if st.button(f"{m['team2'][:8]} gewinnt", key=f"w2_{m['id']}"):
                        db.update_match_result(m['id'], m['team2'], s1, s2)
                        st.success(f"{m['team2']} gewinnt!")
                        st.rerun()
            st.markdown("---")

def show_match_schedule(matches, tournament):
    st.subheader("Spielplan")
    if matches:
        df_data = []
        for m in matches:
            status = "Gespielt" if m['winner'] else "Ausstehend"
            result = ""
            if m['winner']:
                result = f"{m['team1_score']}:{m['team2_score']} (Sieger: {m['winner']})"
            
            df_data.append({
                "Status": status,
                "Runde": m['round_number'],
                "Platz": m['court_number'],
                "Team 1": m['team1'],
                "Team 2": m['team2'],
                "Ergebnis": result
            })
        
        st.dataframe(pd.DataFrame(df_data), hide_index=True, use_container_width=True)

def show_tournament_ranking(tournament_id, user_id):
    st.subheader("Aktuelles Ranking")
    db = TennisDatabase()
    ranking = db.get_ranking(tournament_id, user_id)
    
    if not ranking:
        st.info("Noch keine Spiele gespielt.")
        return

    # Show top 3
    if len(ranking) >= 1 and ranking[0]['matches_played'] > 0:
        col1, col2, col3 = st.columns(3)
        with col2:
            st.markdown("### 1. Platz")
            st.markdown(f"**{ranking[0]['team']}**")
            st.markdown(f"{ranking[0]['ranking_points']} Punkte")

    # Show full ranking table
    table_data = []
    for t in ranking:
        table_data.append({
            "Platz": f"{t['position']}.",
            "Team": t['team'],
            "Spiele": t['matches_played'],
            "Siege": t['matches_won'],
            "Niederlagen": t['matches_lost'],
            "Punkte +": t['points_for'],
            "Punkte -": t['points_against'],
            "Rang-Punkte": t['ranking_points']
        })
    
    st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)

def show_rankings(user_id):
    st.header("Turnier-Rankings")
    db = TennisDatabase()
    tournaments = db.get_tournaments(user_id)
    
    if not tournaments:
        st.info("Noch keine Turniere vorhanden.")
        return

    for t in tournaments:
        created_date = t['created_at'].strftime('%Y-%m-%d') if hasattr(t['created_at'], 'strftime') else str(t['created_at'])[:10]
        with st.expander(f"{t['name']} ({created_date})", expanded=False):
            ranking = db.get_ranking(t['id'], user_id)
            if ranking and any(x['matches_played'] > 0 for x in ranking):
                played_teams = [x for x in ranking if x['matches_played'] > 0]
                if len(played_teams) >= 1:
                    st.markdown(f"**Champion:** {played_teams[0]['team']} ({played_teams[0]['ranking_points']} Punkte)")
                
                total_matches = sum(x['matches_played'] for x in ranking) // 2
                matches_in_db = len(db.get_matches(t['id'], user_id))
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("Gespielte Matches", total_matches)
                with col2: st.metric("Teams", len(t['teams']))
                with col3:
                    completion = (total_matches / matches_in_db * 100) if matches_in_db > 0 else 0
                    st.metric("Fortschritt", f"{completion:.0f}%")
            else:
                st.info("Turnier noch nicht gestartet.")

def show_statistics(user_id):
    st.header("Turnier-Statistiken")
    db = TennisDatabase()
    tournaments = db.get_tournaments(user_id)
    
    if not tournaments:
        st.info("Noch keine Turniere vorhanden.")
        return

    st.subheader("Gesamt-Übersicht")
    total_tournaments = len(tournaments)
    total_teams = sum(len(t['teams']) for t in tournaments)
    total_matches_all = sum(len(db.get_matches(t['id'], user_id)) for t in tournaments)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Turniere", total_tournaments)
    with col2: st.metric("Teams gesamt", total_teams)
    with col3: st.metric("Matches gesamt", total_matches_all)
    with col4:
        avg_teams = total_teams / total_tournaments if total_tournaments > 0 else 0
        st.metric("Durchschnitt Teams/Turnier", f"{avg_teams:.1f}")

    st.subheader("Detaillierte Statistiken")
    rows = []
    for t in tournaments:
        matches = db.get_matches(t['id'], user_id)
        played = len([m for m in matches if m['winner']])
        ranking = db.get_ranking(t['id'], user_id)
        champion = "TBD"
        if ranking and ranking[0]['matches_played'] > 0:
            champion = ranking[0]['team']
        created_date = t['created_at'].strftime('%Y-%m-%d') if hasattr(t['created_at'], 'strftime') else str(t['created_at'])[:10]
        rows.append({
            "Turnier": t['name'],
            "Datum": created_date,
            "Modus": t['mode'],
            "Teams": len(t['teams']),
            "Plätze": t['num_courts'],
            "Matches geplant": len(matches),
            "Matches gespielt": played,
            "Fortschritt %": f"{(played/len(matches)*100):.0f}%" if matches else "0%",
            "Champion": champion
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# -------------- MAIN APPLICATION --------------
def main():
    st.set_page_config(
        page_title="Tennis Turnier System", 
        page_icon="🎾", 
        layout="wide",
        menu_items={
            'Get Help': None,
            'Report a bug': None,
            'About': None
        }
    )

    # Initialize user session and database
    init_user_session()
    require_login()
    
    # Initialize database (create tables if needed)
    if 'db_initialized' not in st.session_state:
        db = TennisDatabase()
        db.init_database()
        st.session_state.db_initialized = True
    
    # User info header
    db = TennisDatabase()
    user_stats = db.get_user_stats(st.session_state.user_id)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"👤 Angemeldet als **{st.session_state.user_email}** | 🏆 {user_stats.get('tournament_count', 0)} Turniere")
    with col2:
        if st.button("🚪 Abmelden", type="secondary", use_container_width=True):
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.rerun()
    
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "➕ Neues Turnier", "⚙️ Turniere verwalten", "🏆 Ranking", "📈 Statistiken"])
    with tab1:
        show_user_dashboard(st.session_state.user_id)
    with tab2:
        create_new_tournament(st.session_state.user_id, st.session_state.user_email)
    with tab3:
        manage_tournaments(st.session_state.user_id)
    with tab4:
        show_rankings(st.session_state.user_id)
    with tab5:
        show_statistics(st.session_state.user_id)

if __name__ == "__main__":
    main()