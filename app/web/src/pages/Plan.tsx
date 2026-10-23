import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Bike, CheckCircle2, CircleDashed, Dumbbell, Footprints, ImageUp, Trash2, Waves, XCircle } from "lucide-react";
import { motion } from "motion/react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { PlanOption, PlannedSessionView, Prediction, Sport } from "../lib/types";

const SPORTS: { value: Sport; label: string }[] = [
  { value: "run", label: "Run" }, { value: "ride", label: "Ride" }, { value: "swim", label: "Swim" }, { value: "strength", label: "Strength" },
];
const SPORT_ICON = { run: Footprints, ride: Bike, swim: Waves, strength: Dumbbell } as const;
const weekday = new Intl.DateTimeFormat(undefined, { weekday: "short" });
const parse = (d: string) => new Date(`${d}T12:00:00`);
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`;

export function PlanPage() {
  const week = useQuery({ queryKey: ["planner"], queryFn: api.plannerWeek });
  const [day, setDay] = useState<string | null>(null);
  if (week.isPending) return <LoadingBlock height={520} />;
  if (week.isError) return <ErrorBlock error={week.error} retry={() => week.refetch()} />;
  const w = week.data;
  const upcoming = w.days.filter((d) => d.day >= w.today);
  const past = w.days.filter((d) => d.day < w.today && d.plans.length);
  const selected = day ?? w.today;
  const plans = w.days.find((d) => d.day === selected)?.plans ?? [];
  const p = w.projection;
  return (
    <>
      <PageHeader eyebrow="Next 7 days" title={<>Plan your <em className="text-gold">week.</em></>} />
      {p && (
        <p className="-mt-6 mb-8 text-sm text-mute">
          Following the plan (~{p.weekly_load} load a week) takes your fitness from <span className="num text-sky">{p.fitness_now.toFixed(0)}</span> to about{" "}
          <span className="num text-sky">{p.fitness_4w.toFixed(0)}</span> in 4 weeks.
        </p>
      )}
      <div className="mb-8 grid grid-cols-7 gap-1.5 sm:gap-3">
        {upcoming.map((d) => {
          const active = d.day === selected;
          return (
            <button key={d.day} type="button" onClick={() => setDay(d.day)} aria-pressed={active}
              className={clsx("flex min-h-20 flex-col items-center gap-1.5 border px-1 py-2.5 text-center transition-colors",
                active ? "border-gold bg-gold/10" : "border-line bg-ink/40 hover:border-line-strong")}>
              <span className="eyebrow !text-[10px]">{d.day === w.today ? "Today" : weekday.format(parse(d.day))}</span>
              <span className="num text-lg text-cream">{parse(d.day).getDate()}</span>
              <span className="flex gap-0.5">
                {d.plans.map((pl) => {
                  const Icon = SPORT_ICON[pl.sport];
                  return <Icon key={pl.id} size={12} className={pl.status === "done" ? "text-lime" : "text-gold"} />;
                })}
              </span>
            </button>
          );
        })}
      </div>
      <DayPlans day={selected} plans={plans} today={w.today} />
      <AddSession day={selected} today={w.today} />
      {past.length > 0 && <PastWeek days={past} />}
    </>
  );
}

function DayPlans({ day, plans, today }: { day: string; plans: PlannedSessionView[]; today: string }) {
  const client = useQueryClient();
  const remove = useMutation({
    mutationFn: api.deletePlan,
    onSuccess: () => ["planner", "overview"].forEach((k) => client.invalidateQueries({ queryKey: [k] })),
  });
  if (!plans.length) return null;
  return (
    <section className="mb-8 space-y-3">
      <p className="eyebrow">{day === today ? "Planned today" : `Planned for ${formatDate(day)}`}</p>
      {plans.map((p) => {
        const Icon = SPORT_ICON[p.sport];
        return (
          <div key={p.id} className="surface flex items-start gap-4 p-5" style={{ borderLeft: `3px solid ${p.status === "done" ? "#c8f560" : "#d9b26a"}` }}>
            <Icon size={20} className="mt-0.5 shrink-0 text-gold" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-paper">{p.title}</p>
              <p className="mt-1 text-sm text-mute">{p.detail}</p>
              <p className="mt-2 text-xs text-dim">
                Predicted load {p.predicted.load}
                {p.status === "done" && p.activity && (
                  <> · done: <Link className="text-lime underline-offset-2 hover:underline" to={`/activities/${p.activity.id}`}>{p.activity.name}</Link>, load {Math.round(p.activity.load ?? 0)}</>
                )}
              </p>
            </div>
            {p.status !== "done" && (
              <button type="button" aria-label="Remove" disabled={remove.isPending} onClick={() => remove.mutate(p.id)}
                className="grid h-10 w-10 shrink-0 place-items-center border border-line text-dim hover:text-coral">
                <Trash2 size={15} />
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}

function AddSession({ day, today }: { day: string; today: string }) {
  const [sport, setSport] = useState<Sport>("run");
  const [text, setText] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const options = useQuery({
    queryKey: ["planner-options", day, sport, sport === "strength" ? text : ""],
    queryFn: () => api.plannerOptions(day, sport, sport === "strength" ? text : undefined),
    enabled: sport !== "strength" || text.trim().length > 3,
  });
  const read = useMutation({
    mutationFn: async (files: File[]) => {
      const parts = [];
      for (const f of files) parts.push((await api.readScreenshot(f)).text);
      return parts.join("\n");
    },
    onSuccess: setText,
  });
  return (
    <section className="surface mb-8 p-5 sm:p-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">{day === today ? "Today" : formatDate(day)}</p>
          <h2 className="font-display text-3xl text-cream">Add a session</h2>
        </div>
        <Segmented label="Sport" options={SPORTS} value={sport} onChange={setSport} />
      </div>
      {sport === "strength" && (
        <div className="mb-6 space-y-3">
          <p className="text-sm text-mute">Upload the class screenshot now; when the session syncs, it's named automatically.</p>
          <input ref={picker} type="file" accept="image/*" multiple hidden onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length) read.mutate(files);
            e.target.value = "";
          }} />
          <button type="button" className="pop pop-lime w-full justify-center sm:w-auto" disabled={read.isPending} onClick={() => picker.current?.click()}>
            <ImageUp size={18} /> {read.isPending ? "Reading screenshot…" : text ? "Replace screenshot" : "Upload screenshot"}
          </button>
          {read.isError && <p className="text-sm text-coral">{(read.error as Error).message}</p>}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} aria-label="Class text" placeholder="…or type the class: block titles on their own lines"
            className="w-full border border-line-strong bg-ink/40 p-3 font-mono text-base text-paper outline-none focus:border-gold sm:text-sm" />
        </div>
      )}
      {options.isPending && options.fetchStatus !== "idle" ? (
        <LoadingBlock height={240} />
      ) : options.isError ? (
        <ErrorBlock error={options.error} retry={() => options.refetch()} />
      ) : options.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {options.data.options.map((o, i) => <OptionCard key={o.key} o={o} day={day} index={i} strengthText={sport === "strength" ? text : undefined} />)}
        </div>
      ) : null}
      {sport !== "run" && sport !== "strength" && (
        <p className="mt-4 text-xs text-dim">
          {sport === "swim"
            ? "Few swims in your history: predictions borrow from your other sports until you have a handful."
            : "No power meter data: targets use heart rate."}
        </p>
      )}
    </section>
  );
}

function OptionCard({ o, day, index, strengthText }: { o: PlanOption; day: string; index: number; strengthText?: string }) {
  const client = useQueryClient();
  const plan = useMutation({
    mutationFn: () => api.createPlan(day, o.sport, o.key, strengthText),
    onSuccess: () => ["planner", "overview", "planner-options"].forEach((k) => client.invalidateQueries({ queryKey: [k] })),
  });
  return (
    <motion.article initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }}
      className={clsx("flex flex-col border bg-ink/40 p-5", o.recommended ? "border-lime/60" : "border-line")}>
      <div className="flex flex-wrap items-center gap-2">
        {o.recommended && <span className="chip text-lime" style={{ borderColor: "#c8f56066" }}>Recommended</span>}
        {o.caution && <span className="chip text-amber" style={{ borderColor: "#ffbe5566" }}>Not ideal</span>}
        <span className="eyebrow">{o.minutes ? `${o.minutes} min` : ""}</span>
      </div>
      <h3 className="mt-2 font-display text-2xl text-cream">{o.title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-mute">{o.detail}</p>
      {(o.why || o.caution) && <p className={clsx("mt-2 text-sm", o.caution ? "text-amber" : "text-paper")}>{o.caution ?? o.why}</p>}
      <Outcomes p={o.predicted} />
      <button type="button" className={clsx("pop mt-5 self-start", o.recommended && "pop-lime")} disabled={plan.isPending || plan.isSuccess} onClick={() => plan.mutate()}>
        {plan.isSuccess ? "Planned" : "Plan this"}
      </button>
      {plan.isError && <p className="mt-2 text-xs text-coral">{(plan.error as Error).message}</p>}
    </motion.article>
  );
}

function Outcomes({ p }: { p: Prediction }) {
  const rows: [string, string][] = [
    ["Load", `${p.load}${p.load_range ? ` (your similar: ${p.load_range[0]}–${p.load_range[1]})` : ""}`],
  ];
  if (p.day_strain != null) rows.push(["Day strain", `≈ ${p.day_strain}`]);
  if (p.fitness) rows.push(["Fitness", `${p.fitness[0].toFixed(1)} → ${p.fitness[1].toFixed(1)} (${signed(p.fitness[1] - p.fitness[0])})`]);
  if (p.form_tomorrow != null) rows.push(["Form tomorrow", `${p.form_tomorrow > 0 ? "+" : ""}${p.form_tomorrow.toFixed(0)}`]);
  if (p.acwr_tomorrow) rows.push(["Acute:chronic", p.acwr_tomorrow.toFixed(2)]);
  if (p.readiness_load) rows.push(["Readiness (load part)", `${p.readiness_load[0]} → ${p.readiness_load[1]}`]);
  if (p.recovery_days != null) rows.push(["Recovered in", `~${p.recovery_days} day${p.recovery_days === 1 ? "" : "s"}${p.recovery_personal ? " (your HRV)" : ""}`]);
  if (p.aerobic_te != null) rows.push(["Aerobic effect", `~${p.aerobic_te} (Garmin TE, like sessions)`]);
  return (
    <div className="mt-4 border-t border-line pt-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-dim">{k}</dt>
            <dd className="num text-paper">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs leading-relaxed text-mute"><span className="text-gold">Builds:</span> {p.builds}</p>
      {p.confidence === "general" && <p className="mt-1 text-xs text-dim">General estimate: not enough similar sessions of yours yet.</p>}
      {p.basis === "other sports" && <p className="mt-1 text-xs text-dim">Estimated from your other sports at this effort.</p>}
    </div>
  );
}

function PastWeek({ days }: { days: { day: string; plans: PlannedSessionView[] }[] }) {
  const all = days.flatMap((d) => d.plans);
  const done = all.filter((p) => p.status === "done").length;
  return (
    <section className="surface p-5 sm:p-8">
      <p className="eyebrow mb-1">Last 7 days</p>
      <h2 className="font-display text-3xl text-cream">{done} of {all.length} planned sessions done</h2>
      <ul className="mt-4 divide-y divide-line">
        {all.map((p) => (
          <li key={p.id} className="flex items-center gap-3 py-3 text-sm">
            {p.status === "done" ? <CheckCircle2 size={16} className="text-lime" /> : p.status === "missed" ? <XCircle size={16} className="text-coral" /> : <CircleDashed size={16} className="text-dim" />}
            <span className="min-w-0 flex-1 truncate text-paper">{p.title}</span>
            <span className="num shrink-0 text-xs text-dim">
              {formatDate(p.day)} · predicted {p.predicted.load}{p.activity?.load != null ? ` · actual ${Math.round(p.activity.load)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
