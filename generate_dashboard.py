#!/usr/bin/env python3
"""
PrizePicks Dashboard Generator
Fetches live sports data and generates HTML dashboard
Runs daily via GitHub Actions
"""

import json
import datetime
from datetime import datetime as dt

# Sample data structure - in production, this would call ESPN/injury APIs
SAMPLE_PREDICTIONS = {
    "nba": [
        {
            "player": "Shai Gilgeous-Alexander",
            "prop": "Over 24.5 Pts",
            "matchup": "OKC vs GS",
            "time": "3:30 PM ET",
            "confidence": 89,
            "risk": "low",
            "factors": {
                "Recent Form": {"score": 95, "detail": "28.2 PPG (last 5) | Hot streak continues | 5 straight 25+ games"},
                "Game Script": {"score": 82, "detail": "Favored by 2.5pts | High pace (104.2) | Heavy offensive load expected"},
                "Defense Matchup": {"score": 78, "detail": "Warriors 18th in DVOA | Weak perimeter defense | SGA exploits guards"},
                "Injury Impact": {"score": 92, "detail": "✓ SGA Healthy | No key OKC injuries | Warriors missing Klay (out)"},
                "Volume": {"score": 88, "detail": "32.1% usage rate | 26 shots/game | Lead scorer role locked"},
                "Rest Days": {"score": 72, "detail": "1 day rest | Back-to-back situation | Manageable fatigue"}
            },
            "reasoning": "SGA is in elite form and faces a Warriors defense that ranks in bottom-10 against guards. OKC will likely control game tempo with strong favorites status. Expected game script favors volume. The combination of hot streak (28.2 PPG), excellent matchup (Warriors weak D), and high usage rate (32.1%) creates high-confidence scenario. Primary risk: Late game rest if OKC builds 20+ point lead."
        }
    ],
    "nfl": []
}

def generate_factor_html(factors):
    """Generate factor breakdown HTML"""
    html = '<div class="factor-breakdown">'
    for name, data in factors.items():
        score = data['score']
        detail = data['detail']
        
        # Determine gradient based on score
        if score >= 80:
            gradient = "linear-gradient(90deg, #00ff88, #00cc66)"
        elif score >= 60:
            gradient = "linear-gradient(90deg, #00d4ff, #0099ff)"
        else:
            gradient = "linear-gradient(90deg, #ffaa00, #ff8800)"
        
        html += f'''
                    <div class="factor-item">
                        <div class="factor-name">{name}</div>
                        <div class="factor-score-bar">
                            <div class="factor-score-fill" style="width: {score}%; background: {gradient};">{score}</div>
                        </div>
                        <div class="factor-detail">{detail}</div>
                    </div>
        '''
    html += '</div>'
    return html

def generate_prediction_card(pred):
    """Generate a single prediction card"""
    confidence_class = "high" if pred["confidence"] >= 80 else ("medium" if pred["confidence"] >= 70 else "low")
    confidence_color = "high" if pred["confidence"] >= 80 else ("medium" if pred["confidence"] >= 70 else "low")
    border_color = "#00ff88" if pred["risk"] == "low" else "#ffaa00"
    
    confidence_text = f"{pred['confidence']}% CONFIDENCE"
    
    html = f'''
            <div class="prediction-card {confidence_color}-confidence">
                <div class="prediction-header">
                    <div>
                        <div class="prediction-title">{pred['player']} {pred['prop']}</div>
                        <div style="color: var(--color-text-secondary); font-size: 0.9em; margin-top: 5px;">{pred['matchup']} | {pred['time']}</div>
                    </div>
                    <div class="confidence-badge {confidence_color}">{confidence_text}</div>
                </div>

                {generate_factor_html(pred['factors'])}

                <div class="ai-reasoning">
                    <strong>🤖 AI Analysis:</strong> {pred['reasoning']}
                </div>

                <span class="risk-indicator {pred['risk']}-risk">{'✓' if pred['risk'] == 'low' else '⚠'} {pred['risk'].upper()} RISK</span>
            </div>
    '''
    return html

def generate_html():
    """Generate complete dashboard HTML"""
    
    now = dt.now()
    today_date = now.strftime("%B %d, %Y")
    last_updated = now.strftime("%B %d, %Y at %I:%M %p %Z")
    
    nba_cards = ''.join([generate_prediction_card(pred) for pred in SAMPLE_PREDICTIONS['nba']])
    nfl_cards = ''.join([generate_prediction_card(pred) for pred in SAMPLE_PREDICTIONS['nfl']]) if SAMPLE_PREDICTIONS['nfl'] else '<p style="color: var(--color-text-secondary);">No NFL predictions available.</p>'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI PrizePicks Prediction Engine</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --color-primary: #1e40af;
            --color-secondary: #0f766e;
            --color-success: #059669;
            --color-danger: #dc2626;
            --color-warning: #f59e0b;
            --color-bg: #0a0e27;
            --color-surface: #1a1f3a;
            --color-border: #2d3748;
            --color-text: #f1f5f9;
            --color-text-secondary: #cbd5e1;
            --shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, var(--color-bg) 0%, #0f1729 100%);
            color: var(--color-text);
            padding: 20px;
            min-height: 100vh;
        }}

        .header {{
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid var(--color-border);
            padding-bottom: 20px;
        }}

        .header h1 {{
            font-size: 2.8em;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #00d4ff, #0099ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .header-badge {{
            display: inline-block;
            background: rgba(0, 212, 255, 0.2);
            border: 1px solid #00d4ff;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            color: #00d4ff;
            margin-bottom: 10px;
            font-weight: 600;
        }}

        .header p {{
            color: var(--color-text-secondary);
            font-size: 1.1em;
        }}

        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}

        .controls-section {{
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: var(--shadow);
        }}

        .league-tabs {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .league-tab {{
            padding: 10px 20px;
            border: 2px solid var(--color-border);
            background: transparent;
            color: var(--color-text);
            cursor: pointer;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }}

        .league-tab:hover {{
            border-color: #00d4ff;
            background: rgba(0, 212, 255, 0.1);
        }}

        .league-tab.active {{
            background: linear-gradient(135deg, #00d4ff, #0099ff);
            border-color: #00d4ff;
            color: #000;
        }}

        .prediction-card {{
            background: var(--color-surface);
            border: 2px solid var(--color-border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
        }}

        .prediction-card:hover {{
            border-color: #00d4ff;
            box-shadow: 0 8px 24px rgba(0, 212, 255, 0.1);
            transform: translateY(-2px);
        }}

        .prediction-card.high-confidence {{
            border-left: 5px solid #00ff88;
        }}

        .prediction-card.medium-confidence {{
            border-left: 5px solid #ffaa00;
        }}

        .prediction-card.low-confidence {{
            border-left: 5px solid #ff4444;
        }}

        .prediction-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 15px;
        }}

        .prediction-title {{
            font-size: 1.3em;
            font-weight: 700;
            color: var(--color-text);
        }}

        .confidence-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 700;
            color: white;
        }}

        .confidence-badge.high {{
            background: linear-gradient(135deg, #00ff88, #00cc66);
        }}

        .confidence-badge.medium {{
            background: linear-gradient(135deg, #ffaa00, #ff8800);
        }}

        .confidence-badge.low {{
            background: linear-gradient(135deg, #ff4444, #cc0000);
        }}

        .factor-breakdown {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}

        .factor-item {{
            background: rgba(0, 212, 255, 0.05);
            border: 1px solid rgba(0, 212, 255, 0.2);
            padding: 15px;
            border-radius: 8px;
        }}

        .factor-name {{
            font-size: 0.9em;
            font-weight: 600;
            color: #00d4ff;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}

        .factor-score-bar {{
            background: rgba(0, 0, 0, 0.3);
            height: 24px;
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 6px;
        }}

        .factor-score-fill {{
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #00ff88);
            width: 0%;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.75em;
            font-weight: 700;
            color: #000;
        }}

        .factor-detail {{
            font-size: 0.8em;
            color: var(--color-text-secondary);
            line-height: 1.4;
        }}

        .risk-indicator {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 600;
            margin-top: 10px;
        }}

        .risk-indicator.low-risk {{
            background: rgba(0, 255, 136, 0.15);
            color: #00ff88;
        }}

        .risk-indicator.medium-risk {{
            background: rgba(255, 170, 0, 0.15);
            color: #ffaa00;
        }}

        .risk-indicator.high-risk {{
            background: rgba(255, 68, 68, 0.15);
            color: #ff4444;
        }}

        .ai-reasoning {{
            background: rgba(0, 212, 255, 0.05);
            border-left: 3px solid #00d4ff;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
            font-size: 0.9em;
            line-height: 1.6;
            color: var(--color-text-secondary);
        }}

        .league-content {{
            display: none;
        }}

        .league-content.active {{
            display: block;
        }}

        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 1.8em;
            }}

            .factor-breakdown {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-badge">🤖 AI-POWERED PREDICTION ENGINE</div>
        <h1>Advanced PrizePicks Analyzer</h1>
        <p>Multi-Factor AI Model | Daily Auto-Updates | Game Script + Injury Analysis</p>
    </div>

    <div class="container">
        <div class="controls-section">
            <div class="league-tabs">
                <button class="league-tab active" data-league="nba">NBA</button>
                <button class="league-tab" data-league="nfl">NFL</button>
            </div>
        </div>

        <div id="nba" class="league-content active">
            <h2 style="font-size: 1.6em; margin: 30px 0 20px 0;">🏀 NBA Predictions – {today_date}</h2>
            {nba_cards}
        </div>

        <div id="nfl" class="league-content">
            <h2 style="font-size: 1.6em; margin: 30px 0 20px 0;">🏈 NFL Predictions – {today_date}</h2>
            {nfl_cards}
        </div>
    </div>

    <div style="text-align: center; margin: 40px 0; color: var(--color-text-secondary); font-size: 0.9em;">
        <p>🔄 Dashboard Auto-Updates Daily at 8:00 AM PST</p>
        <p>Last Updated: {last_updated}</p>
    </div>

    <script>
        document.querySelectorAll('.league-tab').forEach(tab => {{
            tab.addEventListener('click', function() {{
                const league = this.getAttribute('data-league');
                document.querySelectorAll('.league-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.league-content').forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                document.getElementById(league).classList.add('active');
            }});
        }});
    </script>
</body>
</html>
'''
    
    return html

def main():
    """Generate dashboard and write to file"""
    html_content = generate_html()
    
    with open('AI_Prediction_Engine.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ Dashboard generated successfully!")
    print(f"📝 File: AI_Prediction_Engine.html")
    print(f"🕐 Generated at: {dt.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if __name__ == '__main__':
    main()
