// Mirror of PHONE_WRITES in app/backend/cadence_app/share.py: the only writes a paired phone may make.
// Anchored (method, regex) pairs matched against the whole path (query string ignored); tests/test_phone_writes_sync.py fails if the two lists differ.
// Keep every entry a plain ["METHOD", "regex"] string literal pair (no templates), using only syntax common to Python and JS.
const RULES: [string, string][] = [
  ["POST", "/api/push/(subscribe|unsubscribe|test)"],
  ["PUT", "/api/push/prefs"],
  ["POST", "/api/garmin/sync"],
  ["POST", "/api/activities/[0-9]+/fetch"],
  ["PUT", "/api/journal/[^/]+"],
  ["POST", "/api/journal/behaviours"],
  ["PATCH", "/api/journal/behaviours/[^/]+"],
  ["PUT", "/api/wellbeing/[^/]+"],
  ["DELETE", "/api/wellbeing/[^/]+"],
  ["POST", "/api/strength/(parse|ocr)"],
  ["PUT", "/api/strength/[^/]+"],
  ["DELETE", "/api/strength/[^/]+"],
  ["POST", "/api/planner"],
  ["DELETE", "/api/planner/[^/]+"],
  ["PUT", "/api/reading/[^/]+"],
  ["POST", "/api/gym/(generate|alternatives|swap|convert|preview)"],
  ["POST", "/api/gym/sessions(/build)?"],
  ["PUT", "/api/gym/sessions/[^/]+"],
  ["DELETE", "/api/gym/sessions/[^/]+"],
  ["POST", "/api/gym/sessions/[^/]+/(swap|setting|plan)"],
  ["PUT", "/api/settings/gym"],
  ["POST", "/api/gym/workouts"],
  ["DELETE", "/api/gym/workouts/[^/]+"],
  ["POST", "/api/reading/book/read"],
  ["PUT", "/api/reading/book/position"],
  ["POST", "/api/phases"],
  ["PUT", "/api/phases/[^/]+"],
  ["DELETE", "/api/phases/[^/]+"],
  ["POST", "/api/weight/entries"],
  ["DELETE", "/api/weight/entries/[^/]+"],
  ["POST", "/api/food/(dishes|entries|meals|copy|label|label/text)"],
  ["PATCH", "/api/food/(dishes|entries|meals)/[^/]+"],
  ["POST", "/api/food/dishes/[^/]+/names"],
  ["PATCH", "/api/food/dishes/[^/]+/names/[^/]+"],
  ["DELETE", "/api/food/dishes/[^/]+/names/[^/]+"],
  ["DELETE", "/api/food/(entries|meals)/[^/]+"],
  ["POST", "/api/food/meals/[^/]+/log"],
  ["POST", "/api/food/log"],
  ["POST", "/api/food/entries/bulk"],
  ["POST", "/api/food/entries/[^/]+/restore"],
  ["PUT", "/api/settings/(weather|profile|plan)"],
  ["PUT", "/api/settings/calories"],
  ["POST", "/api/time-off"],
  ["PUT", "/api/time-off/[^/]+"],
  ["DELETE", "/api/time-off/[^/]+"],
];
const PHONE_WRITES = RULES.map(([method, p]) => [method, new RegExp(`^(?:${p})$`)] as const);

export function phoneMayWrite(method: string, path: string): boolean {
  const bare = path.split(/[?#]/)[0];
  const m = method.toUpperCase();
  return PHONE_WRITES.some(([rm, rx]) => rm === m && rx.test(bare));
}
