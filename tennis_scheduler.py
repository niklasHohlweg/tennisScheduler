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
from st_supabase_connection import SupabaseConnection

# -------------- SUPABASE DATABASE CLASS --------------
class TennisDatabase:
    def __init__(self):
        # Initialize Supabase connection
        self.conn = st.connection(
            name="supabase_connection",
            type=SupabaseConnection,
            ttl="10m"
        )

    def init_database(self):
        """Initialize database tables if they don't exist"""
        try:
            # Create tournaments table
            self.conn.query("""
                CREATE TABLE IF NOT EXISTS tournaments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name TEXT NOT NULL,
                    teams JSONB NOT NULL,
                    num_courts INTEGER NOT NULL,
                    players_per_team INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    owner_email TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """, ttl=0).execute()

            # Create matches table
            self.conn.query("""
                CREATE TABLE IF NOT EXISTS matches (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tournament_id UUID REFERENCES tournaments(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL,
                    court_number INTEGER NOT NULL,
                    team1 TEXT NOT NULL,
                    team2 TEXT NOT NULL,
                    winner TEXT,
                    team1_score INTEGER DEFAULT 0,
                    team2_score INTEGER DEFAULT 0,
                    played_at TIMESTAMP,
                    start_time_minutes INTEGER,
                    end_time_minutes INTEGER
                )
            """, ttl=0).execute()

            # Create team_stats table
            self.conn.query("""
                CREATE TABLE IF NOT EXISTS team_stats (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tournament_id UUID REFERENCES tournaments(id) ON DELETE CASCADE,
                    team_name TEXT NOT NULL,
                    matches_played INTEGER DEFAULT 0,
                    matches_won INTEGER DEFAULT 0,
                    matches_lost INTEGER DEFAULT 0,
                    points_for INTEGER DEFAULT 0,
                    points_against INTEGER DEFAULT 0,
                    ranking_points INTEGER DEFAULT 0,
                    UNIQUE(tournament_id, team_name)
                )
            """, ttl=0).execute()

        except Exception as e:
            st.error(f"Database initialization error: {e}")

    def create_tournament(self, name, teams, num_courts, players_per_team, mode, owner_id, owner_email):
        """Create a tournament for the logged-in user"""
        try:
            # Insert tournament
            result = self.conn.table("tournaments").insert({
                "name": name,
                "teams": teams,
                "num_courts": num_courts,
                "players_per_team": players_per_team,
                "mode": mode,
                "owner_id": owner_id,
                "owner_email": owner_email
            }).execute()

            tournament_id = result.data[0]["id"]

            # Initialize team stats
            team_stats_data = []
            for team in teams:
                team_stats_data.append({
                    "tournament_id": tournament_id,
                    "team_name": team,
                    "matches_played": 0,
                    "matches_won": 0,
                    "matches_lost": 0,
                    "points_for": 0,
                    "points_against": 0,
                    "ranking_points": 0
                })

            self.conn.table("team_stats").insert(team_stats_data).execute()
            return tournament_id

        except Exception as e:
            st.error(f"Error creating tournament: {e}")
            return None

    def save_matches(self, tournament_id, schedule):
        """Save the match schedule"""
        try:
            # Clear existing matches for this tournament
            self.conn.table("matches").delete().eq("tournament_id", tournament_id).execute()

            matches_data = []
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
                    matches_data.append({
                        "tournament_id": tournament_id,
                        "round_number": round_num,
                        "court_number": court_num,
                        "team1": team1,
                        "team2": team2,
                        "start_time_minutes": start_time,
                        "end_time_minutes": end_time
                    })

            if matches_data:
                self.conn.table("matches").insert(matches_data).execute()

        except Exception as e:
            st.error(f"Error saving matches: {e}")

    def get_tournaments(self, owner_id):
        """Get all tournaments for the current user"""
        try:
            result = self.conn.table("tournaments").select("*").eq("owner_id", owner_id).order("created_at", desc=True).execute()
            return result.data
        except Exception as e:
            st.error(f"Error fetching tournaments: {e}")
            return []

    def get_matches(self, tournament_id, owner_id):
        """Get all matches for a tournament (with owner check)"""
        try:
            # First check if tournament belongs to user
            tournament_check = self.conn.table("tournaments").select("id").eq("id", tournament_id).eq("owner_id", owner_id).execute()
            if not tournament_check.data:
                return []

            result = self.conn.table("matches").select("*").eq("tournament_id", tournament_id).order("round_number, court_number").execute()
            return result.data
        except Exception as e:
            st.error(f"Error fetching matches: {e}")
            return []

    def update_match_result(self, match_id, winner, team1_score, team2_score):
        """Update match result"""
        try:
            # Update match
            self.conn.table("matches").update({
                "winner": winner,
                "team1_score": team1_score,
                "team2_score": team2_score,
                "played_at": datetime.now().isoformat()
            }).eq("id", match_id).execute()

            # Get match info for stats update
            match_result = self.conn.table("matches").select("tournament_id, team1, team2").eq("id", match_id).execute()
            if match_result.data:
                match_info = match_result.data[0]
                self._update_team_stats(
                    match_info["tournament_id"],
                    match_info["team1"],
                    match_info["team2"],
                    winner,
                    team1_score,
                    team2_score
                )

        except Exception as e:
            st.error(f"Error updating match result: {e}")

    def _update_team_stats(self, tournament_id, team1, team2, winner, team1_score, team2_score):
        """Update team statistics"""
        try:
            # Update team1 stats
            team1_stats = self.conn.table("team_stats").select("*").eq("tournament_id", tournament_id).eq("team_name", team1).execute()
            if team1_stats.data:
                stats = team1_stats.data[0]
                new_stats = {
                    "matches_played": stats["matches_played"] + 1,
                    "points_for": stats["points_for"] + team1_score,
                    "points_against": stats["points_against"] + team2_score,
                    "matches_won": stats["matches_won"] + (1 if winner == team1 else 0),
                    "matches_lost": stats["matches_lost"] + (1 if winner == team2 else 0),
                    "ranking_points": stats["ranking_points"] + (3 if winner == team1 else (1 if winner == "Draw" else 0))
                }
                self.conn.table("team_stats").update(new_stats).eq("id", stats["id"]).execute()

            # Update team2 stats
            team2_stats = self.conn.table("team_stats").select("*").eq("tournament_id", tournament_id).eq("team_name", team2).execute()
            if team2_stats.data:
                stats = team2_stats.data[0]
                new_stats = {
                    "matches_played": stats["matches_played"] + 1,
                    "points_for": stats["points_for"] + team2_score,
                    "points_against": stats["points_against"] + team1_score,
                    "matches_won": stats["matches_won"] + (1 if winner == team2 else 0),
                    "matches_lost": stats["matches_lost"] + (1 if winner == team1 else 0),
                    "ranking_points": stats["ranking_points"] + (3 if winner == team2 else (1 if winner == "Draw" else 0))
                }
                self.conn.table("team_stats").update(new_stats).eq("id", stats["id"]).execute()

        except Exception as e:
            st.error(f"Error updating team stats: {e}")

    def get_ranking(self, tournament_id, owner_id):
        """Get tournament ranking"""
        try:
            # Check if tournament belongs to user
            tournament_check = self.conn.table("tournaments").select("id").eq("id", tournament_id).eq("owner_id", owner_id).execute()
            if not tournament_check.data:
                return []

            result = self.conn.table("team_stats").select("*").eq("tournament_id", tournament_id).order("ranking_points", desc=True).order("matches_won", desc=True).execute()
            
            ranking = []
            for i, stats in enumerate(result.data, 1):
                win_rate = (stats["matches_won"] / stats["matches_played"] * 100) if stats["matches_played"] > 0 else 0
                goal_diff = stats["points_for"] - stats["points_against"]
                
                ranking.append({
                    "position": i,
                    "team": stats["team_name"],
                    "matches_played": stats["matches_played"],
                    "matches_won": stats["matches_won"],
                    "matches_lost": stats["matches_lost"],
                    "win_rate": win_rate,
                    "points_for": stats["points_for"],
                    "points_against": stats["points_against"],
                    "goal_difference": goal_diff,
                    "ranking_points": stats["ranking_points"]
                })
            
            return ranking

        except Exception as e:
            st.error(f"Error fetching ranking: {e}")
            return []

# -------------- USER MANAGEMENT --------------
def init_user_session():
    """Initialize simple user session management"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
        st.session_state.user_name = None
        st.session_state.user_email = None

def require_login():
    """Simple login system"""
    st.title("🎾 Tennis Turnier System")
    
    if st.session_state.user_id is None:
        st.info("Bitte geben Sie Ihre Daten ein, um fortzufahren.")
        
        with st.form("login_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name", placeholder="Ihr Name")
            with col2:
                email = st.text_input("E-Mail", placeholder="ihre.email@beispiel.de")
            
            submitted = st.form_submit_button("Anmelden", type="primary")
            
            if submitted and name.strip() and email.strip():
                st.session_state.user_id = str(uuid.uuid4())
                st.session_state.user_name = name.strip()
                st.session_state.user_email = email.strip()
                st.rerun()
            elif submitted:
                st.error("Bitte füllen Sie beide Felder aus.")
        
        st.stop()

# -------------- SCHEDULER (unchanged) --------------
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

# -------------- VIEW HELPERS (same as before) --------------
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
        st.metric("Ø Matches/Team", f"{sum(team_match_count.values()) / len(teams):.1f}")
    with col3:
        st.metric("Max-Min Differenz", difference)
    with col4:
        if difference <= 1:
            st.success("✅ Sehr fair")
        elif difference <= 2:
            st.warning("⚖️ Akzeptabel")
        else:
            st.error("⚠️ Ungleich")

# -------------- MAIN APP FUNCTIONS (adapted for Supabase) --------------
def create_new_tournament(user_id, user_email):
    st.header("🏆 Neues Turnier erstellen")
    
    # Tournament creation form (same as before)
    with st.container():
        st.markdown("### 📋 Schritt 1: Teams konfigurieren")
        col1, col2 = st.columns([1, 2])
        with col1:
            input_method = st.radio("", ["🔢 Anzahl Teams", "✏️ Team-Namen eingeben"])
        with col2:
            if input_method == "🔢 Anzahl Teams":
                num_teams = st.slider("Wie viele Teams nehmen teil?", 2, 20, 8, 1)
                teams = [f"Team {i+1}" for i in range(num_teams)]
            else:
                team_names = st.text_area("Team-Namen (eine Zeile pro Team):",
                                          value="Team A\nTeam B\nTeam C\nTeam D\nTeam E\nTeam F\nTeam G\nTeam H",
                                          height=180)
                teams = [x.strip() for x in team_names.splitlines() if x.strip()]

    st.markdown("---")

    with st.container():
        st.markdown("### ⚙️ Schritt 2: Turnier-Details")
        with st.form("tournament_config_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                tournament_name = st.text_input("Turnier Name",
                                                value=f"Tennis Turnier {datetime.now().strftime('%d.%m.%Y')}")
                num_courts = st.select_slider("Anzahl Tennisplätze", options=list(range(1, 11)), value=4)
                players_per_team = st.select_slider("Spieler pro Team", options=[2,3,4,5,6,7,8], value=4)
            with col2:
                mode = st.selectbox("Modus", ["⏱️ Zeitbasierte Planung", "🔄 Vollständiges Turnier (Round-Robin)", "🎮 Einzelne Runde"])
                if mode == "⏱️ Zeitbasierte Planung":
                    time_mode = st.radio("Zeit-Eingabe:", ["🕐 Stunden/Minuten", "📊 Minuten"], horizontal=True)
                    if time_mode == "🕐 Stunden/Minuten":
                        c1, c2 = st.columns(2)
                        with c1: hours = st.number_input("Stunden", 0, 12, 2, 1)
                        with c2: minutes = st.number_input("Minuten", 0, 59, 0, 15)
                        total_minutes = hours*60 + minutes
                    else:
                        total_minutes = st.slider("Gesamtdauer (Minuten)", 20, 480, 120, 20)

            col_submit1, col_submit2, col_submit3 = st.columns([1,2,1])
            with col_submit2:
                submitted = st.form_submit_button("🚀 Turnier erstellen und starten!", type="primary", use_container_width=True)

        if submitted:
            if len(teams) < 2 or not tournament_name.strip():
                st.error("❌ Mindestens 2 Teams und ein Turnier-Name sind erforderlich")
                return

            with st.spinner("🔄 Turnier wird erstellt..."):
                db = TennisDatabase()
                tid = db.create_tournament(
                    tournament_name.strip(), teams, num_courts, players_per_team, mode, owner_id=user_id, owner_email=user_email
                )
                
                if tid:
                    scheduler = TennisScheduler(num_courts, teams, players_per_team)

                    if mode == "⏱️ Zeitbasierte Planung":
                        schedule, stats = scheduler.create_time_based_schedule(total_minutes)
                        if "error" not in stats:
                            db.save_matches(tid, schedule)
                            st.success(f"✅ Turnier '{tournament_name}' erstellt!")
                            st.balloons()
                    elif mode == "🔄 Vollständiges Turnier (Round-Robin)":
                        schedule = scheduler.create_round_robin_schedule()
                        db.save_matches(tid, schedule)
                        st.success(f"✅ Turnier '{tournament_name}' erstellt!")
                        st.balloons()
                    else:
                        matches = scheduler.create_single_round_distribution()
                        schedule = [matches]
                        db.save_matches(tid, schedule)
                        st.success("✅ Einzelrunde erstellt!")

def manage_tournaments(user_id):
    st.header("📋 Turnier Verwaltung")
    db = TennisDatabase()
    tournaments = db.get_tournaments(user_id)
    
    if not tournaments:
        st.info("📋 Noch keine Turniere erstellt. Gehe zu 'Neues Turnier'.")
        return

    tournament_options = {f"{t['name']} ({t['created_at'][:10]})": t['id'] for t in tournaments}
    selected_name = st.selectbox("Turnier auswählen:", list(tournament_options.keys()))
    
    if selected_name:
        tournament_id = tournament_options[selected_name]
        tournament = next(t for t in tournaments if t['id'] == tournament_id)
        
        st.subheader(f"🏆 {tournament['name']}")
        matches = db.get_matches(tournament_id, user_id)
        
        if matches:
            tab1, tab2, tab3 = st.tabs(["🎮 Ergebnisse eintragen", "📅 Spielplan", "🏅 Aktuelles Ranking"])
            with tab1: 
                enter_match_results(tournament_id, matches, user_id)
            with tab2: 
                show_match_schedule(matches, tournament)
            with tab3: 
                show_tournament_ranking(tournament_id, user_id)

def enter_match_results(tournament_id, matches, user_id):
    st.subheader("🎮 Match-Ergebnisse eintragen")
    db = TennisDatabase()
    
    unplayed = [m for m in matches if not m['winner']]
    played = [m for m in matches if m['winner']]

    col1, col2 = st.columns([2, 1])
    with col2:
        st.metric("Offene Matches", len(unplayed))
        st.metric("Gespielte Matches", len(played))

    with col1:
        if not unplayed:
            st.success("🎉 Alle Matches wurden gespielt!")
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
                    if st.button(f"🏆 {m['team1'][:8]}", key=f"w1_{m['id']}"):
                        db.update_match_result(m['id'], m['team1'], s1, s2)
                        st.success(f"✅ {m['team1']} gewinnt!")
                        st.rerun()
                with b2:
                    if st.button(f"🏆 {m['team2'][:8]}", key=f"w2_{m['id']}"):
                        db.update_match_result(m['id'], m['team2'], s1, s2)
                        st.success(f"✅ {m['team2']} gewinnt!")
                        st.rerun()
            st.markdown("---")

def show_match_schedule(matches, tournament):
    st.subheader("📅 Spielplan")
    if matches:
        df_data = []
        for m in matches:
            status = "✅" if m['winner'] else "⏳"
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
    st.subheader("🏅 Aktuelles Ranking")
    db = TennisDatabase()
    ranking = db.get_ranking(tournament_id, user_id)
    
    if not ranking:
        st.info("🎾 Noch keine Spiele gespielt.")
        return

    # Show top 3
    if len(ranking) >= 1:
        col1, col2, col3 = st.columns(3)
        with col2:
            st.markdown("### 🥇")
            st.markdown(f"**{ranking[0]['team']}**")
            st.markdown(f"🏆 {ranking[0]['ranking_points']} Punkte")

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

# -------------- MAIN APP --------------
def main():
    st.set_page_config(page_title="🎾 Tennis Turnier System", page_icon="🎾", layout="wide")

    # Initialize user session and database
    init_user_session()
    require_login()
    
    # Initialize database (create tables if needed)
    if 'db_initialized' not in st.session_state:
        db = TennisDatabase()
        db.init_database()
        st.session_state.db_initialized = True
    
    st.caption(f"Angemeldet als **{st.session_state.user_name}** ({st.session_state.user_email})")
    
    # Logout button
    with st.sidebar:
        if st.button("🚪 Abmelden", type="secondary"):
            st.session_state.user_id = None
            st.session_state.user_name = None
            st.session_state.user_email = None
            st.rerun()
    
    st.markdown("---")

    tab1, tab2 = st.tabs(["🏆 Neues Turnier", "📋 Aktuelle Turniere"])
    with tab1:
        create_new_tournament(st.session_state.user_id, st.session_state.user_email)
    with tab2:
        manage_tournaments(st.session_state.user_id)

if __name__ == "__main__":
    main()