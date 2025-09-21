import streamlit as st
import itertools
from collections import Counter, defaultdict
import random
import math
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import json
from datetime import datetime, timedelta
import os
import time

class TennisDatabase:
    def __init__(self, db_path="tennis_scheduler.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialisiert die SQLite-Datenbank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Turniere Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                teams TEXT NOT NULL,
                num_courts INTEGER NOT NULL,
                players_per_team INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mode TEXT NOT NULL
            )
        ''')
        
        # Matches Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                round_number INTEGER NOT NULL,
                court_number INTEGER NOT NULL,
                team1 TEXT NOT NULL,
                team2 TEXT NOT NULL,
                winner TEXT,
                team1_score INTEGER DEFAULT 0,
                team2_score INTEGER DEFAULT 0,
                played_at TIMESTAMP,
                start_time_minutes INTEGER,
                end_time_minutes INTEGER,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id)
            )
        ''')
        
        # Team-Statistiken Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                matches_played INTEGER DEFAULT 0,
                matches_won INTEGER DEFAULT 0,
                matches_lost INTEGER DEFAULT 0,
                points_for INTEGER DEFAULT 0,
                points_against INTEGER DEFAULT 0,
                ranking_points INTEGER DEFAULT 0,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
                UNIQUE(tournament_id, team_name)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_tournament(self, name, teams, num_courts, players_per_team, mode):
        """Erstellt ein neues Turnier"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        teams_json = json.dumps(teams)
        cursor.execute('''
            INSERT INTO tournaments (name, teams, num_courts, players_per_team, mode)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, teams_json, num_courts, players_per_team, mode))
        
        tournament_id = cursor.lastrowid
        
        # Initiale Team-Statistiken erstellen
        for team in teams:
            cursor.execute('''
                INSERT OR REPLACE INTO team_stats 
                (tournament_id, team_name, matches_played, matches_won, matches_lost, points_for, points_against, ranking_points)
                VALUES (?, ?, 0, 0, 0, 0, 0, 0)
            ''', (tournament_id, team))
        
        conn.commit()
        conn.close()
        return tournament_id
    
    def save_matches(self, tournament_id, schedule):
        """Speichert Matches in die Datenbank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Lösche existierende Matches für dieses Turnier
        cursor.execute('DELETE FROM matches WHERE tournament_id = ?', (tournament_id,))
        
        for round_num, round_data in enumerate(schedule, 1):
            if isinstance(round_data, dict):  # Zeitbasierte Planung
                matches = round_data['matches']
                start_time = round_data.get('start_time', 0)
                end_time = round_data.get('end_time', 0)
            else:  # Standard Liste von Matches
                matches = round_data
                start_time = (round_num - 1) * 20
                end_time = start_time + 15
            
            for court_num, match in enumerate(matches, 1):
                team1, team2 = match
                cursor.execute('''
                    INSERT INTO matches 
                    (tournament_id, round_number, court_number, team1, team2, start_time_minutes, end_time_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (tournament_id, round_num, court_num, team1, team2, start_time, end_time))
        
        conn.commit()
        conn.close()
    
    def get_tournaments(self):
        """Holt alle Turniere"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, teams, num_courts, players_per_team, created_at, mode
            FROM tournaments
            ORDER BY created_at DESC
        ''')
        
        tournaments = []
        for row in cursor.fetchall():
            tournaments.append({
                'id': row[0],
                'name': row[1],
                'teams': json.loads(row[2]),
                'num_courts': row[3],
                'players_per_team': row[4],
                'created_at': row[5],
                'mode': row[6]
            })
        
        conn.close()
        return tournaments
    
    def get_matches(self, tournament_id):
        """Holt alle Matches eines Turniers"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, round_number, court_number, team1, team2, winner, 
                   team1_score, team2_score, played_at, start_time_minutes, end_time_minutes
            FROM matches 
            WHERE tournament_id = ?
            ORDER BY round_number, court_number
        ''', (tournament_id,))
        
        matches = []
        for row in cursor.fetchall():
            matches.append({
                'id': row[0],
                'round_number': row[1],
                'court_number': row[2],
                'team1': row[3],
                'team2': row[4],
                'winner': row[5],
                'team1_score': row[6],
                'team2_score': row[7],
                'played_at': row[8],
                'start_time_minutes': row[9],
                'end_time_minutes': row[10]
            })
        
        conn.close()
        return matches
    
    def update_match_result(self, match_id, winner, team1_score, team2_score):
        """Aktualisiert das Ergebnis eines Matches"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE matches 
            SET winner = ?, team1_score = ?, team2_score = ?, played_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (winner, team1_score, team2_score, match_id))
        
        # Hole Match-Informationen für Statistik-Update
        cursor.execute('''
            SELECT tournament_id, team1, team2, winner FROM matches WHERE id = ?
        ''', (match_id,))
        
        match_info = cursor.fetchone()
        if match_info:
            tournament_id, team1, team2, match_winner = match_info
            self._update_team_stats(cursor, tournament_id, team1, team2, match_winner, team1_score, team2_score)
        
        conn.commit()
        conn.close()
    
    def _update_team_stats(self, cursor, tournament_id, team1, team2, winner, team1_score, team2_score):
        """Aktualisiert Team-Statistiken nach einem Match"""
        # Team 1 Stats
        cursor.execute('''
            SELECT matches_played, matches_won, matches_lost, points_for, points_against, ranking_points
            FROM team_stats WHERE tournament_id = ? AND team_name = ?
        ''', (tournament_id, team1))
        
        team1_stats = cursor.fetchone()
        if team1_stats:
            played, won, lost, pf, pa, rp = team1_stats
            new_played = played + 1
            new_won = won + (1 if winner == team1 else 0)
            new_lost = lost + (1 if winner == team2 else 0)
            new_pf = pf + team1_score
            new_pa = pa + team2_score
            new_rp = rp + (3 if winner == team1 else 1 if winner == 'Draw' else 0)
            
            cursor.execute('''
                UPDATE team_stats 
                SET matches_played = ?, matches_won = ?, matches_lost = ?, 
                    points_for = ?, points_against = ?, ranking_points = ?
                WHERE tournament_id = ? AND team_name = ?
            ''', (new_played, new_won, new_lost, new_pf, new_pa, new_rp, tournament_id, team1))
        
        # Team 2 Stats
        cursor.execute('''
            SELECT matches_played, matches_won, matches_lost, points_for, points_against, ranking_points
            FROM team_stats WHERE tournament_id = ? AND team_name = ?
        ''', (tournament_id, team2))
        
        team2_stats = cursor.fetchone()
        if team2_stats:
            played, won, lost, pf, pa, rp = team2_stats
            new_played = played + 1
            new_won = won + (1 if winner == team2 else 0)
            new_lost = lost + (1 if winner == team1 else 0)
            new_pf = pf + team2_score
            new_pa = pa + team1_score
            new_rp = rp + (3 if winner == team2 else 1 if winner == 'Draw' else 0)
            
            cursor.execute('''
                UPDATE team_stats 
                SET matches_played = ?, matches_won = ?, matches_lost = ?, 
                    points_for = ?, points_against = ?, ranking_points = ?
                WHERE tournament_id = ? AND team_name = ?
            ''', (new_played, new_won, new_lost, new_pf, new_pa, new_rp, tournament_id, team2))
    
    def get_ranking(self, tournament_id):
        """Holt das Ranking für ein Turnier"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT team_name, matches_played, matches_won, matches_lost, 
                   points_for, points_against, ranking_points
            FROM team_stats 
            WHERE tournament_id = ?
            ORDER BY ranking_points DESC, matches_won DESC, (points_for - points_against) DESC
        ''', (tournament_id,))
        
        ranking = []
        for i, row in enumerate(cursor.fetchall(), 1):
            team_name, played, won, lost, pf, pa, rp = row
            win_rate = (won / played * 100) if played > 0 else 0
            goal_diff = pf - pa
            
            ranking.append({
                'position': i,
                'team': team_name,
                'matches_played': played,
                'matches_won': won,
                'matches_lost': lost,
                'win_rate': win_rate,
                'points_for': pf,
                'points_against': pa,
                'goal_difference': goal_diff,
                'ranking_points': rp
            })
        
        conn.close()
        return ranking

class TennisScheduler:
    def __init__(self, num_courts, teams, players_per_team=4, db=None):
        self.num_courts = num_courts
        self.teams = teams if isinstance(teams, list) else [f"Team {i+1}" for i in range(teams)]
        self.num_teams = len(self.teams)
        self.matches_per_round = num_courts
        self.max_players_per_round = num_courts * 2
        self.players_per_team = players_per_team
        self.max_simultaneous_matches_per_team = players_per_team // 2
        self.db = db
        
    def generate_all_possible_matches(self):
        """Generiert alle möglichen Matches zwischen verschiedenen Teams"""
        return list(itertools.combinations(self.teams, 2))
    
    def create_time_based_schedule(self, total_duration_minutes):
        """Erstellt einen zeitbasierten Spielplan basierend auf der Gesamtdauer"""
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
            
            for match in round_matches:
                team1, team2 = match
                team_game_counts[team1] += 1
                team_game_counts[team2] += 1
        
        stats = self.get_time_based_stats(schedule, team_game_counts, total_duration_minutes)
        
        return schedule, stats
    
    def create_optimal_time_round(self, current_counts, round_num):
        """Erstellt eine optimale Runde für zeitbasierte Planung"""
        round_matches = []
        team_matches_this_round = Counter() 
        
        teams_by_count = sorted(self.teams, key=lambda t: current_counts[t])
        
        possible_matches = []
        for team1 in teams_by_count:
            for team2 in teams_by_count:
                if team1 != team2 and (team1, team2) not in possible_matches and (team2, team1) not in possible_matches:
                    possible_matches.append((team1, team2))
        
        possible_matches.sort(key=lambda match: current_counts[match[0]] + current_counts[match[1]])
        
        for match in possible_matches:
            if len(round_matches) >= self.num_courts:
                break
                
            team1, team2 = match
            
            if (team_matches_this_round[team1] < self.max_simultaneous_matches_per_team and 
                team_matches_this_round[team2] < self.max_simultaneous_matches_per_team):
                
                round_matches.append(match)
                team_matches_this_round[team1] += 1
                team_matches_this_round[team2] += 1
        
        if len(round_matches) < self.num_courts:
            round_matches = self.fill_remaining_time_courts(
                possible_matches, round_matches, team_matches_this_round, current_counts
            )
        
        return round_matches
    
    def fill_remaining_time_courts(self, possible_matches, current_matches, team_round_counts, overall_counts):
        """Füllt verbleibende Plätze in zeitbasierten Runden"""
        remaining_slots = self.num_courts - len(current_matches)
        
        if remaining_slots <= 0:
            return current_matches
        
        for match in possible_matches:
            if len(current_matches) >= self.num_courts:
                break
                
            if match not in current_matches:
                team1, team2 = match
                
                if (team_round_counts[team1] < self.max_simultaneous_matches_per_team and 
                    team_round_counts[team2] < self.max_simultaneous_matches_per_team):
                    
                    current_matches.append(match)
                    team_round_counts[team1] += 1
                    team_round_counts[team2] += 1
        
        return current_matches
    
    def get_time_based_stats(self, schedule, team_counts, total_duration):
        """Berechnet Statistiken für zeitbasierte Planung"""
        total_matches = sum(len(round_data['matches']) for round_data in schedule)
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
        """Erstellt einen vollständigen Round-Robin Spielplan"""
        all_matches = self.generate_all_possible_matches()
        total_matches = len(all_matches)
        
        rounds_needed = math.ceil(total_matches / self.matches_per_round)
        
        schedule = []
        remaining_matches = all_matches.copy()
        random.shuffle(remaining_matches)
        
        for round_num in range(1, rounds_needed + 1):
            round_matches = self.create_optimal_round(remaining_matches, round_num)
            schedule.append(round_matches)
            
            for match in round_matches:
                if match in remaining_matches:
                    remaining_matches.remove(match)
        
        return schedule
    
    def create_optimal_round(self, available_matches, round_num):
        """Erstellt eine optimale Runde mit maximal möglichen Matches"""
        round_matches = []
        used_teams_this_round = set()
        
        for match in available_matches.copy():
            team1, team2 = match
            if team1 not in used_teams_this_round and team2 not in used_teams_this_round:
                if len(round_matches) < self.matches_per_round:
                    round_matches.append(match)
                    used_teams_this_round.add(team1)
                    used_teams_this_round.add(team2)
        
        if len(round_matches) < self.matches_per_round:
            round_matches = self.fill_remaining_courts(
                available_matches, round_matches, used_teams_this_round
            )
        
        return round_matches
    
    def fill_remaining_courts(self, available_matches, current_matches, used_teams):
        """Füllt verbleibende Plätze, erlaubt Teams mehrfach zu spielen"""
        remaining_slots = self.matches_per_round - len(current_matches)
        
        if remaining_slots <= 0:
            return current_matches
        
        available_for_doubles = []
        for match in available_matches:
            team1, team2 = match
            if match not in current_matches:
                current_opponents = {}
                for existing_match in current_matches:
                    t1, t2 = existing_match
                    current_opponents[t1] = t2
                    current_opponents[t2] = t1
                
                can_play = True
                if team1 in current_opponents and current_opponents[team1] == team2:
                    can_play = False
                if team2 in current_opponents and current_opponents[team2] == team1:
                    can_play = False
                
                if can_play:
                    available_for_doubles.append(match)
        
        additional_matches = available_for_doubles[:remaining_slots]
        current_matches.extend(additional_matches)
        
        return current_matches
    
    def create_single_round_distribution(self):
        """Erstellt eine einzelne Runde mit optimaler Teamverteilung"""
        if self.num_teams < 2:
            return []
        
        matches = []
        available_teams = self.teams.copy()
        
        while len(available_teams) >= 2 and len(matches) < self.matches_per_round:
            team1 = available_teams.pop(0)
            team2 = available_teams.pop(0)
            matches.append((team1, team2))
        
        if len(matches) < self.matches_per_round and len(self.teams) >= 2:
            used_teams = set()
            for match in matches:
                used_teams.update(match)
            
            remaining_slots = self.matches_per_round - len(matches)
            all_possible = list(itertools.combinations(self.teams, 2))
            
            for match in all_possible:
                if len(matches) >= self.matches_per_round:
                    break
                if match not in matches:
                    matches.append(match)
        
        return matches
    
    def get_team_participation_stats(self, schedule):
        """Berechnet Statistiken zur Teamteilnahme"""
        team_count = Counter()
        match_count = 0
        
        for round_matches in schedule:
            for match in round_matches:
                team1, team2 = match
                team_count[team1] += 1
                team_count[team2] += 1
                match_count += 1
        
        stats = {
            'total_matches': match_count,
            'team_counts': dict(team_count),
            'avg_games_per_team': sum(team_count.values()) / len(self.teams) if self.teams else 0,
            'min_games': min(team_count.values()) if team_count else 0,
            'max_games': max(team_count.values()) if team_count else 0,
        }
        stats['games_difference'] = stats['max_games'] - stats['min_games']
        
        return stats

def show_match_distribution_preview(teams, schedule, mode_type):
    """Zeigt eine Vorschau der Match-Verteilung nach Turnier-Erstellung"""
    
    # Berechne Match-Anzahl pro Team aus dem Schedule
    team_match_count = Counter()
    
    for round_data in schedule:
        if isinstance(round_data, dict):  # Zeitbasierte Planung
            matches = round_data['matches']
        else:  # Standard Liste von Matches
            matches = round_data
        
        for match in matches:
            team1, team2 = match
            team_match_count[team1] += 1
            team_match_count[team2] += 1
    
    # Fairness-Bewertung
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
    
    # Team-Match-Übersicht in Spalten
    num_cols = min(len(teams), 8)  # Max 8 Spalten
    team_cols = st.columns(num_cols)
    
    for i, team in enumerate(sorted(teams)):
        with team_cols[i % num_cols]:
            matches = team_match_count.get(team, 0)
            
            # Farbkodierung
            if matches == max_matches:
                delta_color = "inverse" if difference > 1 else "normal"
            elif matches == min_matches:
                delta_color = "normal"
            else:
                delta_color = "off"
            
            st.metric(
                f"{team[:12]}", 
                f"{matches} Matches",
                delta=f"+{matches - min_matches}" if difference > 0 and matches > min_matches else None,
                delta_color=delta_color
            )
    
    # Zusätzliche Info je nach Modus
    if mode_type == "time_based":
        st.info(f"⏱️ Zeitbasierte Planung: {len(schedule)} Runden geplant")
    elif mode_type == "round_robin":
        total_possible = len(teams) * (len(teams) - 1) // 2
        actual_matches = sum(team_match_count.values()) // 2
        st.info(f"🔄 Round-Robin: {actual_matches} von {total_possible} möglichen Begegnungen geplant")
    else:
        st.info(f"🎯 Einzelrunde: {len([m for round_data in schedule for m in (round_data['matches'] if isinstance(round_data, dict) else round_data)])} Matches")

def show_team_match_overview(tournament_id, matches, teams):
    """Zeigt eine kompakte Übersicht der Match-Verteilung pro Team"""
    st.subheader("⚖️ Match-Verteilung pro Team")
    
    # Berechne Match-Anzahl pro Team
    team_match_count = Counter()
    team_played_count = Counter()
    
    for match in matches:
        team_match_count[match['team1']] += 1
        team_match_count[match['team2']] += 1
        
        if match['winner']:  # Match wurde gespielt
            team_played_count[match['team1']] += 1
            team_played_count[match['team2']] += 1
    
    # Fairness-Bewertung
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
            st.success("✅ Faire Verteilung")
        elif difference <= 2:
            st.warning("⚖️ Akzeptabel")
        else:
            st.error("⚠️ Ungleiche Verteilung")
    
    # Kompakte Team-Übersicht
    team_cols = st.columns(min(len(teams), 6))
    for i, team in enumerate(sorted(teams)):
        with team_cols[i % len(team_cols)]:
            total_matches = team_match_count.get(team, 0)
            played_matches = team_played_count.get(team, 0)
            
            # Farbkodierung basierend auf Match-Anzahl
            if total_matches == max_matches:
                color = "🔴"  # Meiste Matches
            elif total_matches == min_matches:
                color = "🟢"  # Wenigste Matches
            else:
                color = "🟡"  # Mittlere Anzahl
            
            st.metric(
                f"{color} {team[:10]}", 
                f"{played_matches}/{total_matches}",
                delta=f"{total_matches - min_matches}" if difference > 0 else None
            )

def show_detailed_team_overview(tournament_id, matches, teams):
    """Zeigt eine detaillierte Team-Übersicht mit allen Statistiken"""
    st.subheader("📊 Detaillierte Team-Übersicht")
    
    # Berechne detaillierte Statistiken pro Team
    team_stats = {}
    
    for team in teams:
        team_stats[team] = {
            'total_matches': 0,
            'played_matches': 0,
            'pending_matches': 0,
            'opponents': [],
            'upcoming_opponents': [],
            'next_match_round': None
        }
    
    # Sammle Match-Daten
    for match in matches:
        team1, team2 = match['team1'], match['team2']
        
        # Team 1
        team_stats[team1]['total_matches'] += 1
        team_stats[team1]['opponents'].append(team2)
        
        if match['winner']:
            team_stats[team1]['played_matches'] += 1
        else:
            team_stats[team1]['pending_matches'] += 1
            team_stats[team1]['upcoming_opponents'].append(team2)
            if team_stats[team1]['next_match_round'] is None:
                team_stats[team1]['next_match_round'] = match['round_number']
        
        # Team 2
        team_stats[team2]['total_matches'] += 1
        team_stats[team2]['opponents'].append(team1)
        
        if match['winner']:
            team_stats[team2]['played_matches'] += 1
        else:
            team_stats[team2]['pending_matches'] += 1
            team_stats[team2]['upcoming_opponents'].append(team1)
            if team_stats[team2]['next_match_round'] is None:
                team_stats[team2]['next_match_round'] = match['round_number']
    
    # Erstelle Übersichtstabelle
    overview_data = []
    for team in sorted(teams):
        stats = team_stats[team]
        next_opponents = ", ".join(stats['upcoming_opponents'][:3])  # Zeige max. 3 nächste Gegner
        if len(stats['upcoming_opponents']) > 3:
            next_opponents += f" (+{len(stats['upcoming_opponents']) - 3} weitere)"
        
        overview_data.append({
            "Team": team,
            "Gesamt Matches": stats['total_matches'],
            "Gespielt": stats['played_matches'],
            "Ausstehend": stats['pending_matches'],
            "Fortschritt %": f"{(stats['played_matches'] / stats['total_matches'] * 100):.0f}%" if stats['total_matches'] > 0 else "0%",
            "Nächste Runde": stats['next_match_round'] if stats['next_match_round'] else "Fertig",
            "Nächste Gegner": next_opponents if next_opponents else "Keine ausstehenden Matches"
        })
    
    df_overview = pd.DataFrame(overview_data)
    st.dataframe(df_overview, hide_index=True, use_container_width=True)
    
    # Visualisierung der Match-Verteilung
    col1, col2 = st.columns(2)
    
    with col1:
        # Balkendiagramm: Gesamt-Matches pro Team
        fig_total = px.bar(
            x=[stats['Team'] for stats in overview_data],  # FIXED: Changed from 'team' to 'Team'
            y=[stats['Gesamt Matches'] for stats in overview_data],
            title="Gesamt-Matches pro Team",
            labels={'x': 'Teams', 'y': 'Anzahl Matches'},
            color=[stats['Gesamt Matches'] for stats in overview_data],
            color_continuous_scale="Blues"
        )
        fig_total.update_layout(xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig_total, use_container_width=True)
    
    with col2:
        # Gestapeltes Balkendiagramm: Gespielt vs. Ausstehend
        teams_list = [stats['Team'] for stats in overview_data]  # FIXED: Changed from 'team' to 'Team'
        played_list = [stats['Gespielt'] for stats in overview_data]  # FIXED: Changed from 'played_matches' to 'Gespielt'
        pending_list = [stats['Ausstehend'] for stats in overview_data]  # FIXED: Changed from 'pending_matches' to 'Ausstehend'
        
        fig_progress = go.Figure(data=[
            go.Bar(name='Gespielt', x=teams_list, y=played_list),
            go.Bar(name='Ausstehend', x=teams_list, y=pending_list)
        ])
        fig_progress.update_layout(
            barmode='stack',
            title="Match-Fortschritt pro Team",
            xaxis_title="Teams",
            yaxis_title="Anzahl Matches",
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig_progress, use_container_width=True)
    
    # Match-Matrix (wer spielt gegen wen)
    st.subheader("🔄 Match-Matrix")
    
    # Erstelle Matrix der Begegnungen
    matrix_data = []
    for team1 in sorted(teams):
        row_data = {"Team": team1}
        for team2 in sorted(teams):
            if team1 == team2:
                row_data[team2] = "-"
            else:
                # Prüfe ob diese Teams gegeneinander spielen
                match_found = False
                match_played = False
                for match in matches:
                    if (match['team1'] == team1 and match['team2'] == team2) or \
                       (match['team1'] == team2 and match['team2'] == team1):
                        match_found = True
                        if match['winner']:
                            match_played = True
                        break
                
                if match_found and match_played:
                    row_data[team2] = "✅"
                elif match_found:
                    row_data[team2] = "⏳"
                else:
                    row_data[team2] = "❌"
        
        matrix_data.append(row_data)
    
    df_matrix = pd.DataFrame(matrix_data)
    st.dataframe(df_matrix, hide_index=True, use_container_width=True)
    
    st.caption("✅ = Gespielt | ⏳ = Geplant | ❌ = Kein Match geplant")

def main():
    st.set_page_config(
        page_title="🎾 Tennis Turnier System",
        page_icon="🎾",
        layout="wide"
    )
    
    # Initialisiere Datenbank
    if 'db' not in st.session_state:
        db_path = "/app/data/tennis_scheduler.db" if os.path.exists("/app") else "tennis_scheduler.db"
        st.session_state.db = TennisDatabase(db_path)
    
    st.title("🎾 Tennis Turnier System")
    st.markdown("---")
    
    # Hauptnavigation
    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Neues Turnier", "📋 Aktuelle Turniere", "🏅 Ranking", "📊 Statistiken"])
    
    with tab1:
        create_new_tournament()
    
    with tab2:
        manage_tournaments()
    
    with tab3:
        show_rankings()
    
    with tab4:
        show_statistics()

def create_new_tournament():
    """Tab für die Erstellung neuer Turniere mit verbessertem Design"""
    st.header("🏆 Neues Turnier erstellen")
    st.markdown("Erstellen Sie in wenigen Schritten Ihr perfektes Tennis-Turnier")
    st.markdown("---")
    
    # Schritt 1: Team-Konfiguration in einer schönen Box
    with st.container():
        st.markdown("### 📋 Schritt 1: Teams konfigurieren")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("#### Eingabemethode wählen")
            input_method = st.radio(
                "",
                ["🔢 Anzahl Teams", "✏️ Team-Namen eingeben"],
                help="Wählen Sie, wie Sie Ihre Teams eingeben möchten"
            )
        
        with col2:
            if input_method == "🔢 Anzahl Teams":
                st.markdown("#### Anzahl Teams")
                num_teams = st.slider(
                    "Wie viele Teams nehmen teil?",
                    min_value=2,
                    max_value=20,
                    value=8,
                    step=1,
                    help="Teams werden automatisch als 'Team 1', 'Team 2', etc. benannt"
                )
                teams = [f"Team {i+1}" for i in range(num_teams)]
                
                # Vorschau in einer schönen Box
                with st.expander(f"👀 Vorschau: {len(teams)} Teams", expanded=True):
                    # Teams in Spalten anzeigen
                    team_cols = st.columns(min(4, len(teams)))
                    for i, team in enumerate(teams[:12]):  # Max 12 Teams in Vorschau
                        with team_cols[i % len(team_cols)]:
                            st.markdown(f"**{team}**")
                    if len(teams) > 12:
                        st.markdown(f"... und {len(teams) - 12} weitere Teams")
            
            else:
                st.markdown("#### Team-Namen eingeben")
                team_names = st.text_area(
                    "Geben Sie jeden Team-Namen in eine neue Zeile ein:",
                    value="FC Barcelona\nReal Madrid\nBayern München\nPSG\nManchester City\nLiverpool\nChelsea\nArsenal",
                    height=180,
                    help="Ein Team-Name pro Zeile. Leere Zeilen werden ignoriert."
                )
                teams = [name.strip() for name in team_names.split('\n') if name.strip()]
                
                # Live-Vorschau der erkannten Teams
                if teams:
                    with st.expander(f"✅ {len(teams)} Teams erkannt", expanded=True):
                        if len(teams) >= 2:
                            st.success(f"Bereit für Turnier mit {len(teams)} Teams!")
                        else:
                            st.warning("Mindestens 2 Teams erforderlich")
                        
                        # Teams in einem schönen Grid anzeigen
                        team_cols = st.columns(min(3, len(teams)))
                        for i, team in enumerate(teams):
                            with team_cols[i % len(team_cols)]:
                                st.markdown(f"🏆 **{team}**")
                else:
                    st.warning("Noch keine Teams eingegeben")
    
    st.markdown("---")
    
    # Schritt 2: Turnier-Details in einem schönen Formular
    with st.container():
        st.markdown("### ⚙️ Schritt 2: Turnier-Details")
        
        with st.form("tournament_config_form", clear_on_submit=False):
            # Grundeinstellungen in zwei Spalten
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 🏟️ Basis-Konfiguration")
                tournament_name = st.text_input(
                    "Turnier Name",
                    value=f"Tennis Turnier {datetime.now().strftime('%d.%m.%Y')}",
                    help="Geben Sie Ihrem Turnier einen aussagekräftigen Namen"
                )
                
                num_courts = st.select_slider(
                    "Anzahl Tennisplätze",
                    options=list(range(1, 11)),
                    value=4,
                    help="Anzahl der verfügbaren Plätze für gleichzeitige Spiele"
                )
                
                players_per_team = st.select_slider(
                    "Spieler pro Team",
                    options=[2, 3, 4, 5, 6, 7, 8],
                    value=4,
                    help="Jedes Team kann auf max. 2 Plätzen gleichzeitig spielen"
                )
            
            with col2:
                st.markdown("#### 🎯 Spielmodus")
                mode = st.selectbox(
                    "Wählen Sie den Turnier-Modus:",
                    ["⏱️ Zeitbasierte Planung", "🔄 Vollständiges Turnier (Round-Robin)", "🎮 Einzelne Runde"],
                    help="Verschiedene Modi für unterschiedliche Turnier-Arten"
                )
                
                # Zeitbasierte Einstellungen in einer schönen Box
                if mode == "⏱️ Zeitbasierte Planung":
                    with st.container():
                        st.markdown("##### ⏰ Zeit-Konfiguration")
                        time_input_method = st.radio(
                            "Zeit-Eingabe:",
                            ["🕐 Stunden und Minuten", "📊 Nur Minuten"],
                            horizontal=True
                        )
                        
                        if time_input_method == "🕐 Stunden und Minuten":
                            time_col1, time_col2 = st.columns(2)
                            with time_col1:
                                hours = st.number_input("Stunden", min_value=0, max_value=12, value=2, step=1)
                            with time_col2:
                                minutes = st.number_input("Zusätzliche Minuten", min_value=0, max_value=59, value=0, step=15)
                            total_minutes = hours * 60 + minutes
                        else:
                            total_minutes = st.slider(
                                "Gesamtdauer (Minuten)",
                                min_value=20,
                                max_value=480,
                                value=120,
                                step=20,
                                help="Mindestens 20 Minuten für eine Runde"
                            )
                        
                        # Zeitvorschau
                        estimated_rounds = total_minutes // 20
                        st.info(f"📊 Geschätzt: ~{estimated_rounds} Runden à 20 Minuten")
                
                elif mode == "🔄 Vollständiges Turnier (Round-Robin)":
                    if teams:
                        total_possible_matches = len(teams) * (len(teams) - 1) // 2
                        estimated_rounds = math.ceil(total_possible_matches / num_courts)
                        estimated_time = estimated_rounds * 20
                        
                        st.info(f"📊 {total_possible_matches} Matches in ~{estimated_rounds} Runden")
                        st.info(f"⏰ Geschätzte Dauer: ~{estimated_time // 60}h {estimated_time % 60}min")
                
                else:  # Einzelne Runde
                    max_matches_single = min(num_courts, len(teams) // 2)
                    st.info(f"🎮 {max_matches_single} Matches in einer Runde")
                    st.info(f"⏰ Dauer: ~20 Minuten")
            
            # Erweiterte Optionen (optional)
            with st.expander("🔧 Erweiterte Optionen", expanded=False):
                col_opt1, col_opt2 = st.columns(2)
                with col_opt1:
                    enable_overtime = st.checkbox("⏰ Verlängerung bei Unentschieden", value=False)
                    fair_play_mode = st.checkbox("⚖️ Fairplay-Modus (ausgewogene Verteilung)", value=True)
                
                with col_opt2:
                    auto_scheduling = st.checkbox("🤖 Automatische Optimierung", value=True)
                    notification_mode = st.checkbox("🔔 Benachrichtigungen aktivieren", value=False)
            
            st.markdown("---")
            
            # Submit Button mit Stil
            col_submit1, col_submit2, col_submit3 = st.columns([1, 2, 1])
            with col_submit2:
                submitted = st.form_submit_button(
                    "🚀 Turnier erstellen und starten!",
                    type="primary",
                    use_container_width=True,
                    help="Klicken Sie hier, um Ihr Turnier zu erstellen"
                )
        
        # Validierung und Turnier-Erstellung
        if submitted:
            # Validierung
            validation_errors = []
            
            if len(teams) < 2:
                validation_errors.append("❌ Mindestens 2 Teams erforderlich")
            
            if not tournament_name.strip():
                validation_errors.append("❌ Turnier-Name darf nicht leer sein")
            
            if mode == "⏱️ Zeitbasierte Planung" and total_minutes < 20:
                validation_errors.append("❌ Mindestens 20 Minuten für zeitbasierte Planung erforderlich")
            
            if validation_errors:
                for error in validation_errors:
                    st.error(error)
            else:
                # Erfolgreiche Validierung - Turnier erstellen
                with st.spinner("🔄 Turnier wird erstellt..."):
                    time.sleep(1)  # Kurze Verzögerung für bessere UX
                    
                    tournament_id = st.session_state.db.create_tournament(
                        tournament_name.strip(), teams, num_courts, players_per_team, mode
                    )
                    
                    scheduler = TennisScheduler(num_courts, teams, players_per_team, st.session_state.db)
                    
                    if mode == "⏱️ Zeitbasierte Planung":
                        schedule, stats = scheduler.create_time_based_schedule(total_minutes)
                        if "error" not in stats:
                            st.session_state.db.save_matches(tournament_id, schedule)
                            
                            # Erfolgs-Animation
                            st.success(f"✅ Turnier '{tournament_name}' erfolgreich erstellt!")
                            st.balloons()
                            
                            # Schöne Ergebnis-Übersicht
                            with st.container():
                                st.markdown("### 🎉 Turnier erfolgreich erstellt!")
                                
                                # Zusammenfassung in Metriken
                                summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
                                with summary_col1:
                                    st.metric("Teams", len(teams))
                                with summary_col2:
                                    st.metric("Runden", len(schedule))
                                with summary_col3:
                                    st.metric("Matches", sum(len(r['matches']) if isinstance(r, dict) else len(r) for r in schedule))
                                with summary_col4:
                                    st.metric("Plätze", num_courts)
                                
                                # Match-Verteilung
                                st.subheader("⚖️ Geplante Match-Verteilung")
                                show_match_distribution_preview(teams, schedule, "time_based")
                        else:
                            st.error(f"⚠️ Fehler bei der Turnier-Erstellung: {stats['error']}")
                    
                    elif mode == "🔄 Vollständiges Turnier (Round-Robin)":
                        schedule = scheduler.create_round_robin_schedule()
                        st.session_state.db.save_matches(tournament_id, schedule)
                        
                        st.success(f"✅ Turnier '{tournament_name}' erfolgreich erstellt!")
                        st.balloons()
                        
                        # Zusammenfassung
                        with st.container():
                            st.markdown("### 🎉 Round-Robin Turnier erstellt!")
                            
                            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
                            with summary_col1:
                                st.metric("Teams", len(teams))
                            with summary_col2:
                                st.metric("Runden", len(schedule))
                            with summary_col3:
                                st.metric("Matches", sum(len(round_matches) for round_matches in schedule))
                            with summary_col4:
                                st.metric("Plätze", num_courts)
                            
                            st.subheader("⚖️ Geplante Match-Verteilung")
                            show_match_distribution_preview(teams, schedule, "round_robin")
                    
                    else:  # Einzelne Runde
                        matches = scheduler.create_single_round_distribution()
                        schedule = [matches]
                        st.session_state.db.save_matches(tournament_id, schedule)
                        
                        st.success(f"✅ Runde erfolgreich erstellt!")
                        
                        # Zusammenfassung
                        with st.container():
                            st.markdown("### 🎮 Einzelrunde erstellt!")
                            
                            summary_col1, summary_col2, summary_col3 = st.columns(3)
                            with summary_col1:
                                st.metric("Teams", len(teams))
                            with summary_col2:
                                st.metric("Matches", len(matches))
                            with summary_col3:
                                st.metric("Plätze genutzt", len(matches))
                            
                            st.subheader("🎯 Match-Verteilung dieser Runde")
                            show_match_distribution_preview(teams, schedule, "single_round")

def manage_tournaments():
    """Tab für die Verwaltung bestehender Turniere"""
    st.header("📋 Turnier Verwaltung")
    
    tournaments = st.session_state.db.get_tournaments()
    
    if not tournaments:
        st.info("📋 Noch keine Turniere erstellt. Gehe zum Tab 'Neues Turnier' um zu starten.")
        return
    
    # Turnier auswählen
    tournament_options = {f"{t['name']} ({t['created_at'][:10]})": t['id'] for t in tournaments}
    selected_tournament_name = st.selectbox("Turnier auswählen:", list(tournament_options.keys()))
    
    if selected_tournament_name:
        tournament_id = tournament_options[selected_tournament_name]
        tournament = next(t for t in tournaments if t['id'] == tournament_id)
        
        st.subheader(f"🏆 {tournament['name']}")
        
        # Turnier Info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Teams", len(tournament['teams']))
        with col2:
            st.metric("Plätze", tournament['num_courts'])
        with col3:
            st.metric("Spieler/Team", tournament['players_per_team'])
        with col4:
            st.metric("Modus", tournament['mode'])
        
        # Matches laden
        matches = st.session_state.db.get_matches(tournament_id)
        
        if matches:
            # Match-Verteilung pro Team anzeigen
            show_team_match_overview(tournament_id, matches, tournament['teams'])
            
            st.markdown("---")
            
            # Tabs für Match-Verwaltung
            match_tab1, match_tab2, match_tab3, match_tab4 = st.tabs(["🎮 Ergebnisse eintragen", "📅 Spielplan", "🏅 Aktuelles Ranking", "📊 Team-Übersicht"])
            
            with match_tab1:
                enter_match_results(tournament_id, matches)
            
            with match_tab2:
                show_match_schedule(matches, tournament)
            
            with match_tab3:
                show_tournament_ranking(tournament_id)
            
            with match_tab4:
                show_detailed_team_overview(tournament_id, matches, tournament['teams'])
        else:
            st.info("📋 Keine Matches für dieses Turnier gefunden.")

def enter_match_results(tournament_id, matches):
    """Interface für die Eingabe von Match-Ergebnissen"""
    st.subheader("🎮 Match-Ergebnisse eintragen")
    
    # Filter für ungespielte Matches
    unplayed_matches = [m for m in matches if not m['winner']]
    played_matches = [m for m in matches if m['winner']]
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        st.metric("Offene Matches", len(unplayed_matches))
        st.metric("Gespielte Matches", len(played_matches))
        st.metric("Fortschritt", f"{len(played_matches)}/{len(matches)}")
        
        if len(matches) > 0:
            progress = len(played_matches) / len(matches)
            st.progress(progress)
    
    with col1:
        if unplayed_matches:
            # Gruppiere Matches nach Runden
            rounds = {}
            for match in unplayed_matches:
                round_num = match['round_number']
                if round_num not in rounds:
                    rounds[round_num] = []
                rounds[round_num].append(match)
            
            for round_num in sorted(rounds.keys()):
                with st.expander(f"🎾 Runde {round_num}", expanded=True):
                    round_matches = rounds[round_num]
                    
                    for match in round_matches:
                        with st.container():
                            st.markdown(f"**Platz {match['court_number']}:** {match['team1']} vs {match['team2']}")
                            
                            col_team1, col_vs, col_team2, col_action = st.columns([2, 1, 2, 2])
                            
                            with col_team1:
                                team1_score = st.number_input(
                                    f"Punkte {match['team1']}",
                                    min_value=0,
                                    max_value=100,
                                    value=0,
                                    key=f"team1_score_{match['id']}"
                                )
                            
                            with col_vs:
                                st.markdown("**:**")
                            
                            with col_team2:
                                team2_score = st.number_input(
                                    f"Punkte {match['team2']}",
                                    min_value=0,
                                    max_value=100,
                                    value=0,
                                    key=f"team2_score_{match['id']}"
                                )
                            
                            with col_action:
                                col_buttons = st.columns(3)
                                with col_buttons[0]:
                                    if st.button(f"🏆 {match['team1'][:8]}", key=f"win1_{match['id']}"):
                                        st.session_state.db.update_match_result(
                                            match['id'], match['team1'], team1_score, team2_score
                                        )
                                        st.success(f"✅ {match['team1']} gewinnt!")
                                        st.rerun()
                                
                                with col_buttons[1]:
                                    if st.button("🤝 Unentschieden", key=f"draw_{match['id']}"):
                                        st.session_state.db.update_match_result(
                                            match['id'], 'Draw', team1_score, team2_score
                                        )
                                        st.success("✅ Unentschieden eingetragen!")
                                        st.rerun()
                                
                                with col_buttons[2]:
                                    if st.button(f"🏆 {match['team2'][:8]}", key=f"win2_{match['id']}"):
                                        st.session_state.db.update_match_result(
                                            match['id'], match['team2'], team1_score, team2_score
                                        )
                                        st.success(f"✅ {match['team2']} gewinnt!")
                                        st.rerun()
                            
                            st.markdown("---")
        else:
            st.success("🎉 Alle Matches wurden gespielt!")
            st.balloons()

def show_match_schedule(matches, tournament):
    """Zeigt den Spielplan an"""
    st.subheader("📅 Spielplan")
    
    # Gruppiere Matches nach Runden
    rounds = {}
    for match in matches:
        round_num = match['round_number']
        if round_num not in rounds:
            rounds[round_num] = []
        rounds[round_num].append(match)
    
    for round_num in sorted(rounds.keys()):
        with st.expander(f"🎾 Runde {round_num}", expanded=False):
            round_matches = rounds[round_num]
            
            match_data = []
            for match in round_matches:
                status = "✅" if match['winner'] else "⏳"
                result = ""
                if match['winner']:
                    if match['winner'] == 'Draw':
                        result = f"{match['team1_score']}:{match['team2_score']} (Unentschieden)"
                    else:
                        result = f"{match['team1_score']}:{match['team2_score']} (Sieger: {match['winner']})"
                
                # Zeitinformationen
                time_info = ""
                if match['start_time_minutes'] is not None:
                    start_h, start_m = divmod(match['start_time_minutes'], 60)
                    end_h, end_m = divmod(match['end_time_minutes'], 60)
                    time_info = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
                
                match_data.append({
                    "Status": status,
                    "Platz": match['court_number'],
                    "Team 1": match['team1'],
                    "Team 2": match['team2'],
                    "Ergebnis": result,
                    "Zeit": time_info
                })
            
            df_matches = pd.DataFrame(match_data)
            st.dataframe(df_matches, hide_index=True, use_container_width=True)

def show_tournament_ranking(tournament_id):
    """Zeigt das aktuelle Ranking an"""
    st.subheader("🏅 Aktuelles Ranking")
    
    ranking = st.session_state.db.get_ranking(tournament_id)
    
    if ranking:
        # Top 3 Podium
        if len(ranking) >= 3:
            col1, col2, col3 = st.columns(3)
            
            with col2:  # 1. Platz in der Mitte
                st.markdown("### 🥇")
                st.markdown(f"**{ranking[0]['team']}**")
                st.markdown(f"🏆 {ranking[0]['ranking_points']} Punkte")
                st.markdown(f"📊 {ranking[0]['matches_won']}/{ranking[0]['matches_played']} Siege")
            
            with col1:  # 2. Platz links
                if len(ranking) > 1:
                    st.markdown("### 🥈")
                    st.markdown(f"**{ranking[1]['team']}**")
                    st.markdown(f"🏆 {ranking[1]['ranking_points']} Punkte")
                    st.markdown(f"📊 {ranking[1]['matches_won']}/{ranking[1]['matches_played']} Siege")
            
            with col3:  # 3. Platz rechts
                if len(ranking) > 2:
                    st.markdown("### 🥉")
                    st.markdown(f"**{ranking[2]['team']}**")
                    st.markdown(f"🏆 {ranking[2]['ranking_points']} Punkte")
                    st.markdown(f"📊 {ranking[2]['matches_won']}/{ranking[2]['matches_played']} Siege")
        
        st.markdown("---")
        
        # Vollständige Tabelle
        ranking_data = []
        for team in ranking:
            ranking_data.append({
                "Platz": f"{team['position']}.",
                "Team": team['team'],
                "Spiele": team['matches_played'],
                "Siege": team['matches_won'],
                "Niederlagen": team['matches_lost'],
                "Siegquote %": f"{team['win_rate']:.1f}%",
                "Punkte +": team['points_for'],
                "Punkte -": team['points_against'],
                "Differenz": f"+{team['goal_difference']}" if team['goal_difference'] >= 0 else str(team['goal_difference']),
                "Rang-Punkte": team['ranking_points']
            })
        
        df_ranking = pd.DataFrame(ranking_data)
        st.dataframe(df_ranking, hide_index=True, use_container_width=True)
        
        # Ranking-Visualisierung
        if len(ranking) > 1:
            fig = px.bar(
                x=[team['team'] for team in ranking],
                y=[team['ranking_points'] for team in ranking],
                title="Ranking nach Punkten",
                labels={'x': 'Teams', 'y': 'Rang-Punkte'},
                color=[team['ranking_points'] for team in ranking],
                color_continuous_scale="Blues"
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
    
    else:
        st.info("🎾 Noch keine Spiele gespielt - Ranking wird nach den ersten Ergebnissen angezeigt.")

def show_rankings():
    """Tab für Gesamt-Rankings"""
    st.header("🏅 Turnier-Rankings")
    
    tournaments = st.session_state.db.get_tournaments()
    
    if not tournaments:
        st.info("📋 Noch keine Turniere vorhanden.")
        return
    
    for tournament in tournaments:
        with st.expander(f"🏆 {tournament['name']} ({tournament['created_at'][:10]})", expanded=False):
            ranking = st.session_state.db.get_ranking(tournament['id'])
            
            if ranking and any(team['matches_played'] > 0 for team in ranking):
                # Mini-Podium
                played_teams = [team for team in ranking if team['matches_played'] > 0]
                
                if len(played_teams) >= 1:
                    st.markdown(f"🥇 **Champion:** {played_teams[0]['team']} ({played_teams[0]['ranking_points']} Punkte)")
                
                if len(played_teams) >= 2:
                    st.markdown(f"🥈 **Zweiter:** {played_teams[1]['team']} ({played_teams[1]['ranking_points']} Punkte)")
                
                if len(played_teams) >= 3:
                    st.markdown(f"🥉 **Dritter:** {played_teams[2]['team']} ({played_teams[2]['ranking_points']} Punkte)")
                
                # Kurze Statistiken
                total_matches = sum(team['matches_played'] for team in ranking) // 2  # Jedes Match zählt für 2 Teams
                matches_in_db = len(st.session_state.db.get_matches(tournament['id']))
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Gespielte Matches", total_matches)
                with col2:
                    st.metric("Teams", len(tournament['teams']))
                with col3:
                    completion = (total_matches / matches_in_db * 100) if matches_in_db > 0 else 0
                    st.metric("Fortschritt", f"{completion:.0f}%")
            
            else:
                st.info("🎾 Turnier noch nicht gestartet.")

def show_statistics():
    """Tab für erweiterte Statistiken"""
    st.header("📊 Turnier-Statistiken")
    
    tournaments = st.session_state.db.get_tournaments()
    
    if not tournaments:
        st.info("📋 Noch keine Turniere vorhanden.")
        return
    
    # Gesamt-Übersicht
    st.subheader("📈 Gesamt-Übersicht")
    
    total_tournaments = len(tournaments)
    total_teams = sum(len(t['teams']) for t in tournaments)
    total_matches_all = sum(len(st.session_state.db.get_matches(t['id'])) for t in tournaments)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Turniere", total_tournaments)
    with col2:
        st.metric("Teams gesamt", total_teams)
    with col3:
        st.metric("Matches gesamt", total_matches_all)
    with col4:
        avg_teams = total_teams / total_tournaments if total_tournaments > 0 else 0
        st.metric("Ø Teams/Turnier", f"{avg_teams:.1f}")
    
    # Turnier-Modi Verteilung
    if tournaments:
        mode_counts = Counter(t['mode'] for t in tournaments)
        
        fig_modes = px.pie(
            values=list(mode_counts.values()),
            names=list(mode_counts.keys()),
            title="Verteilung der Turnier-Modi"
        )
        st.plotly_chart(fig_modes, use_container_width=True)
    
    # Detaillierte Turnier-Statistiken
    st.subheader("📋 Detaillierte Statistiken")
    
    tournament_stats = []
    for tournament in tournaments:
        matches = st.session_state.db.get_matches(tournament['id'])
        played_matches = len([m for m in matches if m['winner']])
        ranking = st.session_state.db.get_ranking(tournament['id'])
        
        champion = "TBD"
        if ranking and ranking[0]['matches_played'] > 0:
            champion = ranking[0]['team']
        
        tournament_stats.append({
            "Turnier": tournament['name'],
            "Datum": tournament['created_at'][:10],
            "Modus": tournament['mode'],
            "Teams": len(tournament['teams']),
            "Plätze": tournament['num_courts'],
            "Matches geplant": len(matches),
            "Matches gespielt": played_matches,
            "Fortschritt %": f"{(played_matches / len(matches) * 100):.0f}%" if matches else "0%",
            "Champion": champion
        })
    
    df_stats = pd.DataFrame(tournament_stats)
    st.dataframe(df_stats, hide_index=True, use_container_width=True)

if __name__ == "__main__":
    main()