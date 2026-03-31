#!/bin/bash
# Script to apply database migrations to running containers

echo "Applying database migrations..."

# Check if container is running
if ! docker ps | grep -q tennis-db; then
    echo "Error: Database container 'tennis-db' is not running"
    exit 1
fi

# Apply migration
docker exec -i tennis-db psql -U tennis_user -d tennis_scheduler < add_indexes_migration.sql

if [ $? -eq 0 ]; then
    echo "✓ Migrations applied successfully!"
    echo ""
    echo "Verifying indexes..."
    docker exec tennis-db psql -U tennis_user -d tennis_scheduler -c "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename IN ('matches', 'team_stats') ORDER BY tablename, indexname;"
else
    echo "✗ Migration failed!"
    exit 1
fi
