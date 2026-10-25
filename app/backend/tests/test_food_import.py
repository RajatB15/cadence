from cadence_app import food_import as FI


def rec(rid, name, kcal=100.0, protein=5.0, carbs=15.0, fat=2.0, default=None, portions=(), table=None, verified=False, labels=()):
    return {"id": rid, "name": name, "per_100g": {"kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "fibre_g": 1.0},
            "default_serving": default, "portions": [{"unit": u, "grams": g, "kcal": 1, "protein_g": 1} for u, g in portions],
            "nutrients_per_100g": table or {"Calcium": [10.0, "mg"], "Iron": [1.0, "mg"]}, "verified": verified,
            "provenance": {"labels": list(labels), "urls": []}}


def test_checks_catch_impossible_rows():
    ok = {"kcal": 100, "protein_g": 5, "carbs_g": 15, "fat_g": 2}
    assert FI.check(ok) is None
    assert FI.check({**ok, "kcal": 1200}) == "calories out of range"
    assert FI.check({"kcal": None}) == "no calories"
    assert FI.check({"kcal": 300, "protein_g": 60, "carbs_g": 30, "fat_g": 20}) == "more nutrient than food"
    assert FI.check({"kcal": 500, "protein_g": 2, "carbs_g": 3, "fat_g": 1}) == "macros disagree with calories"
    assert FI.check({"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}) is None  # water is a real food


def test_aliases_of_one_food_become_one_dish():
    same = {"Calcium": [19.0, "mg"], "Iron": [0.8, "mg"]}
    dishes, report = FI.build_catalogue([
        rec("ada-1111111111", "Ada", table=same), rec("adu-2222222222", "Adu", table=same),
        rec("aam-3333333333", "Mango", kcal=60, protein=1, carbs=14, fat=0.3, table={"Calcium": [11.0, "mg"]}),
    ])
    assert len(dishes) == 2 and report["merged_alias_pages"] == 1
    ada = next(d for d in dishes if d["name"] in ("Ada", "Adu"))
    assert ada["aliases"] and {ada["name"], *ada["aliases"]} == {"Ada", "Adu"}


def test_different_foods_with_one_name_keep_it_plus_a_code():
    dishes, _ = FI.build_catalogue([rec("upma-aaaa111111", "Upma", kcal=85, table={"Calcium": [15.0, "mg"]}),
                                    rec("upma-bbbb222222", "Upma", kcal=150, table={"Calcium": [30.0, "mg"]})])
    assert sorted(d["name"] for d in dishes) == sorted(f'Upma ({d["ref_code"][:4]})' for d in dishes) and len({d["name"] for d in dishes}) == 2


def test_portions_carry_weights_and_the_default_unit_states_its_grams():
    r = rec("upma-ce3d43bb57", "Upma", kcal=85.34, protein=2.41, carbs=15.86, fat=1.39,
            default={"qty": 1.0, "unit": "katori", "grams": 130.0}, portions=[("katori", 130.0), ("oz", 28.35), ("bowl", 303.0), ("Small Bowl", 130.0)],
            labels=["hebbarskitchen.com"])
    (d,), _ = FI.build_catalogue([r])
    assert d["unit"] == "1 katori (≈130 g)" and d["grams"] == 130.0
    assert [p["unit"] for p in d["portions"]] == ["katori", "bowl", "Small Bowl"]  # oz dropped, duplicate weight of the default kept once per unit
    assert abs(d["kcal"] - 110.9) < 0.1 and d["per_100g"]["kcal"] == 85.34 and d["page_codes"] == ["ce3d43bb57"]
    assert "hebbarskitchen.com" in d["note"] and "not verified" in d["note"] and d["spread_pct"] == FI.SPREAD_UNVERIFIED


def test_a_gram_only_page_becomes_a_100_g_dish_and_foreign_names_are_aliases_only():
    gram_only = rec("x-aaaaaaaaaa", "Paneer", default={"qty": 1.0, "unit": "grams", "grams": 1.0}, table={"Calcium": [1.0, "mg"]})
    (d,), _ = FI.build_catalogue([gram_only])
    assert d["unit"] == "100 g" and d["grams"] == 100.0 and d["portions"] == []
    dishes, report = FI.build_catalogue([rec("y-bbbbbbbbbb", "Творог", table={"Calcium": [2.0, "mg"]}),
                                         rec("z-cccccccccc", "Cottage cheese", table={"Calcium": [2.0, "mg"]})])
    assert [x["name"] for x in dishes] == ["Cottage cheese"] and dishes[0]["aliases"] == ["Творог"]
    only_foreign, rep = FI.build_catalogue([rec("w-dddddddddd", "Творог", table={"Calcium": [9.0, "mg"]})])
    assert only_foreign == [] and rep["skipped_no_latin_name"] == 1


def test_a_dish_keeps_its_code_when_more_pages_join_it():
    first = [rec("ada-1111111111", "Ada", kcal=100, table={"Calcium": [5.0, "mg"]})]
    later = first + [rec("adu-0000000000", "Adu", kcal=100, table={"Calcium": [5.0, "mg"]})]
    (a,), _ = FI.build_catalogue(first)
    (b,), _ = FI.build_catalogue(later)
    assert a["ref_code"] == b["ref_code"] and b["page_codes"] == ["0000000000", "1111111111"]


def test_dishes_carry_the_tracked_micronutrients_and_every_alias():
    table = {"Calcium": [19.0, "mg"], "Iron": [0.8, "mg"], "Fibre": [3.2, "g"], "Choline": [5.0, "mg"]}
    dishes, _ = FI.build_catalogue([rec(f"n{i}-{i:010d}", f"Name {chr(97 + i)}", table=table) for i in range(20)])
    assert len(dishes) == 1 and dishes[0]["micros_per_100g"] == {"fibre_g": 3.2, "calcium_mg": 19.0, "iron_mg": 0.8}  # untracked Choline left out
    assert len(dishes[0]["aliases"]) == 19  # no cap on search names
