// Mirror of PHONE_WRITES in app/backend/cadence_app/share.py: the only writes a paired phone may make.
// Anchored (method, regex) pairs matched against the whole path (query string ignored); keep the two lists identical.
const SEG = "[^/]+";
const RULES: [string, string][] = [
  ["POST", "/api/push/(subscribe|unsubscribe|test)"],
  ["PUT", "/api/push/prefs"],
  ["POST", "/api/garmin/sync"],
  ["PUT", `/api/journal/${SEG}`],
  ["POST", "/api/journal/behaviours"],
  ["PATCH", `/api/journal/behaviours/${SEG}`],
  ["PUT", `/api/wellbeing/${SEG}`],
  ["DELETE", `/api/wellbeing/${SEG}`],
  ["POST", "/api/strength/(parse|ocr)"],
  ["PUT", `/api/strength/${SEG}`],
  ["DELETE", `/api/strength/${SEG}`],
  ["POST", "/api/planner"],
  ["DELETE", `/api/planner/${SEG}`],
  ["PUT", `/api/reading/${SEG}`],
  ["POST", "/api/phases"],
  ["PUT", `/api/phases/${SEG}`],
  ["DELETE", `/api/phases/${SEG}`],
  ["POST", "/api/weight/entries"],
  ["DELETE", `/api/weight/entries/${SEG}`],
  ["POST", "/api/food/(dishes|entries|meals|copy|label|label/text)"],
  ["PATCH", `/api/food/(dishes|entries|meals)/${SEG}`],
  ["DELETE", `/api/food/(entries|meals)/${SEG}`],
  ["POST", `/api/food/meals/${SEG}/log`],
  ["PUT", "/api/settings/(weather|profile|plan)"],
  ["POST", "/api/time-off"],
  ["PUT", `/api/time-off/${SEG}`],
  ["DELETE", `/api/time-off/${SEG}`],
];
const PHONE_WRITES = RULES.map(([method, p]) => [method, new RegExp(`^(?:${p})$`)] as const);

export function phoneMayWrite(method: string, path: string): boolean {
  const bare = path.split(/[?#]/)[0];
  const m = method.toUpperCase();
  return PHONE_WRITES.some(([rm, rx]) => rm === m && rx.test(bare));
}
