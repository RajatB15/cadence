"""Your own dish names (my names) and the forgiving food search. Synthetic data only."""

import pytest

from cadence_app import foodlog as F
from cadence_app.analytics import foodsearch as S
from tests.test_api import MUTATE
from tests.test_foodlog import fenv, dishes_of, synthetic_dish, write_catalogue  # noqa: F401

def add(client, dish_id, name, preferred=False):
    return client.post(f"/api/food/dishes/{dish_id}/names", json={"name": name, "preferred": preferred}, headers=MUTATE)


# --- folding and golden queries

@pytest.mark.parametrize("a,b", [
    ("chawal", "chaval"), ("aloo", "alu"), ("paneer", "panir"), ("dosa", "dosai"), ("Café", "cafe"),
    ("आलू", "aloo"), ("पनीर", "paneer"), ("चावल", "chawal"), ("कोथिंबीर", "kothimbir"), ("दाल", "daal"), ("Poha", "pohaa"),
    ("ગાજર", "gajar"), ("பனீர்", "panir"),
])
def test_folding_meets_spelling_variants(a, b):
    ta, tb = S.fold(a), S.fold(b)
    assert ta == tb or S.distance(ta, tb, 1) <= 1, (ta, tb)


POOL = [
    {"id": 1, "name": "Paneer bhurji", "aliases": ["Cottage cheese scramble"], "my_names": []},
    {"id": 2, "name": "Steamed rice", "aliases": ["Chawal", "Bhaat"], "my_names": []},
    {"id": 3, "name": "Aloo paratha", "aliases": ["Potato flatbread"], "my_names": []},
    {"id": 4, "name": "Masala dosa", "aliases": [], "my_names": []},
    {"id": 5, "name": "Coriander chutney", "aliases": [], "my_names": [{"id": 9, "name": "Kothimbir chutney", "use_count": 0}]},
    {"id": 6, "name": "Plain curd", "aliases": [], "my_names": [{"id": 10, "name": "दही", "use_count": 3}]},
    {"id": 7, "name": "Rice pudding", "aliases": [], "my_names": []},
]


@pytest.mark.parametrize("query,top", [
    ("chaval", 2), ("bhat", 2), ("चावल", 2), ("panir burji", 1), ("bhurji paneer", 1), ("alu parata", 3), ("आलू पराठा", 3),
    ("dosai", 4), ("masla dosa", 4), ("kothimbir", 5), ("कोथिंबीर", 5), ("dahi", 6), ("दही", 6), ("curd", 6), ("cottage", 1),
])
def test_golden_queries(query, top):
    found = S.rank(query, POOL)
    assert found and found[0]["id"] == top, found


def test_no_match_and_all_tokens_required():
    assert S.rank("zzzz", POOL) == []
    assert S.rank("paneer pizza", POOL) == []
    assert S.rank("", POOL) == []


def test_my_names_rank_first_even_against_an_exact_library_name():
    pool = [{"id": 1, "name": "Rice pudding", "aliases": [], "my_names": []},
            {"id": 2, "name": "Kheer", "aliases": [], "my_names": [{"id": 1, "name": "rice pudding", "use_count": 0}]}]
    assert [r["id"] for r in S.rank("rice pudding", pool)] == [2, 1]
    assert S.rank("rice pudding", pool)[0]["kind"] == "my_name"


def test_frecency_and_own_use_break_ties():
    pool = [{"id": 1, "name": "Dal fry", "aliases": [], "my_names": []}, {"id": 2, "name": "Dal tadka", "aliases": [], "my_names": []}]
    assert [r["id"] for r in S.rank("dal", pool)] == [1, 2]  # shorter name first
    assert [r["id"] for r in S.rank("dal", pool, {2: 1.0})] == [2, 1]
    pool2 = [{"id": 1, "name": "Roti", "aliases": [], "my_names": [{"id": 1, "name": "phulka", "use_count": 0}]},
             {"id": 2, "name": "Roti plain", "aliases": [], "my_names": [{"id": 2, "name": "phulka", "use_count": 8}]}]
    assert S.rank("phulka", pool2)[0]["id"] == 2


def test_typo_bounds():
    assert S.distance("paneer", "panner", 1) == 1 and S.distance("abcd", "abdc", 1) == 1 and S.distance("abc", "xyz", 2) == 3
    assert S.token_score("dal", "dan") == 0.0  # short tokens get no typo tolerance


# --- API

def test_add_validate_and_dedupe(fenv):
    client, _ = fenv
    pid = dishes_of(client)["Paneer"]["id"]
    r = add(client, pid, "  Panir   ji ")
    assert r.status_code == 200 and r.json()["alias"]["name"] == "Panir ji"
    d = dishes_of(client)["Paneer"]
    assert [n["name"] for n in d["my_names"]] == ["Panir ji"] and d["display_name"] == "Paneer" and d["also"] is None
    assert add(client, pid, "panir JI").status_code == 400  # same folded form
    assert add(client, pid, "paneer").status_code == 400  # its own name
    assert add(client, pid, "").status_code in (400, 422) and add(client, pid, " ").status_code == 400
    assert add(client, pid, "x" * 61).status_code == 400 or add(client, pid, "x" * 61).status_code == 422
    assert add(client, pid, "bad\x07name").status_code == 400
    assert add(client, 999999, "x").status_code == 404
    for i in range(11):
        assert add(client, pid, f"name{chr(97 + i)}x").status_code == 200
    assert add(client, pid, "onetoomany").status_code == 400
    assert client.post(f"/api/food/dishes/{pid}/names", json={"name": "q"}).status_code == 403  # needs the CSRF header


def test_preferred_display_and_delete(fenv):
    client, _ = fenv
    pid = dishes_of(client)["Upma"]["id"]
    a = add(client, pid, "Uppittu").json()["alias"]["id"]
    b = add(client, pid, "Rava upma", preferred=True).json()["alias"]["id"]
    d = dishes_of(client)["Upma"]
    assert d["display_name"] == "Rava upma" and d["also"] == "Upma" and d["name"] == "Upma"
    r = client.patch(f"/api/food/dishes/{pid}/names/{a}", json={"preferred": True}, headers=MUTATE).json()
    assert r["dish"]["display_name"] == "Uppittu" and [n["preferred"] for n in r["dish"]["my_names"]] == [True, False]
    r = client.patch(f"/api/food/dishes/{pid}/names/{a}", json={"preferred": False}, headers=MUTATE).json()
    assert r["dish"]["display_name"] == "Upma"
    assert client.patch(f"/api/food/dishes/{pid}/names/{a}", json={}, headers=MUTATE).status_code == 400
    assert client.patch(f"/api/food/dishes/{pid}/names/{b}", json={"name": "uppittu"}, headers=MUTATE).status_code == 400
    assert client.patch(f"/api/food/dishes/{pid}/names/{b}", json={"name": "Rava"}, headers=MUTATE).json()["alias"]["name"] == "Rava"
    out = client.delete(f"/api/food/dishes/{pid}/names/{a}", headers=MUTATE).json()
    assert out["deleted"] == a and [n["name"] for n in out["dish"]["my_names"]] == ["Rava"]
    assert client.delete(f"/api/food/dishes/{pid}/names/{a}", headers=MUTATE).status_code == 404
    other = dishes_of(client)["Paneer"]["id"]
    assert client.delete(f"/api/food/dishes/{other}/names/{b}", headers=MUTATE).status_code == 404  # not that dish's name


def test_search_endpoint_and_via_alias_ranking(fenv):
    client, _ = fenv
    ds = dishes_of(client)
    pid, uid = ds["Paneer"]["id"], ds["Upma"]["id"]
    alias = add(client, uid, "Uppittu").json()["alias"]["id"]
    res = client.get("/api/food/search", params={"q": "uppitu"}).json()["results"]
    assert res[0]["dish"]["id"] == uid and res[0]["match"] == {"kind": "my_name", "text": "Uppittu", "alias_id": alias}
    assert client.get("/api/food/search", params={"q": "cottage chese"}).json()["results"][0]["dish"]["id"] == pid  # library alias + typo
    assert client.get("/api/food/search", params={"q": "  "}).json()["results"] == []
    body = {"day": "2026-10-22", "meal": "breakfast", "dish_id": uid, "servings": 1, "via_alias": alias}
    assert client.post("/api/food/entries", json=body, headers=MUTATE).status_code == 200
    batch = {"day": "2026-10-22", "meal": "lunch", "items": [{"dish_id": uid, "via_alias": alias}, {"dish_id": pid, "via_alias": alias}], "client_key": "k1"}
    assert client.post("/api/food/log", json=batch, headers=MUTATE).status_code == 200
    assert client.post("/api/food/log", json=batch, headers=MUTATE).json()["replayed"] is True  # a replay does not count again
    n = dishes_of(client)["Upma"]["my_names"][0]
    assert n["use_count"] == 2 and n["last_used_at"]  # the alias on another dish (paneer) was ignored


# --- catalogue re-seed keeps your names

def reseed(client, fd, extra):
    write_catalogue(fd, [synthetic_dish(i) for i in range(110)] + extra)
    F._APPLIED.clear()
    return {d["name"]: d for d in client.get("/api/food/dishes").json()["dishes"]}


def test_names_survive_catalogue_reseed(fenv):
    client, fd = fenv
    ds = dishes_of(client)
    pid, uid, old_id = ds["Paneer"]["id"], ds["Upma"]["id"], ds["Paneer"]["id"]
    add(client, pid, "Panir ji", preferred=True)
    add(client, uid, "Uppittu")
    mine = client.post("/api/food/dishes", json={"name": "My khichdi", "unit": "bowl", "kcal": 200}, headers=MUTATE).json()["id"]
    add(client, mine, "Khichri")
    # 1. A rebuilt catalogue drops Paneer: the library row is deleted, your name waits with its code (and is not shown or lost)
    after = reseed(client, fd, [synthetic_dish(201, "Upma")])
    assert "Paneer" not in after
    assert [n["name"] for n in after["Upma"]["my_names"]] == ["Uppittu"] and [n["name"] for n in after["My khichdi"]["my_names"]] == ["Khichri"]
    # 2. Paneer comes back (a new row, a new id): the name is re-attached, preference included
    after = reseed(client, fd, [synthetic_dish(200, "Paneer", grams=50, kcal100=265), synthetic_dish(201, "Upma")])
    paneer = after["Paneer"]
    assert [(n["name"], n["preferred"]) for n in paneer["my_names"]] == [("Panir ji", True)]
    assert paneer["display_name"] == "Panir ji" and paneer["also"] == "Paneer"
    assert client.get("/api/food/search", params={"q": "panirji"}).json()["results"][0]["dish"]["id"] == paneer["id"]
    # 3. A rename in the catalogue (same code) keeps the row and the names
    after = reseed(client, fd, [synthetic_dish(200, "Paneer cubes", grams=50, kcal100=265), synthetic_dish(201, "Upma")])
    assert [n["name"] for n in after["Paneer cubes"]["my_names"]] == ["Panir ji"]


def test_names_follow_a_page_code_merge(fenv):
    client, fd = fenv
    uid = dishes_of(client)["Upma"]["id"]
    add(client, uid, "Uppittu")
    # page-code merge: the dish is stored under an earlier page code and the catalogue now lists it under a new code
    write_catalogue(fd, [synthetic_dish(i) for i in range(110)] + [{**synthetic_dish(250, "Upma"), "page_codes": ["code00201"]}])
    F._APPLIED.clear()
    after = {d["name"]: d for d in client.get("/api/food/dishes").json()["dishes"]}
    assert [n["name"] for n in after["Upma"]["my_names"]] == ["Uppittu"]
