import type { FoodBarcodeResult, FoodBatchResult, FoodBulkBody, FoodQuick, FoodSuggest } from "./foodTypes";
import type { LogItem } from "./foodRow";
import type { CustomSpec } from "./customSession";
import { phoneMayWrite } from "./phoneWrites";
import type {
  CalorieSettings,
  CalorieSettingsView,
  ImproveReport,
  ImproveSummary,
  ActivityDetail,
  PlanSettings,
  SeriesTrend,
  TimeOffBody,
  TimeOffView,
  TrainingTrend,
  Behaviour,
  JournalView,
  ReadingView, BookView,
  PlanOption,
  Review,
  BodyProfile,
  WeightEntries,
  FoodCrawlProgress,
  FoodDish,
  FoodDishInput,
  FoodEntryInput,
  FoodLabelRead,
  FoodSavedMeal,
  FoodView,
  Meal,
  BackupStatus,
  GarminConnectStatus,
  PlannedSessionView,
  PlannerWeek,
  Sport,
  StrengthLabel,
  ActivityItem,
  ActivityLog,
  EventDetail,
  HabitOption,
  PhaseBody,
  PhaseDetail,
  PhaseSummary,
  EventSummary,
  CredentialStatus,
  DayDetail,
  GarminStatus,
  GoalDistance,
  GoalInput,
  GoalsResponse,
  GoalView,
  Insights,
  Outcomes,
  TrainingMode,
  WellbeingEntry,
  LabAccuracy,
  LabModel,
  LabRoutes,
  LabWhatIf,
  MetricSeries,
  Overview,
  PushStatus,
  ScoreReport,
  ShareStatus,
  SourceInfo,
  SyncRun,
  TrainingGoal,
  VaultItemMeta,
  WhatIfResult,
  WeightResponse,
} from "./types";

export type ApiErrorKind = "http" | "offline" | "timeout" | "parse" | "aborted";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public kind: ApiErrorKind = "http",
  ) {
    super(message);
  }
}

/** Default per-request timeout; uploads that run OCR get longer. */
export const REQUEST_TIMEOUT_MS = 30_000;
export const UPLOAD_TIMEOUT_MS = 90_000;

/** After a write, GETs ask the service worker for the network so a refetch never shows pre-write cached data. */
export const FRESH_WINDOW_MS = 30_000;
let lastWriteAt = -Infinity;
export const markWrite = (now = Date.now()) => {
  lastWriteAt = now;
};
export const wantsFresh = (now = Date.now()) => now - lastWriteAt < FRESH_WINDOW_MS;

/** Message shown when a write timed out: the server may still have committed it. */
export const MIGHT_HAVE_SAVED = "Might have saved — check before retrying.";
export const NOT_PAIRED = "Not paired — scan a fresh QR code from Settings on your Mac.";

export function newIdempotencyKey(): string {
  const c = typeof crypto !== "undefined" ? crypto : undefined;
  if (c && "randomUUID" in c) return c.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

/** Same key for the same payload until it succeeds (a retry after a timeout dedupes); a changed payload gets a new key. */
export function keyFor(slot: { current: { sig: string; key: string } | null }, payload: unknown): string {
  const sig = JSON.stringify(payload);
  if (!slot.current || slot.current.sig !== sig) slot.current = { sig, key: newIdempotencyKey() };
  return slot.current.key;
}

/** React Query retry rule: never retry client errors (4xx) or deliberate aborts; retry once otherwise. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.kind === "aborted" || (error.status >= 400 && error.status < 500))) return false;
  return failureCount < 1;
}

/** fetch with a timeout, caller abort support and distinct offline/timeout errors. */
export async function apiFetch(path: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs);
  const outer = init.signal;
  const onOuterAbort = () => ctrl.abort();
  if (outer) {
    if (outer.aborted) ctrl.abort();
    else outer.addEventListener("abort", onOuterAbort, { once: true });
  }
  try {
    return await fetch(path, { ...init, signal: ctrl.signal });
  } catch (e) {
    if (timedOut) {
      const write = (init.method ?? "GET").toUpperCase() !== "GET";
      throw new ApiError(0, write ? MIGHT_HAVE_SAVED : "The request timed out. Check your connection and try again.", "timeout");
    }
    if (outer?.aborted || (e instanceof DOMException && e.name === "AbortError")) throw new ApiError(0, "Request cancelled.", "aborted");
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    throw new ApiError(0, offline ? "You're offline. Reconnect and try again." : "Couldn't reach the Cadence server. Is it running?", "offline");
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", onOuterAbort);
  }
}

async function readJson<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text().catch(() => "");
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(res.status, "The server sent an unexpected response.", "parse");
  }
}

async function failure(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  if (res.status === 401 || res.status === 403) {
    // A revoked or unpaired phone must not keep showing cached health data.
    try {
      navigator.serviceWorker?.controller?.postMessage({ type: "clear-cache" });
    } catch {
      /* no service worker */
    }
    if (res.status === 401) return new ApiError(401, NOT_PAIRED);
  }
  // FastAPI validation errors (422) send a list of {msg, loc}; show the first one's message.
  const detail = typeof body?.detail === "string" ? body.detail : Array.isArray(body?.detail) && typeof body.detail[0]?.msg === "string" ? body.detail[0].msg : null;
  return new ApiError(res.status, detail ?? (res.statusText || `Request failed (${res.status})`));
}

// The phone share server injects this meta tag; it only accepts reads.
export const READ_ONLY =
  typeof document !== "undefined" &&
  document.querySelector('meta[name="cadence-mode"]')?.getAttribute("content") === "read-only";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  if (READ_ONLY && method !== "GET" && !phoneMayWrite(method, path)) {
    throw new ApiError(405, "Read-only on this device. Make changes on your Mac.");
  }
  const headers = new Headers(init.headers);
  if (method !== "GET") headers.set("X-Cadence-Request", "1");
  else if (wantsFresh()) headers.set("X-Cadence-Fresh", "1");
  // Only JSON string bodies get a JSON type; FormData/Blob set their own (multipart boundary etc.).
  if (typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (method !== "GET") markWrite();
  const res = await apiFetch(path, { ...init, headers });
  if (method !== "GET") markWrite();
  if (!res.ok) throw await failure(res);
  return readJson<T>(res);
}

export const api = {
  push: () => request<PushStatus>("/api/push"),
  pushSubscribe: (sub: PushSubscriptionJSON, label: string) =>
    request<{ devices: PushStatus["devices"] }>("/api/push/subscribe", {
      method: "POST",
      body: JSON.stringify({ endpoint: sub.endpoint, keys: sub.keys, label }),
    }),
  pushUnsubscribe: (endpoint: string) =>
    request<{ devices: PushStatus["devices"] }>("/api/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify({ endpoint }),
    }),
  pushTest: () => request<{ delivered: number }>("/api/push/test", { method: "POST" }),
  pushPrefs: (prefs: Record<string, boolean>) =>
    request<{ prefs: Record<string, boolean> }>("/api/push/prefs", { method: "PUT", body: JSON.stringify(prefs) }),
  share: () => request<ShareStatus>("/api/share"),
  shareStart: () => request<ShareStatus>("/api/share/start", { method: "POST" }),
  shareStop: () => request<ShareStatus>("/api/share/stop", { method: "POST" }),
  shareRevoke: (id: string) => request<ShareStatus>(`/api/share/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }),
  shareReset: () => request<ShareStatus>("/api/share/reset", { method: "POST" }),
  credentialStatus: () => request<CredentialStatus>("/api/credentials/status"),
  dismissReminder: (key: string) =>
    request<{ dismissed: boolean }>("/api/credentials/reminders/dismiss", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),
  overview: () => request<Overview>("/api/overview"),
  calorieSettings: () => request<CalorieSettingsView>("/api/settings/calories"),
  /** Any subset of mode, manual_kcal, eat_back_pct, pace; the server validates and returns the full settings. */
  saveCalorieSettings: (patch: Partial<CalorieSettings>) =>
    request<CalorieSettingsView>("/api/settings/calories", { method: "PUT", body: JSON.stringify(patch) }),
  score: (days = 90) => request<ScoreReport>(`/api/score?days=${days}`),
  metric: (metric: string, days: number) =>
    request<MetricSeries>(`/api/metrics/${encodeURIComponent(metric)}?days=${days}`),
  improve: (metric: string) => request<ImproveReport>(`/api/improve/${encodeURIComponent(metric)}`),
  improveSummary: () => request<ImproveSummary>("/api/improve"),
  activities: (limit: number, offset: number, family?: string) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (family) params.set("family", family);
    return request<{ total: number; families: Record<string, number>; items: ActivityItem[] }>(
      `/api/activities?${params}`,
    );
  },
  activityLog: (family?: string) =>
    request<ActivityLog>(`/api/activities/summary${family ? `?family=${encodeURIComponent(family)}` : ""}`),
  weight: (days: number) => request<WeightResponse>(`/api/weight?days=${days}`),
  setWeightGoal: (goal_kg: number | null) =>
    request<{ goal_kg: number | null }>("/api/settings/weight-goal", {
      method: "PUT",
      body: JSON.stringify({ goal_kg }),
    }),
  reading: () => request<ReadingView>("/api/reading"),
  setReading: (id: string, status: "read" | "saved" | "skipped" | "unread") =>
    request<ReadingView>(`/api/reading/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ status }) }),
  readingBook: () => request<BookView>("/api/reading/book"),
  readBookPart: () => request<BookView>("/api/reading/book/read", { method: "POST" }),
  setBookPosition: (part: number) => request<BookView>("/api/reading/book/position", { method: "PUT", body: JSON.stringify({ part }) }),
  refreshReadingFeed: () => request<{ started: boolean; reason: string | null }>("/api/reading/feed/refresh", { method: "POST" }),
  readingFeedSetting: () => request<{ enabled: boolean; available: boolean }>("/api/settings/reading-feed"),
  setReadingFeed: (enabled: boolean) =>
    request<{ enabled: boolean; available: boolean }>("/api/settings/reading-feed", { method: "PUT", body: JSON.stringify({ enabled }) }),
  journal: (days = 14) => request<JournalView>(`/api/journal?days=${days}`),
  saveJournal: (day: string, answers: Record<string, number>) =>
    request<{ day: string; answers: Record<string, number> }>(`/api/journal/${day}`, { method: "PUT", body: JSON.stringify({ answers }) }),
  addBehaviour: (b: { label: string; question: string; kind: Behaviour["kind"]; unit: string }) =>
    request<Behaviour>("/api/journal/behaviours", { method: "POST", body: JSON.stringify(b) }),
  updateBehaviour: (key: string, patch: { active?: boolean }) =>
    request<Behaviour>(`/api/journal/behaviours/${encodeURIComponent(key)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  phases: () => request<{ items: PhaseSummary[]; habits: HabitOption[] }>("/api/phases"),
  activePhases: () => request<{ items: PhaseSummary[]; habits: HabitOption[] }>("/api/phases/active"),
  phase: (id: number) => request<PhaseDetail>(`/api/phases/${id}`),
  createPhase: (body: PhaseBody) => request<PhaseDetail>("/api/phases", { method: "POST", body: JSON.stringify(body) }),
  updatePhase: (id: number, body: PhaseBody) => request<PhaseDetail>(`/api/phases/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deletePhase: (id: number) => request<{ deleted: boolean }>(`/api/phases/${id}`, { method: "DELETE" }),
  events: () => request<{ items: EventSummary[] }>("/api/events"),
  event: (id: number) => request<EventDetail>(`/api/events/${id}`),
  createEvent: (name: string, activityIds: number[]) =>
    request<EventDetail>("/api/events", { method: "POST", body: JSON.stringify({ name, activity_ids: activityIds }) }),
  renameEvent: (id: number, name: string) =>
    request<EventDetail>(`/api/events/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  linkToEvent: (id: number, activityIds: number[]) =>
    request<EventDetail>(`/api/events/${id}/activities`, { method: "POST", body: JSON.stringify({ activity_ids: activityIds }) }),
  unlinkFromEvent: (id: number, activityId: number) =>
    request<{ event: EventDetail | null }>(`/api/events/${id}/activities/${activityId}`, { method: "DELETE" }),
  deleteEvent: (id: number) => request<{ deleted: boolean }>(`/api/events/${id}`, { method: "DELETE" }),
  parseStrength: (text: string) => request<StrengthLabel>("/api/strength/parse", { method: "POST", body: JSON.stringify({ text }) }),
  readScreenshot: async (file: Blob): Promise<StrengthLabel> => {
    // Raw image body: read on the Cadence machine; nothing is stored until you save.
    const res = await apiFetch("/api/strength/ocr", {
      method: "POST",
      body: file,
      headers: { "X-Cadence-Request": "1", "Content-Type": file.type || "image/png" },
    }, UPLOAD_TIMEOUT_MS);
    if (!res.ok) throw await failure(res);
    return readJson<StrengthLabel>(res);
  },
  saveStrength: (id: number, text: string, template: string | null) =>
    request<StrengthLabel>(`/api/strength/${id}`, { method: "PUT", body: JSON.stringify({ text, template }) }),
  deleteStrength: (id: number) => request<{ deleted: boolean }>(`/api/strength/${id}`, { method: "DELETE" }),
  review: (kind: "week" | "month", start?: string) =>
    request<Review | { has_data: false }>(`/api/reviews/${kind}${start ? `?start=${start}` : ""}`),
  plannerWeek: () => request<PlannerWeek>("/api/planner"),
  plannerOptions: (day: string, sport: Sport, extra: { strengthText?: string; startHour?: number | null; custom?: CustomSpec | null } = {}) => {
    const q = new URLSearchParams({ day, sport });
    if (extra.strengthText) q.set("strength_text", extra.strengthText);
    if (extra.startHour != null) q.set("start_hour", String(extra.startHour));
    if (extra.custom) {
      q.set("custom", "true");
      Object.entries(extra.custom).forEach(([k, v]) => q.set(k, String(v)));
    }
    return request<{ day: string; sport: Sport; start_hour: number; options: PlanOption[] }>(`/api/planner/options?${q}`);
  },
  createPlan: (day: string, sport: Sport, optionKey: string, extra: { strengthText?: string; startHour?: number | null; custom?: CustomSpec | null } = {}) =>
    request<PlannedSessionView>("/api/planner", {
      method: "POST",
      body: JSON.stringify({ day, sport, option_key: optionKey, strength_text: extra.strengthText ?? null, start_hour: extra.startHour ?? null, custom: extra.custom ?? null }),
    }),
  deletePlan: (id: number) => request<{ deleted: boolean; garmin_removed?: boolean }>(`/api/planner/${id}`, { method: "DELETE" }),
  sendPlanToGarmin: (id: number) => request<PlannedSessionView>(`/api/planner/${id}/garmin`, { method: "POST" }),
  removePlanFromGarmin: (id: number) => request<PlannedSessionView>(`/api/planner/${id}/garmin`, { method: "DELETE" }),
  garminConnect: () => request<GarminConnectStatus>("/api/garmin-connect"),
  garminLogin: (email: string, password: string) =>
    request<{ status: "connected" | "needs_code" }>("/api/garmin-connect/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  garminCode: (code: string) => request<{ status: "connected" }>("/api/garmin-connect/code", { method: "POST", body: JSON.stringify({ code }) }),
  garminDisconnect: () => request<GarminConnectStatus>("/api/garmin-connect", { method: "DELETE" }),
  weatherSetting: () => request<{ enabled: boolean; available: boolean }>("/api/settings/weather"),
  setWeather: (enabled: boolean) =>
    request<{ enabled: boolean; available: boolean }>("/api/settings/weather", { method: "PUT", body: JSON.stringify({ enabled }) }),
  bodyProfile: () => request<{ profile: BodyProfile | null }>("/api/settings/profile"),
  setBodyProfile: (profile: { height_cm: number; birth_date: string; sex: "male" | "female" }) =>
    request<{ profile: BodyProfile }>("/api/settings/profile", { method: "PUT", body: JSON.stringify(profile) }),
  backupStatus: () => request<BackupStatus>("/api/backup/status"),
  weightEntries: () => request<WeightEntries>("/api/weight/entries"),
  addWeight: (day: string, weight_kg: number) =>
    request<{ day: string; weight_kg: number }>("/api/weight/entries", { method: "POST", body: JSON.stringify({ day, weight_kg }) }),
  food: (day: string) => request<FoodView>(`/api/food?day=${day}`),
  foodCrawl: () => request<{ progress: FoodCrawlProgress | null }>("/api/food/crawl"),
  foodDishes: () => request<{ dishes: FoodDish[] }>("/api/food/dishes"),
  addFoodDish: (dish: FoodDishInput) => request<FoodDish>("/api/food/dishes", { method: "POST", body: JSON.stringify(dish) }),
  addDishName: (dishId: number, name: string, preferred: boolean, idempotencyKey?: string) =>
    request<unknown>(`/api/food/dishes/${dishId}/names`, {
      method: "POST",
      body: JSON.stringify({ name, preferred }),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),
  deleteDishName: (dishId: number, aliasId: number) => request<unknown>(`/api/food/dishes/${dishId}/names/${aliasId}`, { method: "DELETE" }),
  setDishNamePreferred: (dishId: number, aliasId: number, preferred: boolean) =>
    request<unknown>(`/api/food/dishes/${dishId}/names/${aliasId}`, { method: "PATCH", body: JSON.stringify({ preferred }) }),
  addFoodEntry: (entry: FoodEntryInput, idempotencyKey?: string) =>
    request<unknown>("/api/food/entries", {
      method: "POST",
      body: JSON.stringify(entry),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),
  deleteFoodEntry: (id: number) => request<{ deleted: number }>(`/api/food/entries/${id}`, { method: "DELETE" }),
  setFoodEntryAmount: (id: number, servings: number) =>
    request<unknown>(`/api/food/entries/${id}`, { method: "PATCH", body: JSON.stringify({ servings }) }),
  readFoodLabel: async (photo: Blob): Promise<FoodLabelRead> => {
    // Raw image body, read with Tesseract on the Cadence server; nothing is saved until you confirm.
    const res = await apiFetch("/api/food/label", {
      method: "POST",
      body: photo,
      headers: { "X-Cadence-Request": "1", "Content-Type": photo.type || "image/jpeg" },
    }, UPLOAD_TIMEOUT_MS);
    if (!res.ok) throw await failure(res);
    return readJson<FoodLabelRead>(res);
  },
  readFoodLabelText: (text: string) => request<FoodLabelRead>("/api/food/label/text", { method: "POST", body: JSON.stringify({ text }) }),
  foodMeals: () => request<{ meals: FoodSavedMeal[] }>("/api/food/meals"),
  saveFoodMeal: (name: string, entry_ids: number[]) =>
    request<FoodSavedMeal>("/api/food/meals", { method: "POST", body: JSON.stringify({ name, entry_ids }) }),
  renameFoodMeal: (id: number, name: string) =>
    request<FoodSavedMeal>(`/api/food/meals/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteFoodMeal: (id: number) => request<{ deleted: number }>(`/api/food/meals/${id}`, { method: "DELETE" }),
  logFoodMeal: (id: number, input: { day: string; meal: Meal; scale: number; eating_out?: boolean }) =>
    request<{ entries: unknown[] }>(`/api/food/meals/${id}/log`, { method: "POST", body: JSON.stringify(input) }),
  copyFoodDay: (source: string, target: string, opts?: { meal?: Meal; target_meal?: Meal; entry_ids?: number[] }) =>
    request<{ copied: number; entries?: unknown[] }>("/api/food/copy", { method: "POST", body: JSON.stringify({ source, target, ...opts }) }),
  /** One request for a whole draft; `key` is both the Idempotency-Key header and the client_key field. */
  foodLogBatch: (body: { day: string; meal: Meal; eaten_at?: string | null; eating_out?: boolean; source?: string; items: LogItem[] }, key: string) =>
    request<FoodBatchResult>("/api/food/log", {
      method: "POST",
      body: JSON.stringify({ ...body, client_key: key }),
      headers: { "Idempotency-Key": key },
    }),
  foodQuick: (day: string, meal: Meal) => request<FoodQuick>(`/api/food/quick?day=${day}&meal=${meal}`),
  foodSuggest: (day: string, meal: Meal) => request<FoodSuggest>(`/api/food/suggest?day=${day}&meal=${meal}`),
  foodBarcode: (code: string) => request<FoodBarcodeResult>(`/api/food/barcode/${encodeURIComponent(code)}`),
  foodRestore: (id: number) => request<unknown>(`/api/food/entries/${id}/restore`, { method: "POST" }),
  foodBulk: (body: FoodBulkBody) => request<{ entries: unknown[]; affected: number }>("/api/food/entries/bulk", { method: "POST", body: JSON.stringify(body) }),
  patchFoodEntry: (id: number, body: { servings?: number; grams?: number; meal?: Meal; eaten_at?: string | null }) =>
    request<unknown>(`/api/food/entries/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteWeight: (day: string) => request<{ deleted: string }>(`/api/weight/entries/${day}`, { method: "DELETE" }),
  setGoal: (goal: { distance: GoalDistance; date: string; target_s: number | null } | null) =>
    request<{ goal: TrainingGoal | null }>("/api/settings/goal", { method: "PUT", body: JSON.stringify(goal ?? {}) }),
  goals: () => request<GoalsResponse>("/api/goals"),
  createGoal: (goal: GoalInput) => request<{ id: number }>("/api/goals", { method: "POST", body: JSON.stringify(goal) }),
  updateGoal: (id: number, patch: Partial<GoalInput> & { status?: GoalView["status"] }) =>
    request<{ id: number }>(`/api/goals/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteGoal: (id: number) => request<{ deleted: boolean }>(`/api/goals/${id}`, { method: "DELETE" }),
  labAccuracy: () => request<LabAccuracy>("/api/lab/accuracy"),
  labModel: () => request<LabModel>("/api/lab/model"),
  labRoutes: () => request<LabRoutes>("/api/lab/routes"),
  labWhatIf: () => request<LabWhatIf>("/api/lab/whatif"),
  labReplay: (edits: { id: number; action: string }[]) =>
    request<WhatIfResult>(`/api/lab/whatif/replay?${edits.map((e) => `edit=${e.id}:${e.action}`).join("&")}`),
  timeOff: () => request<TimeOffView>("/api/time-off"),
  createTimeOff: (body: TimeOffBody) => request<TimeOffView>("/api/time-off", { method: "POST", body: JSON.stringify(body) }),
  updateTimeOff: (id: number, body: TimeOffBody) => request<TimeOffView>(`/api/time-off/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTimeOff: (id: number) => request<TimeOffView>(`/api/time-off/${id}`, { method: "DELETE" }),
  savePlanSettings: (patch: Partial<{ [K in keyof PlanSettings]: PlanSettings[K] | null }>) =>
    request<TimeOffView>("/api/settings/plan", { method: "PUT", body: JSON.stringify(patch) }),
  seriesTrend: (kind: "readiness" | "score", days: number) => request<SeriesTrend>(`/api/trends/${kind}?days=${days}`),
  trainingTrend: (weeks: number) => request<TrainingTrend>(`/api/trends/training?weeks=${weeks}`),
  wellbeing: () => request<{ today: string; entry: WellbeingEntry | null; entries: WellbeingEntry[] }>("/api/wellbeing"),
  saveWellbeing: (day: string, patch: Partial<Omit<WellbeingEntry, "day">>) =>
    request<WellbeingEntry>(`/api/wellbeing/${day}`, { method: "PUT", body: JSON.stringify(patch) }),
  setTrainingMode: (mode: TrainingMode) =>
    request<{ mode: TrainingMode }>("/api/settings/training-mode", { method: "PUT", body: JSON.stringify({ mode }) }),
  outcomes: () => request<Outcomes>("/api/outcomes"),
  sources: () => request<SourceInfo[]>("/api/sources"),
  syncDemo: () => request<SyncRun>("/api/sync/demo", { method: "POST" }),
  garminStatus: () => request<GarminStatus>("/api/garmin/status"),
  garminSync: (mode: "quick" | "full") =>
    request<{ run_id: number }>("/api/garmin/sync", { method: "POST", body: JSON.stringify({ mode }) }),
  garminStop: () => request<{ stopping: boolean }>("/api/garmin/stop", { method: "POST" }),
  garminRebuild: () => request<{ run_id: number }>("/api/garmin/rebuild", { method: "POST" }),
  activity: (id: number) => request<ActivityDetail>(`/api/activities/${id}`),
  day: (day: string) => request<DayDetail>(`/api/days/${day}`),
  insights: () => request<Insights>("/api/insights"),
  fetchDay: (day: string) => request<{ fetched: string[] }>(`/api/days/${day}/fetch`, { method: "POST" }),
  fetchActivity: (id: number) =>
    request<{ fetched: string[] }>(`/api/activities/${id}/fetch`, { method: "POST" }),
  vaultList: (dataset: string, limit: number, offset: number) =>
    request<{ total: number; items: VaultItemMeta[] }>(
      `/api/garmin/vault/${encodeURIComponent(dataset)}?limit=${limit}&offset=${offset}`,
    ),
  vaultItem: (id: number) =>
    request<{ meta: VaultItemMeta; payload: unknown; activity_id: number | null }>(`/api/garmin/vault/item/${id}`),
  syncRuns: () => request<SyncRun[]>("/api/sync/runs"),
  deleteDemo: () => request<{ deleted: boolean }>("/api/sources/demo/data", { method: "DELETE" }),
};
