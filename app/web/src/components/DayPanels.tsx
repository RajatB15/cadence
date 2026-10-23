import { clsx } from "clsx";
import { motion } from "motion/react";
import { useMemo, type ReactNode } from "react";
import { Chart, chartBase, type ChartOption } from "./Chart";
import { ActivityRow } from "./ActivityRow";
import { RecordTable, humanize } from "./DataViews";
import type { DayDetail, Json } from "../lib/types";

type Raw = Record<string, unknown>;

// ---- helpers --------------------------------------------------------------

function obj(v: unknown): Raw | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : null;
}

function n(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
}

function at(o: unknown, ...path: string[]): unknown {
  let cur: unknown = o;
  for (const p of path) cur = obj(cur)?.[p];
  return cur;
}

/** Garmin "local" timestamps are wall-clock; represent them as UTC ms so formatting with timeZone UTC shows them verbatim. */
function wallMs(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v !== "string") return null;
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] ?? 0)) : null;
}

/** Local minus GMT offset for payloads that carry both start timestamps. */
function offsetMs(p: Raw | null): number {
  const local = wallMs(p?.startTimestampLocal);
  const gmt = wallMs(p?.startTimestampGMT);
  return local != null && gmt != null ? local - gmt : 0;
}

const clock = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
export const fmtClock = (ms: number | null) => (ms == null ? "—" : clock.format(ms));

function dur(seconds: number | null): string {
  if (seconds == null) return "—";
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
}

/** Map a Garmin descriptor list ([{...Index, ...Key}]) to key -> column index. */
function descriptors(list: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  for (const d of Array.isArray(list) ? list : []) {
    const o = obj(d);
    if (!o) continue;
    const idx = Object.entries(o).find(([k, v]) => /index$/i.test(k) && typeof v === "number")?.[1] as number | undefined;
    const key = Object.entries(o).find(([k, v]) => /key$/i.test(k) && typeof v === "string")?.[1] as string | undefined;
    if (idx != null && key) out[key] = idx;
  }
  return out;
}

function series(rows: unknown, desc: Record<string, number>, valueKey: RegExp, offset: number): [number, number][] {
  const ti = Object.entries(desc).find(([k]) => /timestamp/i.test(k))?.[1] ?? 0;
  const vi = Object.entries(desc).find(([k]) => valueKey.test(k))?.[1] ?? 1;
  return (Array.isArray(rows) ? rows : [])
    .map((r) => (Array.isArray(r) ? [r[ti], r[vi]] : [null, null]))
    .filter((p): p is [number, number] => typeof p[0] === "number" && typeof p[1] === "number" && p[1] >= 0)
    .map(([t, v]) => [t + offset, v]);
}

/** Garmin feedback enums like HRV_BALANCED_5 name a message variant, not text; show the category and variant. */
function feedbackText(code: string): string {
  const m = code.match(/^(?:[A-Z]+_)?([A-Z_]+?)_(\d+)$/);
  return m ? `${humanize(m[1].toLowerCase())} · message ${m[2]}` : humanize(code.toLowerCase());
}

// ---- building blocks -----------------------------------------------------

export function Panel({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="surface p-6 sm:p-8">
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-3xl text-cream">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Stat({ label, value, unit, color, hint }: { label: string; value: ReactNode; unit?: string; color?: string; hint?: ReactNode }) {
  // Absent fields are simply not recorded that day; omit rather than show a placeholder.
  if (value === null || value === undefined || value === "—") return null;
  return (
    <div>
      <p className="eyebrow mb-1.5">{label}</p>
      <p className="num text-3xl" style={{ color: color ?? "#ecebe6" }}>
        {value}
        {unit && <span className="ml-1 text-sm text-mute">{unit}</span>}
      </p>
      {hint && <p className="mt-1 text-xs text-dim">{hint}</p>}
    </div>
  );
}

function Stats({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-5">{children}</div>;
}

function Segments({ parts }: { parts: { label: string; value: number; color: string; detail?: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  const shown = parts.filter((p) => p.value > 0);
  return (
    <div>
      <div className="flex h-5 overflow-hidden">
        {shown.map((p) => (
          <motion.div
            key={p.label}
            initial={{ width: 0 }}
            animate={{ width: `${(p.value / total) * 100}%` }}
            transition={{ duration: 0.9, ease: [0.2, 0.9, 0.1, 1] }}
            style={{ background: p.color }}
            title={`${p.label}: ${Math.round((p.value / total) * 100)}%`}
          />
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {shown.map((p) => (
          <div key={p.label} className="border-l-2 pl-3" style={{ borderColor: p.color }}>
            <p className="eyebrow">{p.label}</p>
            <p className="num mt-1 text-lg text-paper">{p.detail ?? `${Math.round((p.value / total) * 100)}%`}</p>
            {p.detail && <p className="text-xs text-dim">{Math.round((p.value / total) * 100)}%</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Ring({ label, value, goal, unit, color }: { label: string; value: number | null; goal: number | null; unit?: string; color: string }) {
  const pct = value != null && goal ? Math.min(value / goal, 1.5) : 0;
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 128 128" className="h-28 w-28 shrink-0 -rotate-90">
        <circle cx="64" cy="64" r={r} fill="none" stroke="#1c1c1f" strokeWidth="12" />
        <motion.circle
          cx="64" cy="64" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - Math.min(pct, 1)) }}
          transition={{ duration: 1.1, ease: [0.2, 0.9, 0.1, 1] }}
        />
      </svg>
      <div>
        <p className="eyebrow">{label}</p>
        <p className="num text-3xl text-paper">
          {value != null ? Math.round(value).toLocaleString() : "—"}
          {unit && <span className="ml-1 text-sm text-mute">{unit}</span>}
        </p>
        <p className="text-xs text-dim">
          {goal ? `${Math.round(pct * 100)}% of ${Math.round(goal).toLocaleString()} goal` : "No goal set"}
        </p>
      </div>
    </div>
  );
}

function TimeChart({
  data,
  color,
  unit,
  area,
  band,
  min,
  max,
  label,
  height = 220,
}: {
  data: [number, number][];
  color: string;
  unit: string;
  area?: boolean;
  band?: [number, number] | null;
  min?: number;
  max?: number;
  label: string;
  height?: number;
}) {
  const sparse = data.length < 60;
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      useUTC: true,
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      xAxis: { ...chartBase.xAxis, type: "time", axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => fmtClock(v) } },
      yAxis: { ...chartBase.yAxis, min, max },
      tooltip: {
        ...chartBase.tooltip,
        formatter: (items: { value: [number, number] }[]) => {
          const p = items[0]?.value;
          return p ? `${fmtClock(p[0])}<br/><b style="color:${color}">${p[1]} ${unit}</b>` : "";
        },
      },
      series: [
        {
          type: "line",
          data,
          // Few samples: show each one rather than implying a continuous curve.
          symbol: sparse ? "circle" : "none",
          symbolSize: 7,
          itemStyle: { color },
          smooth: sparse ? false : 0.2,
          lineStyle: { color, width: 1.8 },
          areaStyle: area
            ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${color}66` }, { offset: 1, color: `${color}00` }] } }
            : undefined,
          markArea: band
            ? { silent: true, itemStyle: { color: "rgba(200,245,96,0.08)" }, data: [[{ yAxis: band[0] }, { yAxis: band[1] }]] }
            : undefined,
        },
      ],
    }),
    [data, color, unit, area, band, min, max, sparse],
  );
  if (data.length < 2) return null;
  return <Chart option={option} height={height} label={label} />;
}

function Missing({ what }: { what: string }) {
  return <p className="text-sm text-dim">{what} for this day isn't in the vault yet — it's fetched automatically when available.</p>;
}

// ---- metric families -----------------------------------------------------

const QUALIFIER: Record<string, string> = {
  EXCELLENT: "#5be3b0", GOOD: "#c8f560", FAIR: "#ffbe55", POOR: "#ff6a55",
  BALANCED: "#c8f560", UNBALANCED: "#ffbe55", LOW: "#ff6a55", NONE: "#5c5a55",
};

function HrvDay({ d }: { d: DayDetail }) {
  const s = obj(d.raw.hrv) ?? obj(at(d.raw.hrv_intraday, "hrvSummary"));
  const intraday = obj(d.raw.hrv_intraday);
  const b = obj(s?.baseline);
  const lowUpper = n(b?.lowUpper), balLow = n(b?.balancedLow), balHigh = n(b?.balancedUpper);
  const last = n(s?.lastNightAvg), weekly = n(s?.weeklyAvg), high = n(s?.lastNight5MinHigh);
  const status = typeof s?.status === "string" ? s.status : null;
  const readings = useMemo(
    () =>
      (Array.isArray(intraday?.hrvReadings) ? intraday.hrvReadings : [])
        .map((r) => [wallMs(obj(r)?.readingTimeLocal), n(obj(r)?.hrvValue)] as [number | null, number | null])
        .filter((p): p is [number, number] => p[0] != null && p[1] != null),
    [intraday],
  );
  const marks = [high, balHigh, weekly, last, lowUpper, balLow].filter((v): v is number => v != null);
  const scaleMax = marks.length ? Math.max(...marks) * 1.15 : 100;
  const scaleMin = marks.length ? Math.min(...marks) * 0.7 : 0;
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - scaleMin) / (scaleMax - scaleMin)) * 100))}%`;

  if (!s) return <Missing what="HRV summary" />;
  return (
    <div className="space-y-6">
      <Panel
        title="Overnight HRV"
        aside={status && <span className="chip" style={{ borderColor: `${QUALIFIER[status] ?? "#8d8a82"}88`, color: QUALIFIER[status] }}>{humanize(status.toLowerCase())}</span>}
      >
        <Stats>
          <Stat label="Last night avg" value={last} unit="ms" color="#9b8cff" />
          <Stat label="5-min high" value={high} unit="ms" />
          <Stat label="7-day avg" value={weekly} unit="ms" hint="Garmin's status uses this" />
          <Stat label="Balanced range" value={balLow != null && balHigh != null ? `${balLow}–${balHigh}` : null} unit="ms" />
          <Stat label="Readings" value={readings.length || null} hint={readings.length ? "5-minute averages" : undefined} />
        </Stats>
        {balLow != null && balHigh != null && (
          <div className="mt-8">
            <p className="eyebrow mb-3">Where you sit in your personal baseline</p>
            <div className="relative h-10">
              <div className="absolute inset-x-0 top-3 h-3 bg-coral/30" />
              {lowUpper != null && (
                <div className="absolute top-3 h-3 bg-amber/40" style={{ left: pos(lowUpper), width: `calc(${pos(balLow)} - ${pos(lowUpper)})` }} />
              )}
              <div className="absolute top-3 h-3 bg-lime/60" style={{ left: pos(balLow), width: `calc(${pos(balHigh)} - ${pos(balLow)})` }} />
              <div className="absolute top-3 h-3 bg-amber/40" style={{ left: pos(balHigh), right: 0 }} />
              {weekly != null && (
                <div className="absolute top-0 -translate-x-1/2 text-center" style={{ left: pos(weekly) }}>
                  <div className="mx-auto h-9 w-0.5 bg-cream" />
                </div>
              )}
              {last != null && (
                <div className="absolute top-1.5 h-6 w-6 -translate-x-1/2 rounded-full border-2 border-ink bg-violet" style={{ left: pos(last) }} />
              )}
            </div>
            <p className="mt-3 text-xs text-dim">
              <span className="text-violet">●</span> last night · <span className="text-cream">|</span> 7-day average ·{" "}
              <span className="text-lime">balanced</span> {balLow}–{balHigh} ms
              {lowUpper != null && <> · low below {lowUpper} ms</>}
            </p>
          </div>
        )}
        {typeof s.feedbackPhrase === "string" && s.feedbackPhrase !== "NONE" && (
          <p className="mt-6 text-sm text-mute">
            Garmin feedback: <span className="text-paper">{feedbackText(s.feedbackPhrase)}</span>
          </p>
        )}
      </Panel>
      <Panel title="Through the night" aside={intraday && <p className="eyebrow">{fmtClock(wallMs(intraday.sleepStartTimestampLocal))} → {fmtClock(wallMs(intraday.sleepEndTimestampLocal))}</p>}>
        {readings.length > 1 ? (
          <TimeChart data={readings} color="#9b8cff" unit="ms" band={balLow != null && balHigh != null ? [balLow, balHigh] : null} label="Overnight HRV readings" />
        ) : (
          <Missing what="Overnight HRV readings" />
        )}
      </Panel>
    </div>
  );
}

function HeartDay({ d }: { d: DayDetail }) {
  const hr = obj(d.raw.hr_intraday);
  const summary = obj(at(d.raw.daily_summaries, "heartRate"));
  const points = useMemo(() => (hr ? series(hr.heartRateValues, descriptors(hr.heartRateValueDescriptors), /heartrate|value/i, offsetMs(hr)) : []), [hr]);
  const resting = n(hr?.restingHeartRate) ?? n(summary?.restingValue);
  return (
    <Panel title="Heart rate, all day">
      <Stats>
        <Stat label="Resting" value={resting} unit="bpm" color="#ff6a55" />
        <Stat label="Lowest" value={n(hr?.minHeartRate) ?? n(summary?.minValue)} unit="bpm" />
        <Stat label="Highest" value={n(hr?.maxHeartRate) ?? n(summary?.maxValue)} unit="bpm" />
        <Stat label="7-day resting avg" value={n(hr?.lastSevenDaysAvgRestingHeartRate)} unit="bpm" />
        <Stat label="Samples" value={points.length ? points.length.toLocaleString() : null} />
      </Stats>
      <div className="mt-8">
        {points.length > 1 ? (
          <TimeChart data={points} color="#ff6a55" unit="bpm" label="All-day heart rate" height={260} />
        ) : (
          <Missing what="All-day heart rate" />
        )}
      </div>
    </Panel>
  );
}

function SleepDay({ d }: { d: DayDetail }) {
  const s = obj(d.raw.sleep);
  if (!s) return <Missing what="Sleep" />;
  const scores = obj(s.sleepScores) ?? {};
  const overall = obj(scores.overall);
  const need = obj(s.sleepNeed);
  const start = wallMs(s.sleepStartTimestampLocal), end = wallMs(s.sleepEndTimestampLocal);
  const stages = [
    { label: "Deep", value: n(s.deepSleepSeconds) ?? 0, color: "#5b6cff" },
    { label: "Light", value: n(s.lightSleepSeconds) ?? 0, color: "#6cc7ff" },
    { label: "REM", value: n(s.remSleepSeconds) ?? 0, color: "#9b8cff" },
    { label: "Awake", value: n(s.awakeSleepSeconds) ?? 0, color: "#ffbe55" },
    { label: "Unmeasurable", value: n(s.unmeasurableSleepSeconds) ?? 0, color: "#5c5a55" },
  ].map((p) => ({ ...p, detail: dur(p.value) }));
  const components = Object.entries(scores).filter(([k]) => k !== "overall");
  return (
    <div className="space-y-6">
      <Panel
        title="The night"
        aside={start && end ? <p className="eyebrow">{fmtClock(start)} → {fmtClock(end)}</p> : null}
      >
        <Stats>
          <Stat label="Asleep" value={dur(n(s.sleepTimeSeconds))} color="#6cc7ff" />
          <Stat label="Score" value={n(overall?.value)} color={QUALIFIER[String(overall?.qualifierKey)]} hint={overall?.qualifierKey ? humanize(String(overall.qualifierKey).toLowerCase()) : undefined} />
          <Stat label="Need" value={need ? dur((n(need.actual) ?? n(need.baseline) ?? 0) * 60) : null} hint={need ? "Garmin's estimate" : undefined} />
          <Stat label="Awakenings" value={n(s.awakeCount)} />
          <Stat label="Naps" value={n(s.napTimeSeconds) ? dur(n(s.napTimeSeconds)) : null} />
          <Stat label="Avg sleep HR" value={n(s.avgHeartRate)?.toFixed(0) ?? null} unit="bpm" />
          <Stat label="Sleep stress" value={n(s.avgSleepStress)?.toFixed(0) ?? null} />
          <Stat label="Avg SpO₂" value={n(s.averageSpO2Value)?.toFixed(0) ?? null} unit="%" hint={n(s.lowestSpO2Value) != null ? `low ${s.lowestSpO2Value}%` : undefined} />
          <Stat label="Respiration" value={n(s.averageRespirationValue)?.toFixed(1) ?? null} unit="brpm" hint={n(s.lowestRespirationValue) != null ? `${s.lowestRespirationValue}–${s.highestRespirationValue}` : undefined} />
        </Stats>
        <div className="mt-8">
          <Segments parts={stages} />
        </div>
      </Panel>
      {components.length > 0 && (
        <Panel title="Score breakdown">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {components.map(([k, v]) => {
              const o = obj(v) ?? {};
              const q = String(o.qualifierKey ?? "");
              return (
                <div key={k} className="flex items-center justify-between border-b border-line/60 py-2.5">
                  <span className="text-sm text-mute">{humanize(k)}</span>
                  <span className="flex items-center gap-3">
                    {n(o.value) != null && <span className="num text-paper">{String(o.value)}</span>}
                    <span className="chip" style={{ color: QUALIFIER[q], borderColor: `${QUALIFIER[q] ?? "#34343a"}88` }}>
                      {humanize(q.toLowerCase()) || "—"}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
          {[s.sleepScoreFeedback, s.sleepScoreInsight, s.sleepScorePersonalizedInsight].some((x) => typeof x === "string") && (
            <div className="mt-6 space-y-1 text-sm text-mute">
              {[s.sleepScoreFeedback, s.sleepScoreInsight, s.sleepScorePersonalizedInsight]
                .filter((x): x is string => typeof x === "string" && x !== "NONE")
                .map((x) => (
                  <p key={x}>Garmin insight: <span className="text-paper">{humanize(x.toLowerCase())}</span></p>
                ))}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}

function BodyBatteryDay({ d }: { d: DayDetail }) {
  const report = obj(d.raw.body_battery);
  const summary = obj(at(d.raw.daily_summaries, "bodyBattery"));
  const points = useMemo(
    () => (report ? series(report.bodyBatteryValuesArray, descriptors(report.bodyBatteryValueDescriptorDTOList), /level|value/i, offsetMs(report)) : []),
    [report],
  );
  const events = [report?.bodyBatteryActivityEvent, summary?.activityEvents].find((e) => Array.isArray(e) && e.length) as Json[] | undefined;
  const feedback = obj(summary?.dynamicFeedbackEvent) ?? obj(report?.bodyBatteryDynamicFeedbackEvent);
  return (
    <Panel title="Energy through the day">
      <Stats>
        <Stat label="Peak" value={n(summary?.maxValue)} color="#c8f560" />
        <Stat label="Low" value={n(summary?.minValue)} />
        <Stat label="Charged" value={n(report?.charged) ?? n(summary?.chargedValue)} color="#5be3b0" />
        <Stat label="Drained" value={n(report?.drained) ?? n(summary?.drainedValue)} color="#ff6a55" />
        <Stat label="Latest" value={n(summary?.latestValue)} />
      </Stats>
      <div className="mt-8">
        {points.length > 1 ? (
          <TimeChart data={points} color="#c8f560" unit="" area min={0} max={100} label="Body Battery timeline" height={240} />
        ) : (
          <Missing what="Body Battery timeline" />
        )}
      </div>
      {feedback && typeof feedback.bodyBatteryLevel === "string" && (
        <p className="mt-4 text-sm text-mute">Garmin: <span className="text-paper">{humanize(String(feedback.feedbackShortType ?? feedback.bodyBatteryLevel).toLowerCase())}</span></p>
      )}
      {events && (
        <div className="mt-6">
          <p className="eyebrow mb-3">What moved it</p>
          <RecordTable rows={events} />
        </div>
      )}
    </Panel>
  );
}

function StressDay({ d }: { d: DayDetail }) {
  const s = obj(at(d.raw.daily_summaries, "stress"));
  if (!s) return <Missing what="Stress" />;
  const ms = (k: string) => (n(s[k]) ?? 0) / 1000;
  const parts = [
    { label: "Rest", value: ms("restDurationInMillis"), color: "#6cc7ff" },
    { label: "Low", value: ms("lowStressDurationInMillis"), color: "#ffd98a" },
    { label: "Medium", value: ms("mediumStressDurationInMillis"), color: "#ffbe55" },
    { label: "High", value: ms("highStressDurationInMillis"), color: "#ff6a55" },
    { label: "Activity", value: ms("activityDurationInMillis"), color: "#5c5a55" },
    { label: "Unmeasured", value: ms("uncategorizedDurationInMillis"), color: "#34343a" },
  ].map((p) => ({ ...p, detail: dur(p.value) }));
  return (
    <Panel title="Stress through the day" aside={typeof s.qualifier === "string" && <span className="chip">{humanize(s.qualifier.toLowerCase())}</span>}>
      <Stats>
        <Stat label="Average" value={n(s.avgLevel)} color="#ffbe55" />
        <Stat label="Peak" value={n(s.maxLevel)} />
        <Stat label="Measured" value={dur(ms("totalDurationInMillis"))} />
        <Stat label="Rest" value={dur(ms("restDurationInMillis"))} color="#6cc7ff" />
        <Stat label="High stress" value={dur(ms("highStressDurationInMillis"))} color="#ff6a55" />
      </Stats>
      <div className="mt-8">
        <Segments parts={parts} />
      </div>
    </Panel>
  );
}

function MovementDay({ d }: { d: DayDetail }) {
  const row = obj(d.raw.daily_summaries);
  if (!row) return <Missing what="Daily summary" />;
  const steps = obj(at(row, "movement", "steps"));
  const floors = obj(at(row, "movement", "floorsAscended"));
  const im = obj(row.intensityMinutes);
  const cal = obj(row.calories);
  const moderate = n(im?.moderate) ?? 0, vigorous = n(im?.vigorous) ?? 0;
  return (
    <div className="space-y-6">
      <Panel title="Movement">
        <div className="grid gap-8 md:grid-cols-3">
          <Ring label="Steps" value={n(steps?.value)} goal={n(steps?.goal)} color="#5be3b0" />
          <Ring label="Floors" value={n(floors?.value)} goal={n(floors?.goal)} color="#5be3b0" />
          <Ring label="Intensity minutes" value={moderate + 2 * vigorous} goal={n(im?.goal) ? n(im?.goal)! / 7 : null} unit="pts" color="#ff9a5b" />
        </div>
        <div className="mt-8">
          <Stats>
            <Stat label="Distance" value={n(steps?.distanceInMeters) != null ? (n(steps?.distanceInMeters)! / 1000).toFixed(2) : null} unit="km" />
            <Stat label="Moderate" value={moderate} unit="min" />
            <Stat label="Vigorous" value={vigorous} unit="min" hint="counts double" />
            <Stat label="Weekly goal" value={n(im?.goal)} unit="min" />
            <Stat label="Floors down" value={n(at(row, "movement", "floorsDescended", "value"))} />
          </Stats>
        </div>
      </Panel>
      {cal && (
        <Panel title="Energy">
          <Segments
            parts={[
              { label: "Resting (BMR)", value: n(cal.burnedResting) ?? 0, color: "#5c5a55", detail: `${n(cal.burnedResting) ?? 0} kcal` },
              { label: "Active", value: n(cal.burnedActive) ?? 0, color: "#ff9a5b", detail: `${n(cal.burnedActive) ?? 0} kcal` },
            ]}
          />
          <div className="mt-6">
            <Stats>
              <Stat label="Total burned" value={n(cal.burnedTotal)} unit="kcal" />
              <Stat label="Eaten" value={n(cal.consumedValue)} unit="kcal" />
              <Stat label="Eating goal" value={n(cal.consumedGoal)} unit="kcal" />
            </Stats>
          </div>
        </Panel>
      )}
    </div>
  );
}

function Spo2Day({ d }: { d: DayDetail }) {
  const p = obj(d.raw.spo2);
  const summary = obj(at(d.raw.daily_summaries, "pulseOx"));
  const hourly = useMemo(() => (p ? series(p.spO2HourlyAverages, descriptors(p.spO2HourlyAveragesDescriptorList), /spo2|value/i, offsetMs(p)) : []), [p]);
  return (
    <Panel title="Blood oxygen">
      <Stats>
        <Stat label="Average" value={n(p?.averageSpO2) ?? n(summary?.avgValue)} unit="%" color="#ff6a55" />
        <Stat label="Lowest" value={n(p?.lowestSpO2) ?? n(summary?.minValue)} unit="%" />
        <Stat label="During sleep" value={n(p?.avgSleepSpO2)?.toFixed(0) ?? null} unit="%" />
        <Stat label="7-day avg" value={n(p?.lastSevenDaysAvgSpO2)?.toFixed(1) ?? null} unit="%" />
        <Stat label="Altitude" value={n(summary?.avgAltitudeInMeters)?.toFixed(0) ?? null} unit="m" />
      </Stats>
      <div className="mt-8">
        {hourly.length > 1 ? <TimeChart data={hourly} color="#ff6a55" unit="%" label="Hourly SpO₂" /> : <Missing what="Hourly SpO₂" />}
      </div>
    </Panel>
  );
}

function RespirationDay({ d }: { d: DayDetail }) {
  const r = obj(at(d.raw.daily_summaries, "respiration"));
  const s = obj(d.raw.sleep);
  return (
    <Panel title="Breathing">
      <Stats>
        <Stat label="Waking avg" value={n(r?.avgValue)} unit="brpm" color="#6cc7ff" />
        <Stat label="Range" value={n(r?.minValue) != null ? `${r!.minValue}–${r!.maxValue}` : null} unit="brpm" />
        <Stat label="Latest" value={n(r?.latestValue)} unit="brpm" />
        <Stat label="Asleep avg" value={n(s?.averageRespirationValue)?.toFixed(1) ?? null} unit="brpm" />
        <Stat label="Asleep range" value={n(s?.lowestRespirationValue) != null ? `${s!.lowestRespirationValue}–${s!.highestRespirationValue}` : null} unit="brpm" />
      </Stats>
    </Panel>
  );
}

function TrainingDay({ d }: { d: DayDetail }) {
  return (
    <Panel title="Sessions this day" aside={<p className="eyebrow">{d.activities.length} recorded</p>}>
      {d.activities.length ? (
        <ul className="divide-y divide-line">
          {d.activities.map((a) => (
            <ActivityRow key={a.id} a={a} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-dim">Rest day — no sessions recorded.</p>
      )}
    </Panel>
  );
}

function FitnessAgeDay({ d }: { d: DayDetail }) {
  const raw = d.raw.fitness_age;
  const fa = obj(Array.isArray(raw) ? raw[0] : raw);
  if (!fa) return <Missing what="Fitness age" />;
  const components = Object.entries(obj(fa.components) ?? {}).map(([name, v]) => ({ component: humanize(name), ...(obj(v) ?? {}) }));
  return (
    <Panel title="Fitness age">
      <Stats>
        <Stat label="Fitness age" value={n(fa.fitnessAge)?.toFixed(1) ?? null} unit="yrs" color="#d9b26a" />
        <Stat label="Actual age" value={n(fa.chronologicalAge)} unit="yrs" />
        <Stat label="Achievable" value={n(fa.achievableFitnessAge)?.toFixed(1) ?? null} unit="yrs" />
        <Stat label="Previous" value={n(fa.previousFitnessAge)?.toFixed(1) ?? null} unit="yrs" />
      </Stats>
      {components.length > 0 && (
        <div className="mt-8">
          <p className="eyebrow mb-3">What drives it</p>
          <RecordTable rows={components} />
        </div>
      )}
    </Panel>
  );
}

function HydrationDay({ d }: { d: DayDetail }) {
  const h = obj(at(d.raw.daily_summaries, "hydration"));
  return (
    <Panel title="Hydration">
      <Ring label="Water" value={n(h?.consumedInFractionalMl)} goal={n(h?.goalInFractionalMl) ?? n(h?.goalInMl)} unit="ml" color="#6cc7ff" />
    </Panel>
  );
}

const FAMILY: Record<string, (props: { d: DayDetail }) => ReactNode> = {
  hrv: HrvDay, hrv_weekly: HrvDay,
  resting_hr: HeartDay,
  sleep_hours: SleepDay, sleep_score: SleepDay, deep_sleep_h: SleepDay, rem_sleep_h: SleepDay, sleep_stress: SleepDay,
  body_battery: BodyBatteryDay, body_battery_low: BodyBatteryDay,
  stress: StressDay,
  steps: MovementDay, floors: MovementDay, intensity_minutes: MovementDay, active_calories: MovementDay,
  total_calories: MovementDay, calories_consumed: MovementDay,
  spo2: Spo2Day,
  respiration: RespirationDay,
  training_load: TrainingDay, vo2max: TrainingDay,
  fitness_age: FitnessAgeDay,
  hydration_ml: HydrationDay,
};

export function MetricDayPanels({ metric, d }: { metric: string; d: DayDetail }) {
  const Family = FAMILY[metric];
  return (
    <div className={clsx("space-y-6")}>
      {Family && <Family d={d} />}
      {Family !== TrainingDay && d.activities.length > 0 && <TrainingDay d={d} />}
    </div>
  );
}
