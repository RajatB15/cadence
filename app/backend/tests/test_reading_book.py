import json

from cadence_app import reading_book as rb
from tests.test_api import MUTATE
from tests.test_reading import make_env


def para(i, n=120):
    return ["p", f"Synthetic paragraph {i}. " + "word " * n]


def write_book(tmp_path, chapters=((" One", 20), ("Two", 6)), **meta):
    root = tmp_path / "reading" / "books" / "demo"
    (root / "chapters").mkdir(parents=True)
    names = []
    for i, (title, n) in enumerate(chapters, 1):
        blocks = []
        for j in range(n):
            if j % 5 == 0:
                blocks.append(["h", f"Heading {i}.{j}"])
            blocks.append(para(j))
        (root / "chapters" / f"{i:02d}.json").write_text(json.dumps({"title": title.strip(), "url": "https://example.org/c", "blocks": blocks}))
        names.append(f"{i:02d}.json")
    (root / "book.json").write_text(json.dumps({"id": "demo", "title": "Synthetic Book", "authors": "Nobody", "url": "https://example.org",
                                                "licence": "CC BY-NC 4.0", "chapters": names, **meta}))


def test_cut_never_splits_a_paragraph_and_keeps_headings_with_their_text():
    blocks = [["h", "Intro"]] + [para(i) for i in range(12)] + [["h", "Next"], para(99, 5)]
    parts = rb._cut(blocks)
    assert [b for p in parts for b in p] == blocks  # nothing lost, nothing reordered
    assert all(p[-1][0] != "h" for p in parts[:-1])  # a heading never ends a part
    assert all(rb._words(p) >= rb.PART_WORDS for p in parts[:-1])
    assert rb._words(parts[-1]) >= rb.PART_WORDS // 3  # a stub tail is folded into the part before it


def test_api_walks_the_book_one_part_at_a_time(tmp_path):
    write_book(tmp_path)
    with make_env(tmp_path, with_cards=False) as client:
        v = client.get("/api/reading/book").json()
        assert v["available"] and v["book"]["licence"] == "CC BY-NC 4.0" and v["current"]["index"] == 0
        total = v["progress"]["parts"]
        assert total > 3 and v["progress"]["parts_done"] == 0 and not v["read_today"] and v["days_read"] == 0
        assert v["current"]["chapter_title"] == "One" and v["chapters"][1]["first"] > 0
        v = client.post("/api/reading/book/read", headers=MUTATE).json()
        assert v["current"]["index"] == 1 and v["progress"]["parts_done"] == 1 and v["read_today"] and v["days_read"] == 1
        v = client.post("/api/reading/book/read", headers=MUTATE).json()
        assert v["days_read"] == 1  # two parts on one day is one day read
        jump = client.put("/api/reading/book/position", json={"part": v["chapters"][1]["first"]}, headers=MUTATE).json()
        assert jump["current"]["chapter_title"] == "Two" and jump["current"]["n"] == 1
        assert client.put("/api/reading/book/position", json={"part": total}, headers=MUTATE).status_code == 404
        assert client.post("/api/reading/book/read").status_code == 403  # needs the header


def test_finishing_the_book_and_a_bad_book(tmp_path):
    write_book(tmp_path, chapters=(("Only", 6),))
    with make_env(tmp_path, with_cards=False) as client:
        total = client.get("/api/reading/book").json()["progress"]["parts"]
        for _ in range(total):
            v = client.post("/api/reading/book/read", headers=MUTATE).json()
        assert v["progress"]["finished"] and v["current"] is None and v["progress"]["minutes_left"] == 0
        assert client.post("/api/reading/book/read", headers=MUTATE).status_code == 404


def test_missing_or_malformed_book_is_unavailable_not_an_error(tmp_path):
    root = tmp_path / "reading" / "books" / "bad"
    root.mkdir(parents=True)
    (root / "book.json").write_text("{not json")
    rb._cache.clear()
    with make_env(tmp_path, with_cards=False) as client:
        assert client.get("/api/reading/book").json() == {"available": False}
