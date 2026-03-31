"""Main Flask Application for Tennis Tournament Scheduler"""
import os
import io
import logging
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from functools import wraps
from datetime import datetime

from config import config
from database import Database, get_db
from scheduler import TennisScheduler
from utils import export_to_pdf, export_to_csv, export_to_excel, format_time_minutes, calculate_match_stats, calculate_team_distribution


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(config_name='default'):
    """Application factory"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize database
    db = Database(app.config)
    if not db.init_db():
        logger.error("Failed to initialize database!")
    
    # Template filters
    @app.template_filter('format_time')
    def format_time_filter(minutes):
        return format_time_minutes(minutes)
    
    @app.template_filter('format_datetime')
    def format_datetime_filter(dt):
        if dt:
            return dt.strftime('%Y-%m-%d %H:%M')
        return ''
    
    # Authentication decorator
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Bitte melden Sie sich an.', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    
    # ==================== AUTHENTICATION ROUTES ====================
    
    @app.route('/')
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User login/registration"""
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            
            if not email or '@' not in email:
                flash('Bitte geben Sie eine gültige E-Mail-Adresse ein.', 'error')
                return render_template('login.html')
            
            db = get_db()
            user, is_new_user = db.get_or_create_user(email)
            
            if user:
                session.permanent = True
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                
                if is_new_user:
                    flash(f'Willkommen! Ihr Konto wurde erstellt.', 'success')
                else:
                    flash(f'Willkommen zurück!', 'success')
                
                return redirect(url_for('dashboard'))
            else:
                flash('Fehler bei der Anmeldung. Bitte versuchen Sie es erneut.', 'error')
        
        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        """User logout"""
        session.clear()
        flash('Sie wurden erfolgreich abgemeldet.', 'info')
        return redirect(url_for('login'))
    
    # ==================== DASHBOARD ====================
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """User dashboard"""
        db = get_db()
        tournaments = db.get_tournaments(session['user_id'])
        stats = db.get_user_stats(session['user_id'])
        
        return render_template('dashboard.html', 
                             tournaments=tournaments,
                             stats=stats,
                             user_email=session['user_email'])
    
    # ==================== TOURNAMENT CRUD ====================
    
    @app.route('/tournament/create', methods=['GET', 'POST'])
    @login_required
    def create_tournament():
        """Create new tournament"""
        if request.method == 'POST':
            try:
                name = request.form.get('name', '').strip()
                num_teams = int(request.form.get('num_teams', 4))
                num_courts = int(request.form.get('num_courts', 2))
                players_per_team = int(request.form.get('players_per_team', 4))
                mode = request.form.get('mode', 'time_based')
                
                # Validate input ranges
                if not name:
                    flash('Turniername ist erforderlich.', 'error')
                    return redirect(url_for('create_tournament'))
                
                if num_teams < 2 or num_teams > 100:
                    flash('Anzahl der Teams muss zwischen 2 und 100 liegen.', 'error')
                    return redirect(url_for('create_tournament'))
                
                if num_courts < 1 or num_courts > 50:
                    flash('Anzahl der Plätze muss zwischen 1 und 50 liegen.', 'error')
                    return redirect(url_for('create_tournament'))
                
                if players_per_team < 2 or players_per_team > 10:
                    flash('Spieler pro Team muss zwischen 2 und 10 liegen.', 'error')
                    return redirect(url_for('create_tournament'))
                
                # Get team names
                teams = []
                for i in range(num_teams):
                    team_name = request.form.get(f'team_{i}', '').strip()
                    # If no team name provided, use default "Team X"
                    if not team_name:
                        team_name = f'Team {i+1}'
                    teams.append(team_name)
                
                # Validate team name uniqueness
                if len(teams) != len(set(teams)):
                    flash('Teamnamen müssen eindeutig sein.', 'error')
                    return redirect(url_for('create_tournament'))
                
                if len(teams) < 2:
                    flash('Mindestens 2 Teams erforderlich.', 'error')
                    return redirect(url_for('create_tournament'))
                
                # Create tournament
                db = get_db()
                tournament_id = db.create_tournament(
                    name, teams, num_courts, players_per_team, mode,
                    session['user_id'], session['user_email']
                )
                
                if tournament_id:
                    flash('Turnier erfolgreich erstellt!', 'success')
                    return redirect(url_for('tournament_schedule', tournament_id=tournament_id))
                else:
                    flash('Fehler beim Erstellen des Turniers.', 'error')
                    
            except Exception as e:
                logger.error(f"Error creating tournament: {e}")
                flash('Fehler beim Erstellen des Turniers.', 'error')
        
        return render_template('tournament_create.html')
    
    @app.route('/tournament/<tournament_id>')
    @login_required
    def tournament_detail(tournament_id):
        """View tournament details"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        matches = db.get_matches(tournament_id, session['user_id'])
        ranking = db.get_ranking(tournament_id, session['user_id'])
        
        match_stats = calculate_match_stats(matches)
        team_distribution = calculate_team_distribution(matches, tournament['teams'])
        
        return render_template('tournament_detail.html',
                             tournament=tournament,
                             matches=matches,
                             ranking=ranking,
                             match_stats=match_stats,
                             team_distribution=team_distribution)
    
    @app.route('/tournament/<tournament_id>/schedule', methods=['GET', 'POST'])
    @login_required
    def tournament_schedule(tournament_id):
        """Generate and save tournament schedule"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            try:
                scheduler = TennisScheduler(
                    tournament['num_courts'],
                    tournament['teams'],
                    tournament['players_per_team']
                )
                
                if tournament['mode'] == 'time_based':
                    duration = int(request.form.get('duration', 120))
                    schedule, stats = scheduler.create_time_based_schedule(duration)
                else:  # round_robin
                    import time
                    start_time = time.time()
                    schedule = scheduler.create_round_robin_schedule()
                    elapsed = time.time() - start_time
                    logger.info(f"Schedule generation took {elapsed:.2f}s for {len(tournament['teams'])} teams")
                    # Convert to dict format
                    schedule = [{'round': i+1, 'matches': round_matches} for i, round_matches in enumerate(schedule)]
                    stats = scheduler.get_schedule_stats(schedule)
                
                # Save to database
                result = db.save_matches(tournament_id, schedule)
                if result:
                    flash('Spielplan erfolgreich generiert!', 'success')
                    return redirect(url_for('tournament_detail', tournament_id=tournament_id))
                else:
                    flash('Fehler beim Speichern des Spielplans. Möglicherweise wurden bereits Spiele ausgetragen.', 'error')
                    
            except Exception as e:
                logger.error(f"Error generating schedule: {e}")
                flash('Fehler beim Generieren des Spielplans.', 'error')
        
        return render_template('tournament_schedule.html', tournament=tournament)
    
    @app.route('/tournament/<tournament_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_tournament(tournament_id):
        """Edit tournament name"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if name and db.update_tournament(tournament_id, session['user_id'], name):
                flash('Turnier aktualisiert!', 'success')
                return redirect(url_for('tournament_detail', tournament_id=tournament_id))
            else:
                flash('Fehler beim Aktualisieren.', 'error')
        
        return render_template('tournament_edit.html', tournament=tournament)
    
    @app.route('/tournament/<tournament_id>/delete', methods=['POST'])
    @login_required
    def delete_tournament(tournament_id):
        """Delete tournament"""
        db = get_db()
        if db.delete_tournament(tournament_id, session['user_id']):
            flash('Turnier gelöscht.', 'success')
        else:
            flash('Fehler beim Löschen.', 'error')
        
        return redirect(url_for('dashboard'))
    
    # ==================== MATCH MANAGEMENT ====================
    
    @app.route('/match/<match_id>/update', methods=['POST'])
    @login_required
    def update_match(match_id):
        """Update match result - HTMX endpoint"""
        try:
            winner = request.form.get('winner', '').strip()
            team1_score = int(request.form.get('team1_score', 0))
            team2_score = int(request.form.get('team2_score', 0))
            
            # Get match details for validation
            db = get_db()
            matches = db.get_matches_by_id(match_id)
            if not matches:
                return jsonify({'success': False, 'message': 'Match nicht gefunden.'}), 404
            
            match = matches[0]
            team1 = match['team1']
            team2 = match['team2']
            
            # Validate winner
            valid_winners = [team1, team2, 'Draw', '']
            if winner not in valid_winners:
                return jsonify({'success': False, 'message': 'Ungültiger Gewinner.'}), 400
            
            # Validate scores
            if team1_score < 0 or team2_score < 0:
                return jsonify({'success': False, 'message': 'Punkte dürfen nicht negativ sein.'}), 400
            
            if team1_score > 999 or team2_score > 999:
                return jsonify({'success': False, 'message': 'Punkte dürfen nicht größer als 999 sein.'}), 400
            
            if db.update_match_result(match_id, winner, team1_score, team2_score):
                # Return updated match card as HTMX response
                return jsonify({'success': True, 'message': 'Match aktualisiert!'})
            else:
                return jsonify({'success': False, 'message': 'Fehler beim Aktualisieren.'}), 400
                
        except ValueError:
            return jsonify({'success': False, 'message': 'Ungültige Punktzahl.'}), 400
        except Exception as e:
            logger.error(f"Error updating match: {e}")
            return jsonify({'success': False, 'message': 'Fehler beim Aktualisieren.'}), 500
    
    @app.route('/tournament/<tournament_id>/matches')
    @login_required
    def tournament_matches(tournament_id):
        """View all matches for tournament"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        matches = db.get_matches(tournament_id, session['user_id'])
        
        # Group matches by round
        rounds = {}
        for match in matches:
            round_num = match['round_number']
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(match)
        
        return render_template('matches.html',
                             tournament=tournament,
                             rounds=rounds,
                             matches=matches)
    
    @app.route('/tournament/<tournament_id>/ranking')
    @login_required
    def tournament_ranking(tournament_id):
        """View tournament ranking"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        ranking = db.get_ranking(tournament_id, session['user_id'])
        
        return render_template('ranking.html',
                             tournament=tournament,
                             ranking=ranking)
    
    # ==================== EXPORT ROUTES ====================
    
    @app.route('/tournament/<tournament_id>/export/pdf')
    @login_required
    def export_pdf(tournament_id):
        """Export tournament to PDF"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        matches = db.get_matches(tournament_id, session['user_id'])
        ranking = db.get_ranking(tournament_id, session['user_id'])
        
        pdf_data = export_to_pdf(tournament['name'], matches, ranking)
        
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{tournament['name']}_export.pdf"
        )
    
    @app.route('/tournament/<tournament_id>/export/csv')
    @login_required
    def export_csv(tournament_id):
        """Export tournament to CSV"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        matches = db.get_matches(tournament_id, session['user_id'])
        ranking = db.get_ranking(tournament_id, session['user_id'])
        
        csv_data = export_to_csv(tournament['name'], matches, ranking)
        
        return send_file(
            io.BytesIO(csv_data.encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{tournament['name']}_export.csv"
        )
    
    @app.route('/tournament/<tournament_id>/export/excel')
    @login_required
    def export_excel(tournament_id):
        """Export tournament to Excel"""
        db = get_db()
        tournament = db.get_tournament(tournament_id, session['user_id'])
        
        if not tournament:
            flash('Turnier nicht gefunden.', 'error')
            return redirect(url_for('dashboard'))
        
        matches = db.get_matches(tournament_id, session['user_id'])
        ranking = db.get_ranking(tournament_id, session['user_id'])
        
        excel_data = export_to_excel(tournament['name'], matches, ranking)
        
        return send_file(
            io.BytesIO(excel_data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"{tournament['name']}_export.xlsx"
        )
    
    # ==================== SEARCH ====================
    
    @app.route('/search')
    @login_required
    def search_tournaments():
        """Search tournaments"""
        search_term = request.args.get('q', '').strip()
        date_from = request.args.get('from', '')
        date_to = request.args.get('to', '')
        
        db = get_db()
        tournaments = db.search_tournaments(
            session['user_id'],
            search_term=search_term if search_term else None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None
        )
        
        return render_template('search.html',
                             tournaments=tournaments,
                             search_term=search_term,
                             date_from=date_from,
                             date_to=date_to)
    
    # ==================== ERROR HANDLERS ====================
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html', error='Seite nicht gefunden'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal error: {error}")
        return render_template('error.html', error='Interner Serverfehler'), 500
    
    return app


if __name__ == '__main__':
    import io  # Add missing import for send_file
    
    app = create_app(os.getenv('FLASK_ENV', 'development'))
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=app.config['DEBUG']
    )
