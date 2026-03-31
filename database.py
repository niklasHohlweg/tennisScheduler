"""Database operations for Tennis Scheduler"""
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from flask import current_app, g
import logging
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL database handler"""
    
    def __init__(self, config):
        self.config = {
            'host': config.get('DB_HOST', 'localhost'),
            'port': config.get('DB_PORT', '5432'),
            'database': config.get('DB_NAME', 'tennis_scheduler'),
            'user': config.get('DB_USER', 'tennis_user'),
            'password': config.get('DB_PASSWORD', 'tennis_password'),
            'connect_timeout': 10,  # Connection timeout in seconds
            'options': '-c statement_timeout=30000'  # Query timeout: 30s
        }
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(**self.config)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def init_db(self):
        """Check if database is accessible"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM tournaments LIMIT 1")
                cursor.close()
            return True
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            return False
    
    # ==================== USER OPERATIONS ====================
    
    def get_or_create_user(self, email):
        """Get user by email or create if doesn't exist. Returns (user_dict, is_new_user)"""
        try:
            with self.get_connection() as conn:
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
                    user_dict = dict(user)
                    user_dict['id'] = str(user_dict['id'])
                    logger.info(f"User logged in: {email}")
                else:
                    # Create new user
                    cursor.execute("""
                        INSERT INTO users (email, created_at, last_login)
                        VALUES (%s, NOW(), NOW())
                        RETURNING id, email, created_at, last_login
                    """, (email.lower(),))
                    user = cursor.fetchone()
                    user_dict = dict(user)
                    user_dict['id'] = str(user_dict['id'])
                    is_new_user = True
                    logger.info(f"New user created: {email}")
                
                cursor.close()
                return user_dict, is_new_user
                
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return None, False
    
    def get_user_stats(self, user_id):
        """Get statistics for a user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                cursor.execute("""
                    SELECT COUNT(*) as tournament_count
                    FROM tournaments
                    WHERE owner_id = %s
                """, (user_id,))
                stats = cursor.fetchone()
                cursor.close()
                
                return dict(stats) if stats else {'tournament_count': 0}
                
        except Exception as e:
            logger.error(f"Error in get_user_stats: {e}")
            return {'tournament_count': 0}
    
    # ==================== TOURNAMENT OPERATIONS ====================
    
    def create_tournament(self, name, teams, num_courts, players_per_team, mode, owner_id, owner_email, 
                         match_type='single', num_players=None, team_size=None, round_duration=15, break_duration=5):
        """Create a tournament for the logged-in user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                cursor.execute("""
                    INSERT INTO tournaments (name, teams, num_courts, players_per_team, mode, owner_id, owner_email,
                                           match_type, num_players, team_size, round_duration, break_duration)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (name, Json(teams), num_courts, players_per_team, mode, owner_id, owner_email, 
                      match_type, num_players, team_size, round_duration, break_duration))

                tournament_id = cursor.fetchone()['id']

                # Initialize team stats
                for team in teams:
                    cursor.execute("""
                        INSERT INTO team_stats (tournament_id, team_name, matches_played, matches_won, 
                                              matches_lost, points_for, points_against, ranking_points)
                        VALUES (%s, %s, 0, 0, 0, 0, 0, 0)
                    """, (tournament_id, team))

                cursor.close()
                return str(tournament_id)

        except Exception as e:
            logger.error(f"Error creating tournament: {e}")
            return None
    
    def get_tournaments(self, owner_id):
        """Get all tournaments for the current user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT id, name, teams, num_courts, players_per_team, mode, 
                           owner_id, owner_email, created_at, match_type, num_players, team_size,
                           round_duration, break_duration
                    FROM tournaments
                    WHERE owner_id = %s
                    ORDER BY created_at DESC
                """, (owner_id,))
                tournaments = cursor.fetchall()
                cursor.close()
                
                result = []
                for t in tournaments:
                    t_dict = dict(t)
                    t_dict['id'] = str(t_dict['id'])
                    result.append(t_dict)
                return result
        except Exception as e:
            logger.error(f"Error fetching tournaments: {e}")
            return []
    
    def get_tournament(self, tournament_id, owner_id):
        """Get a single tournament (with owner check)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT id, name, teams, num_courts, players_per_team, mode, 
                           owner_id, owner_email, created_at, match_type, num_players, team_size,
                           round_duration, break_duration
                    FROM tournaments
                    WHERE id = %s AND owner_id = %s
                """, (tournament_id, owner_id))
                tournament = cursor.fetchone()
                cursor.close()
                
                if tournament:
                    t_dict = dict(tournament)
                    t_dict['id'] = str(t_dict['id'])
                    return t_dict
                return None
        except Exception as e:
            logger.error(f"Error fetching tournament: {e}")
            return None
    
    def update_tournament(self, tournament_id, owner_id, name):
        """Update tournament name"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE tournaments SET name = %s
                    WHERE id = %s AND owner_id = %s
                """, (name, tournament_id, owner_id))
                
                cursor.close()
                return True
                
        except Exception as e:
            logger.error(f"Error updating tournament: {e}")
            return False
    
    def update_tournament_round_settings(self, tournament_id, owner_id, round_duration, break_duration):
        """Update tournament round duration and break duration"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE tournaments 
                    SET round_duration = %s, break_duration = %s
                    WHERE id = %s AND owner_id = %s
                """, (round_duration, break_duration, tournament_id, owner_id))
                
                cursor.close()
                return True
                
        except Exception as e:
            logger.error(f"Error updating tournament round settings: {e}")
            return False
    
    def delete_tournament(self, tournament_id, owner_id):
        """Delete a tournament (with ownership check)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Verify ownership
                cursor.execute("""
                    SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
                """, (tournament_id, owner_id))
                
                if not cursor.fetchone():
                    cursor.close()
                    return False
                
                # Delete tournament (cascades to matches and team_stats)
                cursor.execute("DELETE FROM tournaments WHERE id = %s", (tournament_id,))
                cursor.close()
                logger.info(f"Tournament {tournament_id} deleted by {owner_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error deleting tournament: {e}")
            return False
    
    def search_tournaments(self, owner_id, search_term=None, date_from=None, date_to=None):
        """Search tournaments with filters"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                query = """
                    SELECT id, name, teams, num_courts, players_per_team, mode, 
                           owner_id, owner_email, created_at, match_type, team_creation_mode, player_names
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
                
                result = []
                for t in tournaments:
                    t_dict = dict(t)
                    t_dict['id'] = str(t_dict['id'])
                    result.append(t_dict)
                
                return result
                
        except Exception as e:
            logger.error(f"Error searching tournaments: {e}")
            return []
    
    # ==================== MATCH OPERATIONS ====================
    
    def save_players(self, tournament_id, player_team_mapping):
        """Save player-to-team assignments
        
        Args:
            tournament_id: UUID of the tournament
            player_team_mapping: List of tuples (player_name, team_name)
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete existing players for this tournament
                cursor.execute("DELETE FROM players WHERE tournament_id = %s", (tournament_id,))
                
                # Insert new player assignments
                for player_name, team_name in player_team_mapping:
                    cursor.execute("""
                        INSERT INTO players (tournament_id, name, team_name)
                        VALUES (%s, %s, %s)
                    """, (tournament_id, player_name, team_name))
                
                cursor.close()
                return True
                
        except Exception as e:
            logger.error(f"Error saving players: {e}")
            return False
    
    def get_players(self, tournament_id, owner_id):
        """Get all players for a tournament (with owner check)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # First check if tournament belongs to user
                cursor.execute("""
                    SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
                """, (tournament_id, owner_id))
                if not cursor.fetchone():
                    cursor.close()
                    return []
                
                # Get players
                cursor.execute("""
                    SELECT id, name, team_name
                    FROM players
                    WHERE tournament_id = %s
                    ORDER BY team_name, name
                """, (tournament_id,))
                
                players = cursor.fetchall()
                cursor.close()
                
                result = []
                for p in players:
                    p_dict = dict(p)
                    p_dict['id'] = str(p_dict['id'])
                    result.append(p_dict)
                return result
                
        except Exception as e:
            logger.error(f"Error fetching players: {e}")
            return []
    
    def get_players_by_team(self, tournament_id, owner_id):
        """Get players grouped by team"""
        players = self.get_players(tournament_id, owner_id)
        
        teams_dict = {}
        for player in players:
            team_name = player['team_name']
            if team_name not in teams_dict:
                teams_dict[team_name] = []
            teams_dict[team_name].append(player['name'])
        
        return teams_dict
    
    # ==================== MATCH OPERATIONS ====================
    
    def save_matches(self, tournament_id, schedule):
        """Save the match schedule"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if any matches have been played
                cursor.execute("""
                    SELECT COUNT(*) as played_count FROM matches 
                    WHERE tournament_id = %s AND winner IS NOT NULL
                """, (tournament_id,))
                result = cursor.fetchone()
                
                if result and result[0] > 0:
                    cursor.close()
                    logger.warning(f"Cannot regenerate schedule: {result[0]} matches already played")
                    return False
                
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

                cursor.close()
                return True

        except Exception as e:
            logger.error(f"Error saving matches: {e}")
            return False
    
    def get_matches(self, tournament_id, owner_id):
        """Get all matches for a tournament (with owner check)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # First check if tournament belongs to user
                cursor.execute("""
                    SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
                """, (tournament_id, owner_id))
                if not cursor.fetchone():
                    cursor.close()
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
                
                result = []
                for m in matches:
                    m_dict = dict(m)
                    m_dict['id'] = str(m_dict['id'])
                    m_dict['tournament_id'] = str(m_dict['tournament_id'])
                    result.append(m_dict)
                return result
        except Exception as e:
            logger.error(f"Error fetching matches: {e}")
            return []
    
    def get_matches_by_id(self, match_id):
        """Get a specific match by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                cursor.execute("""
                    SELECT id, tournament_id, round_number, court_number, team1, team2, 
                           winner, team1_score, team2_score, played_at, 
                           start_time_minutes, end_time_minutes
                    FROM matches
                    WHERE id = %s
                """, (match_id,))
                
                match = cursor.fetchone()
                cursor.close()
                
                if match:
                    m_dict = dict(match)
                    m_dict['id'] = str(m_dict['id'])
                    m_dict['tournament_id'] = str(m_dict['tournament_id'])
                    return [m_dict]
                return []
        except Exception as e:
            logger.error(f"Error fetching match by ID: {e}")
            return []
    
    def update_match_result(self, match_id, winner, team1_score, team2_score):
        """Update match result"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Get current match state to check if already played and validate winner
                cursor.execute("""
                    SELECT tournament_id, team1, team2, winner as old_winner, 
                           team1_score as old_team1_score, team2_score as old_team2_score
                    FROM matches
                    WHERE id = %s
                """, (match_id,))
                
                match_info = cursor.fetchone()
                if not match_info:
                    cursor.close()
                    return False
                
                # If match was already played, reverse the old stats first
                if match_info['old_winner'] is not None:
                    self._reverse_team_stats(
                        cursor,
                        match_info['tournament_id'],
                        match_info['team1'],
                        match_info['team2'],
                        match_info['old_winner'],
                        match_info['old_team1_score'] or 0,
                        match_info['old_team2_score'] or 0
                    )

                # Update match
                cursor.execute("""
                    UPDATE matches
                    SET winner = %s, team1_score = %s, team2_score = %s, played_at = NOW()
                    WHERE id = %s
                """, (winner, team1_score, team2_score, match_id))

                # Apply new stats
                self._update_team_stats(
                    cursor,
                    match_info['tournament_id'],
                    match_info['team1'],
                    match_info['team2'],
                    winner,
                    team1_score,
                    team2_score
                )

                cursor.close()
                return True

        except Exception as e:
            logger.error(f"Error updating match result: {e}")
            return False
    
    def _update_team_stats(self, cursor, tournament_id, team1, team2, winner, team1_score, team2_score):
        """Update team statistics"""
        # Update team1 stats (no SELECT needed - just UPDATE)
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

        # Update team2 stats (no SELECT needed - just UPDATE)
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
    
    def _reverse_team_stats(self, cursor, tournament_id, team1, team2, winner, team1_score, team2_score):
        """Reverse team statistics (for correcting match results)"""
        # Reverse team1 stats
        cursor.execute("""
            UPDATE team_stats
            SET matches_played = matches_played - 1,
                points_for = points_for - %s,
                points_against = points_against - %s,
                matches_won = matches_won - %s,
                matches_lost = matches_lost - %s,
                ranking_points = ranking_points - %s
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

        # Reverse team2 stats
        cursor.execute("""
            UPDATE team_stats
            SET matches_played = matches_played - 1,
                points_for = points_for - %s,
                points_against = points_against - %s,
                matches_won = matches_won - %s,
                matches_lost = matches_lost - %s,
                ranking_points = ranking_points - %s
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
        # ==================== RANKING OPERATIONS ====================
    
    def get_ranking(self, tournament_id, owner_id):
        """Get tournament ranking"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Check if tournament belongs to user
                cursor.execute("""
                    SELECT id FROM tournaments WHERE id = %s AND owner_id = %s
                """, (tournament_id, owner_id))
                if not cursor.fetchone():
                    cursor.close()
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
            logger.error(f"Error in get_ranking: {e}")
            return []
    
    # ==================== STATISTICS OPERATIONS ====================
    
    def get_tournament_statistics(self, tournament_id, owner_id):
        """Get detailed tournament statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Verify ownership
                cursor.execute("""
                    SELECT * FROM tournaments WHERE id = %s AND owner_id = %s
                """, (tournament_id, owner_id))
                
                tournament = cursor.fetchone()
                if not tournament:
                    cursor.close()
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
                
                return {
                    'tournament': dict(tournament),
                    'match_stats': dict(match_stats) if match_stats else {},
                    'team_stats': [dict(ts) for ts in team_stats]
                }
                
        except Exception as e:
            logger.error(f"Error in get_tournament_statistics: {e}")
            return None


def get_db():
    """Get database instance from Flask app context"""
    if 'db' not in g:
        g.db = Database(current_app.config)
    return g.db
