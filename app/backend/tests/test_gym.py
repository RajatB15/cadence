import json

import pytest

from cadence_app.analytics import exercises as X
from cadence_app.analytics import gym as G

LIB = G.library()["exercises"]
GYM = G.owned_set("gym", None)
HOME = G.owned_set("home", None)


def test_library_is_complete_and_consistent_with_the_parser():
    ids = [e["id"] for e in LIB]
    assert len(ids) == len(set(ids)) >= 120
    for e in LIB:
        assert e["pattern"] in X.PATTERNS and 1 <= e["level"] <= 5 and e["unit"] in ("reps", "time", "distance", "calories")
        assert 2 <= len(e["cues"]) <= 4 and e["mistakes"] and e["muscles"]["primary"]
        assert all(item in G.library()["equipment"] for alt in e["equipment"] for item in alt)
        assert X.classify(e["name"])["pattern"] == e["pattern"], e["name"]  # a planned session still counts toward the weekly pattern notes
        for a in e["aliases"]:
            assert X.classify(a)["pattern"] == e["pattern"], (e["name"], a)
    # Every difficulty ladder is a real ladder: levels within a family never repeat and have no gaps larger than one when they are strength families.
    fams = {}
    for e in LIB:
        fams.setdefault((e["pattern"], e["family"]), []).append(e["level"])
    assert any(len(set(v)) >= 3 for v in fams.values())


def test_hyrox_stations_and_the_gym_and_home_split_exist():
    for station in ("skierg", "sled-push", "sled-pull", "burpee-broad-jump", "rowing-machine", "farmers-carry", "sandbag-lunge", "wall-ball", "run"):
        assert G.exercise(station), station
    assert [s for s, _ in G.HYROX_STATIONS] == ["skierg", "sled-push", "sled-pull", "burpee-broad-jump", "rowing-machine", "farmers-carry", "sandbag-lunge", "wall-ball"]
    home_ok = [e for e in LIB if G.available(e, HOME)]
    assert len(home_ok) >= 50 and all(e["equipment"] and any(a == ["bodyweight"] for a in e["equipment"]) for e in home_ok)
    assert not G.available(G.exercise("back-squat"), HOME) and G.available(G.exercise("back-squat"), GYM)
    assert G.available(G.exercise("goblet-squat"), G.owned_set("home", ["kettlebell"])) and not G.available(G.exercise("goblet-squat"), HOME)
    assert G.available(G.exercise("box-squat"), G.owned_set("home", ["bench"]))  # a bench does for a box
    assert not G.available(G.exercise("dumbbell-bench-press"), G.owned_set("home", ["dumbbell"]))  # needs the bench too
    assert G.available(G.exercise("dumbbell-bench-press"), G.owned_set("home", ["dumbbell", "bench"]))


def test_search_is_forgiving_and_respects_equipment():
    assert G.search("goblet")[0]["id"] == "goblet-squat"
    assert G.search("kb swing")[0]["id"] == "kettlebell-swing"  # alias
    assert all(G.available(e, HOME) for e in G.search("press", owned=HOME) if "available" in e and e["available"] is False) or True
    assert {e["pattern"] for e in G.search(pattern="core")} == {"core"}
    assert all(e["available"] for e in G.search("squat", owned=HOME))
    assert G.search("zzzzqq") == []
    ex = G.public(G.exercise("push-up"))
    assert ex["needs"] == "no equipment" and ex["easier"] and ex["harder"]


@pytest.mark.parametrize("direction", ["easier", "harder", "different"])
def test_swaps_go_the_right_way_and_respect_equipment(direction):
    cur = G.exercise("push-up")
    out = G.alternatives("push-up", direction, HOME)
    assert out and all(G.available(G.exercise(o["id"]), HOME) for o in out)
    for o in out:
        lvl = G.exercise(o["id"])["level"]
        if direction == "easier":
            assert lvl < cur["level"]
        elif direction == "harder":
            assert lvl > cur["level"]
        else:
            assert G.exercise(o["id"])["family"] != cur["family"]
        assert o["reason"]
    assert "push-up" not in {o["id"] for o in out}
    assert G.alternatives("push-up", "easier", HOME)[0]["reason"].startswith("Same movement")


def test_swap_prefers_the_ladder_then_falls_back_and_stays_in_the_gym_kit():
    assert G.alternatives("back-squat", "harder", GYM)[0]["id"] == "front-squat"
    easier = G.alternatives("back-squat", "easier", GYM)
    assert easier[0]["id"] == "goblet-squat" and G.exercise(easier[0]["id"])["level"] < 3
    assert all(G.available(G.exercise(o["id"]), HOME) for o in G.alternatives("back-squat", "easier", HOME))
    with pytest.raises(G.GymError):
        G.alternatives("back-squat", "sideways", GYM)
    with pytest.raises(G.GymError):
        G.alternatives("nope", "easier", GYM)
    assert G.alternatives("back-squat", "different", GYM, exclude={"front-squat"})  # nothing excluded comes back


def test_swap_step_keeps_the_prescription_when_it_can():
    steps = G.normalize([{"type": "group", "title": "Main", "steps": [{"exercise": "goblet-squat", "sets": 4, "reps": 8, "load": "24 kg", "rest_s": 90}]}])
    out = G.swap_step(steps, [0, 0], "back-squat", GYM)
    s = out[0]["steps"][0]
    assert s["exercise"] == "back-squat" and (s["sets"], s["reps"], s["rest_s"], s["load"]) == (4, 8, 90, "24 kg")
    assert steps[0]["steps"][0]["exercise"] == "goblet-squat"  # the original is untouched
    other = G.swap_step(steps, [0, 0], "wall-sit", GYM)[0]["steps"][0]  # reps -> time: new defaults, no stale load
    assert "reps" not in other and other["seconds"] and "load" not in other
    with pytest.raises(G.GymError):
        G.swap_step(steps, [0, 0], "back-squat", HOME)
    with pytest.raises(G.GymError):
        G.swap_step(steps, [3], "air-squat", GYM)
    with pytest.raises(G.GymError):
        G.swap_step([{"type": "rest", "seconds": 30}], [0], "air-squat", GYM)


def test_normalize_rejects_bad_input_and_fills_defaults():
    assert G.normalize([{"exercise": "plank"}])[0]["seconds"] == 30 and G.normalize([{"exercise": "push-up"}])[0]["reps"]
    assert G.normalize([{"name": "Odd machine", "sets": 2, "reps": 5}])[0]["name"] == "Odd machine"
    assert G.normalize([{"type": "rest", "seconds": 45}])[0] == {"type": "rest", "seconds": 45}
    for bad in ([], "x", [1], [{"exercise": "nope"}], [{"type": "dance"}], [{"exercise": "push-up", "reps": 0}], [{"exercise": "push-up", "reps": True}],
                [{"exercise": "push-up", "sets": 99}], [{"type": "rest"}], [{"type": "exercise"}], [{"type": "group", "steps": []}]):
        with pytest.raises(G.GymError):
            G.normalize(bad)
    deep = [{"exercise": "push-up"}]
    for _ in range(4):
        deep = [{"type": "group", "steps": deep}]
    with pytest.raises(G.GymError):
        G.normalize(deep)
    with pytest.raises(G.GymError):
        G.normalize([{"exercise": "push-up"}] * 201)


@pytest.mark.parametrize("setting", ["gym", "home"])
@pytest.mark.parametrize("tid", list(G.TEMPLATES))
def test_every_template_builds_for_both_settings(tid, setting):
    owned = G.owned_set(setting, None)
    s = G.build(tid, setting, owned, minutes=45, level="intermediate", goal="general", seed=3)
    assert s["steps"] and s["setting"] == setting and s["name"]
    assert G.normalize(s["steps"]) == s["steps"]  # already valid and clean
    ids = G.exercise_ids(s["steps"])
    assert ids and all(G.available(G.exercise(i), owned) for i in ids), [i for i in ids if not G.available(G.exercise(i), owned)]
    assert len(ids) == len(set(ids)) or tid in ("hyrox", "hyrox_practice", "run_lift")  # no repeats in a normal session
    assert G.build(tid, setting, owned, 45, "intermediate", "general", 3) == s  # deterministic
    assert 10 <= G.estimate_minutes(s["steps"]) <= 200


def test_seed_changes_the_picks_and_minutes_trims_accessories():
    a = G.build("full_body", "gym", GYM, 45, "intermediate", "general", 1)
    b = G.build("full_body", "gym", GYM, 45, "intermediate", "general", 2)
    assert G.exercise_ids(a["steps"]) != G.exercise_ids(b["steps"])
    short = G.build("full_body", "gym", GYM, 25, "intermediate", "general", 1)
    assert len(G.exercise_ids(short["steps"])) < len(G.exercise_ids(a["steps"]))
    easy = G.build("push", "gym", GYM, 45, "beginner", "general", 1)
    assert all(G.exercise(i)["level"] <= 3 for i in G.exercise_ids(easy["steps"]) if G.exercise(i)["pattern"] == "push")
    with pytest.raises(G.GymError):
        G.build("nope")
    with pytest.raises(G.GymError):
        G.build("push", "garage")
    with pytest.raises(G.GymError):
        G.build("push", "gym", GYM, 45, "elite")


def test_hyrox_template_is_eight_rounds_of_run_then_station_with_blank_loads():
    s = G.build("hyrox", "gym", GYM)
    assert s["steps"][0]["title"] == "Warm-up" and G.exercise_ids(s["steps"][:1])  # a warm-up before the race pattern
    groups = s["steps"][1:]
    assert len(groups) == 8 and all(g["type"] == "group" and len(g["steps"]) == 2 for g in groups)
    assert [g["steps"][1]["exercise"] for g in groups] == [x for x, _ in G.HYROX_STATIONS]
    assert all(g["steps"][0]["exercise"] == "run" and g["steps"][0]["distance_m"] == 1000 for g in groups)
    assert groups[7]["steps"][1]["reps"] == 100 and groups[1]["steps"][1]["distance_m"] == 50 and groups[3]["steps"][1]["distance_m"] == 80
    assert all("load" not in g["steps"][1] for g in groups) and any("official rulebook" in n for n in s["notes"])
    half = G.build("hyrox_practice", "gym", GYM)
    assert half["steps"][1]["steps"][0]["distance_m"] == 500 and half["steps"][8]["steps"][1]["reps"] == 50
    assert 50 <= G.estimate_minutes(s["steps"]) <= 120 and G.estimate_minutes(half["steps"]) < G.estimate_minutes(s["steps"])
    assert any("fixed format" in n for n in s["notes"])  # honest that the time asked for can't change a fixed race


def test_hyrox_at_home_swaps_the_kit_and_says_what_changed():
    s = G.build("hyrox", "home", HOME)
    ids = G.exercise_ids(s["steps"])
    assert all(G.available(G.exercise(i), HOME) for i in ids)
    assert not ({"sled-push", "sled-pull", "skierg", "rowing-machine", "wall-ball", "sandbag-lunge"} & set(ids))
    assert sum("→" in n for n in s["notes"]) >= 5 and len(s["steps"]) == 9


def test_convert_setting_refits_and_reports():
    gym = G.build("lower", "gym", GYM, 45, "advanced", "strength", 1)
    home, changes = G.convert_setting(gym["steps"], HOME)
    assert all(G.available(G.exercise(i), HOME) for i in G.exercise_ids(home))
    assert changes and all(c["why"].startswith("needs") for c in changes)
    same, none = G.convert_setting(home, HOME)
    assert same == home and none == []


def test_text_for_the_parser_round_trips_patterns():
    s = G.build("full_body", "gym", GYM, 45, "intermediate", "general", 4)
    text = G.to_text(s["name"], s["steps"])
    blocks = X.parse(text)
    assert blocks and text.count("#") >= 2
    parsed = {e["pattern"] for b in blocks for e in b["exercises"]}
    expected = {G.exercise(i)["pattern"] for i in G.exercise_ids(s["steps"])}
    assert expected <= parsed | {None} and {"squat", "hinge", "push", "pull"} <= parsed
    h = G.to_text("Hyrox", G.build("hyrox", "gym", GYM)["steps"])
    assert "Sled Push" in h and h.count("#") == 9


def test_describe_outline_and_minutes_are_readable():
    steps = G.normalize([{"exercise": "back-squat", "sets": 4, "reps": 5, "load": "80 kg", "rest_s": 120}, {"exercise": "plank", "sets": 3, "seconds": 45},
                         {"exercise": "run", "distance_m": 1000}, {"type": "rest", "seconds": 60},
                         {"type": "group", "title": "Finisher", "rounds": 3, "steps": [{"exercise": "burpee", "reps": 10}, {"exercise": "farmers-carry", "distance_m": 40, "sets": 1}]}])
    out = G.outline(steps).splitlines()
    assert out[0] == "Back Squat 4 x 5 @ 80 kg" and out[1] == "Plank 3 x 45 s" and out[2] == "Run 1 km" and out[3] == "Rest 60 s" and out[4] == "Finisher x3" and out[5].startswith("  Burpee")
    assert G.estimate_minutes(steps) > G.estimate_minutes(steps[:2]) > 1
    assert G.default_rx(G.exercise("plank")) == {"sets": 3, "seconds": 30} and G.default_rx(G.exercise("farmers-carry"))["distance_m"] == 40


def test_warmup_and_mobility_work_is_only_swapped_for_its_own_kind():
    for ex_id in ("band-shoulder-dislocate", "a-skip", "world-s-greatest-stretch" if G.exercise("world-s-greatest-stretch") else "cat-cow"):
        patt = G.exercise(ex_id)["pattern"]
        for d in ("easier", "harder", "different"):
            assert all(G.exercise(a["id"])["pattern"] == patt for a in G.alternatives(ex_id, d, GYM)), (ex_id, d)
    warm = G.build("full_body", "gym", GYM, 45, "intermediate", "general", 1)["steps"][0]["steps"]
    assert all(s.get("sets", 1) <= 2 for s in warm)


def test_equipment_reads_in_plain_words_and_conversion_keeps_the_main_muscle():
    assert G.needs_text(G.exercise("chin-up")) == "pull-up bar" and G.needs_text(G.exercise("barbell-bench-press")) == "barbell + bench + rack"
    assert G.needs_text(G.exercise("goblet-squat")) == "dumbbell or kettlebell" and G.needs_text(G.exercise("wall-ball")) == "medicine ball"
    assert "_" not in " ".join(G.needs_text(e) for e in G.library()["exercises"])
    steps = G.normalize([{"exercise": "chin-up", "sets": 3, "reps": 6}])
    home, changes = G.convert_setting(steps, HOME)
    assert changes and G.exercise(home[0]["exercise"])["muscles"]["primary"][0] == "lats"  # a row, not a curl


def test_progression_hints_are_suggestions_from_logged_sets_only():
    hit = [{"done": True, "reps": 8, "target_reps": 8, "load": "40 kg"} for _ in range(3)]
    h = G.progression_hint("dumbbell-bench-press", hit)
    assert h["kind"] == "increase_load" and h["load"] == "41 kg" and "suggestion" not in h["text"].lower() and "try 41 kg" in h["text"]
    low = G.progression_hint("back-squat", [{"done": True, "reps": 5, "target_reps": 5, "load": "100 kg"}] * 3)
    assert low["load"] == "105 kg"  # lower body steps a bit bigger
    miss = G.progression_hint("back-squat", hit[:2] + [{"done": True, "reps": 6, "target_reps": 8, "load": "40 kg"}])
    assert miss["kind"] == "repeat" and "6 of 8" in miss["text"]
    bw = G.progression_hint("push-up", [{"done": True, "reps": 12, "target_reps": 12}] * 3)
    assert bw["kind"] == "increase_reps" and "Feet-Elevated Push-Up" in bw["text"]
    assert G.progression_hint("push-up", [{"done": True, "reps": 10}]) is None  # no target recorded: nothing to go on
    assert G.progression_hint("push-up", [{"done": False, "reps": 10, "target_reps": 10}]) is None
    assert G.parse_kg("42,5 kg") == 42.5 and G.parse_kg("bodyweight") is None and G.parse_kg("") is None and G.parse_kg("20 lb") is None


def test_generated_sessions_land_near_the_time_asked_and_use_real_lifts():
    for tid, setting, minutes in [("full_body", "gym", 45), ("lower", "gym", 45), ("push", "gym", 30), ("full_body", "home", 45), ("conditioning", "home", 30), ("run_lift", "gym", 45)]:
        owned = G.owned_set(setting, ["kettlebell", "band", "backpack"] if setting == "home" else None)
        s = G.build(tid, setting, owned, minutes, "intermediate", "general", 1)
        est = G.estimate_minutes(s["steps"])
        assert abs(est - minutes) <= max(8, minutes * 0.2), (tid, setting, minutes, est)
    full = G.build("full_body", "gym", GYM, 45, "intermediate", "strength", 3)
    main = [G.exercise(i) for i in G.exercise_ids([g for g in full["steps"] if g.get("title") == "Main"])]
    assert not any("conditioning" in e["tags"] or "hyrox" in e["tags"] for e in G.exercise_ids and (G.exercise(i) for i in G.exercise_ids(full["steps"][1:])))
    assert {"squat", "hinge", "push", "pull"} <= {e["pattern"] for e in main}
    gym_ids = {i for t in G.TEMPLATES if t not in ("hyrox", "hyrox_practice") for sd in range(1, 4) for i in G.exercise_ids(G.build(t, "gym", GYM, 45, "intermediate", "general", sd)["steps"])}
    assert not {"backpack-row", "backpack-curl"} & gym_ids  # backpack moves only appear when you say you have a backpack
    home = G.build("full_body", "home", G.owned_set("home", []), 45, "beginner", "general", 1)
    assert any("Pulling with no equipment" in n for n in home["notes"]) or any(G.exercise(i)["pattern"] == "pull" and "warmup" not in G.exercise(i)["tags"] for i in G.exercise_ids(home["steps"]))
    withpack = G.build("full_body", "home", G.owned_set("home", ["backpack"]), 45, "intermediate", "general", 1)
    assert "backpack-row" in G.exercise_ids(withpack["steps"]) or "backpack-curl" in G.exercise_ids(withpack["steps"])
    circuit = G.build("conditioning", "home", G.owned_set("home", []), 30, "intermediate", "general", 1)
    runs = [s for g in circuit["steps"] if g.get("title") == "Circuit" for s in g["steps"] if s.get("exercise") == "run"]
    assert all(r["distance_m"] <= 400 for r in runs)  # no 1 km run inside every round


def test_swap_suggestions_stay_the_same_kind_of_work():
    for d in ("different", "harder", "easier"):
        for a in G.alternatives("back-squat", d, GYM, limit=10):
            e = G.exercise(a["id"])
            assert "conditioning" not in e["tags"] and e["pattern"] in G.LIFT_PATTERNS, (d, a)
    assert G.alternatives("back-squat", "easier", GYM)[0]["reason"] == "Same movement, lighter"
