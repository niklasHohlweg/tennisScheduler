# Tennis Tournament Scheduler

A modern web application for managing tennis tournaments with match scheduling, scoring, and rankings.

## 🎾 Features

- **User Authentication**: Email-based login system
- **Tournament Management**: Create, edit, and delete tournaments
- **Smart Scheduling**: 
  - Time-based scheduling (maximize matches in available time)
  - Round-robin scheduling (every team plays every other team)
- **Match Tracking**: Record match results and scores in real-time
- **Live Rankings**: Automatic ranking calculation with detailed statistics
- **Data Export**: Export tournament data as PDF, CSV, or Excel
- **PostgreSQL Database**: Persistent data storage with full ACID compliance
- **Modern UI**: Responsive design with Tailwind CSS and HTMX for smooth interactions

## 🚀 Technology Stack

- **Backend**: Flask 3.0 (Python)
- **Frontend**: HTML5, Tailwind CSS, HTMX, Alpine.js
- **Database**: PostgreSQL 16
- **Export**: ReportLab (PDF), Pandas (CSV/Excel)
- **Deployment**: Docker & Docker Compose

## 📋 Prerequisites

- Docker and Docker Compose installed
- Port 8501 available for the Flask application
- PostgreSQL runs internally in Docker network (not exposed to host)

## 🎯 Usage Guide

### Creating a Tournament

1. **Login**: Enter your email (account created automatically)
2. **Create Tournament**: Click "Neues Turnier" and configure:
   - Tournament name
   - Mode (Time-based or Round Robin)
   - Number of teams, courts, and players per team
   - Team names
3. **Generate Schedule**: Choose duration (time-based) or generate full schedule (round robin)

### Managing Matches

1. Navigate to "Matches" from tournament detail page
2. Enter scores for each match
3. Select winner
4. Rankings update automatically

### Viewing Rankings

- View live rankings on the tournament detail page
- Full ranking table with detailed statistics
- Export options for sharing