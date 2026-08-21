# -*- coding: utf-8 -*-
"""Geographic Intelligence Certificate generator for 02GeoQuest."""
from __future__ import annotations

import html
import time


def rank_title(score: int, accuracy: float) -> tuple[str, str]:
    """Return an honorary rank title and badge icon according to player mastery."""
    acc_pct = accuracy * 100.0
    if score >= 3500 and acc_pct >= 90.0:
        return "Grand Geographer & Master Cartographer", "👑"
    elif score >= 2500 and acc_pct >= 80.0:
        return "Senior Spatial Analyst", "🌟"
    elif score >= 1500 and acc_pct >= 65.0:
        return "Journeyman Surveyor", "🧭"
    elif score >= 800 and acc_pct >= 50.0:
        return "Cartographic Scout", "🗺️"
    else:
        return "Apprentice Navigator", "📍"


def generate_certificate_html(summary_data: dict, player_name: str = "Explorer",
                              quest_title: str = "Spatial Intelligence Quest") -> str:
    """Return a self-contained, printable HTML certificate of achievement."""
    score = int(summary_data.get("score", 0))
    rounds = int(summary_data.get("rounds", 0))
    correct = int(summary_data.get("correct", 0))
    accuracy = float(summary_data.get("accuracy", 0.0))
    best_streak = int(summary_data.get("best_streak", 0))
    acc_pct = round(accuracy * 100.0, 1)
    title_rank, badge = rank_title(score, accuracy)
    date_str = time.strftime("%Y-%m-%d %H:%M")

    safe_name = html.escape(player_name)
    safe_quest = html.escape(quest_title)
    safe_rank = html.escape(title_rank)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>02GeoQuest Certificate &mdash; {safe_name}</title>
<style>
@page {{ size: landscape; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0f172a;
  color: #1e293b;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
}}
.cert-card {{
  width: 900px;
  background: #ffffff;
  border-radius: 20px;
  padding: 48px 56px;
  position: relative;
  box-shadow: 0 25px 60px rgba(0,0,0,0.35);
  border: 10px solid #f8fafc;
  outline: 3px solid #6c4cff;
}}
.cert-header {{
  text-align: center;
  margin-bottom: 24px;
}}
.cert-badge {{
  font-size: 48px;
  line-height: 1;
  margin-bottom: 8px;
}}
.cert-brand {{
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.18em;
  color: #6c4cff;
  text-transform: uppercase;
}}
.cert-title {{
  font-size: 32px;
  font-weight: 900;
  color: #0f172a;
  margin-top: 4px;
  letter-spacing: -0.5px;
}}
.cert-sub {{
  color: #64748b;
  font-size: 15px;
  margin-top: 4px;
}}
.cert-body {{
  text-align: center;
  margin: 28px 0;
}}
.cert-presented {{
  font-size: 14px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}}
.cert-name {{
  font-size: 36px;
  font-weight: 800;
  color: #6c4cff;
  margin: 8px 0 12px;
}}
.cert-rank {{
  display: inline-block;
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  padding: 6px 18px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 16px;
  color: #0f172a;
}}
.cert-stats {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 32px 0 24px;
}}
.stat-box {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px 10px;
  text-align: center;
}}
.stat-label {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: #64748b;
  letter-spacing: 0.05em;
}}
.stat-val {{
  font-size: 24px;
  font-weight: 900;
  color: #6c4cff;
  margin-top: 2px;
}}
.cert-footer {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  border-top: 1px dashed #cbd5e1;
  padding-top: 20px;
  margin-top: 20px;
  color: #64748b;
  font-size: 12px;
}}
.print-btn {{
  display: block;
  margin: 20px auto 0;
  background: #6c4cff;
  color: #fff;
  border: none;
  padding: 10px 24px;
  font-size: 14px;
  font-weight: 700;
  border-radius: 8px;
  cursor: pointer;
}}
@media print {{
  body {{ background: transparent; padding: 0; }}
  .cert-card {{ box-shadow: none; width: 100%; border: 4px solid #6c4cff; }}
  .print-btn {{ display: none; }}
}}
</style>
</head>
<body>
<div>
<div class="cert-card">
  <div class="cert-header">
    <div class="cert-badge">{badge}</div>
    <div class="cert-brand">02GeoQuest &bull; Playable Map Studio</div>
    <h1 class="cert-title">Certificate of Spatial Intelligence</h1>
    <p class="cert-sub">{safe_quest}</p>
  </div>
  <div class="cert-body">
    <div class="cert-presented">This is proudly awarded to</div>
    <div class="cert-name">{safe_name}</div>
    <div class="cert-rank">{badge} {safe_rank}</div>
  </div>
  <div class="cert-stats">
    <div class="stat-box">
      <div class="stat-label">Final Score</div>
      <div class="stat-val">{score:,} ★</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Accuracy</div>
      <div class="stat-val">{acc_pct}%</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Correct / Rounds</div>
      <div class="stat-val">{correct} / {rounds}</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Best Streak</div>
      <div class="stat-val">{best_streak} 🔥</div>
    </div>
  </div>
  <div class="cert-footer">
    <div><strong>Date Issued:</strong> {date_str}</div>
    <div><strong>Verification:</strong> QGIS Monorepo / 02GeoQuest v1.1.0</div>
  </div>
</div>
<button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
</div>
</body>
</html>
"""
