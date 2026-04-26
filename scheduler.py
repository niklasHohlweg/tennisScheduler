"""Tennis tournament scheduling logic"""
import itertools
import math
import random
from collections import Counter


class TennisScheduler:
    """Generate optimal tennis match schedules"""
    
    def __init__(self, num_courts, teams, players_per_team=4, match_type='single', team_player_counts=None):
        self.num_courts = num_courts
        self.teams = teams if isinstance(teams, list) else [f"Team {i+1}" for i in range(teams)]
        self.num_teams = len(self.teams)
        self.matches_per_round = num_courts
        self.max_players_per_round = num_courts * 2
        self.players_per_team = players_per_team
        self.match_type = match_type
        
        # Per-team player counts (used when teams have unequal sizes, e.g. team_assignment mode)
        self.team_player_counts = team_player_counts  # dict {team_name: player_count} or None
        
        # Calculate max simultaneous matches per team based on match type
        if match_type == 'double':
            # In doubles, each match needs 2 players per team, so max matches = players / 2
            self.max_simultaneous_matches_per_team = players_per_team // 2
        else:  # 'single'
            # In singles, each match needs 1 player per team, so max matches = players
            self.max_simultaneous_matches_per_team = players_per_team

    def create_time_based_schedule(self, total_duration_minutes, round_duration=15, break_duration=5):
        """Create schedule based on available time
        
        Args:
            total_duration_minutes: Total tournament duration in minutes
            round_duration: Duration of each round in minutes (default: 15)
            break_duration: Break time between rounds in minutes (default: 5)
        """
        # Calculate time for one complete round cycle (play + break)
        minutes_per_round = round_duration + break_duration
        max_rounds = total_duration_minutes // minutes_per_round
        
        if max_rounds == 0:
            return [], {"error": "Zu wenig Zeit für mindestens eine Runde"}

        schedule = []
        team_game_counts = Counter({team: 0 for team in self.teams})
        
        # Create all possible pairings (Round-Robin)
        all_pairings = set()
        for t1 in self.teams:
            for t2 in self.teams:
                if t1 != t2:
                    # Store as sorted tuple to avoid duplicates (A,B) and (B,A)
                    pairing = tuple(sorted([t1, t2]))
                    all_pairings.add(pairing)
        
        remaining_pairings = all_pairings.copy()

        for round_num in range(1, max_rounds + 1):
            # If all pairings have been played, start a new round-robin cycle
            # so that the available time is used fully and teams play equally often
            if not remaining_pairings:
                remaining_pairings = all_pairings.copy()

            round_matches = self.create_optimal_time_round(remaining_pairings, team_game_counts, round_num)
            
            # If no more matches can be created, stop
            if not round_matches:
                break
            
            # Calculate start and end times
            round_start = (round_num - 1) * minutes_per_round
            round_end = round_start + round_duration
                
            schedule.append({
                'round': round_num,
                'matches': round_matches,
                'start_time': round_start,
                'end_time': round_end
            })
            
            # Update counts and remove played pairings
            for match in round_matches:
                t1, t2 = match
                team_game_counts[t1] += 1
                team_game_counts[t2] += 1
                # Remove the pairing from remaining
                pairing = tuple(sorted([t1, t2]))
                remaining_pairings.discard(pairing)

        stats = self.get_time_based_stats(schedule, team_game_counts, total_duration_minutes, round_duration, break_duration)
        return schedule, stats

    def create_optimal_time_round(self, remaining_pairings, current_counts, round_num):
        """Create optimal round for time-based scheduling
        
        Strategy:
        1. Phase 1: Prioritize teams that haven't played yet (max 1 match per team)
        2. Phase 2: Add more matches for teams with available players
        3. Phase 3: Fill remaining courts from any available pairings
        
        Teams can play multiple times in a round if:
        - They have enough players (based on max_simultaneous_matches_per_team)
        - They have remaining pairings to play
        - Preferably when other teams are already playing
        """
        round_matches = []
        team_matches_this_round = Counter()
        
        # Convert remaining pairings to list and sort by priority
        # Priority: teams with fewer total games should play first
        available_pairings = sorted(
            list(remaining_pairings),
            key=lambda p: current_counts[p[0]] + current_counts[p[1]]
        )
        
        if not available_pairings:
            return []
        
        # PHASE 1: Give every team at least one match (if possible)
        # Try to get different teams to play first
        used_pairings = set()
        for pairing in available_pairings:
            if len(round_matches) >= self.num_courts:
                break
            t1, t2 = pairing
            # Only add if both teams haven't played in this round yet
            if team_matches_this_round[t1] == 0 and team_matches_this_round[t2] == 0:
                round_matches.append(pairing)
                team_matches_this_round[t1] += 1
                team_matches_this_round[t2] += 1
                used_pairings.add(pairing)
        
        # PHASE 2: Fill remaining courts with teams that can play multiple matches
        # This allows teams with enough players to play more than once per round
        for pairing in available_pairings:
            if len(round_matches) >= self.num_courts:
                break
            
            if pairing in used_pairings:
                continue
                
            t1, t2 = pairing
            # Determine per-team simultaneous match limit (actual player count if available)
            if self.team_player_counts:
                if self.match_type == 'double':
                    limit_t1 = self.team_player_counts.get(t1, self.players_per_team) // 2
                    limit_t2 = self.team_player_counts.get(t2, self.players_per_team) // 2
                else:
                    limit_t1 = self.team_player_counts.get(t1, self.players_per_team)
                    limit_t2 = self.team_player_counts.get(t2, self.players_per_team)
            else:
                limit_t1 = self.max_simultaneous_matches_per_team
                limit_t2 = self.max_simultaneous_matches_per_team
            # Check if both teams can play another match (within their simultaneous limit)
            if (team_matches_this_round[t1] < limit_t1 and
                    team_matches_this_round[t2] < limit_t2):
                round_matches.append(pairing)
                team_matches_this_round[t1] += 1
                team_matches_this_round[t2] += 1
                used_pairings.add(pairing)

        return round_matches

    def get_time_based_stats(self, schedule, team_counts, total_duration, round_duration=15, break_duration=5):
        """Calculate statistics for time-based schedule"""
        total_matches = sum(len(r['matches']) for r in schedule) if schedule else 0
        minutes_per_round = round_duration + break_duration
        actual_duration = len(schedule) * minutes_per_round if schedule else 0
        
        # Calculate total possible pairings (Round-Robin)
        total_possible_pairings = (len(self.teams) * (len(self.teams) - 1)) // 2
        
        # Track which pairings were played
        played_pairings = set()
        for round_data in schedule:
            for match in round_data['matches']:
                t1, t2 = match
                pairing = tuple(sorted([t1, t2]))
                played_pairings.add(pairing)
        
        unique_pairings_played = len(played_pairings)
        
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
            'unique_pairings_played': unique_pairings_played,
            'total_possible_pairings': total_possible_pairings,
            'pairings_completion': (unique_pairings_played / total_possible_pairings * 100) if total_possible_pairings > 0 else 0,
        }
        stats['games_difference'] = stats['max_games'] - stats['min_games']
        stats['court_utilization'] = (total_matches / (len(schedule) * self.num_courts) * 100) if len(schedule) > 0 else 0
        return stats

    def create_round_robin_schedule(self, round_duration=15, break_duration=5):
        """Create full round-robin schedule where every team plays every other team once
        
        Args:
            round_duration: Duration of each round in minutes (default: 15)
            break_duration: Break time between rounds in minutes (default: 5)
        """
        all_matches = list(itertools.combinations(self.teams, 2))
        total_matches = len(all_matches)
        rounds_needed = math.ceil(total_matches / self.matches_per_round)
        schedule = []
        
        # Use a set for O(1) removal instead of list
        remaining = set(all_matches)
        
        # Calculate time for one complete round cycle (play + break)
        minutes_per_round = round_duration + break_duration
        
        for round_num in range(1, rounds_needed + 1):
            round_matches = self.create_optimal_round(remaining, round_num)
            
            # Calculate start and end times
            round_start = (round_num - 1) * minutes_per_round
            round_end = round_start + round_duration
            
            schedule.append({
                'round': round_num,
                'matches': round_matches,
                'start_time': round_start,
                'end_time': round_end
            })
            
            # Remove used matches from set - O(1) per match
            remaining -= set(round_matches)
        return schedule

    def create_optimal_round(self, available_matches, round_num):
        """Create optimal round from available matches"""
        round_matches = []
        used = set()
        # Convert to list for iteration (needed for set input)
        matches_list = list(available_matches)
        for match in matches_list:
            a, b = match
            if a not in used and b not in used:
                if len(round_matches) < self.matches_per_round:
                    round_matches.append(match)
                    used.add(a)
                    used.add(b)
        return round_matches

    def create_single_round_distribution(self):
        """Create a single round with fair team distribution"""
        if self.num_teams < 2:
            return []
        matches = []
        available = self.teams.copy()
        while len(available) >= 2 and len(matches) < self.matches_per_round:
            t1 = available.pop(0)
            t2 = available.pop(0)
            matches.append((t1, t2))
        return matches
    
    def get_schedule_stats(self, schedule):
        """Get statistics for any schedule"""
        team_match_count = Counter()
        total_matches = 0
        
        for round_data in schedule:
            matches = round_data['matches'] if isinstance(round_data, dict) else round_data
            for t1, t2 in matches:
                team_match_count[t1] += 1
                team_match_count[t2] += 1
                total_matches += 1
        
        return {
            'total_rounds': len(schedule),
            'total_matches': total_matches,
            'avg_matches_per_team': sum(team_match_count.values()) / len(self.teams) if self.teams else 0,
            'min_matches': min(team_match_count.values()) if team_match_count else 0,
            'max_matches': max(team_match_count.values()) if team_match_count else 0,
            'team_match_count': dict(team_match_count),
            'fairness_score': max(team_match_count.values()) - min(team_match_count.values()) if team_match_count else 0
        }
