"""Utility functions for PDF export and data formatting"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import pandas as pd


def export_to_pdf(tournament_name, matches, ranking):
    """Export tournament data to PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph(f"<b>{tournament_name}</b>", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 0.2*inch))
    
    # Date
    date_text = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
    story.append(date_text)
    story.append(Spacer(1, 0.3*inch))
    
    # Rankings Table
    if ranking:
        story.append(Paragraph("<b>Rankings</b>", styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        
        rank_data = [['Pos', 'Team', 'Played', 'Won', 'Lost', 'Points']]
        for r in ranking[:10]:  # Top 10
            rank_data.append([
                str(r['position']),
                r['team'][:20],
                str(r['matches_played']),
                str(r['matches_won']),
                str(r['matches_lost']),
                str(r['ranking_points'])
            ])
        
        rank_table = Table(rank_data)
        rank_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(rank_table)
        story.append(Spacer(1, 0.3*inch))
    
    # Matches Table
    if matches:
        story.append(Paragraph("<b>Recent Matches</b>", styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        
        match_data = [['Rnd', 'Court', 'Team 1', 'Team 2', 'Score', 'Winner']]
        for m in matches[:20]:  # First 20 matches
            score = f"{m['team1_score']}:{m['team2_score']}" if m['winner'] else "TBD"
            winner = m['winner'][:15] if m['winner'] else "-"
            match_data.append([
                str(m['round_number']),
                str(m['court_number']),
                m['team1'][:15],
                m['team2'][:15],
                score,
                winner
            ])
        
        match_table = Table(match_data)
        match_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(match_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_to_csv(tournament_name, matches, ranking):
    """Export tournament data to CSV"""
    output = io.StringIO()
    
    # Write tournament info
    output.write(f"Tournament: {tournament_name}\n")
    output.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # Write matches
    output.write("MATCHES\n")
    if matches:
        df_matches = pd.DataFrame(matches)
        df_matches.to_csv(output, index=False)
    output.write("\n\n")
    
    # Write rankings
    output.write("RANKINGS\n")
    if ranking:
        df_ranking = pd.DataFrame(ranking)
        df_ranking.to_csv(output, index=False)
    
    return output.getvalue()


def export_to_excel(tournament_name, matches, ranking):
    """Export tournament data to Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Write matches
        if matches:
            df_matches = pd.DataFrame(matches)
            df_matches.to_excel(writer, sheet_name='Matches', index=False)
        
        # Write rankings
        if ranking:
            df_ranking = pd.DataFrame(ranking)
            df_ranking.to_excel(writer, sheet_name='Rankings', index=False)
        
        # Write summary
        summary_data = {
            'Tournament Name': [tournament_name],
            'Export Date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            'Total Matches': [len(matches) if matches else 0],
            'Played Matches': [len([m for m in matches if m['winner']]) if matches else 0],
            'Teams': [len(ranking) if ranking else 0]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
    
    output.seek(0)
    return output.getvalue()


def format_time_minutes(minutes):
    """Convert minutes to HH:MM format"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def calculate_match_stats(matches):
    """Calculate statistics from matches"""
    if not matches:
        return {
            'total': 0,
            'played': 0,
            'pending': 0,
            'completion_rate': 0
        }
    
    played = len([m for m in matches if m.get('winner')])
    total = len(matches)
    
    return {
        'total': total,
        'played': played,
        'pending': total - played,
        'completion_rate': round((played / total * 100), 1) if total > 0 else 0
    }


def calculate_team_distribution(matches, teams):
    """Calculate match distribution per team"""
    from collections import Counter
    
    team_match_count = Counter()
    team_played_count = Counter()
    
    for m in matches:
        team_match_count[m['team1']] += 1
        team_match_count[m['team2']] += 1
        if m.get('winner'):
            team_played_count[m['team1']] += 1
            team_played_count[m['team2']] += 1
    
    distribution = []
    for team in teams:
        total = team_match_count.get(team, 0)
        played = team_played_count.get(team, 0)
        distribution.append({
            'team': team,
            'total_matches': total,
            'played_matches': played,
            'pending_matches': total - played,
            'completion_rate': round((played / total * 100), 1) if total > 0 else 0
        })
    
    return distribution
