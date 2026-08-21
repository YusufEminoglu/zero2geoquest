# -*- coding: utf-8 -*-
"""Unit tests for Certificate generation."""
from zero2geoquest.core.certificate import generate_certificate_html, rank_title


def test_rank_title_tiers():
    title, badge = rank_title(4000, 0.95)
    assert "Grand Geographer" in title
    assert badge == "👑"

    title_mid, _ = rank_title(1800, 0.70)
    assert "Journeyman Surveyor" in title_mid

    title_low, _ = rank_title(200, 0.30)
    assert "Apprentice Navigator" in title_low


def test_certificate_html_structure():
    summary = {
        "score": 3200,
        "rounds": 10,
        "correct": 9,
        "accuracy": 0.9,
        "best_streak": 8,
    }
    html = generate_certificate_html(summary, player_name="Ada Lovelace", quest_title="World Cities")
    assert "<!doctype html>" in html
    assert "Ada Lovelace" in html
    assert "World Cities" in html
    assert "3,200" in html
    assert "90.0%" in html
    assert "8 🔥" in html
