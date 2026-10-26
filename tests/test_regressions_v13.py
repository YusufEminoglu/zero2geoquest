"""Regression tests for the 1.3.0 fixes.

Run against the 1.2.3 tree, 20 of these 21 fail; the exception is the sector-edge
guard for the rewritten ``compass_direction``, which keeps the old behaviour.
"""
import pytest

from zero2geoquest.core.exporter import build_html, build_payload
from zero2geoquest.core.game import (
    LCG, Joker, QuestionFactory, bearing_margin, compass_direction, nice_ceiling,
)
from zero2geoquest.core.quest_pack import STARTER_PACKS, export_pack, import_pack, validate_pack


# ── Engine ────────────────────────────────────────────────────────────────────

def test_value_duel_never_compares_a_value_with_an_area():
    mixed = [
        {"fid": 1, "label": "Big value", "value": 50, "area": 1},
        {"fid": 2, "label": "Small value", "value": 10, "area": 2},
        {"fid": 3, "label": "No value, huge area", "value": None, "area": 1_000_000},
    ]
    factory = QuestionFactory(mixed, seed=4, value_label="population")
    assert factory.metric == "value"
    for _ in range(20):
        question = factory.make("bigger")
        assert "No value, huge area" not in question["choices"]
        assert question["prompt"] == "Which one has the greater population?"


def test_area_prompt_is_honest_when_no_value_field():
    two = [{"fid": 1, "label": "A", "area": 1}, {"fid": 2, "label": "B", "area": 2}]
    assert QuestionFactory(two, seed=1).make("bigger")["prompt"] == "Which one covers the larger area?"


def test_records_without_or_with_text_ids_are_still_distinct():
    # Quest Packs may omit fid or use text ids; every record keeps its identity.
    no_ids = [{"label": f"City {i}", "centroid": [i * 1.0, (i * i) % 7 * 0.5]} for i in range(8)]
    assert "nearest" in QuestionFactory(no_ids, seed=5).available_modes(["nearest"])
    text_ids = [dict(record, fid=f"id-{i}") for i, record in enumerate(no_ids)]
    question = QuestionFactory(text_ids, seed=5).make("nearest")
    assert question["answer"] in question["choices"]


def test_distance_input_range_does_not_depend_on_the_answer():
    places = [{"fid": i, "label": f"P{i}", "centroid": [29.0 + i * 0.5, 41.0]} for i in range(6)]
    factory = QuestionFactory(places, seed=8)
    answers = set()
    for _ in range(15):
        question = factory.make("distance")
        answers.add(round(question["answer"]))
        assert question["unit"] == "km"
        assert question["input_max"] == factory.distance_scale()["input_max"]
    assert len(answers) > 1  # several answers, one shared input range


def test_city_scale_distances_are_asked_in_metres():
    blocks = [{"fid": i, "label": f"B{i}", "centroid": [27.0 + i * 0.001, 38.4]} for i in range(5)]
    question = QuestionFactory(blocks, seed=2).make("distance")
    assert question["unit"] == "m" and question["unit_factor"] == 1.0


def test_compass_pairs_avoid_sector_boundaries():
    grid = [{"fid": i, "label": f"R{i}", "centroid": [10 + (i % 5) * 0.37, 10 + (i // 5) * 0.29]}
            for i in range(20)]
    factory = QuestionFactory(grid, seed=3)
    for _ in range(30):
        question = factory.make("direction")
        assert bearing_margin(question["bearing_deg"]) >= 4.9
        assert question["answer"] == "{} ({}°)".format(*compass_direction(question["bearing_deg"]))


def test_compass_direction_sector_edges():
    assert compass_direction(0) == ("North", 0)
    assert compass_direction(22.49) == ("North", 0)
    assert compass_direction(22.5) == ("North-East", 45)
    assert compass_direction(337.5) == ("North", 0)
    assert compass_direction(337.49) == ("North-West", 315)


def test_value_hint_window_always_contains_the_answer():
    for seed in range(200):
        joker = Joker(3, rng=LCG(seed))
        truth = float((seed * 37) % 101)
        lo, hi = joker.narrow_range(0.0, 100.0, truth=truth)
        assert lo <= truth <= hi
        assert hi - lo == pytest.approx(50.0)


def test_eliminate_is_not_wasted_on_two_choices():
    joker = Joker(3, rng=LCG(1))
    assert joker.eliminate(["A", "B"], "A") == ["A", "B"]
    assert joker.available(Joker.ELIMINATE)
    remaining = joker.eliminate(["A", "B", "C"], "A")
    assert "A" in remaining and len(remaining) == 2


def test_lcg_draws_are_not_trivially_periodic():
    rng = LCG(123)
    draws = [rng.below(2) for _ in range(64)]
    # A raw `state % 2` LCG strictly alternates 0,1,0,1...
    assert any(first == second for first, second in zip(draws, draws[1:]))


def test_unseeded_generators_differ():
    assert [LCG().below(1000) for _ in range(3)] != [LCG(20260720).below(1000) for _ in range(3)]


def test_blind_zoom_requires_a_known_extent():
    plain = [{"fid": i, "label": f"P{i}", "centroid": [i, i]} for i in range(4)]
    assert QuestionFactory(plain, seed=1).available_modes(["blind_zoom"]) == []


def test_ranking_never_starts_already_solved():
    data = [{"fid": i, "label": f"V{i}", "value": i} for i in range(3)]
    for seed in range(40):
        question = QuestionFactory(data, seed=seed).make("ordering")
        assert [item["label"] for item in question["items"]] != question["answer"]


def test_attribute_tolerance_follows_the_real_range():
    ratios = [{"fid": i, "label": f"R{i}", "value": v} for i, v in enumerate((0.1, 0.3, 0.5))]
    assert QuestionFactory(ratios, seed=1).make("attr_guess")["tolerance_scale"] == pytest.approx(0.4)


def test_nice_ceiling():
    assert nice_ceiling(0.7) == 1.0
    assert nice_ceiling(1.0) == 1.0
    assert nice_ceiling(1.2) == 2.0
    assert nice_ceiling(2.2) == 2.5
    assert nice_ceiling(4100) == 5000


# ── Quest Packs ───────────────────────────────────────────────────────────────

def test_starter_pack_populations_share_one_definition():
    # Paris (city proper, 2.16 M) used to rank below Ankara while Tokyo used
    # its 37 M agglomeration figure.
    capitals = {r["label"]: r["value"]
                for r in STARTER_PACKS["World Capitals & Metropolises"]["records"]}
    assert capitals["Paris (France)"] > capitals["Ankara (Türkiye)"]
    for pack in STARTER_PACKS.values():
        assert pack["value_label"] == "population"
        assert "World Urbanization Prospects 2018" in pack["source"]


def test_value_label_round_trips_through_a_pack(tmp_path):
    records = [
        {"fid": 1, "label": "Alpha", "centroid": [10.0, 20.0], "value": 100},
        {"fid": 2, "label": "Beta", "centroid": [15.0, 25.0], "value": 200},
    ]
    pack_file = tmp_path / "labelled.geoquest.json"
    export_pack(pack_file, "Labelled", "", records, ["bigger"], value_label="households")
    assert import_pack(pack_file)["value_label"] == "households"


def test_pack_without_ids_is_valid_and_playable():
    pack = {
        "title": "No ids", "modes": ["nearest", "bigger"],
        "records": [{"label": f"C{i}", "value": i, "centroid": [i * 1.0, (i * i) % 5 * 0.7]}
                    for i in range(6)],
    }
    valid, message = validate_pack(pack)
    assert valid, message


# ── Offline HTML ──────────────────────────────────────────────────────────────

def _grid_records(count=6):
    return [{"fid": i, "label": f"P{i}", "value": i * 3.5, "area": i,
             "centroid": [28.0 + i * 0.01, 41.0 + (i % 3) * 0.01],
             "outline": [[0, 0], [i + 1, 0], [i + 1, 2 * i + 2], [0, 2 * i + 2]]}
            for i in range(1, count + 1)]


def test_payload_carries_difficulty_lives_and_metric():
    payload = build_payload("Q", _grid_records(), ["bigger", "distance"], 7,
                            difficulty="Hard", lives=5, value_label="population")
    assert payload["settings"] == {"timer": 15, "choices": 6, "tolerance": 0.10}
    assert payload["lives"] == 5 and payload["rounds"] == 7
    assert payload["metric"] == "value"
    assert payload["value_label"] == "population"
    # A city-scale quest asks for metres, with an input range from the data.
    assert payload["distance"]["unit"] == "m"
    assert payload["distance"]["max"] >= payload["distance"]["widest_m"]


def test_payload_strips_layer_bookkeeping():
    records = _grid_records()
    for record in records:
        record.update(layer_id="secret_layer_id", bbox_wgs84=[0, 0, 1, 1])
    output = build_html("Q", records, ["bigger"], 3)
    assert "secret_layer_id" not in output
    assert "bbox_wgs84" not in output


def test_engine_does_not_use_a_fixed_seed_or_leak_answers():
    output = build_html("Q", _grid_records(), ["distance", "attr_guess"], 3)
    assert "lcg_state=42" not in output
    assert "crypto.getRandomValues" in output
    # The old slider started at 1.25 x the answer, which scored as correct.
    assert "truth*2.5" not in output
    assert "rng.value='0'" in output
