# Faster food logging without an LLM: design

Status: proposal (2026-11-08). Nothing here is built. Obeys CLAUDE.md: library numbers are estimates calculated from web recipes and always carry a range, nothing from the private `food-data` submodule is copied here, labels are read by Tesseract only, no LLM, no key, no external call unless stated optional.

## 1. Survey and slow points

What exists (read, not changed):

- `foodlog.py`: `log_dish` (servings or grams), `log_quick`, `copy_day`, saved meals (`food_meals`, `food_meal_items`, `log_meal` with a scale), `recent_dish_ids` (30-day count, no weekday or meal awareness), `entry_for_key` plus unique `FoodEntry.client_key` (idempotent create). `FoodDish` has `aliases` and `portions` (JSON `[{unit, grams}]`, first is default), `unit_g`, per-100 g values, `basis` library/estimate/label. `FoodEntry` has `day`, `meal`, `logged_at` (server write time, not eating time), copied nutrition and micros.
- API: `/api/food` (view, plan, notes), `/dishes`, `/entries` (POST/PATCH servings only/DELETE), `/meals*`, `/copy` (whole day only), `/label`, `/label/text`.
- Web: `Food.tsx` (564 lines) opens an add sheet per meal; `lib/food.ts` `searchList` is prefix/contains over name and aliases (no typo tolerance, no transliteration folding, one dish at a time); `FoodLabel.tsx`, `FoodMeals.tsx`.
- Energy card: `analytics/energy.assemble` takes today's `day_summary` (kcal, low, high, protein) and compares it with the projected full-day burn. It has no notion of when food was eaten, so "intake so far" is the day total.

Slow points for "2 idli + sambar + filter coffee" on a phone:

1. Choose meal (4 tabs), then open the sheet: 1 to 2 taps before typing.
2. One dish per search: type, pick, set count, add, repeat (about 12 taps and 3 searches for 3 items).
3. Spelling: "idly", "ildi", "kaapi", "filter kaapi" miss unless the crawl listed that alias. Prefix match fails on "sambhar".
4. Count entry is a stepper from 1 in steps that ignore the dish's natural unit; the last portion you used is forgotten.
5. The same 8 meals recur, but only saved meals are one tap; "usual breakfast" needs manual saving first.
6. Entries have no time, so the day is a list by meal, and the energy card cannot tell breakfast-only from a full day.
7. Offline: a failed POST shows an error and the entry is lost.
8. Packaged food: OCR works but the product is not findable again by barcode, and saving is a separate step.

Target: the typical meal in 1 typed line plus 1 tap (about 6 s), the repeat meal in 1 tap.

## 2. Workflow design

### 2a. Smart entry bar (client, instant, offline)

One input, always at the top of the Food page, `enterKeyHint="done"`. All dishes (about 9,000 compact rows: id, folded name, folded aliases, unit, portions) are already fetched by `/api/food/dishes`; build an in-memory index once (Map by token, plus trigram sets for fuzzy). Parsing and matching are pure TS (`lib/foodParse.ts`, `lib/foodIndex.ts`) and run per keystroke (budget 8 ms).

**Folding** (applied to dish names, aliases and input): lowercase, strip diacritics, `aa->a`, `ee/ii->i`, `oo/uu->u`, `ph->f`, `bh/dh/gh/kh/th->b/d/g/k/t` when followed by a vowel only for matching keys (not display), `w->v`, `z->j`, collapse `yy`, double letters -> single, remove spaces and hyphens, drop trailing `a/e/i` on words of 5+ letters ("sambhar", "sambar", "sambaar" all fold to `sambr`; "idli", "idly", "idlee" to `idli`... the final vowel rule is applied to the key only if the other forms collide, verified by golden tests). Devanagari input is transliterated by a small fixed map (about 60 consonant/vowel glyphs) before folding, so "इडली" finds idli. A fixed built-in synonym list in code (about 150 pairs: kaapi=coffee, chai=tea, dahi=curd=yogurt, chawal=rice, roti=chapati=phulka, bhaji/sabzi, anda=egg, doodh=milk, paneer, atta) is original text, not derived from the food-data repo.

**Ranking** of a candidate dish for token string `q` (higher wins):

```
score = 100*exact_key + 70*prefix_key + 50*word_prefix + 35*alias_exact
      + 25*trigram_jaccard(q,name) (only if >= 0.35) - 8*edit_distance (<= 1 for len<=5, <= 2 otherwise)
      + 18*mine_or_label + 30*frecency_norm        # frecency from section 2b, 0..1
```

Ties: shorter name. The top 5 are shown; the matched alias is shown ("also called kaapi", existing behaviour).

**Multi-item grammar** (EBNF; whitespace-insensitive, case-insensitive):

```
line     := item (SEP item)*
SEP      := "," | "+" | ";" | "\n" | " and " | " & " | " with " | " aur "
item     := qty? unit? "of"? name | name qty_after | name "x" NUM | "x" NUM name
qty_after:= NUM unit? | NUM          # "idli 2", "dal 1.5 katori", "idli x2"
qty      := NUM | WORD | NUM " " FRAC | "half" | "quarter" | "a" | "an" | "one" ... "ten" | "do"|"teen"|"char" (hi: 2,3,4)
NUM      := [0-9]+("."[0-9]+)? | [0-9]+"/"[0-9]+ | "½" "¼" "¾" "⅓" "⅔"
unit     := katori|bowl|cup|piece|pc|pcs|nos|glass|plate|tsp|tbsp|spoon|slice|ladle|g|gm|gram|grams|ml|handful|scoop
```

Rules: a leading integer binds to the item that follows ("2 idli"); a trailing integer binds to the item before it ("idli 2"); in "idli 2 sambar" the number after a name binds backward (nearest-name-left), unless the name is followed by a unit ("sambar 1 katori"). A unit not in the dish's `portions` is mapped through a fixed table (katori 150 ml-ish bowl -> volume tag, cup 240 ml, tsp 5, tbsp 15, glass 250 ml, handful 30 g) only for dishes whose `unit_g` is known, as grams = qty x table x density-assumed 1.0, and the row is flagged "unit converted, rough" with widened spread (+10 points). `g/gm/ml` use grams directly (`ml` assumed 1 g/ml, flagged for non-liquids). Missing quantity = 1 default portion = `portions[0]`, or the user's remembered portion for that dish (2c). `half`=0.5, `quarter`=0.25, `a`/`an`=1.

Result: `ParsedRow {text, dishId|null, candidates[3], qty, unit, servings, grams, flags[]}`. Unmatched tokens become a row with "No match" and two actions: "Quick add kcal" (2e) and "Add as new dish" (existing NewDish).

**Golden tests** (`lib/foodParse.golden.json`, shared fixtures; synthetic names only; expected `servings` against a fixture dish table with `idli` portion `1 piece = 40 g`, `sambar` `1 katori = 150 g`, `roti` `1 piece = 35 g`, `rice cooked` `1 katori = 150 g`, `coffee filter` `1 cup = 150 g`):

| Input | Expected rows |
| --- | --- |
| `idli 2, sambar, coffee` | idli x2 piece; sambar x1 katori; filter coffee x1 cup (alias coffee) |
| `2 idly + sambhar + filter kaapi` | same three (fuzzy/transliteration) |
| `idli x3` / `3x idli` / `three idli` | idli x3 |
| `do roti, dal 1.5 katori` | roti x2; dal x1.5 katori |
| `1/2 cup rice` / `½ katori chawal` | rice cooked 0.5 cup (or katori); chawal alias |
| `rice 200g` / `200 g rice` | rice grams 200 (servings 1.33) |
| `curd 1 glass` | curd, unit glass not in portions: converted 250 g, flag "rough" |
| `a handful almonds` | almonds 30 g, flag rough |
| `paneer bhurji with 2 roti` | paneer bhurji x1 default; roti x2 |
| `idli 2 sambar 1 katori coffee` (no separators) | idli 2; sambar 1 katori; coffee 1 (number-after-name rule) |
| `xyzzy 2` | unmatched row, qty 2, "No match" |
| `` / `,,` | no rows, no error |
| `इडली 2, सांभर` | idli x2; sambar x1 |
| `2` | no rows (a number alone is not an item) |
| `idly 0` / `idli 100` | qty 0 rejected, 100 over `MAX_SERVINGS` flagged "Check amount" |

### 2b. Smart defaults, frecency and usual meals

Meal picker defaults from local time: before 11:00 breakfast, 11:00 to 15:30 lunch, 15:30 to 18:30 snack, after 18:30 dinner (editable in Settings later; stored per day in the timeline, not magic). The entry bar always shows the chosen meal as a tappable pill.

**Frecency** per dish `d` and context: `f(d) = sum over logs i of  w_i * 0.5^(age_days_i / 14) * (1 + 0.5*same_meal_i + 0.3*same_weekday_i)` where `w_i=1`; normalised `frecency_norm = f / max f` over the user's dishes. Half-life 14 days; only dishes logged at least twice get a boost above 0.2.

**Usual for this meal** (suggestion chips, each is one tap, creates all entries for that combo): compute from the last 60 days, per meal slot, the sets of dish ids logged in that slot per day. Cluster by Jaccard >= 0.6, keep clusters with >= 3 days; rank by `count_recent (14 day half-life)` with +0.3 if the weekday matches. A chip shows "Usual breakfast · 3 items · 340 kcal" (a range in the preview sheet) with the typical servings (median per dish). Also fixed chips: "Same as yesterday's <meal>", "Repeat last entry", pinned dishes (new `pinned` flag), and saved meals (first-class chips sorted by `last_used` and meal affinity: the slot where it has been logged most). Chips never exceed 6; horizontally scrollable, 44 px tall.

Tapping a chip adds it to the draft sheet (2d) pre-filled, with an "Add all" primary button, so a mis-tap is one swipe from undone. A "Log immediately" long-press is not provided (non-discoverable).

### 2c. Portion UX

- Row stepper shows the dish's natural unit: `[-] 2 piece [+]`; step 1 for countable units (piece, slice, glass, cup), 0.5 for katori/bowl/plate/ladle, 5 g for grams. The unit label is a tappable chip that cycles through the dish's `portions` plus "grams".
- Kcal and protein beside the row update live as a range ("80 to 110 kcal"), from `spread_pct`.
- Reference line under the stepper: "1 piece is about 40 g" plus the dish's visual hint where known ("about a palm" is NOT invented: only shown if `portions[].unit` carries it).
- Memory: `food_portion_memory(dish_id, servings, unit, grams, n, updated_at)`: after each log, store the last servings; if the user logs a dish with the same amount 3 times, mark it `habitual` and use it as default, otherwise default to `portions[0]` x last servings. Memory is local, never exported, and "Reset portions" lives in Settings.

### 2d. Itemised draft sheet

Typing or tapping chips builds a draft (not saved). One Sheet shows rows, a running total range, and one "Log meal" button. The whole draft posts in one request (`/api/food/log`), with one idempotency key for the batch. Draft survives reload (localStorage, key `cadence.food.draft`, try/catch around access).

### 2e. Quick-add kcal, copy, bulk edit, undo

- Quick add: bar accepts `450 biryani` or `biryani 450` as kcal when the number is >= 50 and has no unit; the row is "kcal 450 (rough)". Spread logic: `spread_pct = 25` default, 35 if eating out (existing `OUT_SPREAD`), shown as "350 to 560 kcal"; protein unknown stays unknown, never zero. "Remember as a dish" checkbox keeps existing behaviour.
- Copy: `POST /api/food/copy` extended with optional `meal` and `entry_ids`, and `target_meal`; "Same as yesterday's lunch" uses it. Copy skips nothing silently and returns the new entries.
- Bulk: timeline has a "Select" mode: multi-select, then Delete, Move to meal, Scale (x0.5/x1.5), Save as meal. Endpoint `POST /api/food/entries/bulk`.
- Undo: every destructive action shows a 6 s "Undone available" toast. Delete is soft: `food_entries.deleted_at` (see section 3); the undo is `POST /api/food/entries/{id}/restore`. A purge job (nightly in the existing scheduler) hard-deletes rows with `deleted_at` older than 7 days. All aggregates filter `deleted_at IS NULL`.

### 2f. What to eat now (deterministic)

Endpoint `GET /api/food/suggest?day&meal`, over the user's own history, saved meals and own/label dishes (library dishes only if logged before; never the whole 9,000). Inputs: remaining kcal range and protein to the day's target band (`analytics/nutrition.food_plan`), micronutrient gaps (fibre, calcium, iron, potassium vs the `nutrients.py` references, shown only with at least 3 logged days). Candidate = a past "usual" combo or saved meal or single dish for this meal slot.

```
fit_kcal  = 1 - clamp(|portion_kcal - kcal_budget_for_slot| / kcal_budget_for_slot, 0, 1)    # budget = remaining / remaining slots
fit_prot  = clamp(portion_protein / protein_gap_for_slot, 0, 1)                                # unknown protein -> 0 and flagged
fit_micro = mean over gaps (top 2) of clamp(candidate_amount / (0.25*reference), 0, 1)        # only known values
score = 0.35*fit_kcal + 0.30*fit_prot + 0.15*fit_micro + 0.20*frecency_norm
```

Each suggestion carries `reasons[]` strings built from the terms that contributed ("About 380 to 470 kcal, you have roughly 600 left", "about 18 g protein, you are 30 g short today", "you have eaten this 6 times this month"), and the caveat line "From your own log. Library values are estimates." No medical claims; with a weight-loss goal it never praises a smaller number, and a day with no log shows suggestions without "left" wording. Minimum data: at least 10 logged entries in history, otherwise the empty state "Log a few meals and your usuals will show up here."

### 2g. Day view

Timeline instead of meal blocks: entries ordered by `eaten_at` (falls back to `logged_at`), grouped under a time header ("08:10 Breakfast"). A sticky summary at the top (Card with `accent=sky`): kcal as a range, kcal left against the energy card's target (same values `energy.assemble` uses, linking to Home), protein with a "30 g to go before 2 pm" prompt only when the plan has a per-meal protein band, fibre prompt after dinner if the day's fibre is below 60% of the WHO reference ("Fibre so far 14 g of 25 g reference"), with counts of how many foods reported each nutrient (existing rule: missing is not zero). Nutrition summary collapses to 6 rows, "More" opens the existing `FoodNutrients`.

### 2h. Offline-first

Service worker already exists (`sw.js`). Add a persisted outbox in IndexedDB (`cadence-food-outbox`): each queued op `{key, method, path, body, created_at}`. The key is a UUID generated once per draft and reused on every retry (`Idempotency-Key` header and `client_key`). On `online` event and app foreground, flush in order, one at a time, stop on 4xx (surface the op as "Needs a look"), retry on 5xx and network errors with backoff. UI: a queued entry renders in the timeline with a small cloud-off icon and "Will sync" text; totals include queued rows labelled "includes 2 waiting". Dishes, meals and the suggestion payload are cached (stale-while-revalidate) so search and chips work offline; label OCR and barcode network features need a connection and say so. Duplicate safety: batch endpoint writes `client_key` as `"{key}:{index}"`, so a replay is a no-op per row; a partially applied batch resumes correctly. Edits and deletes of queued items modify the outbox, never the server.

### 2i. Barcode and packaged food

- Scan: `BarcodeDetector` (formats EAN-13, EAN-8, UPC-A, UPC-E, Code 128) over a `getUserMedia` stream where `'BarcodeDetector' in window`; iOS Safari does not ship it, so the fallback is a numeric manual entry field and "Photograph label". Camera needs HTTPS or localhost; on the phone-share server over plain HTTP the scan button says "Camera isn't available on this connection. Type the code instead."
- Resolution order: (1) the user's own `food_products` by exact `barcode` (one tap logs the saved serving); (2) nothing found: offer "Read the label" (existing Tesseract flow), pre-filled with the barcode; saving stores the product and its barcode so the next scan is one tap. Products are `FoodDish` rows with `basis="label"` plus a `barcode` column (below), not a new table.
- Optional, off by default: Open Food Facts lookup (`https://world.openfoodfacts.org/api/v2/product/{barcode}.json`, keyless, ODbL; user must verify the current terms and send a descriptive User-Agent before enabling). Settings toggle "Look up unknown barcodes online"; consent text: "Only the barcode number is sent to Open Food Facts. No account, no health data." Server-side proxy call (the phone never talks to a third party), one request per scan, 5 s timeout, cache the result (hit or miss) in `food_barcode_cache` for 90 days, then it is saved as the user's own dish only after the user taps Save, marked "From Open Food Facts, community data, may be wrong". No bulk copy. Not part of MVP.

### 2j. Reminders (optional)

New push kind `food` in `push.Notifier.due`: pref `food` default off; sends at most one nudge per meal slot ("Nothing logged for lunch yet. Log it?") at 14:00 and 20:30 local, only if the slot is empty, quiet 22:00 to 08:00, never on days with a time-off period or illness check-in, never mentions weight or restriction. Key `food:{day}:{slot}` makes it once-only, using the existing `_logged` dedupe.

## 3. Data model, migration, API

**Migration `0032_food_quick.py`** (latest is 0031; confirm the next free number when starting). SQLite, additive only:

- `food_entries`: `eaten_at TIME NULL` (local time of eating; `NULL` for older rows, treated as meal default 08:00/13:00/16:30/20:00 in display only, never invented in energy), `deleted_at DATETIME NULL` (indexed), `source VARCHAR(12) DEFAULT 'manual'` (manual | quick | chip | scan | copy).
- `food_dishes`: `barcode VARCHAR(20) NULL` (unique index where not null), `pinned BOOLEAN DEFAULT 0`.
- New `food_portion_memory(dish_id PK FK, servings FLOAT, unit VARCHAR(40), grams FLOAT NULL, n INT, updated_at)`.
- New `food_barcode_cache(barcode PK, found BOOL, payload TEXT NULL, fetched_at)` (only if the optional lookup is built).
- Settings keys (existing settings store): `food.lookup_online`, `food.meal_times`.
- No backfill needed. Energy: `food.day_summary` also returns `by_time` buckets when `eaten_at` is known for all entries; `energy.assemble` uses "intake so far" only when every entry has `eaten_at` <= now, otherwise the existing day total. Rebuild safety: food tables are user data, never touched by Garmin rebuilds.

**Endpoints** (new unless marked):

`POST /api/food/log` (batch draft, idempotent)
```json
{"day":"2026-11-08","meal":"breakfast","eaten_at":"08:10","eating_out":false,"client_key":"7c2f…",
 "items":[{"dish_id":412,"servings":2,"unit":"piece"},
          {"dish_id":97,"grams":150},
          {"name":"Biryani","kcal":450,"protein_g":null,"save_dish":false}],
 "source":"chip"}
```
Response: `{"entries":[<entry_dict + eaten_at, id>], "replayed":false, "saved_dishes":[…]}`. Each item uses `client_key:"{key}:{i}"`. Limit 40 items. Errors 400 `{"detail":"..."}` with the failing index prefix `"Item 2: …"`; the batch is all-or-nothing in one transaction.

`GET /api/food/quick?day=&meal=` returns `{"meal_guess":"breakfast","chips":[{"kind":"usual|yesterday|last|saved|pinned","id":"u:breakfast:3","label":"Usual breakfast","items":[{"dish_id":412,"name":"Idli","servings":2,"unit":"piece","kcal":160,"protein_g":5.6}],"kcal":{"value":340,"low":275,"high":410},"n_days":6}],"memory":{"412":{"servings":2,"unit":"piece"}},"pinned":[412]}`.

`GET /api/food/suggest?day=&meal=` returns `{"status":"ok|insufficient","reasons_note":"…","suggestions":[{"label":"Idli x2 + sambar","items":[…],"kcal":{"value":380,"low":320,"high":450},"protein_g":14,"score":0.71,"reasons":["…"]}]}`; `status:"insufficient"` carries `needs`.

`PATCH /api/food/entries/{id}` (extended body, current `{servings}` still works): `{"servings"?,"grams"?,"meal"?,"eaten_at"?}`.
`POST /api/food/entries/bulk`: `{"ids":[1,2],"action":"delete|move|scale","meal"?,"scale"?}` returns `{"entries":[…],"affected":2}`.
`POST /api/food/entries/{id}/restore`: returns the entry. `DELETE` becomes soft.
`POST /api/food/copy` extended: `{"source":"2026-11-07","target":"2026-11-08","meal":"lunch","target_meal":"lunch","entry_ids":[…]?}`.
`PUT /api/food/dishes/{id}/pin`: `{"pinned":true}`. (PATCH `/dishes/{id}` already allowed; adding `pinned` and `barcode` to `FoodDishPatch` avoids a new route, preferred.)
`GET /api/food/barcode/{code}` returns `{"found":true,"dish":{…}}` or `{"found":false,"online_lookup":"off|available"}`; `POST /api/food/barcode/{code}/lookup` (optional, only when the setting is on).
`POST /api/food/label` unchanged; `FoodDishRequest` gains `barcode`.

**Phone allowlist**: all current food POST/PATCH/DELETE patterns already allow `entries|dishes|meals|copy|label`. Add, in BOTH `share.py PHONE_WRITES` and `phoneWrites.ts RULES` (plain literals, anchored by fullmatch / `^(?:…)$`; `tests/test_phone_writes_sync.py` enforces equality):

```
("POST", r"/api/food/log")
("POST", r"/api/food/entries/bulk")
("POST", rf"/api/food/entries/{_SEG}/restore")      # TS literal: "/api/food/entries/[^/]+/restore"
("POST", r"/api/food/barcode/[0-9]{6,14}/lookup")    # only with the optional lookup
```
Reads (`GET /quick`, `/suggest`, `/barcode/{code}`) need no write rule. Note `("DELETE", "/api/food/(entries|meals)/[^/]+")` already covers soft delete; `entries/bulk` must not collide with `entries/[^/]+` for PATCH/DELETE (POST only, different method pattern: fine, but the route order must declare `/entries/bulk` before `/entries/{id}`). Add a negative test: `PATCH /api/food/entries/bulk` is routed 404/405, not treated as id "bulk".

## 4. UI spec (375 px, ui-system.md tokens)

Layout, top to bottom, 16 px gutters, Card = existing `Card`, no hard-coded hex:

1. `PageHeader` "Food" with date switcher (existing).
2. Sticky summary `Card accent="sky"`: `.numeral` kcal range, "left" line vs energy card, protein bar, tiny nutrition rows. Height under 132 px. Collapses on scroll to one line.
3. Entry bar (56 px, `slate` fill, pill radius): placeholder "Type what you ate: idli 2, sambar, coffee"; trailing icon buttons (44 px) for barcode and label. Beneath it a one-line meal pill "Breakfast · 08:10" opening a small Segmented control + time field.
4. Chip row (horizontal scroll, `.chip .press`, 44 px): usual combos first, then saved meals, pinned, "Yesterday's lunch", "Repeat last". Each chip: bold name, one-line `dim` kcal range.
5. Live parse preview (appears while typing): matched rows as compact lines; tapping a line focuses its stepper; the top fuzzy candidates appear as inline "Did you mean sambar?" chips under unmatched rows.
6. Draft `Sheet` (opens on first row, peeks at 96 px with the total, expands): rows with stepper and unit chip, swipe-left to remove (also a visible 44 px remove button), footer `.pop` button "Log 3 items · 420 to 560 kcal". After logging, an "Undo" toast for 6 s.
7. Timeline: time-grouped entries (`eaten_at`), each a 64 px row; long-press or "Select" opens bulk bar (Delete, Move, Scale, Save as meal). "Suggestion" card near the end: "What fits now" with 2 suggestions, reasons expandable.
8. Existing plan/charts and `FoodNutrients` below, unchanged.

States and microcopy:

- Loading: `Skeleton` shaped as summary card + chip row + 3 timeline rows. Search is usable once the dish list is cached.
- Empty day: `EmptyCard` "Nothing logged yet today. Type what you ate above, or tap a usual." (no streak or shame language; no "you missed").
- First use, no history: chips replaced by "Your usual meals show up here after you've logged a few."
- No match: "No dish called “xyz”. Add calories only, or save it as a new dish."
- Error: `ErrorBlock` with Retry; failed log keeps the draft.
- Offline: banner "Offline. Entries are saved on this phone and will sync." Queued rows show "Will sync".
- Unsupported: no BarcodeDetector -> button shows "Type the barcode"; no Tesseract (HTTP 501) -> "Reading photos isn't available here. Type the numbers in."; no camera permission -> "Camera blocked. You can type the code."
- Estimate wording everywhere: kcal always a range; library rows tagged "Estimate from a web recipe"; footer "Amounts are estimates, usually within 10 to 25%."
- Undo wording: "Removed 2 items. Undo".
- Accessibility: all targets >= 44 px, steppers have aria labels ("More idli"), live region announces total changes politely, reduced-motion respected.

## 5. Work breakdown

**Workstream A: backend** (files: `models.py`, new `migrations/versions/0032_food_quick.py`, new `food_quick.py` (frecency, usuals clustering, suggest ranking, portion memory, bulk), `foodlog.py` (eaten_at, soft delete, batch log, copy options), `main.py` food routes + request models, `share.py`, `analytics/nutrition.py`/`energy.py` read of `by_time` (pure functions kept pure), `push.py` (food reminder), `food_barcode.py` (optional), tests `tests/test_food_quick.py`, `tests/test_foodlog.py`, `tests/test_phone_writes_sync.py`, `tests/test_push.py`, plus `app/web/src/lib/phoneWrites.ts` (one-line mirror owned by A, the only web file A touches).

**Workstream B: web** (files: `pages/Food.tsx`, new `components/food/*` (EntryBar, Chips, DraftSheet, PortionStepper, Timeline, SuggestCard, BarcodeScan), `FoodLabel.tsx`, `FoodMeals.tsx`, `lib/food*.ts` (`foodParse.ts`, `foodIndex.ts`, `foodOutbox.ts`, golden JSON), `lib/api.ts`, `lib/types.ts`, `sw.js` cache entries, Vitest tests). B mocks the endpoints against the JSON in section 3 until A lands.

Order (MVP first):

1. MVP-1 (B alone): parser, index, typo/transliteration search, itemised draft sheet posting existing `/api/food/entries` one by one with idempotency keys, steppers with natural units. No backend change. Ships the biggest win.
2. MVP-2 (A): migration, `eaten_at`, `/api/food/log` batch, soft delete + restore, bulk; B switches to batch and adds undo and timeline.
3. MVP-3 (A+B): `/api/food/quick` chips (usual, yesterday, last, saved, pinned), portion memory.
4. Then: offline outbox (B) with batch idempotency (A already done), energy `by_time` (A), suggestions (A+B), barcode own-products (A+B), reminders, optional online lookup last.

Test plan: pytest for frecency math (hand-computed tables with synthetic logs), cluster of usuals, batch idempotency (replay same key twice, partial replay), soft-delete exclusion from `day_summary`/`view`/energy, migration up/down on an empty vault copy, phone-write sync test plus negative cases, suggestions determinism and the `insufficient` path, barcode uniqueness. Vitest for the golden parser table, folding, ranking, outbox (fake IndexedDB: order, backoff, 4xx stop, dedupe). Browser check at 375 and 1024 px on synthetic fixtures (demo connector), offline toggle in devtools, reduced motion.

Risks:

- Fuzzy over-matching logs the wrong dish: mitigated by always showing the matched dish and a range before saving, and never auto-saving on typing.
- Grammar ambiguity ("idli 2 sambar 1"): bind rules are tested; row-level steppers fix errors in a tap.
- Unit conversion (glass, handful) is crude: flagged "rough" with wider spread.
- Library data are web-recipe estimates (known -13% to -24% against IFCT checks); wording stays "estimate".
- Soft delete touches every aggregate: one shared `active_entries()` query helper and a test that greps for raw `FoodEntry` selects.
- `eaten_at` null for old rows: energy never infers a time.
- iOS lacks BarcodeDetector and plain-HTTP share has no camera: typed code and label photo remain the supported path.
- Dish list size (about 9,000) at startup on phone: send compact fields only and cache; measure index build time (< 150 ms target).
- Frecency can loop users into repeating one meal; suggestions include a variety term only if requested, and nothing is framed as good or bad.
- Public repo: golden fixtures and synonyms are hand-written, no catalogue content is committed.

## 6. Implemented payload (backend, 2026-11-08)

The backend workstream is built; this section is authoritative where it differs from section 3. Every response keeps its old keys; new ones are additive.

**Entry dict** (everywhere an entry appears) gains `eaten_at` ("HH:MM" or null), `eaten_at_est` (true on rows that existed before migration 0032: their `eaten_at` is a meal default for ordering, never a real time), `source` (manual|quick|chip|scan|copy) and `deleted_at` (null for live entries). Times are the user's local wall clock. When `eaten_at` is omitted on a write: today means now (user's zone), another day means null.

**Dish dict** gains `barcode` (digits or null) and `pinned`. **Meal dict** gains `pinned`.

`POST /api/food/log` as in section 3, with these details. Body: `{day, meal, items[1..40], eaten_at?, eating_out?, client_key?, source?}`; item = `{dish_id, servings?|grams?, unit?}` or `{name, kcal, protein_g?, carbs_g?, fat_g?, save_dish?}` (`save_dish` defaults to false here). Key: `Idempotency-Key` header or `client_key`, at most 56 characters; item i is stored as `"{key}:{i}"`. Response `{entries, replayed, saved_dishes}`. A replay returns the entries already written (`replayed: true`, nothing added, removed ones omitted); a partly written batch is completed. 400 `{"detail": "Item 2: ..."}` writes nothing. `source` defaults to `manual` for dishes and `quick` for kcal items.

`POST /api/food/entries` also accepts `eaten_at`, `unit`, `source`. `PATCH /api/food/entries/{id}` body: any of `servings`, `grams` (entries with a weight), `meal`, `eaten_at` (null clears); `{servings}` alone still works; empty body is 400; a removed entry is 404.

`DELETE /api/food/entries/{id}` is soft (`{"deleted": id}`; 404 if missing or already removed). `POST /api/food/entries/{id}/restore` returns the entry. Removed entries are hard-deleted after 7 days by the scheduler tick. `POST /api/food/entries/bulk`: `{ids[1..100], action: delete|restore|move|scale, meal?, scale?}` returns `{entries, affected}` (deleted entries are returned so the client can offer undo; `restore` is an extra action for bulk undo). All-or-nothing, 400 if any id is gone. `PATCH /entries/bulk` is a 422 (the id is not an integer), never an edit.

`POST /api/food/copy`: `{source, target, meal?, target_meal?, entry_ids?}` returns `{copied, entries}` (`copied` unchanged). Entries that are gone give 400, not a silent skip. Copies have `source: "copy"`.

`GET /api/food/quick?day=&meal=` returns `{meal_guess, chips[<=6], memory{dish_id: {servings, unit, grams, habitual}}, pinned[dish ids], pinned_meals[meal ids]}`. A chip is `{kind: usual|yesterday|saved|pinned|last, id, label, items[{dish_id|null, name, servings, unit, kcal, protein_g|null}], kcal{value, low, high}, n_days? (usual only)}`; order is usual (max 2), yesterday, saved (max 2, pinned first), pinned dishes (max 2), last; ids `u:{meal}:{k}`, `y:{meal}`, `m:{meal id}`, `p:{dish id}`, `l:{entry id}`. Item with `dish_id: null` is a one-off: log it as `{name, kcal, protein_g}`. `meal` defaults to the guess (before 11:00 breakfast, to 15:30 lunch, to 18:30 snack, else dinner; for a past day, dinner).

`GET /api/food/suggest?day=&meal=` returns `{status: ok|insufficient, needs[], day, meal, reasons_note, suggestions[<=3]}`; suggestion = `{label, source: usual|saved|dish, items[], kcal{value, low, high}, protein_g|null, score, parts{fit_kcal, fit_prot, fit_micro, habit (null = term not used)}, reasons[], times, facts{budget_kcal, remaining_kcal, protein_gap_g}}`. `insufficient` when fewer than 10 logged foods in 90 days (empty-state text in `reasons_note`) or no candidates for the slot.

**Barcode** (your own products only; no online lookup, Open Food Facts skipped): `GET /api/food/barcode/{code}` returns `{found: true, dish, portion}` or `{found: false, online_lookup: "off"}` (400 unless 6 to 14 digits). Save a product by `POST /api/food/dishes` with `basis: "label"` and `barcode`, or attach a code with `PATCH /api/food/dishes/{id} {barcode}` (null clears; another dish owning it is 400 with its name). `PATCH /dishes/{id}` also takes `pinned`; `PATCH /meals/{id}` takes `name?` and `pinned?`. There is no `/pin` route and no `/lookup` route (so no phone rule for them). `DELETE /api/food/portion-memory` resets remembered portions (Mac only).

**Energy card**: `energy.eaten` is unchanged except an additive `later: {entries, kcal}` (only when present). For today, entries with a real `eaten_at` after the user's current local time are not in "eaten so far"; entries with no time, or only a default (`eaten_at_est`), count as before. Removed entries count nowhere.

**Phone allowlist** adds exactly: `POST /api/food/log`, `POST /api/food/entries/bulk`, `POST /api/food/entries/[^/]+/restore`.

## 7. Implemented payload (personal names and search)

Backend built (migration `0033`, table `food_user_alias`). Every existing response keeps its keys; the additions are additive.

**Dish dict** (every place a dish appears: `/api/food/dishes`, add/patch responses, search) gains:
`my_names`: `[{id, name, preferred, use_count, last_used_at (ISO or null)}]` ordered by id; `display_name`: the preferred own name, else the dish `name`; `also`: the library/original `name` when a preferred own name is shown, else `null`. `name` itself never changes (it is what a log entry stores). Show `display_name`, and `also: <name>` underneath when `also` is not null.

**Names** (phone-writable, `X-Cadence-Request` header like every write):
- `POST /api/food/dishes/{id}/names` body `{name, preferred?: false}` returns `{dish, alias}` with `alias = {id, name, preferred, use_count, last_used_at}`.
- `PATCH /api/food/dishes/{id}/names/{alias_id}` body `{name?, preferred?}` (at least one) returns `{dish, alias}`. `preferred: true` clears the flag on the dish's other names; `false` returns to the library name.
- `DELETE /api/food/dishes/{id}/names/{alias_id}` returns `{deleted: alias_id, dish}`.
- Rules: the name is trimmed with inner whitespace collapsed, 1 to 60 characters, no control characters, must contain a letter or digit, must differ (after folding) from the dish's own name and from its other names, at most 12 per dish. 400 `{"detail": "..."}` with a readable sentence; 404 for an unknown dish or a name that belongs to another dish; 422 if `name` is empty or over 200 characters.
- Your names survive a catalogue re-seed: a library dish's names also keep its `ref_code` and re-attach to the new row (also across page-code merges). A dish that is dropped from the catalogue keeps its names waiting (not shown) until it returns.

**Search**: `GET /api/food/search?q=&limit=20` (limit 1..50; empty `q` returns no results) returns
`{"query": "uppitu", "results": [{"dish": {dish dict}, "score": 0.75, "match": {"kind": "my_name" | "name" | "alias", "text": "Uppittu", "alias_id": 4 | null}}]}`, best first. `alias_id` is set only for `kind: "my_name"`; pass it back as `via_alias` when logging. Matches your names, the dish name and library `aliases`; folds case, diacritics, Devanagari and other Indic scripts, and spelling variants (chawal/chaval, aloo/alu, paneer/panir, dosa/dosai); word order is ignored; typos within 1 to 2 edits; prefixes work while typing. Your names rank first when they match well (score 0.8 or more); frecency and how often you chose a name break ties. Only active dishes are searched. Show `match.text` as "matched: ..." when `kind` is not `name`.

**Counting your name**: `POST /api/food/entries` and each item of `POST /api/food/log` accept optional `via_alias` (alias id of that dish; ignored if it is not that dish's name; a replayed batch does not count again). It raises `use_count` and sets `last_used_at`.

**Phone allowlist** adds exactly: `POST /api/food/dishes/[^/]+/names`, `PATCH` and `DELETE /api/food/dishes/[^/]+/names/[^/]+`.
