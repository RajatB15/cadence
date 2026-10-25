"""The nutrition-label reader, on synthetic label text (what OCR would return)."""
from cadence_app import food_label as L
from tests.test_foodlog import fenv  # noqa: F401  (fixture)

INDIAN = """Nutritional Information (approx.)
Per 100 g   Per serve (30 g)   %RDA
Energy (kcal)  389  117  6%
Protein (g)  13.5  4.1  7%
Carbohydrate (g)  66  19.8
of which Total Sugars (g)  1.2  0.4
Total Fat (g)  7  2.1
Saturated Fat (g)  1.2  0.4
Dietary Fibre (g)  10  3
Sodium (mg)  4  1.2
"""


def test_two_column_label_reads_both_columns_in_header_order_and_ignores_percent_rda():
    r = L.parse(INDIAN)
    assert r["order"] == ["per_100g", "per_serving"] and r["serving_g"] == 30 and not r["column_assumed"]
    assert r["columns"]["per_100g"] == {"kcal": 389, "protein_g": 13.5, "carbs_g": 66, "sugars_g": 1.2, "fat_g": 7, "sat_fat_g": 1.2, "fibre_g": 10, "sodium_mg": 4}
    assert r["columns"]["per_serving"]["kcal"] == 117 and r["columns"]["per_serving"]["protein_g"] == 4.1
    assert r["issues"] == {"per_100g": [], "per_serving": []} and r["warnings"] == []


def test_kilojoule_and_kcal_on_one_row_takes_kcal_and_salt_becomes_sodium():
    text = "Nutrition facts per 100 g\nEnergy 1650 kJ / 390 kcal\nFat 4,5 g\nof which saturates 0,8 g\nCarbohydrate 70 g\nof which sugars 5 g\nFibre 6 g\nProtein 12 g\nSalt 0,5 g"
    r = L.parse(text)
    c = r["columns"]["per_100g"]
    assert r["order"] == ["per_100g"] and c["kcal"] == 390 and c["fat_g"] == 4.5 and c["sat_fat_g"] == 0.8  # comma decimals, saturates is not fat
    assert c["sodium_mg"] == 200 and c["sugars_g"] == 5 and c["fibre_g"] == 6 and c["protein_g"] == 12


def test_kj_only_is_converted_and_untagged_large_energy_is_flagged():
    assert L.parse("Per 100 g\nEnergy 1674 kJ\nProtein 10 g\nCarbohydrate 60 g\nFat 10 g")["columns"]["per_100g"]["kcal"] == 400
    r = L.parse("Energy 1674\nProtein 10\nCarbohydrate 60\nFat 10")
    assert r["columns"]["per_100g"]["kcal"] == 400 and any("kilojoules" in w for w in r["warnings"])


def test_no_header_assumes_per_100g_first_and_says_so():
    r = L.parse("Energy (kcal) 250 75\nProtein 8 2.4\nCarbohydrate 30 9\nFat 10 3")
    assert r["column_assumed"] and r["order"] == ["per_100g", "per_serving"] and r["columns"]["per_serving"]["kcal"] == 75
    assert any("column headings" in w for w in r["warnings"])
    one = L.parse("Energy 120 kcal\nProtein 4 g\nCarbohydrate 20 g\nFat 3 g")
    assert one["order"] == ["per_100g"] and one["columns"]["per_100g"]["kcal"] == 120


def test_a_misread_digit_is_flagged_and_missing_rows_stay_unknown():
    r = L.parse("Per 100 g\nEnergy (kcal) 3890\nProtein 13 g\nCarbohydrate 66 g\nFat 7 g")
    assert any("above 900" in i for i in r["issues"]["per_100g"])
    r = L.parse("Per 100 g\nEnergy (kcal) 120\nProtein 30 g\nCarbohydrate 30 g\nFat 30 g")
    assert any("add up to about" in i for i in r["issues"]["per_100g"])
    partial = L.parse("Per 100 g\nEnergy (kcal) 120\nProtein 4 g")["columns"]["per_100g"]
    assert partial == {"kcal": 120, "protein_g": 4} and "carbs_g" not in partial  # unknown, not zero


def test_serving_size_forms_and_unrelated_text():
    assert L.serving_size(["Serving size: 45 g"]) == (45, "g")
    assert L.serving_size(["Per serve (30g)"]) == (30, "g")
    assert L.serving_size(["Net weight 500 g"]) == (None, None)
    r = L.parse("Best before 12/2027\nStore in a cool dry place")
    assert r["columns"] == {} and any("No nutrition table" in w for w in r["warnings"])


def test_the_label_endpoints_read_text_and_a_photo(fenv):  # noqa: F811
    import io
    import shutil

    import pytest
    from PIL import Image, ImageDraw, ImageFont

    from tests.test_api import MUTATE
    client, _ = fenv
    r = client.post("/api/food/label/text", json={"text": INDIAN}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["columns"]["per_100g"]["kcal"] == 389
    assert client.post("/api/food/label", content=b"hello", headers={**MUTATE, "Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/food/label", content=b"", headers={**MUTATE, "Content-Type": "image/png"}).status_code == 413
    if not shutil.which("tesseract"):
        pytest.skip("tesseract not installed")
    lines = ["Per 100 g      Per serve (30 g)", "Energy (kcal)   389     117", "Protein (g)     13.5    4.1", "Carbohydrate (g)   66    19.8", "Total Fat (g)   7     2.1"]
    img = Image.new("RGB", (1300, 80 * len(lines) + 40), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=44)
    for i, line in enumerate(lines):
        draw.text((30, 30 + 80 * i), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    got = client.post("/api/food/label", content=buf.getvalue(), headers={**MUTATE, "Content-Type": "image/png"})
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["columns"]["per_100g"]["kcal"] == 389 and body["columns"]["per_serving"]["protein_g"] == 4.1
    assert client.post("/api/food/label", content=b"not an image", headers={**MUTATE, "Content-Type": "image/png"}).status_code == 400
