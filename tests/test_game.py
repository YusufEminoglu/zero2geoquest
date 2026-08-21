import pytest

from zero2geoquest.core.game import GameSession, QuestionFactory


def records():
    return [
        {"fid": i, "label": f"Place {i}", "value": i * 10, "area": i * 100,
         "centroid": [i * 0.01, i * 0.02],
         "outline": [[0, 0], [i + 1, 0], [i + 1, i + 1], [0, 0]]}
        for i in range(1, 8)
    ]


def test_all_question_modes_are_serializable_and_answered():
    factory = QuestionFactory(records(), seed=7)
    for mode in ("locate", "bigger", "distance", "silhouette", "attr_guess",
                 "ordering", "nearest", "blind_zoom", "direction"):
        question = factory.make(mode)
        assert question["mode"] == mode
        assert question["answer"] is not None


def test_session_tracks_score_streak_lives_and_limit():
    session = GameSession(["locate"], round_limit=3, lives=2, seed=1)
    session.next_mode()
    first = session.answer(True, elapsed=1)
    assert first["gained"] >= 500
    assert session.streak == 1
    session.next_mode()
    session.answer(False, elapsed=1)
    assert session.lives == 1 and session.streak == 0
    session.next_mode()
    session.answer(True, elapsed=1)
    assert session.finished
    assert session.summary()["accuracy"] == 2 / 3


def test_questions_require_enough_features():
    factory = QuestionFactory(records()[:1], seed=1)
    with pytest.raises(ValueError, match="different numeric values"):
        factory.make("bigger")



def test_session_rejects_repeat_answers_and_enforces_timeout():
    session = GameSession(["locate"], round_limit=3, lives=2, difficulty="Hard")
    session.next_mode()
    timed_out = session.answer(True, elapsed=15)
    assert timed_out["timed_out"] and not timed_out["correct"]
    assert session.lives == 1
    with pytest.raises(RuntimeError, match="Start a challenge"):
        session.answer(True, elapsed=1)


def test_session_rotates_modes_before_repeating_and_deduplicates_input():
    session = GameSession(
        ["locate", "bigger", "distance", "locate"],
        round_limit=9, lives=9, seed=17)
    sequence = []
    for _ in range(9):
        sequence.append(session.next_mode())
        session.answer(True, elapsed=1)

    expected = {"locate", "bigger", "distance"}
    assert set(session.modes) == expected
    assert all(set(sequence[index:index + 3]) == expected for index in range(0, 9, 3))
    assert all(first != second for first, second in zip(sequence, sequence[1:]))


def test_score_closeness_is_bounded_to_prevent_inflated_points():
    baseline = GameSession(["locate"], round_limit=1, seed=3)
    baseline.next_mode()
    normal = baseline.answer(True, elapsed=1, closeness=1.0)

    oversized = GameSession(["locate"], round_limit=1, seed=3)
    oversized.next_mode()
    bounded = oversized.answer(True, elapsed=1, closeness=99.0)
    assert bounded["gained"] == normal["gained"]


def test_equal_or_invalid_data_is_filtered_before_question_generation():
    tied = [
        {"fid": 1, "label": "A", "value": 5, "area": 5, "centroid": [1, 1]},
        {"fid": 2, "label": "B", "value": 5, "area": 5, "centroid": [1, 1]},
        {"fid": 3, "label": "C", "value": 5, "area": 5, "centroid": [1, 1]},
    ]
    factory = QuestionFactory(tied, seed=1)
    assert factory.available_modes(["bigger", "distance", "attr_guess", "ordering"]) == []
    with pytest.raises(ValueError, match="different numeric values"):
        factory.make("bigger")


def test_duplicate_labels_are_disambiguated_across_layers():
    source = [
        {"fid": 7, "layer_id": "a", "layer_name": "Alpha", "label": "Centre", "value": 1},
        {"fid": 7, "layer_id": "b", "layer_name": "Beta", "label": "Centre", "value": 2},
    ]
    question = QuestionFactory(source, seed=2).make("bigger")
    assert len(set(question["choices"])) == 2
    assert "Alpha #7" in " ".join(question["choices"])
    assert "Beta #7" in " ".join(question["choices"])


def test_attribute_guess_uses_range_tolerance_for_zero_and_negative_values():
    source = [
        {"fid": 1, "label": "Negative", "value": -10},
        {"fid": 2, "label": "Zero", "value": 0},
        {"fid": 3, "label": "Positive", "value": 10},
    ]
    question = QuestionFactory(source, seed=3).make("attr_guess")
    assert question["tolerance_scale"] == 20
    assert question["min_val"] == -10
    assert question["max_val"] == 10
def test_distance_questions_use_metres():
    two = [
        {"fid": 1, "label": "A", "centroid": [29.0, 41.0]},
        {"fid": 2, "label": "B", "centroid": [29.0, 42.0]},
    ]
    question = QuestionFactory(two, seed=2).make("distance")
    assert 110_000 < question["answer"] < 112_500


def test_value_duel_falls_back_to_area_when_value_is_null():
    two = [
        {"fid": 1, "label": "Small", "value": None, "area": 10},
        {"fid": 2, "label": "Large", "value": None, "area": 20},
    ]
    question = QuestionFactory(two, seed=2).make("bigger")
    assert question["answer"] == "Large"


def test_compass_direction_question_generates_correct_azimuth():
    # Due North: lat increases
    north_pair = [
        {"fid": 1, "label": "South Point", "centroid": [0.0, 0.0]},
        {"fid": 2, "label": "North Point", "centroid": [0.0, 10.0]},
    ]
    q_north = QuestionFactory(north_pair, seed=1).make("direction")
    assert "North (0°)" in q_north["choices"]
    assert q_north["answer"] == "North (0°)"
    assert q_north["bearing_deg"] == 0.0

    # Due East: lon increases
    east_pair = [
        {"fid": 1, "label": "West Point", "centroid": [0.0, 0.0]},
        {"fid": 2, "label": "East Point", "centroid": [10.0, 0.0]},
    ]
    q_east = QuestionFactory(east_pair, seed=1).make("direction")
    assert "East (90°)" in q_east["choices"]
    assert q_east["answer"] == "East (90°)"
    assert q_east["bearing_deg"] == 90.0
