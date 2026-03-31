"""Tennis tournament scheduling logic"""
import itertools
import math
import random
from collections import Counter


class TennisScheduler:
    """Generate optimal tennis match schedules"""
    
    def __init__(self, num_courts, teams, players_per_team=4):
        self.num_courts = num_courts
        self.teams = teams if isinstance(teams, list) else [f"Team {i+1}" for i in range(teams)]
        self.num_teams = len(self.teams)
        self.matches_per_round = num_courts
        self.max_players_per_round = num_courts * 2
        self.players_per_team = players_per_team
        self.max_simultaneous_matches_per_team = players_per_team // 2

    def create_time_based_schedule(self, total_duration_minutes):
        """Create schedule based on available time"""
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
        """Create optimal round for time-based scheduling"""
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
        """Calculate statistics for time-based schedule"""
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
        """Create full round-robin schedule where every team plays every other team once"""
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
        """Create optimal round from available matches"""
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
