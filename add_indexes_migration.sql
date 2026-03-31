-- Migration script to add missing indexes to existing database
-- Run this script on your production database to add performance indexes

-- Add missing indexes for matches table
CREATE INDEX IF NOT EXISTS idx_matches_winner ON matches(tournament_id, winner);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(tournament_id, team1, team2);

-- Add missing index for team_stats table
CREATE INDEX IF NOT EXISTS idx_team_stats_lookup ON team_stats(tournament_id, team_name);

-- Verify indexes were created
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('matches', 'team_stats')
ORDER BY tablename, indexname;
