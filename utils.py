"""Utility functions for PDF export and data formatting"""
import io
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
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
    date_text = Paragraph(f"Erstellt am: {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}", styles['Normal'])
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


def export_timetable_to_pdf(tournament_name, matches, start_time, num_courts):
    """Export tournament timetable to PDF with actual times
    
    Args:
        tournament_name: Name of the tournament
        matches: List of matches with round, court, teams, and time info
        start_time: Tournament start datetime
        num_courts: Number of courts
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), 
                           leftMargin=0.5*inch, rightMargin=0.5*inch,
                           topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Create custom title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#0F3A4A'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    # Title
    title = Paragraph(f"<b>{tournament_name} - Spielplan</b>", title_style)
    story.append(title)
    
    # Start time and date
    if start_time:
        date_text = Paragraph(
            f"Start: {start_time.strftime('%d.%m.%Y um %H:%M Uhr')}", 
            styles['Normal']
        )
        story.append(date_text)
    
    story.append(Spacer(1, 0.2*inch))
    
    # Group matches by round
    rounds = {}
    for match in matches:
        round_num = match['round_number']
        if round_num not in rounds:
            rounds[round_num] = []
        rounds[round_num].append(match)
    
    # Create timetable for each round
    for round_num in sorted(rounds.keys()):
        round_matches = rounds[round_num]
        
        # Round header
        story.append(Paragraph(f"<b>Runde {round_num}</b>", styles['Heading2']))
        
        # Calculate round time
        if round_matches and start_time and round_matches[0].get('start_time_minutes') is not None:
            start_minutes = round_matches[0]['start_time_minutes']
            end_minutes = round_matches[0].get('end_time_minutes', start_minutes + 15)
            
            round_start_time = start_time + timedelta(minutes=start_minutes)
            round_end_time = start_time + timedelta(minutes=end_minutes)
            
            time_text = Paragraph(
                f"Zeit: {round_start_time.strftime('%H:%M')} Uhr - {round_end_time.strftime('%H:%M')} Uhr",
                styles['Normal']
            )
            story.append(time_text)
        
        story.append(Spacer(1, 0.1*inch))
        
        # Create table for this round
        table_data = [['Platz', 'Team 1', 'vs', 'Team 2']]
        
        # Sort by court number
        sorted_matches = sorted(round_matches, key=lambda x: x['court_number'])
        
        for match in sorted_matches:
            table_data.append([
                f"Platz {match['court_number']}",
                match['team1'],
                'vs',
                match['team2']
            ])
        
        # Create table
        match_table = Table(table_data, colWidths=[1*inch, 3*inch, 0.5*inch, 3*inch])
        match_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F3A4A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F4F6F5')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F6F5')])
        ]))
        story.append(match_table)
        story.append(Spacer(1, 0.3*inch))
    
    # Footer with generation info
    story.append(Spacer(1, 0.2*inch))
    footer = Paragraph(
        f"<i>Erstellt am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}</i>",
        styles['Normal']
    )
    story.append(footer)
    
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
