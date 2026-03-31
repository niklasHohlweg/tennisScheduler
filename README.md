# Tennis Tournament Scheduler

A Streamlit-based web application for managing tennis tournaments with match scheduling, scoring, and rankings.

## Features

- 🎾 Create and manage tennis tournaments
- 📅 Generate optimal match schedules
- 🏆 Track scores and rankings
- 🗄️ PostgreSQL database for persistent storage
- 📊 Advanced analytics and data export
- 🔍 Search and filter tournaments

## Architecture

The application uses a local PostgreSQL database, providing:
- Full control over your data
- No external dependencies
- Easy backup and migration
- Support for local development and deployment

## Prerequisites

- Docker and Docker Compose installed
- Port 8501 and 5432 available (or modify docker-compose.yml)

## Database Management

### Initial Setup
The database is automatically initialized with the required tables on first startup using the `init.sql` script.

### Backup Database
```bash
docker exec tennis-scheduler-db pg_dump -U tennis_user tennis_scheduler > backup.sql
```

### Restore Database
```bash
docker exec -i tennis-scheduler-db psql -U tennis_user tennis_scheduler < backup.sql
```

### Access Database Shell
```bash
docker exec -it tennis-scheduler-db psql -U tennis_user -d tennis_scheduler
```