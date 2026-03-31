-- Tennis Scheduler Database Initialization Script
-- This script creates the necessary tables for the tennis tournament scheduler

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP DEFAULT NOW()
);

-- Create index on email for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create tournaments table
CREATE TABLE IF NOT EXISTS tournaments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    teams JSONB NOT NULL,
    num_courts INTEGER NOT NULL,
    players_per_team INTEGER NOT NULL,
    mode TEXT NOT NULL,
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    owner_email TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index on owner_id for faster queries
CREATE INDEX IF NOT EXISTS idx_tournaments_owner_id ON tournaments(owner_id);
CREATE INDEX IF NOT EXISTS idx_tournaments_created_at ON tournaments(created_at DESC);

-- Create matches table
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
);

-- Create indexes for matches table
CREATE INDEX IF NOT EXISTS idx_matches_tournament_id ON matches(tournament_id);
CREATE INDEX IF NOT EXISTS idx_matches_round_court ON matches(round_number, court_number);

-- Create team_stats table
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
);

-- Create indexes for team_stats table
CREATE INDEX IF NOT EXISTS idx_team_stats_tournament_id ON team_stats(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_stats_ranking ON team_stats(tournament_id, ranking_points DESC, matches_won DESC);

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tennis_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tennis_user;
