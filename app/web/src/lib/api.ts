import type {
  ActivityDetail,
  Behaviour,
  JournalView,
  PlanOption,
  Review,
  BodyProfile,
  WeightEntries,
  PlannedSessionView,
  PlannerWeek,
  Sport,
  StrengthLabel,
  ActivityItem,
  ActivityLog,
  CredentialStatus,
  DayDetail,
  GarminStatus,
  GoalDistance,
  Insights,
  MetricSeries,
  Overview,
  PushStatus,
  ScoreReport,
  ShareStatus,
  SourceInfo,
  SyncRun,
  TrainingGoal,
  VaultItemMeta,
  WeightResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// The phone share server injects this meta tag; it only accepts reads.
export const READ_ONLY =
  typeof document !== "undefined" &&
  document.querySelector('meta[name="cadence-mode"]')?.getAttribute("content") === "read-only";
const PHONE_WRITES = ["/api/push/", "/api/garmin/sync", "/api/journal/", "/api/strength/", "/api/planner", "/api/weight/entries", "/api/settings/weather", "/api/settings/profile"];

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  if (READ_ONLY && method !== "GET" && !PHONE_WRITES.some((p) => path.startsWith(p))) {
    throw new ApiError(405, "Read-only on this device. Make changes on your Mac.");
  }
  const headers = new Headers(init.headers);
  if (method !== "GET") headers.set("X-Cadence-Request", "1");
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, typeof body?.detail === "string" ? body.detail : res.statusText);
  }
  return res.json() as Promise<T>;
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
  shareReset: () => request<ShareStatus>("/api/share/reset", { method: "POST" }),
  credentialStatus: () => request<CredentialStatus>("/api/credentials/status"),
  dismissReminder: (key: string) =>
    request<{ dismissed: boolean }>("/api/credentials/reminders/dismiss", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),
  overview: () => request<Overview>("/api/overview"),
  score: (days = 90) => request<ScoreReport>(`/api/score?days=${days}`),
  metric: (metric: string, days: number) =>
    request<MetricSeries>(`/api/metrics/${encodeURIComponent(metric)}?days=${days}`),
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
  journal: (days = 14) => request<JournalView>(`/api/journal?days=${days}`),
  saveJournal: (day: string, answers: Record<string, number>) =>
    request<{ day: string; answers: Record<string, number> }>(`/api/journal/${day}`, { method: "PUT", body: JSON.stringify({ answers }) }),
  addBehaviour: (b: { label: string; question: string; kind: Behaviour["kind"]; unit: string }) =>
    request<Behaviour>("/api/journal/behaviours", { method: "POST", body: JSON.stringify(b) }),
  updateBehaviour: (key: string, patch: { active?: boolean }) =>
    request<Behaviour>(`/api/journal/behaviours/${encodeURIComponent(key)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  parseStrength: (text: string) => request<StrengthLabel>("/api/strength/parse", { method: "POST", body: JSON.stringify({ text }) }),
  readScreenshot: async (file: Blob): Promise<StrengthLabel> => {
    // Raw image body: the Mac reads it with Apple Vision; nothing is stored until you save.
    const res = await fetch("/api/strength/ocr", {
      method: "POST",
      body: file,
      headers: { "X-Cadence-Request": "1", "Content-Type": file.type || "image/png" },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(res.status, typeof body?.detail === "string" ? body.detail : res.statusText);
    }
    return res.json() as Promise<StrengthLabel>;
  },
  saveStrength: (id: number, text: string, template: string | null) =>
    request<StrengthLabel>(`/api/strength/${id}`, { method: "PUT", body: JSON.stringify({ text, template }) }),
  deleteStrength: (id: number) => request<{ deleted: boolean }>(`/api/strength/${id}`, { method: "DELETE" }),
  review: (kind: "week" | "month", start?: string) =>
    request<Review | { has_data: false }>(`/api/reviews/${kind}${start ? `?start=${start}` : ""}`),
  plannerWeek: () => request<PlannerWeek>("/api/planner"),
  plannerOptions: (day: string, sport: Sport, strengthText?: string) => {
    const q = new URLSearchParams({ day, sport });
    if (strengthText) q.set("strength_text", strengthText);
    return request<{ day: string; sport: Sport; options: PlanOption[] }>(`/api/planner/options?${q}`);
  },
  createPlan: (day: string, sport: Sport, optionKey: string, strengthText?: string) =>
    request<PlannedSessionView>("/api/planner", { method: "POST", body: JSON.stringify({ day, sport, option_key: optionKey, strength_text: strengthText ?? null }) }),
  deletePlan: (id: number) => request<{ deleted: boolean }>(`/api/planner/${id}`, { method: "DELETE" }),
  weatherSetting: () => request<{ enabled: boolean; available: boolean }>("/api/settings/weather"),
  setWeather: (enabled: boolean) =>
    request<{ enabled: boolean; available: boolean }>("/api/settings/weather", { method: "PUT", body: JSON.stringify({ enabled }) }),
  bodyProfile: () => request<{ profile: BodyProfile | null }>("/api/settings/profile"),
  setBodyProfile: (profile: { height_cm: number; birth_date: string; sex: "male" | "female" }) =>
    request<{ profile: BodyProfile }>("/api/settings/profile", { method: "PUT", body: JSON.stringify(profile) }),
  weightEntries: () => request<WeightEntries>("/api/weight/entries"),
  addWeight: (day: string, weight_kg: number) =>
    request<{ day: string; weight_kg: number }>("/api/weight/entries", { method: "POST", body: JSON.stringify({ day, weight_kg }) }),
  deleteWeight: (day: string) => request<{ deleted: string }>(`/api/weight/entries/${day}`, { method: "DELETE" }),
  setGoal: (goal: { distance: GoalDistance; date: string; target_s: number | null } | null) =>
    request<{ goal: TrainingGoal | null }>("/api/settings/goal", { method: "PUT", body: JSON.stringify(goal ?? {}) }),
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
