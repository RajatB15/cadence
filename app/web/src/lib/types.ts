export type CredentialLevel =
  | "missing"
  | "invalid_expiry"
  | "ok"
  | "notice"
  | "warning"
  | "critical"
  | "expired";

export interface CredentialStatus {
  configured: boolean;
  expires_on: string | null;
  days_remaining: number | null;
  level: CredentialLevel;
  active_threshold: number | null;
  thresholds: number[];
  reminder_dates: string[];
  reminder_key: string | null;
  dismissed: boolean;
  today: string;
}

export interface Point {
  day: string;
  value: number;
}

export interface MetricSummary {
  metric: string;
  label: string;
  unit: string;
  higher_is_better: boolean | null;
  latest: number;
  latest_day: string;
  recent_mean: number | null;
  baseline_mean: number | null;
  delta_pct: number | null;
  spark: Point[];
}

export interface ActivityItem {
  id: number;
  source_id: string;
  start_time_utc: string;
  timezone: string;
  local_date: string;
  type: string;
  family: string;
  name: string;
  duration_s: number;
  distance_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  elevation_gain_m: number | null;
  calories: number | null;
  training_load: number | null;
  moving_duration_s?: number | null;
  avg_speed_mps?: number | null;
  vo2max?: number | null;
  aerobic_te?: number | null;
  verdict?: Verdict | null;
  intensity?: { easy_pct: number; moderate_pct: number; hard_pct: number; kind: string } | null;
  event?: { id: number; name: string } | null;
}

export type Json = Record<string, unknown>;

export interface FitData {
  error?: string;
  streams: Record<string, (number | null)[]>;
  stream_stats: Record<string, { min: number; avg: number; max: number; count: number }>;
  route: [number, number][];
  /** GPS points with values from the same record; channels without data are omitted. */
  track?: Partial<Record<"lat" | "lon" | "t" | "hr" | "speed" | "alt" | "dist", (number | null)[]>>;
  zones: { zone: number; low: number | null; high: number | null; seconds: number }[] | null;
  messages: Record<string, Json[]>;
  streamed_counts: Record<string, number>;
  unknown_messages: { id: number; count: number; sample: unknown }[];
  decode_errors: string[];
}

export interface ActivityDetail {
  activity: ActivityItem;
  garmin_summary: Json | null;
  detail: Json | null;
  workouts: unknown;
  fit: FitData | null;
  missing: string[];
  stored: Record<string, { fetched_at: string; status: number; bytes: number }>;
  coach: SessionCoach | null;
  route: ActivityRoute | null;
  strength: { label: StrengthLabel | null; templates: { id: number; name: string; text: string }[] } | null;
  planned: PlannedSessionView | null;
}

export interface StrengthExercise {
  name: string;
  pattern: string | null;
  muscles: string[];
  loaded: boolean;
}

export interface StrengthBlock {
  name: string;
  kind: "strength" | "conditioning" | "core" | "mixed";
  exercises: StrengthExercise[];
}

export interface StrengthLabel {
  text: string;
  blocks: StrengthBlock[];
  summary: { patterns: Record<string, number>; heavy_lower: boolean; unknown: string[]; exercises: number };
  segments?: {
    segments: { name: string; kind: string; start_s: number; end_s: number; avg_hr: number; max_hr: number; hard_pct?: number }[];
    fit: number;
  } | null;
}

export interface StrengthContent {
  sessions_28d: number;
  labelled_28d: number;
  patterns_28d: Record<string, number>;
  last_trained: Record<string, string>;
  heavy_lower_this_week: number;
  unlabelled: { id: number; day: string; name: string }[];
}

export interface Verdict {
  label: string;
  tone: "good" | "warn" | "info" | "key";
}

export interface Note extends Finding {
  metrics: string[];
}

export interface WhatIfCard {
  lines?: string[];
  tone: "good" | "info";
  title: string;
  scope: "home" | "week" | "month" | "session";
  text: string;
  action: string | null;
  link: string;
  sessions?: { id: number; day: string; name: string; load: number; load_after: number; kind: string }[];
}

export interface ActivityRoute {
  id: number;
  name: string;
  sport: "run" | "ride";
  n: number;
  distance_km: number;
  best: { id: number; day: string; time_s: number };
  median_time_s: number;
  trend: { n: number; span_days: number; change_pct: number; ci_pct: [number, number]; significant: boolean } | null;
  notes: Finding[];
  this: (RouteEffort & { rank: number; of: number; is_best: boolean; earlier_efforts: number; vs_prior: { time_s: number | null; avg_hr: number | null; ef_pct: number | null; temperature: number | null } }) | null;
}

export interface SessionCoach {
  what_if?: WhatIfCard | null;
  verdict: Verdict | null;
  intensity: { easy_pct: number; moderate_pct: number; hard_pct: number; kind: "easy" | "grey" | "hard" } | null;
  readiness: { score: number; label: string } | null;
  notes: Note[];
}

export interface Recommendation {
  source?: "check-in";
  headline: string;
  detail: string;
  reasons: { factor: string; tone: string; score: number }[];
}

export interface ReadinessToday {
  score: number;
  label: string;
  components: Record<string, ReadinessComponent>;
  morning_score?: number;
  changes?: { label: string; delta: number }[];
  live?: boolean;
}

export interface DayCoach {
  readiness: ReadinessToday | null;
  call: Recommendation | null;
  notes: Note[];
}

export interface RecentSession {
  id: number;
  name: string;
  family: string;
  type: string;
  start: string | null;
  moving_s: number | null;
  distance_m: number | null;
  load: number;
  avg_hr: number | null;
  verdict: Verdict | null;
  intensity: { easy_pct: number; moderate_pct: number; hard_pct: number; kind: string } | null;
  notes: number;
  note: { severity: Finding["severity"]; title: string; detail: string } | null;
}

export interface Brief {
  wellbeing: BriefWellbeing;
  recovery_wins: RecoveryWins | null;
  what_if: WhatIfCard | null;
  as_of: string;
  readiness: ReadinessToday | null;
  readiness_trend: { day: string; score: number }[];
  call: Recommendation | null;
  today: {
    kind: "key" | "easy" | "long" | "rest" | "strength" | "done" | "unknown";
    title: string;
    detail: string;
    status?: "matched" | "open" | "over" | "extra";
    planned?: string | null;
    next?: string;
    load?: number;
    second?: { title: string; detail: string } | null;
  };
  focus: string | null;
  phase: PlanPhase | null;
  goal: TrainingGoal | null;
  recent: { label: string | null; day: string | null; items: RecentSession[] };
  week: {
    start: string;
    days_left: number;
    items: { key: string; label: string; done: number; target: number; low?: number }[];
  };
  streaks: { key: string; label: string; current: number; best: number; unit: string }[];
  tonight: Tonight | null;
  strain: StrainToday | null;
  weather: WeatherOutlook | null;
  fix: Finding[];
  wins: Finding[];
}

export interface ScoreFactor {
  key: string;
  group: string;
  label: string;
  score: number;
  value: string;
  target: string;
  tip: string;
  weight: number;
  points_lost: number;
}

export interface ScoreGroup {
  key: string;
  label: string;
  blurb: string;
  weight: number;
  score: number;
}

export interface ScoreSummary {
  score: number;
  label: string;
  delta_7d: number | null;
  groups: { key: string; label: string; score: number }[];
  top_gaps: { label: string; points_lost: number; value: string; target: string }[];
  spark: number[];
}

export type ScoreReport =
  | { has_data: false }
  | {
      has_data: true;
      day: string;
      score: number;
      label: string;
      delta_7d: number | null;
      groups: ScoreGroup[];
      factors: ScoreFactor[];
      gaps: ScoreFactor[];
      history: ({ day: string; score: number } & Record<string, number | string>)[];
    };

export interface DayMetric {
  value: number;
  unit: string;
  label: string;
  higher_is_better: boolean | null;
  avg_7d: number | null;
  prev_7d: number | null;
  avg_30d: number | null;
  baseline_60d: number | null;
  all_min: number;
  all_max: number;
  all_avg: number;
  percentile: number | null;
  rank_high: number;
  count: number;
  first_day: string;
}

export interface DayDetail {
  day: string;
  source_id: string;
  metrics: Record<string, DayMetric>;
  raw: Record<string, unknown>;
  missing: string[];
  activities: ActivityItem[];
  prev_day: string | null;
  next_day: string | null;
  coach: DayCoach | null;
}

export interface Finding {
  id: string;
  severity: "alert" | "warn" | "info" | "good";
  category: string;
  title: string;
  detail: string;
  action: string | null;
  evidence: { label: string; value: string | number }[];
  link: string | null;
}

export interface ReadinessComponent {
  score: number;
  weight: number;
  value: number | null;
  baseline?: number;
  z?: number;
  hours?: number | null;
  need?: number;
  fitness?: number;
  range?: [number, number];
  delta?: number;
  acwr?: number | null;
  strain?: number;
  now?: number;
  peak?: number;
}

export interface Effect {
  id: string;
  cause: string;
  outcome: string;
  exposed: string;
  reference: string;
  lag_days: number;
  unit: string;
  higher_is_better: boolean;
  exposed_mean: number;
  reference_mean: number;
  diff: number;
  pct: number;
  n_exposed: number;
  n_reference: number;
  p_value: number;
  q_value: number;
  effect_size: number;
  significant: boolean;
  adjusted_for: string[];
  n_effective: number;
}

export interface WeekSummary {
  week: string;
  load: number;
  sessions: Record<string, number>;
  total_sessions: number;
  rest_days: number;
  run_km: number;
  long_run_km: number;
  long_run_min: number;
  hard_sessions: number;
  strength_sessions: number;
  hours: number;
  monotony: number | null;
  strain: number | null;
  easy_pct: number | null;
  moderate_pct: number | null;
  hard_pct: number | null;
  complete: boolean;
}

export interface Review {
  has_data: true;
  what_if: WhatIfCard | null;
  first: string;
  today: string;
  kind: "week" | "month";
  complete: boolean;
  start: string;
  end: string;
  days: number;
  verdict: string;
  focus: { title: string; detail: string };
  training: {
    sessions: number; by_sport: Record<string, number>; hours: number; run_km: number; ride_km: number; load: number; quality: number;
    long_run_min: number; easy_pct: number | null; hard_sessions_pct: number | null; strain: number | null; everyday_strain: number | null; rest_days: number;
  };
  plan: { planned: number; done: number; missed: number; predicted_load: number | null; actual_load: number | null };
  fitness: { start: number | null; end: number | null; form: number | null; acwr: number | null };
  recovery: { readiness: number | null; hrv: number | null; hrv_base: number | null; rhr: number | null; rhr_base: number | null; warning_days: number };
  sleep: { avg_hours: number | null; need: number; nights_at_need: number; nights: number; avg_bedtime_min: number | null; regularity: number | null };
  habits: { logged_days: number; items: { key: string; label: string; days: number; logged: number; total: number | null; unit: string }[] };
  strength: { sessions: number; heavy_lower: number; patterns: Record<string, number> };
  highlights: { id: number; name: string; day: string; value: string }[];
  hot_sessions: number;
  vs_previous: { load: number | null; sessions: number | null; hours: number | null; run_km: number | null; readiness: number | null; sleep: number | null; fitness_change: number | null };
  previous: { start: string; end: string };
  trends?: { critical_speed_pace: (number | null)[]; efficiency_pct: number | null; vo2max: (number | null)[]; weight: (number | null)[] };
}

export type Sport = "run" | "ride" | "swim" | "strength";

export interface WeatherOutlook {
  hour: number;
  temperature: number | null;
  dew_point: number | null;
  apparent: number | null;
  wind: number | null;
  cost_pct: number;
  basis: "personal" | "general";
  hot: boolean;
  better_hour: number | null;
  better_cost_pct: number | null;
}

export interface Prediction {
  weather?: WeatherOutlook | null;
  load: number;
  load_range: [number, number] | null;
  similar_n: number;
  similar_load: number | null;
  aerobic_te: number | null;
  day_strain: number | null;
  fitness: [number, number] | null;
  form_tomorrow: number | null;
  acwr_tomorrow: number | null;
  readiness_load: [number, number] | null;
  recovery_days: number | null;
  recovery_personal: boolean;
  builds: string;
  basis: "similar" | "other sports" | "model" | "general";
  confidence: "personal" | "general";
}

export interface PlanOption {
  key: string;
  sport: Sport;
  kind: string;
  title: string;
  minutes: number;
  detail: string;
  heavy_lower?: boolean;
  blocks?: StrengthBlock[];
  predicted: Prediction;
  recommended: boolean;
  why: string | null;
  caution: string | null;
}

export interface PlannedSessionView {
  id: number;
  day: string;
  sport: Sport;
  kind: string;
  title: string;
  detail: string;
  minutes: number;
  predicted: Prediction;
  heavy_lower: boolean;
  blocks: StrengthBlock[];
  start_hour: number | null;
  status: "planned" | "done" | "missed";
  activity: { id: number; name: string; load: number | null; minutes: number } | null;
}

export interface PlannerWeek {
  today: string;
  days: { day: string; plans: PlannedSessionView[] }[];
  projection: { fitness_now: number; fitness_4w: number; weekly_load: number } | null;
  model: { n: number; r2: number; counts: Record<string, number> } | null;
}

export interface StrainToday {
  total: number;
  workout: number;
  everyday: number;
  band: { typical: number; low: number; high: number } | null;
  status: "below" | "in" | "above" | null;
  message: string | null;
  calibrated: boolean;
}

export interface Tonight {
  day: string;
  need_h: number;
  tonight_h: number;
  ideal_h: number;
  capped: boolean;
  extra_load_min: number;
  repay_min: number;
  debt_h: number;
  wake_min: number;
  lights_out_min: number;
  bed_min: number;
  weekend: boolean;
}

export interface Behaviour {
  key: string;
  label: string;
  question: string;
  kind: "yes_no" | "count";
  unit: string;
  active: boolean;
  builtin: boolean;
}

export interface JournalView {
  behaviours: Behaviour[];
  checkin: { day: string; done: boolean };
  days: { day: string; answers: Record<string, number> }[];
  today: string;
}

export interface HabitProgress {
  key: string;
  label: string;
  yes: number;
  no: number;
  needed: number;
  ready: boolean;
  yes_label: string;
  no_label: string;
}

export type HabitEffect = Effect & { extra: { behaviour: string; outcome: string } };

export type GoalDistance = "5k" | "10k" | "half" | "marathon";

export interface TrainingGoal {
  distance: GoalDistance | null;
  sport?: GoalSport;
  label: string;
  date: string;
  target_s: number | null;
  target_pace_s: number | null;
}

export interface PlanPhase {
  phase: "base" | "build" | "specific" | "maintain" | "recovery" | "absorb" | "taper" | "race";
  label: string;
  blurb: string;
  week_in_block: number | null;
  weeks_to_race: number | null;
}

export interface KeySession {
  kind: string;
  title: string;
  reps: string;
  detail: string;
  hr: [number, number] | null;
  pace_s: [number, number] | null;
}

export interface TrainingPlan {
  focus: string;
  phase: PlanPhase;
  goal: TrainingGoal | null;
  items: { label: string; value: string; why: string }[];
  sessions: KeySession[];
  targets: Record<string, number | number[] | null>;
}

export interface CriticalSpeed {
  valid: boolean;
  window_days: number;
  points: { seconds: number; speed: number; id: number; day: string; name: string }[];
  missing?: string;
  cs_mps?: number;
  d_prime_m?: number;
  r2?: number;
  pace_s?: number;
  predictions?: { key: string; label: string; distance_m: number; seconds: number; pace_s: number; caveat: string | null }[];
  paces?: { key: string; label: string; slow_s: number; fast_s: number }[];
}

export interface Performance {
  critical_speed: CriticalSpeed;
  history: { day: string; cs_mps: number; pace_s: number; d_prime_m: number }[];
  zone_check: {
    status: "ok" | "stale";
    issues: { key: string; label: string; zones: number; observed: number; detail: string }[];
    observed_max: number | null;
    lthr_estimate: number | null;
    zones_max: number | null;
    zones_threshold: number | null;
  } | null;
  form: {
    ref_speed: number;
    ref_pace_s: number;
    n: number;
    cadence_now: number;
    cadence_before: number | null;
    stance_ms?: number;
    stance_ms_before?: number | null;
    vertical_ratio?: number;
    vertical_ratio_before?: number | null;
    vertical_osc_mm?: number;
    vertical_osc_mm_before?: number | null;
  } | null;
  durability: { fade_now: number; fade_before: number | null; n: number } | null;
  analysed_runs: number;
}

export interface HrvGuided {
  status: "below" | "normal" | "above";
  coping: "coping" | "strained" | "struggling";
  green_light: boolean;
  today_low: boolean;
  mean7_ms: number;
  range_ms: [number, number];
  today_ms: number | null;
  cv7: number;
  cv_base: number;
  history: { day: string; mean7: number; low: number; high: number }[];
}

export interface RecoveryProfile {
  kinds: Record<"hard" | "long" | "easy", { days: number; dip_sd: number | null; n: number; personal: boolean }>;
  hard_spacing_days: number;
  half_life_h: number;
}

export interface ReadinessValidation {
  n: number;
  enough: boolean;
  rho?: number;
  p?: number;
  predictive?: boolean;
  components?: Record<string, { rho: number; p: number; n: number }>;
  suggested_weights?: Record<string, number> | null;
}

export interface SleepNeed {
  hours: number;
  personal: boolean;
  n: number;
  detail: string;
}

export interface WarningSignals {
  day: string;
  signals: { key: string; label: string }[];
  persisting: boolean;
  level: "warn" | "alert";
}

export interface StrengthSummary {
  sessions: number;
  labelled: number;
  by_category: { category: string; sets: number; reps: number; volume_kg: number; sessions: number }[];
}

export type Insights =
  | { has_data: false; goal: TrainingGoal | null }
  | {
      has_data: true;
      source_id: string;
      as_of: string;
      readiness: { day: string; score: number; label: string; components: Record<string, ReadinessComponent> } | null;
      recommendation: { headline: string; detail: string; reasons: { factor: string; tone: string; score: number }[] } | null;
      readiness_history: { day: string; score: number }[];
      findings: Finding[];
      pmc: { day: string; load: number; fitness: number; fatigue: number; form: number; acwr: number | null }[];
      weeks: WeekSummary[];
      readiness_validation: ReadinessValidation | null;
      intensity_28d: {
        zones_min: number[];
        easy_pct: number;
        moderate_pct: number;
        hard_pct: number;
        minutes: number;
        by_sport: Record<string, { easy_pct: number; moderate_pct: number; hard_pct: number; minutes: number }>;
        sessions: number;
        hard_sessions_pct: number | null;
      } | null;
      efficiency: {
        runs: { id: number; day: string; ef: number; hr: number; rhr: number; speed: number; pace_s: number; name: string }[];
        trend: {
          ref_hr: number;
          rhr: number;
          change_pct_90d: number | null;
          ci_pct_90d: [number, number] | null;
          significant: boolean;
          pace_now_s: number;
          pace_90d_ago_s: number | null;
          monthly: { month: string; ef: number; n: number; pace_s: number }[];
          n: number;
        } | null;
      };
      durability: { id: number; day: string; name: string; decoupling_pct: number; speed_cv: number; steady: boolean; minutes: number }[];
      vo2max: { day: string; value: number }[];
      sleep: {
        pattern_14d: {
          nights: number;
          avg_hours: number;
          need_hours: number;
          nights_short: number;
          debt_hours: number;
          avg_bedtime_min: number | null;
          bedtime_sd_min: number | null;
          avg_wake_min: number | null;
          wake_sd_min: number | null;
        } | null;
        need: SleepNeed;
        tonight: Tonight | null;
        target_check: Effect | null;
        regularity: { sri: number; pairs: number; midpoint_min: number; midpoint_sd_min: number } | null;
        nights: { day: string; bedtime: number | null; wake: number | null; hours: number | null }[];
      };
      effects: Effect[];
      plan: TrainingPlan | null;
      training_mode: TrainingMode;
      goal: TrainingGoal | null;
      performance: Performance;
      hrv_guided: HrvGuided | null;
      recovery: RecoveryProfile;
      warnings: WarningSignals | null;
      run_load: { acwr: number | null; km_7d: number; km_week_avg_28d: number } | null;
      strength: StrengthSummary | null;
      habits: { effects: HabitEffect[]; progress: HabitProgress[] };
      strength_content: StrengthContent | null;
      heat: { n: number; warm: number; significant: boolean; slope_pct_per_c: number | null; ci?: [number, number] } | null;
      strain: { days: { day: string; total: number; workout: number; everyday: number }[]; scale: number; calibrated_on: number; hr_max: number } | null;
      hr_zones: { method: string | null; floors: number[]; max: number | null; threshold: number | null } | null;
      analysis_pending: number;
      analysis_running: boolean;
    };

export interface VaultItemMeta {
  id: number;
  dataset: string;
  request_key: string;
  window_start: string | null;
  window_end: string | null;
  fetched_at: string;
  status: number;
  final: boolean;
  item_count: number;
  body_bytes: number;
  stored_bytes: number;
  is_file: boolean;
}

export type ProjectionStatus =
  | "reached"
  | "on_track"
  | "off_track"
  | "flat"
  | "insufficient_data"
  | "too_far";

export interface Projection {
  goal_kg: number;
  status: ProjectionStatus;
  expected: string | null;
  earliest: string | null;
  latest: string | null;
}

export interface BodyEstimate {
  bmi: number;
  bmi_category: "underweight" | "normal" | "overweight" | "obese";
  body_fat_pct: number;
  fat_mass_kg: number;
  lean_mass_kg: number;
  bmr_kcal: number;
  healthy_min_kg: number;
  healthy_max_kg: number;
  to_healthy_kg: number;
  bsa_m2: number;
  energy_kcal: { light: number; active: number; vigorous: number };
}

export interface BodyProfile {
  height_cm: number;
  birth_date: string;
  sex: "male" | "female";
}

export interface TrendPoint {
  day: string;
  weight_kg: number;
  trend_kg: number;
  band_kg: number;
  body: BodyEstimate | null;
}

export type Overview =
  | { has_data: false }
  | {
      has_data: true;
      source_id: string;
      as_of: string;
      today: string;
      coach: Brief | null;
      score: ScoreSummary | null;
      journal: { day: string; done: boolean; behaviours: Behaviour[] };
      planned_today: PlannedSessionView[];
      metrics: MetricSummary[];
      week: {
        start: string;
        activities: number;
        duration_s: number;
        distance_m: number;
        training_load: number;
      };
      recent_activities: ActivityItem[];
      weight: {
        latest_trend_kg: number | null;
        rate_kg_per_week: number | null;
        latest_reading: TrendPoint | null;
        weighed_today: boolean;
        goal_kg: number | null;
        projection: Projection | null;
        spark: Point[];
      };
    };

export interface PeriodTotals {
  sessions: number;
  hours: number;
  km: number;
  load: number;
  active_days: number;
}

export type ActivityLog =
  | { has_data: false }
  | {
      has_data: true;
      as_of: string;
      calendar: { day: string; load: number; sessions: number; minutes: number; family: string | null }[];
      year: PeriodTotals;
      last_30: PeriodTotals;
      prev_30: PeriodTotals;
      weeks: Record<string, { sessions: number; load: number; hours: number; km: number; hard_days: number; families: Record<string, number> }>;
      mix: { family: string; sessions: number; hours: number }[];
      records: { key: string; label: string; value: number; kind: "distance" | "pace" | "load" | "duration"; id: number; day: string; name: string; family: string }[];
      streak: { current: number; best: number; unit: string } | null;
    };

export interface ShareStatus {
  running: boolean;
  port: number;
  web_built_at: number | null;
  urls: string[];
  pair_url: string | null;
  qr: number[][] | null;
  secure: boolean;
}

export interface PushStatus {
  public_key: string;
  devices: { label: string; created_at: string; last_sent_at: string | null; endpoint_host: string }[];
  prefs: Record<string, boolean>;
  labels: Record<string, string>;
  recent: { kind: string; title: string; body: string; sent_at: string; delivered: number }[];
  scheduler: boolean;
  sync_every_h: number;
}

export interface WeightResponse {
  points: TrendPoint[];
  body_profile: BodyProfile | null;
  latest_trend_kg: number | null;
  rate_kg_per_week: number | null;
  rate_se_kg_per_week: number | null;
  goal_kg: number | null;
  projection: Projection | null;
  latest_body_fat_pct: number | null;
  coach: Note[];
  model: { process_var_per_day: number; measurement_var: number; rate_window_days: number };
}

export interface MetricSeries {
  metric: string;
  label: string;
  unit: string;
  higher_is_better: boolean | null;
  points: Point[];
}

export interface WeightEntries {
  entries: { day: string; weight_kg: number }[];
  today: string;
}

export type BackupStatus =
  | { configured: false }
  | {
      configured: true;
      last_success_at: string | null;
      last_attempt_at: string | null;
      snapshot: string | null;
      last_error: string | null;
      stale: boolean;
    };

export interface SourceInfo {
  id: string;
  name: string;
  status: string;
  last_synced_at: string | null;
  detail: string;
}

export interface SyncRun {
  id: number;
  source_id: string;
  status: "running" | "succeeded" | "failed" | "stopped" | "paused" | "partial" | "interrupted";
  started_at: string;
  finished_at: string | null;
  records_written: number;
  error: string | null;
  mode?: string | null;
  requests_made?: number;
  message?: string | null;
}

export interface GarminDataset {
  key: string;
  label: string;
  tier: "core" | "deep";
  kind: string;
  status: "pending" | "backfilling" | "complete" | "synced" | "unavailable";
  oldest: string | null;
  covered_from: string | null;
  calls: number;
  responses: number;
  stored_bytes: number;
  last_fetched_at: string | null;
  error: string | null;
}

export interface GarminStatus {
  busy: boolean;
  run: SyncRun | null;
  vault: { responses: number; raw_bytes: number; stored_bytes: number; files: number; file_bytes: number };
  totals: {
    activities: number;
    days: number;
    metrics: number;
    weigh_ins: number;
    first_day: string | null;
    api_calls: number;
  };
  datasets: GarminDataset[];
}

// ---- lab: how far to trust the models, and what-ifs -------------------------------------

export interface Headline {
  tone: "good" | "info" | "warn";
  text: string;
}

export interface AccuracyStats {
  n: number;
  enough: boolean;
  typical_error_pct?: number;
  ratio?: number;
  ratio_ci?: [number, number];
  bias_pct?: number;
  biased?: boolean;
  within_10_pct?: number;
  within_25_pct?: number;
  range_coverage_pct?: number | null;
  range_n?: number;
}

export interface AccuracyPoint {
  day: string;
  sport: string;
  predicted: number;
  actual: number;
}

export type LabAccuracy =
  | { has_data: false }
  | {
      has_data: true;
      as_of: string;
      min_bias_n: number;
      headline: Headline;
      explain: { q: string; a: string }[];
      plans: {
        overall: AccuracyStats;
        by_sport: Record<string, AccuracyStats>;
        recent: { id: number; day: string; sport: string; title: string; predicted: number; actual: number; error_pct: number }[];
        followed: { done: number; missed: number; of: number } | null;
        points: AccuracyPoint[];
      };
      backtest: AccuracyStats & { kind: "backtest"; window?: [string, string] | null; by_sport?: Record<string, AccuracyStats>; points?: AccuracyPoint[] };
      calibration: Record<string, { factor: number; n: number; ratio: number; ratio_ci: [number, number] }>;
      form: { n: number; median_error: number; typical_abs_error: number } | null;
    };

export type LabModel =
  | { has_data: false }
  | ({
      has_data: true;
      headline: Headline;
      explain: { q: string; a: string }[];
      explain_fatigue: { q: string; a: string }[];
      explain_saturation: { q: string; a: string }[];
      explain_channels: { q: string; a: string }[];
      fatigue: FatigueFit;
      saturation: SaturationFit;
      channels: ChannelsFit;
      model: WhatIfModel;
      performance_label: string;
      n: number;
      min_obs: number;
      valid: boolean;
      adopted: boolean;
      missing?: string;
      why_not?: string;
      tau1?: number;
      tau2?: number;
      k1?: number;
      k2?: number;
      r2?: number | null;
      default_taus?: [number, number];
      span_days?: number;
      consistent_with_default?: boolean;
      region?: { tau1: [number, number]; tau2: [number, number]; n_eff: number; points: number; of: number };
      cv?: { personal: number; default: number; mean: number; gain_vs_default_pct: number; gain_vs_mean_pct: number };
      series?: { day: string; observed: number; fitted: number }[];
      curve?: { day: string; value: number }[];
      taper?: { peak_day: number; gain_pct: number | null; range: [number, number] } | null;
    });

export interface RouteEffort {
  id: number;
  day: string;
  time_s: number;
  pace_s: number;
  distance_km: number;
  avg_hr: number | null;
  load: number;
  ef: number | null;
  temperature: number | null;
  dew_point: number | null;
  wind: number | null;
  hot: boolean | null;
  pr: boolean;
  hard: boolean;
}

export interface RouteView {
  id: number;
  name: string;
  sport: "run" | "ride";
  n: number;
  distance_km: number;
  loop: boolean | null;
  first: string;
  last: string;
  elevation_m: number | null;
  best: { id: number; day: string; time_s: number };
  median_time_s: number;
  latest: RouteEffort & { vs_prior: { time_s: number; avg_hr: number | null; ef_pct: number | null; temperature: number | null } };
  trend: { n: number; span_days: number; change_pct: number; ci_pct: [number, number]; significant: boolean } | null;
  efforts: RouteEffort[];
  notes: Finding[];
}

export type LabRoutes = { has_data: false } | { has_data: true; n_with_gps: number; routes: RouteView[]; reason: string | null };

export interface WhatIfPoint {
  day: string;
  fitness: number;
  fatigue: number;
  form: number;
  acwr: number | null;
  alt_fitness: number;
  alt_fatigue: number;
  alt_form: number;
  alt_acwr: number | null;
}

export interface WhatIfRanges {
  fitness_delta: [number, number] | null;
  next_morning_form: [number, number] | null;
  avg_form_delta: [number, number] | null;
  n_pairs: number;
  basis: string;
}

export interface WhatIfPayoff {
  status: "measured" | "unproven" | "unmeasured";
  n_hard?: number;
  needed?: number;
  per10_pct?: number | null;
  ci_per10_pct?: [number, number] | null;
  total_gain_pct?: number | null;
  items: { after: number; session_id: number; name: string; day: string; form_delta: number; payoff: { gain_pct: number; ci_pct: [number, number] } | null }[];
}

export interface WhatIfModel {
  ctl_days: number;
  atl_days: number;
  alpha: number;
  personal: boolean;
  sources: string[];
}

export interface WhatIfExtras {
  ranges: WhatIfRanges;
  zones: { before: { aerobic: number; high: number }; after: { aerobic: number; high: number }; zone3_minutes: number };
  channels: { ef_pct: number; ci: [number, number]; aerobic_hours_per_week: number; high_hours_per_week: number } | null;
  payoff: WhatIfPayoff;
  model: WhatIfModel;
  lines?: string[];
}

export interface WhatIfResult extends WhatIfExtras {
  valid: true;
  rough: boolean;
  window_days: number;
  n_days: number;
  edits: { id: number; day: string; name: string; family: string; action: string; load: number; load_after: number }[];
  end: { fitness: [number, number]; fatigue: [number, number]; form: [number, number]; fitness_delta: number; fitness_delta_pct: number | null; form_delta: number };
  next_morning: { day: string; form_delta: number; fatigue_delta: number } | null;
  avg_form_delta: number;
  acwr_days_over: [number, number];
  trajectory: WhatIfPoint[];
  performance?: { delta_pct: number | null; taus: [number, number] };
  headline: string;
}

export interface WhatIfBundle extends WhatIfExtras {
  label: string;
  n: number;
  end: WhatIfResult["end"];
  avg_form_delta: number;
  acwr_days_over: [number, number];
  rough: boolean;
  trajectory: WhatIfPoint[];
  n_days: number;
  performance?: WhatIfResult["performance"];
  headline: string;
}

export type LabWhatIf =
  | { has_data: false }
  | {
      has_data: true;
      window_days: number;
      actions: Record<"skip" | "easy" | "half", string>;
      easy_rates: Record<string, { rate: number | null; n: number }>;
      model: WhatIfModel;
      freshness: Freshness;
      explain_freshness: { q: string; a: string }[];
      items: ({ id: number; day: string; name: string; family: string; kind: "grey" | "hard_again"; load: number; load_after: number; fitness_delta: number; fitness_delta_pct: number | null; next_morning_form: number | null; rough: boolean } & WhatIfExtras)[];
      bundles: Record<string, WhatIfBundle>;
      recent: { id: number; day: string; name: string; family: string; load: number }[];
    };

// ---- goals ----------------------------------------------------------------------------------

export type GoalKind = "race" | "performance" | "distance" | "weight";
export type GoalSport = "run" | "ride" | "swim";
export type GoalBand = "likely" | "plausible" | "a stretch" | "unlikely";

export interface GoalOutlook {
  band: GoalBand;
  probability?: number;
  heuristic?: boolean;
  required_gain_pct?: number;
  per_month_pct?: number | null;
  spare_weeks?: number;
}

export interface GoalView {
  id: number;
  kind: GoalKind;
  sport: GoalSport | null;
  title: string;
  date: string | null;
  status: "active" | "achieved" | "dropped";
  spec: { distance_m?: number; label?: string; target_s?: number; key?: string; target_kg?: number };
  start_value: number | null;
  created_on: string;
  closed_on: string | null;
  days_left: number | null;
  weeks_left: number | null;
  overdue: boolean;
  state: "ok" | "no_data" | "no_basis" | "closed";
  reason?: string;
  headline: Headline;
  achieved_hint?: boolean;
  caveats?: string[];
  outlook?: GoalOutlook;
  roadmap?: { week: string; weeks_to_go: number | null; phase: string; label: string; blurb: string }[];
  // run / ride / swim performance and race goals
  basis?: string;
  horizon_days?: number;
  current_s?: number;
  required_s?: number;
  projected?: { p10_s: number; p50_s: number; p90_s: number; probability?: number };
  cs_needed_mps?: number;
  cs_gain_pct?: number;
  cs?: { cs_mps: number; n_history: number; sigma_pct: number; sigma_assumed: boolean; slope_pct_per_month: number | null };
  demonstrated?: { time_s: number; id: number; day: string; distance_m: number; name: string } | null;
  // single-session distance goals
  longest_recent?: { id: number; day: string; distance_m: number; name: string } | null;
  longest_ever?: { id: number; day: string; distance_m: number; name: string } | null;
  ladder?: { weeks: { week: number; m: number; kind: "build" | "recovery" | "easier" | "attempt" }[]; weeks_needed: number };
  earliest?: string;
  // weight goals
  current_kg?: number;
  target_kg?: number;
  gap_kg?: number;
  rate_kg_wk?: number | null;
  rate_pct_wk?: number;
  rate_flag?: "too_fast" | "wrong_way" | null;
  progress_pct?: number;
  required?: { kg_wk: number; pct_wk: number; too_fast: boolean; wrong_way: boolean };
  path?: { week: string; kg: number }[];
  earliest_safe?: string | null;
  steady?: string | null;
  projection?: { status: string; expected: string | null; earliest: string | null; latest: string | null };
}

export interface GoalsResponse {
  today: string;
  goals: GoalView[];
  plan_goal_id: number | null;
  summary: { active: number; achieved: number; next: number | null };
  has_training: boolean;
}

export interface GoalInput {
  kind: GoalKind;
  sport?: GoalSport | null;
  title?: string | null;
  date?: string | null;
  distance_m?: number | null;
  label?: string | null;
  target_s?: number | null;
  speed_kmh?: number | null;
  target_kg?: number | null;
}

export interface Freshness {
  hard: {
    n: number;
    enough: boolean;
    min: number;
    helpful?: boolean;
    significant?: boolean;
    per10_pct?: number;
    ci_per10_pct?: [number, number];
    split?: { cut: number; fresh_n: number; tired_n: number; diff_pct: number; ci_pct: [number, number] } | null;
    points?: { day: string; form: number; quality_pct: number }[];
  };
  easy: { n: number; enough: boolean; min: number; per10_pct?: number; ci_per10_pct?: [number, number]; helpful?: boolean; significant?: boolean };
}

export interface FatigueFit {
  valid: boolean;
  adopted: boolean;
  n?: number;
  missing?: string;
  why_not?: string;
  tau?: number;
  half_life_days?: number;
  default_tau?: number;
  region?: [number, number];
  cv?: { personal: number; default: number; mean: number; gain_vs_default_pct: number; gain_vs_mean_pct: number };
  series?: { day: string; observed: number; fitted: number }[];
}

export interface SaturationFit {
  valid: boolean;
  adopted: boolean;
  alpha: number;
  missing?: string;
  gain_pct?: number;
  cv?: Record<string, number>;
}

export interface ChannelsFit {
  valid: boolean;
  adopted: boolean;
  missing?: string;
  why_not?: string;
  n?: number;
  aerobic?: { pct_per_hour: number; ci: [number, number] };
  high?: { pct_per_hour: number; ci: [number, number] };
  gain_vs_total_pct?: number;
}

export type Meal = "breakfast" | "lunch" | "snack" | "dinner";

export interface FoodDish {
  id: number;
  name: string;
  unit: string;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  spread_pct: number;
  builtin: boolean;
  active: boolean;
  source: "library" | "mine";
  ref_code: string | null;
  /** Weight of one serving as eaten, in grams. */
  unit_g: number | null;
  per_100g: { kcal: number; protein_g: number; carbs_g: number; fat_g: number } | null;
  basis: "library" | "estimate";
  /** Where the numbers come from, e.g. the recipe site the source site calculated them from. */
  note: string | null;
  /** Other names for the same food, searched alongside the name. */
  aliases: string[];
  /** Household portions with their weights; the first is the default serving. */
  portions: { unit: string; grams: number }[];
  /** Can be logged by grams (it has a weight). */
  grams_ok: boolean;
}

export interface FoodEntry {
  id: number;
  day: string;
  meal: Meal;
  dish_id: number | null;
  name: string;
  servings: number;
  grams: number | null;
  kcal: number;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  spread_pct: number;
}

export interface FoodDaySummary {
  logged: boolean;
  entries: number;
  kcal: number | null;
  kcal_low: number | null;
  kcal_high: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  protein_g_per_kg: number | null;
  partial_macros: boolean;
}

export interface FoodPlan {
  /** Inputs that are missing, so targets can't be set: weight and/or profile. */
  needs: ("weight" | "profile")[];
  phase: "cut" | "gain" | "maintain";
  goal_kg: number | null;
  weight_kg: number | null;
  /** What a typical day costs: Garmin's recent mean, or the profile formula until there is a week of Garmin data. */
  reference_energy: { kcal: number; low: number; high: number; source: "garmin" | "formula"; days: number } | null;
  targets: {
    phase: "cut" | "gain" | "maintain";
    protein_g: [number, number];
    protein_per_meal_g: [number, number];
    fat_g: [number, number];
    kcal: [number, number] | null;
    pace_pct_week: [number, number] | null;
    pace_kg_week: [number, number] | null;
  } | null;
  today: { state: "not_logged" | "no_target" | "under" | "within" | "over"; remaining_kcal?: [number, number] } | null;
  balance: { days: number; intake: number; intake_range: [number, number]; burn: number; burn_range: [number, number]; balance: number; balance_range: [number, number] } | null;
  implied: { days: number; kcal: number; range: [number, number]; intake: number; trend_kg_week: number } | null;
  protein: { days: number; g: number; g_per_kg: number | null } | null;
  trend_kg_week: number | null;
  meal_protein: Partial<Record<Meal, number>>;
}

export interface FoodView {
  day: string;
  today: string;
  entries: FoodEntry[];
  summary: FoodDaySummary;
  trail: (FoodDaySummary & { day: string; burn: number | null })[];
  trail14: (FoodDaySummary & { day: string })[];
  average: { days_logged: number; days_covered: number; kcal: number; kcal_low: number; kcal_high: number; protein_g: number | null } | null;
  weight_kg: number | null;
  protein_reference_g_per_kg: [number, number];
  recent_dish_ids: number[];
  plan: FoodPlan;
  notes: Finding[];
}

export interface FoodEntryInput {
  day: string;
  meal: Meal;
  dish_id?: number;
  servings?: number;
  grams?: number;
  eating_out?: boolean;
  name?: string;
  kcal?: number;
  protein_g?: number | null;
}

export interface FoodDishInput {
  name: string;
  unit: string;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  /** Weight of one serving in grams, so the dish can also be logged by weight. */
  grams?: number;
}

// ---- check-in, recovery and outcomes ------------------------------------------------------

export type TrainingMode = "auto" | "build" | "maintain";

export interface WellbeingEntry {
  day: string;
  feel: number | null;
  soreness: number | null;
  pain_level: number | null;
  pain_area: string | null;
  illness: number | null;
  life_stress: number | null;
  note: string | null;
}

export interface BriefWellbeing {
  today: WellbeingEntry | null;
  level: "rest" | "easy" | "watch" | null;
  needed: boolean;
  notes: Finding[];
}

export interface RecoveryWins {
  title: string;
  window: number;
  items: string[];
  text: string;
}

export interface OutcomeMarker {
  key: string;
  label: string;
  unit: string;
  now: number | null;
  before: number | null;
  change: number | null;
  state: "better" | "worse" | "flat" | "missing";
  higher_is_better: boolean;
  n: [number, number];
}

export interface OutcomeContext {
  load_per_week: number;
  sessions_per_week: number;
  hard_share_pct: number | null;
  adherence_pct: number | null;
  plans: number;
  checkins: number;
  pain_days: number;
  ill_days: number;
  flat_days: number;
}

export type Outcomes =
  | { has_data: false }
  | {
      has_data: true;
      enough: false;
      reason: string;
      headline: Headline;
      lines: string[];
    }
  | {
      has_data: true;
      enough: true;
      weeks: number;
      verdict: "improving" | "slipping" | "holding" | "edging_up" | "edging_down" | "mixed" | "unclear";
      markers: OutcomeMarker[];
      now: OutcomeContext;
      before: OutcomeContext;
      headline: Headline;
      lines: string[];
    };

/** Totals over linked activities; a field no activity reported is null (missing), never 0. */
export interface EventTotals {
  count: number;
  distance_m?: number | null;
  duration_s?: number;
  moving_s?: number;
  elapsed_s?: number;
  elevation_gain_m?: number | null;
  calories?: number | null;
  training_load?: number | null;
  avg_hr?: number | null;
  max_hr?: number | null;
}

export interface EventSummary {
  id: number;
  name: string;
  start: string | null;
  end: string | null;
  span_days: number;
  families: Record<string, number>;
  totals: EventTotals;
  linked: number;
  missing: number;
}

export interface EventDay {
  day: string;
  number: number;
  totals: EventTotals;
  recovery: { sleep_h?: number; hrv_ms?: number; rhr?: number } | null;
  activities: {
    id: number;
    name: string;
    type: string;
    family: string;
    start_time_utc: string;
    timezone: string;
    local_date: string;
    duration_s: number;
    distance_m: number | null;
    elevation_gain_m: number | null;
    avg_hr: number | null;
    training_load: number | null;
  }[];
}

export interface EventDetail extends EventSummary {
  created_at: string;
  days: EventDay[];
}
