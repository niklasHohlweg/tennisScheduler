-- Migration: Add start_time to tournaments table
-- Date: 2026-03-31

-- Add start_time column to tournaments table
ALTER TABLE tournaments 
ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_tournaments_start_time ON tournaments(start_time);
