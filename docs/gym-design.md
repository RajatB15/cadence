# Gym planner

Plan strength and conditioning sessions beyond "name a class": build them from a library of exercises with a short how-to for each,
mix running and exercises in any order (Hyrox-style), swap any exercise for an easier, harder or different one, and keep a gym version and
a no-equipment home version of the same idea. Everything is also reachable from the Claude connector (rule: every feature has connector tools).

## Is the existing exercise dictionary a good baseline?

Partly. `analytics/exercises.json` (288 names, aliases, a movement pattern each) is good at what it was built for: recognising names in a
pasted class and sorting them into movement patterns. It has no equipment, no difficulty, no how-to, no easier/harder links, and a flat
"loaded" flag, so it cannot plan, swap or guide. It stays as the parser's dictionary. The planner gets its own richer library
(`analytics/gym_library.json`) whose patterns are the same fourteen categories, so everything a session contains still parses, labels and
counts toward the weekly movement-pattern notes. A test checks that every library exercise resolves to its own pattern through the parser.

## Library

One record per exercise, written for this project (own words; general technique cues of the kind in NSCA *Essentials of Strength
Training and Conditioning* and ACSM guidance, not copied from any source or third-party dataset):

- `id`, `name`, `aliases`, `pattern` (squat, hinge, lunge, push, pull, carry, core, plyometric, olympic, calves, hips, cardio, drill, mobility)
- `family` and `level` 1-5: the progression ladder. Easier = same family, level - 1; harder = level + 1. A family is "the same idea at different difficulty"
  (push-up ladder: wall, incline, knee, full, feet-elevated, archer, one-arm).
- `equipment`: what you need (any of `bodyweight, dumbbell, kettlebell, barbell, bench, rack, pullup_bar, cable, machine, band, box, sled, skierg,
  rower, treadmill, medicine_ball, sandbag, rings, bike`). Bodyweight needs nothing.
- `muscles` primary/secondary, `unit` (reps, time, distance, calories), `cues` (how to do it, in order), `mistakes`, optional `tip`, `tags`
  (`hyrox`, `conditioning`, `mobility`, `warmup`).
- Guides are technique, not medical advice: no claims about injury or rehabilitation, "stop if sharp pain", start light.

## Settings: gym vs home

A session has `setting`: `gym` (everything) or `home` (only the equipment you say you own; default none, i.e. bodyweight). The home equipment list is
one setting. Building, swapping and suggesting only offer exercises whose equipment you have for that setting. Switching a session to home
swaps each exercise for its closest available one and tells you which were swapped and why.

## Sessions: flexible steps

A session is an ordered list of steps; steps nest so any format works:

- `exercise` step: exercise, sets, then reps or seconds or metres or calories, load (kg, "bodyweight", or empty), rest seconds, note.
- `cardio` step: run, row, ski, bike or walk with distance (m), or time, optional target pace/effort note.
- `rest` step: seconds.
- `group` step: `rounds` and `steps` inside (a circuit, an EMOM block, or Hyrox's eight times run + station). Groups can hold cardio and exercises mixed.

Formats are only labels and generators over this one structure: `straight` (sets), `circuit`, `hybrid` (run + lift intervals), `hyrox`. Hyrox:
8 rounds of a 1 km run then a station in the fixed order SkiErg 1000 m, sled push 50 m, sled pull 50 m, burpee broad jumps 80 m, rowing 1000 m,
farmers carry 200 m, sandbag lunges 100 m, wall balls 100 reps. Loads differ by division and the public sources disagree, so the template leaves
loads blank for you to set from the current official rulebook; a practice template does half the rounds at easier loads.

## Swapping

`swap(step, direction)` with direction `easier`, `harder` or `different`:
easier/harder walk the family ladder within available equipment, falling back to the nearest level in the same pattern with overlapping primary
muscles; `different` keeps the pattern and muscles but changes family (and says so). Candidates are scored transparently (same family, muscle overlap,
level distance, equipment, not already in the session) and the top few are shown with the reason; nothing changes until one is picked. The prescription
is kept unless the unit changes (reps to seconds) in which case a sensible default for the new exercise is used.

## Generating

Rule-based, no model: a template (full body, upper, lower, push, pull, legs and core, home no-equipment full body, Hyrox, Hyrox practice, run-lift
hybrid) plus minutes, setting and level picks exercises per movement pattern deterministically for a given seed, within the equipment you have, with
the usual structure (warm-up, main, accessory, core or finisher) and sets/reps by goal (strength 3-5 x 3-6, hypertrophy 3-4 x 8-12, endurance 2-3 x 12-20).
Level is yours to set; there is no load recommendation (we don't know your 1RM): the load field is left for you, and last-used loads are not built yet.

## Planning

A gym session can be put on a day. It becomes an ordinary planned `strength` session (so the week, plan-vs-actual, the class label on the matched
Garmin activity and the weekly movement-pattern notes keep working) with the session written out as text the existing parser reads, and a link back.
The planned copy is a snapshot: later edits to the saved session don't rewrite days already planned. Not pushed to Garmin (strength steps aren't supported there).

## Connector rule (applies to every future feature)

Every user-facing feature that stores, plans or reads user data ships with Claude connector tools in the same change, in the right switch group:
reads always available, `log` writes for daily logging, `plan` writes for plans/goals/sessions. `tests/test_connector_coverage.py` fails when a new
`/api` route is neither covered by a tool nor listed in `tests/connector_exempt.txt` with a reason, so it cannot be forgotten.

## Not built (first slice)

Workout logging of actual sets and loads, progression suggestions from past loads, per-exercise video or images, supersets with timers,
Garmin strength workout push, RPE tracking. Hyrox division loads are the user's to fill.
