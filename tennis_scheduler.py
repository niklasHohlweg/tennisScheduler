import streamlit as st
import itertools
from collections import Counter, defaultdict
import random
import math
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

class TennisScheduler:
    def __init__(self, num_courts, teams, players_per_team=4):
        self.num_courts = num_courts
        self.teams = teams if isinstance(teams, list) else [f"Team {i+1}" for i in range(teams)]
        self.num_teams = len(self.teams)
        self.matches_per_round = num_courts
        self.max_players_per_round = num_courts * 2
        self.players_per_team = players_per_team
        self.max_simultaneous_matches_per_team = players_per_team // 2
        
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

def main():
    st.set_page_config(
        page_title="🎾 Tennis Platz Verteilungssystem",
        page_icon="🎾",
        layout="wide"
    )
    
    st.title("🎾 Tennis Platz Verteilungssystem")
    st.markdown("---")
    
    with st.sidebar:
        st.header("⚙️ Einstellungen")
        
        # Anzahl der Tennisplätze
        num_courts = st.number_input(
            "Anzahl der Tennisplätze",
            min_value=1,
            max_value=20,
            value=4,
            step=1
        )
        
        # Team-Eingabe
        st.subheader("Teams")
        input_method = st.radio(
            "Team-Eingabemethode:",
            ["Anzahl Teams", "Team-Namen eingeben"]
        )
        
        if input_method == "Anzahl Teams":
            num_teams = st.number_input(
                "Anzahl der Teams",
                min_value=2,
                max_value=50,
                value=8,
                step=1
            )
            teams = [f"Team {i+1}" for i in range(num_teams)]
        else:
            team_names = st.text_area(
                "Team-Namen (eine pro Zeile):",
                value="Team 1\nTeam 2\nTeam 3\nTeam 4\nTeam 5\nTeam 6\nTeam 7\nTeam 8",
                height=150
            )
            teams = [name.strip() for name in team_names.split('\n') if name.strip()]
        
        # Spieler pro Team
        players_per_team = st.number_input(
            "Spieler pro Team",
            min_value=2,
            max_value=8,
            value=4,
            step=1,
            help="Jedes Team kann gleichzeitig auf max. 2 Plätzen spielen (bei 4 Spielern)"
        )
        
        st.info(f"📊 {len(teams)} Teams konfiguriert\n👥 {players_per_team} Spieler pro Team")
        
        # Modus-Auswahl
        st.subheader("Modus")
        mode = st.radio(
            "Spielmodus auswählen:",
            ["Zeitbasierte Planung", "Einzelne Runde", "Vollständiges Turnier (Round-Robin)"]
        )
        
        # Zeitbasierte Einstellungen
        if mode == "Zeitbasierte Planung":
            st.subheader("⏰ Zeitplanung")
            
            time_input_method = st.radio(
                "Zeit-Eingabe:",
                ["Stunden und Minuten", "Nur Minuten"]
            )
            
            if time_input_method == "Stunden und Minuten":
                hours = st.number_input("Stunden", min_value=0, max_value=12, value=2, step=1)
                minutes = st.number_input("Zusätzliche Minuten", min_value=0, max_value=59, value=0, step=5)
                total_minutes = hours * 60 + minutes
            else:
                total_minutes = st.number_input(
                    "Gesamtdauer (Minuten)",
                    min_value=20,
                    max_value=720,
                    value=120,
                    step=20,
                    help="Mindestens 20 Minuten für eine Runde"
                )
            
            st.info(f"⏱️ Gesamtdauer: {total_minutes} Minuten ({total_minutes//60}h {total_minutes%60}min)")
            st.info(f"🏟️ Pro Runde: 15 min Spiel + 5 min Pause = 20 min")
            st.info(f"🔄 Mögliche Runden: {total_minutes // 20}")
    
    # Hauptbereich
    if len(teams) < 2:
        st.error("⚠️ Mindestens 2 Teams erforderlich!")
        return
    
    scheduler = TennisScheduler(num_courts, teams, players_per_team)
    
    # Zeige Basisinformationen
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Teams", len(teams))
    with col2:
        st.metric("Plätze", num_courts)
    with col3:
        possible_matches = len(scheduler.generate_all_possible_matches())
        st.metric("Mögliche Matches", possible_matches)
    with col4:
        max_simultaneous = scheduler.max_simultaneous_matches_per_team
        st.metric("Max Matches/Team gleichzeitig", max_simultaneous)
    
    st.markdown("---")
    
    if mode == "Zeitbasierte Planung":
        st.header("⏰ Zeitbasierte Planung")
        
        if st.button("🚀 Zeitplan generieren", type="primary"):
            with st.spinner("Generiere zeitbasierten Spielplan..."):
                schedule, stats = scheduler.create_time_based_schedule(total_minutes)
            
            if "error" in stats:
                st.error(f"⚠️ {stats['error']}")
                return
            
            # Tabs für verschiedene Ansichten
            tab1, tab2, tab3, tab4 = st.tabs(["🕒 Zeitplan", "📊 Statistiken", "📈 Visualisierung", "📋 Zusammenfassung"])
            
            with tab1:
                st.subheader("🗓️ Detaillierter Zeitplan")
                
                for round_data in schedule:
                    round_num = round_data['round']
                    matches = round_data['matches']
                    start_time = round_data['start_time']
                    end_time = round_data['end_time']
                    
                    start_h, start_m = divmod(start_time, 60)
                    end_h, end_m = divmod(end_time, 60)
                    
                    with st.expander(f"🎾 Runde {round_num} ({start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d})", expanded=True):
                        if matches:
                            match_data = []
                            for i, match in enumerate(matches, 1):
                                team1, team2 = match
                                match_data.append({
                                    "Platz": i,
                                    "Team 1": team1,
                                    "vs": "vs",
                                    "Team 2": team2,
                                    "Zeit": f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
                                })
                            
                            df_round = pd.DataFrame(match_data)
                            st.dataframe(df_round, hide_index=True, use_container_width=True)
                        else:
                            st.info("Keine Matches in dieser Runde")
            
            with tab2:
                st.subheader("📊 Zeitplan-Statistiken")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Geplante Zeit", f"{stats['planned_duration']} min")
                with col2:
                    st.metric("Tatsächliche Zeit", f"{stats['actual_duration']} min")
                with col3:
                    st.metric("Zeiteffizienz", f"{stats['efficiency']:.1f}%")
                with col4:
                    st.metric("Platzauslastung", f"{stats['court_utilization']:.1f}%")
                
                col5, col6, col7, col8 = st.columns(4)
                with col5:
                    st.metric("Gesamte Matches", stats['total_matches'])
                with col6:
                    st.metric("Ø Spiele pro Team", f"{stats['avg_games_per_team']:.1f}")
                with col7:
                    st.metric("Min Spiele", stats['min_games'])
                with col8:
                    st.metric("Max Spiele", stats['max_games'])
                
                # Fairness-Bewertung
                difference = stats['games_difference']
                if difference <= 1:
                    st.success("✅ Sehr faire Verteilung!")
                elif difference <= 2:
                    st.warning("⚖️ Akzeptable Verteilung")
                else:
                    st.error("⚠️ Ungleiche Verteilung")
                
                # Team-Spiele Tabelle
                st.subheader("🏅 Spiele pro Team")
                team_stats = []
                for team in sorted(teams):
                    count = stats['team_counts'].get(team, 0)
                    team_stats.append({
                        "Team": team,
                        "Anzahl Spiele": count,
                        "Spielzeit (min)": count * 15,  # 15 min pro Match
                        "Prozent der Max-Spiele": f"{(count / stats['max_games'] * 100):.1f}%" if stats['max_games'] > 0 else "0%"
                    })
                
                df_stats = pd.DataFrame(team_stats)
                st.dataframe(df_stats, hide_index=True, use_container_width=True)
            
            with tab3:
                st.subheader("📈 Visualisierungen")
                
                if stats['team_counts']:
                    # Balkendiagramm für Spiele pro Team
                    df_viz = pd.DataFrame([
                        {"Team": team, "Spiele": count}
                        for team, count in stats['team_counts'].items()
                    ])
                    
                    fig_bar = px.bar(
                        df_viz,
                        x="Team",
                        y="Spiele",
                        title="Anzahl Spiele pro Team",
                        color="Spiele",
                        color_continuous_scale="Blues"
                    )
                    fig_bar.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_bar, use_container_width=True)
                    
                    # Zeitachse der Runden
                    timeline_data = []
                    for round_data in schedule:
                        round_num = round_data['round']
                        start_time = round_data['start_time']
                        end_time = round_data['end_time']
                        matches = len(round_data['matches'])
                        
                        timeline_data.append({
                            "Runde": f"Runde {round_num}",
                            "Start": start_time,
                            "Ende": end_time,
                            "Matches": matches
                        })
                    
                    df_timeline = pd.DataFrame(timeline_data)
                    
                    fig_timeline = px.timeline(
                        df_timeline,
                        x_start="Start",
                        x_end="Ende",
                        y="Runde",
                        color="Matches",
                        title="Zeitplan-Timeline",
                        labels={"Start": "Zeit (Minuten)", "Ende": "Zeit (Minuten)"}
                    )
                    st.plotly_chart(fig_timeline, use_container_width=True)
            
            with tab4:
                st.subheader("📋 Zeitplan-Zusammenfassung")
                
                st.write("**Zeitplan-Details:**")
                st.write(f"- **Teams:** {len(teams)} ({players_per_team} Spieler pro Team)")
                st.write(f"- **Plätze:** {num_courts}")
                st.write(f"- **Runden:** {stats['total_rounds']}")
                st.write(f"- **Gesamte Matches:** {stats['total_matches']}")
                st.write(f"- **Geplante Zeit:** {stats['planned_duration']} Minuten")
                st.write(f"- **Tatsächliche Spielzeit:** {stats['actual_duration']} Minuten")
                st.write(f"- **Platzauslastung:** {stats['court_utilization']:.1f}%")
                
                # Export für Zeitplan
                st.subheader("💾 Export")
                
                export_data = []
                for round_data in schedule:
                    round_num = round_data['round']
                    start_time = round_data['start_time']
                    end_time = round_data['end_time']
                    start_h, start_m = divmod(start_time, 60)
                    end_h, end_m = divmod(end_time, 60)
                    
                    for court_num, match in enumerate(round_data['matches'], 1):
                        team1, team2 = match
                        export_data.append({
                            "Runde": round_num,
                            "Platz": court_num,
                            "Team 1": team1,
                            "Team 2": team2,
                            "Startzeit": f"{start_h:02d}:{start_m:02d}",
                            "Endzeit": f"{end_h:02d}:{end_m:02d}",
                            "Dauer": "15 min"
                        })
                
                if export_data:
                    df_export = pd.DataFrame(export_data)
                    csv = df_export.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Zeitplan als CSV herunterladen",
                        data=csv,
                        file_name="tennis_zeitplan.csv",
                        mime="text/csv"
                    )
    
    elif mode == "Einzelne Runde":
        st.header("🎯 Einzelne Runde")
        
        if st.button("🎮 Runde generieren", type="primary"):
            matches = scheduler.create_single_round_distribution()
            
            if not matches:
                st.error("Keine Matches möglich - zu wenige Teams!")
                return
            
            # Zeige Matches
            st.subheader("🏟️ Platz-Verteilung")
            
            match_data = []
            for i, match in enumerate(matches, 1):
                team1, team2 = match
                match_data.append({
                    "Platz": i,
                    "Team 1": team1,
                    "vs": "vs",
                    "Team 2": team2
                })
            
            df_matches = pd.DataFrame(match_data)
            st.dataframe(df_matches, hide_index=True, use_container_width=True)
            
            # Zeige wartende Teams
            used_teams = set()
            for match in matches:
                used_teams.update(match)
            unused_teams = set(teams) - used_teams
            
            if unused_teams:
                st.subheader("⏳ Wartende Teams")
                waiting_cols = st.columns(min(len(unused_teams), 5))
                for i, team in enumerate(sorted(unused_teams)):
                    with waiting_cols[i % len(waiting_cols)]:
                        st.info(team)
    
    else:  # Vollständiges Turnier
        st.header("🏆 Vollständiges Turnier (Round-Robin)")
        
        if st.button("🚀 Turnier generieren", type="primary"):
            with st.spinner("Generiere Turnierplan..."):
                schedule = scheduler.create_round_robin_schedule()
                stats = scheduler.get_team_participation_stats(schedule)
            
            # Tabs für verschiedene Ansichten
            tab1, tab2, tab3, tab4 = st.tabs(["📅 Spielplan", "📊 Statistiken", "📈 Visualisierung", "📋 Zusammenfassung"])
            
            with tab1:
                st.subheader("🗓️ Detaillierter Spielplan")
                
                for round_num, round_matches in enumerate(schedule, 1):
                    with st.expander(f"🎾 Runde {round_num}", expanded=True):
                        match_data = []
                        for i, match in enumerate(round_matches, 1):
                            team1, team2 = match
                            match_data.append({
                                "Platz": i,
                                "Team 1": team1,
                                "vs": "vs",
                                "Team 2": team2
                            })
                        
                        if match_data:
                            df_round = pd.DataFrame(match_data)
                            st.dataframe(df_round, hide_index=True, use_container_width=True)
                        else:
                            st.info("Keine Matches in dieser Runde")
            
            with tab2:
                st.subheader("📊 Team-Statistiken")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Gesamte Matches", stats['total_matches'])
                with col2:
                    st.metric("Ø Spiele pro Team", f"{stats['avg_games_per_team']:.1f}")
                with col3:
                    st.metric("Min Spiele", stats['min_games'])
                with col4:
                    st.metric("Max Spiele", stats['max_games'])
                
                # Fairness-Bewertung
                difference = stats['games_difference']
                if difference <= 1:
                    st.success("✅ Sehr faire Verteilung!")
                elif difference <= 2:
                    st.warning("⚖️ Akzeptable Verteilung")
                else:
                    st.error("⚠️ Ungleiche Verteilung - Optimierung empfohlen")
                
                # Team-Spiele Tabelle
                st.subheader("🏅 Spiele pro Team")
                team_stats = []
                for team in sorted(teams):
                    count = stats['team_counts'].get(team, 0)
                    team_stats.append({
                        "Team": team,
                        "Anzahl Spiele": count,
                        "Prozent der Max-Spiele": f"{(count / stats['max_games'] * 100):.1f}%" if stats['max_games'] > 0 else "0%"
                    })
                
                df_stats = pd.DataFrame(team_stats)
                st.dataframe(df_stats, hide_index=True, use_container_width=True)
            
            with tab3:
                st.subheader("📈 Spiele-Verteilung Visualisierung")
                
                if stats['team_counts']:
                    # Balkendiagramm
                    df_viz = pd.DataFrame([
                        {"Team": team, "Spiele": count}
                        for team, count in stats['team_counts'].items()
                    ])
                    
                    fig_bar = px.bar(
                        df_viz,
                        x="Team",
                        y="Spiele",
                        title="Anzahl Spiele pro Team",
                        color="Spiele",
                        color_continuous_scale="Blues"
                    )
                    fig_bar.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_bar, use_container_width=True)
                    
                    # Kreisdiagramm
                    fig_pie = px.pie(
                        df_viz,
                        values="Spiele",
                        names="Team",
                        title="Spiele-Verteilung (Prozentual)"
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
            
            with tab4:
                st.subheader("📋 Turnier-Zusammenfassung")
                
                st.write("**Turnier-Details:**")
                st.write(f"- **Teams:** {len(teams)}")
                st.write(f"- **Plätze:** {num_courts}")
                st.write(f"- **Runden:** {len(schedule)}")
                st.write(f"- **Gesamte Matches:** {stats['total_matches']}")
                st.write(f"- **Matches pro Runde:** {num_courts}")
                
                st.write("\n**Team-Liste:**")
                team_cols = st.columns(min(len(teams), 4))
                for i, team in enumerate(teams):
                    with team_cols[i % len(team_cols)]:
                        games = stats['team_counts'].get(team, 0)
                        st.metric(team, f"{games} Spiele")
                
                # Download-Option für Spielplan
                st.subheader("💾 Export")
                
                # Erstelle Export-Daten
                export_data = []
                for round_num, round_matches in enumerate(schedule, 1):
                    for court_num, match in enumerate(round_matches, 1):
                        team1, team2 = match
                        export_data.append({
                            "Runde": round_num,
                            "Platz": court_num,
                            "Team 1": team1,
                            "Team 2": team2
                        })
                
                if export_data:
                    df_export = pd.DataFrame(export_data)
                    csv = df_export.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Spielplan als CSV herunterladen",
                        data=csv,
                        file_name="tennis_spielplan.csv",
                        mime="text/csv"
                    )

if __name__ == "__main__":
    main()