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
    for mode in ("locate", "bigger", "distance", "silhouette"):
        question = factory.make(mode)
        assert question["mode"] == mode
        assert question["answer"] is not None


def test_session_tracks_score_streak_lives_and_limit():
    session = GameSession(["locate"], round_limit=3, lives=2, seed=1)
    session.next_mode()
    first = session.answer(True, elapsed=1)
    assert first["gained"] >= 500
    assert session.streak == 1
    session.answer(False, elapsed=1)
    assert session.lives == 1 and session.streak == 0
    session.answer(True, elapsed=50)
    assert session.finished
    assert session.summary()["accuracy"] == 2 / 3


def test_questions_require_enough_features():
    factory = QuestionFactory(records()[:1], seed=1)
    try:
        factory.make("bigger")
    except ValueError as exc:
        assert "At least 2" in str(exc)
    else:
        raise AssertionError("Expected a useful validation error")


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