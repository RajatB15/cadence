import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Flame, Trophy } from "lucide-react";
import { motion } from "motion/react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ActivityRow } from "../components/ActivityRow";
import { CountUp } from "../components/CountUp";
import { MoreMenu } from "../components/MoreMenu";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { formatDuration, parseDay } from "../lib/format";
import { ACTIVITY_FAMILIES } from "../lib/metrics";
import type { ActivityItem, ActivityLog } from "../lib/types";

const PAGE = 25;
type Log = Extract<ActivityLog, { has_data: true }>;

const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" });
const weekFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const monthFmt = new Intl.DateTimeFormat(undefined, { month: "short" });
const recordDate = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const familyColor = (f: string | null) => (f ? ACTIVITY_FAMILIES[f]?.color : undefined) ?? ACTIVITY_FAMILIES.other.color;

function weekKey(day: string): string {
  const d = parseDay(day);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function ActivitiesPage() {
  const [family, setFamily] = useState("");
  const navigate = useNavigate();
  // "Group with other activities" on an activity's page lands here with that one already ticked.
  const start = Number(useSearchParams()[0].get("group"));
  const [grouping, setGrouping] = useState(Number.isFinite(start) && start > 0);
  const [picked, setPicked] = useState<Set<number>>(new Set(Number.isFinite(start) && start > 0 ? [start] : []));
  const selection = grouping
    ? {
        picked,
        toggle: (id: number) =>
          setPicked((p) => {
            const next = new Set(p);
            if (!next.delete(id)) next.add(id);
            return next;
          }),
      }
    : undefined;
  const query = useInfiniteQuery({
    queryKey: ["activities", family],
    queryFn: ({ pageParam }) => api.activities(PAGE, pageParam, family || undefined),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });
  const log = useQuery({ queryKey: ["activity-log", family], queryFn: () => api.activityLog(family || undefined) });
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[0]?.total ?? 0;
  const families = query.data?.pages[0]?.families ?? {};
  const all = Object.values(families).reduce((a, b) => a + b, 0);
  const options = [
    { value: "", label: `All ${all || ""}`.trim() },
    ...Object.entries(families)
      .sort((a, b) => b[1] - a[1])
      .map(([key, n]) => ({ value: key, label: `${ACTIVITY_FAMILIES[key]?.label ?? key} ${n}` })),
  ];
  const data = log.data?.has_data ? log.data : null;

  return (
    <>
      <PageHeader
        eyebrow={query.data ? `${total.toLocaleString()} sessions on record` : "Training log"}
        title={<>Every session, <em className="text-gold">on record.</em></>}
      >
        {all > 0 && <Segmented label="Activity type" options={options} value={family} onChange={setFamily} />}
        <MoreMenu
          items={[
            { label: "Treks & multisport events", hint: "Several activities combined into one", onSelect: () => navigate("/events") },
            ...(!READ_ONLY && all > 0
              ? [{ label: grouping ? "Stop grouping" : "Group activities into an event", hint: "Multi-day treks, bike + run, bike + swim", onSelect: () => { setGrouping(!grouping); setPicked(new Set()); } }]
              : []),
          ]}
        />
      </PageHeader>
      {grouping && <GroupBar picked={picked} onDone={() => { setGrouping(false); setPicked(new Set()); }} />}

      {data && (
        <div className="mb-10 space-y-6">
          <YearStats log={data} />
          <Heatmap log={data} />
          {data.records.length > 0 && <Records log={data} />}
        </div>
      )}

      {query.isPending ? (
        <LoadingBlock height={480} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <div className="surface p-12 text-center text-mute">
          No sessions yet. Run a Garmin sync from the Vault to import your history.
        </div>
      ) : (
        <Weeks items={items} log={data} selection={selection} />
      )}
      {query.hasNextPage && (
        <div className="mt-10 flex justify-center">
          <button
            type="button"
            className="pop pop-ghost"
            disabled={query.isFetchingNextPage}
            onClick={() => query.fetchNextPage()}
          >
            {query.isFetchingNextPage ? "Loading…" : `Load more · ${(total - items.length).toLocaleString()} left`}
          </button>
        </div>
      )}
    </>
  );
}

// ---- headline numbers -------------------------------------------------------------

function YearStats({ log }: { log: Log }) {
  const int = useCallback((v: number) => Math.round(v).toLocaleString(), []);
  const stats = [
    { label: "Sessions", year: log.year.sessions, now: log.last_30.sessions, prev: log.prev_30.sessions, unit: "" },
    { label: "Hours", year: log.year.hours, now: log.last_30.hours, prev: log.prev_30.hours, unit: "h" },
    { label: "Distance", year: log.year.km, now: log.last_30.km, prev: log.prev_30.km, unit: "km" },
    { label: "Active days", year: log.year.active_days, now: log.last_30.active_days, prev: log.prev_30.active_days, unit: "" },
  ];
  return (
    <section aria-label="Last 12 months" className="grid grid-cols-2 border-y border-line lg:grid-cols-4">
      {stats.map((s, i) => {
        const delta = s.prev ? ((s.now - s.prev) / s.prev) * 100 : null;
        return (
          <div
            key={s.label}
            className={clsx("px-1 py-6 sm:px-6", i % 2 === 1 && "border-l border-line", i >= 2 && "border-t border-line lg:border-t-0", i === 2 && "lg:border-l")}
          >
            <p className="eyebrow mb-3">{s.label} · 12 mo</p>
            <p className="text-4xl text-paper sm:text-5xl">
              <CountUp value={s.year} format={int} className="num" />
              {s.unit && <span className="ml-1.5 text-base text-mute">{s.unit}</span>}
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-mute">
              <span>
                30 days <span className="num text-paper">{Math.round(s.now).toLocaleString()}</span>
              </span>
              {delta != null && Math.abs(delta) >= 1 && (
                <span className={clsx("num inline-flex items-center", delta > 0 ? "text-lime" : "text-coral")}>
                  {delta > 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                  {delta >= 200 ? `${(s.now / s.prev).toFixed(0)}×` : `${Math.abs(delta).toFixed(0)}%`} vs prior 30
                </span>
              )}
            </p>
          </div>
        );
      })}
    </section>
  );
}

// ---- year heatmap -------------------------------------------------------------------

const ALPHA = ["", "40", "70", "b0", "ff"];

function Heatmap({ log }: { log: Log }) {
  const navigate = useNavigate();
  const scroller = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Log["calendar"][number] | null>(null);
  const { columns, months, cuts } = useMemo(() => {
    const loads = log.calendar.filter((d) => d.load > 0).map((d) => d.load).sort((a, b) => a - b);
    const q = (p: number) => loads[Math.min(loads.length - 1, Math.floor(p * loads.length))] ?? 0;
    const cols: Log["calendar"][] = [];
    log.calendar.forEach((d, i) => {
      (cols[Math.floor(i / 7)] ??= []).push(d);
    });
    const labels = cols.map((col, i) => {
      const first = col.find((d) => parseDay(d.day).getDate() === 1);
      return first || i === 0 ? monthFmt.format(parseDay((first ?? col[0]).day)) : "";
    });
    return { columns: cols, months: labels, cuts: [q(0.25), q(0.5), q(0.75)] };
  }, [log.calendar]);

  useEffect(() => {
    scroller.current?.scrollTo({ left: scroller.current.scrollWidth });
  }, [columns.length]);

  const level = (d: Log["calendar"][number]) =>
    d.sessions === 0 ? 0 : d.load <= cuts[0] ? 1 : d.load <= cuts[1] ? 2 : d.load <= cuts[2] ? 3 : 4;
  const totalHours = log.mix.reduce((s, m) => s + m.hours, 0) || 1;

  return (
    <section className="surface p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-2">Last 12 months</p>
          <h2 className="font-display text-3xl text-cream">
            {log.year.active_days} active days <span className="text-mute">of {log.calendar.length}</span>
          </h2>
        </div>
        {log.streak && log.streak.current > 0 && (
          <span className="chip !border-gold/50 !text-gold">
            <Flame size={12} /> {log.streak.current}-week streak of 3+ sessions
            {log.streak.current >= log.streak.best && " · best ever"}
          </span>
        )}
      </div>

      <p className="mb-3 min-h-5 text-sm text-mute" aria-live="polite">
        {hover ? (
          <>
            <span className="text-paper">{dayFmt.format(parseDay(hover.day))}</span>
            {hover.sessions
              ? ` · ${hover.sessions} session${hover.sessions > 1 ? "s" : ""} · ${formatDuration(hover.minutes * 60)} · load ${hover.load}`
              : " · rest day"}
          </>
        ) : (
          "Colour shows the main sport, brightness the load. Click a day to open it."
        )}
      </p>

      <div ref={scroller} className="overflow-x-auto pb-2">
        <div
          className="grid gap-[3px]"
          style={{ gridTemplateColumns: `26px repeat(${columns.length}, minmax(10px, 1fr))`, minWidth: columns.length * 13 + 26 }}
        >
          <span />
          {months.map((m, c) => (
            <span key={c} className="overflow-visible text-[9px] leading-[14px] whitespace-nowrap text-dim">{m}</span>
          ))}
          {["Mon", "", "Wed", "", "Fri", "", "Sun"].map((label, r) => (
            <Fragment key={r}>
              <span className="self-center text-[9px] text-dim">{label}</span>
              {columns.map((col, c) => {
                const d = col[r];
                if (!d) return <span key={c} />;
                const lv = level(d);
                return (
                  <button
                    key={d.day}
                    type="button"
                    aria-label={`${d.day}: ${d.sessions} sessions, load ${d.load}`}
                    onMouseEnter={() => setHover(d)}
                    onFocus={() => setHover(d)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => d.sessions && navigate(`/metrics/training_load?day=${d.day}`)}
                    className={clsx("aspect-square w-full transition-transform hover:scale-125", d.sessions ? "cursor-pointer" : "cursor-default")}
                    style={{ background: lv ? `${familyColor(d.family)}${ALPHA[lv]}` : "#1c1c1f" }}
                  />
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="mt-6 border-t border-line pt-5">
        <p className="eyebrow mb-3">Where your time went</p>
        <div className="flex h-2.5 overflow-hidden">
          {log.mix.map((m) => (
            <motion.div
              key={m.family}
              initial={{ width: 0 }}
              animate={{ width: `${(m.hours / totalHours) * 100}%` }}
              transition={{ duration: 0.9, ease: [0.2, 0.9, 0.1, 1] }}
              style={{ background: familyColor(m.family) }}
              title={`${ACTIVITY_FAMILIES[m.family]?.label ?? m.family}: ${m.hours} h`}
            />
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs">
          {log.mix.map((m) => (
            <li key={m.family} className="flex items-center gap-2 text-mute">
              <span className="h-2 w-2" style={{ background: familyColor(m.family) }} />
              <span className="text-paper">{ACTIVITY_FAMILIES[m.family]?.label ?? m.family}</span>
              <span className="num">
                {Math.round(m.hours)} h · {m.sessions}×
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ---- personal records -------------------------------------------------------------

function recordValue(r: Log["records"][number]): { value: string; unit: string } {
  if (r.kind === "distance") return { value: (r.value / 1000).toFixed(1), unit: "km" };
  if (r.kind === "pace") return { value: `${Math.floor(r.value / 60)}:${String(Math.round(r.value % 60)).padStart(2, "0")}`, unit: "/km" };
  if (r.kind === "duration") return { value: formatDuration(r.value), unit: "" };
  return { value: String(Math.round(r.value)), unit: "load" };
}

function Records({ log }: { log: Log }) {
  return (
    <section aria-label="Personal records">
      <p className="eyebrow mb-3 flex items-center gap-2">
        <Trophy size={13} className="text-gold" /> Personal records
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {log.records.map((r, i) => {
          const v = recordValue(r);
          const color = familyColor(r.family);
          return (
            <motion.div key={r.key} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Link
                to={`/activities/${r.id}`}
                className="surface surface-hover group relative flex h-full flex-col overflow-hidden p-5"
                style={{ borderTop: `2px solid ${color}` }}
              >
                <span
                  className="pointer-events-none absolute -top-12 -right-12 h-28 w-28 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-30"
                  style={{ background: color }}
                />
                <p className="eyebrow">{r.label}</p>
                <p className="num mt-3 text-3xl text-cream">
                  {v.value}
                  {v.unit && <span className="ml-1 text-sm text-mute">{v.unit}</span>}
                </p>
                <p className="mt-auto truncate pt-3 text-xs text-paper">{r.name}</p>
                <p className="text-[11px] text-dim">{recordDate.format(parseDay(r.day))}</p>
              </Link>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

// ---- weekly log -----------------------------------------------------------------------

function Weeks({ items, log, selection }: { items: ActivityItem[]; log: Log | null; selection?: { picked: Set<number>; toggle: (id: number) => void } }) {
  const groups = useMemo(() => {
    const out: { key: string; items: ActivityItem[] }[] = [];
    for (const a of items) {
      const key = weekKey(a.local_date);
      if (out[out.length - 1]?.key !== key) out.push({ key, items: [] });
      out[out.length - 1].items.push(a);
    }
    return out;
  }, [items]);
  const maxLoad = useMemo(() => Math.max(1, ...Object.values(log?.weeks ?? {}).map((w) => w.load)), [log]);
  const thisWeek = log ? weekKey(log.as_of) : null;

  return (
    <div className="space-y-6">
      {groups.map((g) => {
        const w = log?.weeks[g.key];
        const start = parseDay(g.key);
        const end = new Date(start);
        end.setDate(end.getDate() + 6);
        return (
          <section key={g.key} className="surface overflow-hidden">
            <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-ink/40 px-6 py-4">
              <div className="min-w-36">
                <p className="eyebrow">{g.key === thisWeek ? "This week" : "Week"}</p>
                <p className="font-display text-2xl text-cream">
                  {weekFmt.format(start)} – {weekFmt.format(end)}
                </p>
              </div>
              {w && (
                <>
                  <dl className="flex gap-5 text-sm">
                    {[
                      { k: "sessions", v: w.sessions },
                      { k: "hours", v: w.hours },
                      ...(w.km ? [{ k: "km", v: w.km }] : []),
                      { k: "load", v: w.load },
                    ].map((s) => (
                      <div key={s.k}>
                        <dd className="num text-paper">{s.v}</dd>
                        <dt className="text-[10px] tracking-widest text-dim uppercase">{s.k}</dt>
                      </div>
                    ))}
                  </dl>
                  <div className="flex min-w-32 flex-1 items-center gap-3">
                    <div className="h-1.5 flex-1 bg-slate" title={`Load ${w.load} vs your biggest week ${maxLoad}`}>
                      <motion.div
                        className="h-full bg-gold"
                        initial={{ width: 0 }}
                        animate={{ width: `${(w.load / maxLoad) * 100}%` }}
                        transition={{ duration: 0.8 }}
                      />
                    </div>
                    {w.hard_days >= 3 && (
                      <span className="chip shrink-0 !border-amber/50 !text-amber" title="Two hard days a week is the sweet spot">
                        <AlertTriangle size={11} /> {w.hard_days} hard days
                      </span>
                    )}
                  </div>
                </>
              )}
            </header>
            <ul className="divide-y divide-line px-6">
              {g.items.map((a) => (
                <ActivityRow key={a.id} a={a} selection={selection && { selected: selection.picked.has(a.id), toggle: () => selection.toggle(a.id) }} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

// ---- group into an event ---------------------------------------------------------------

function GroupBar({ picked, onDone }: { picked: Set<number>; onDone: () => void }) {
  const client = useQueryClient();
  const events = useQuery({ queryKey: ["events"], queryFn: api.events });
  const [name, setName] = useState("");
  const [target, setTarget] = useState("new");
  const ids = [...picked];
  const save = useMutation({
    mutationFn: () => (target === "new" ? api.createEvent(name, ids) : api.linkToEvent(Number(target), ids)),
    onSuccess: () => {
      for (const key of ["events", "event", "activities", "activity"]) client.invalidateQueries({ queryKey: [key] });
      onDone();
    },
  });
  const ready = ids.length > 0 && (target !== "new" || name.trim().length > 0);
  return (
    <section aria-label="Group into event" className="surface sticky top-2 z-20 mb-8 space-y-3 border-gold/40 p-5">
      <p className="text-sm text-mute">
        Pick every day or leg that belongs together (load more below to reach older ones). Activities stay as they are and keep counting on their own days; the link lasts until you unlink them.
      </p>
      <div className="flex flex-wrap items-end gap-4">
        <label className="text-xs tracking-widest text-dim uppercase">
          Event
          <select className="mt-1 block max-w-full border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold text-base normal-case" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="new">New event</option>
            {(events.data?.items ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                Add to “{e.name}”
              </option>
            ))}
          </select>
        </label>
        {target === "new" && (
          <label className="min-w-48 flex-1 text-xs tracking-widest text-dim uppercase">
            Name
            <input className="mt-1 block w-full border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold text-base normal-case" maxLength={120} placeholder="Annapurna circuit" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <button type="button" className="pop pop-lime" disabled={!ready || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : `Link ${ids.length} activit${ids.length === 1 ? "y" : "ies"}`}
        </button>
      </div>
      {save.isError && <p role="alert" className="text-sm text-coral">{save.error.message}</p>}
    </section>
  );
}
