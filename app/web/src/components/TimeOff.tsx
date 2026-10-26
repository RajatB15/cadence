import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Check, Pencil, Plane, Plus, Stethoscope, Trash2, X } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { formatShortDate } from "../lib/format";
import { KIND_LABEL, spanDays, usesText } from "../lib/trends";
import type { AwayActivity, PlanSettings, TimeOffBody, TimeOffItem, TimeOffKind, TimeOffView } from "../lib/types";
import { ErrorBlock, LoadingBlock } from "./Shell";

const field = "w-full border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold";
const KINDS = Object.keys(KIND_LABEL) as TimeOffKind[];
const ACTIVITY: { value: AwayActivity; label: string; help: string }[] = [
  { value: "none", label: "Rest", help: "No training; the week's targets shrink to the days you have." },
  { value: "light", label: "Light", help: "Walks, a short easy run or mobility; counts as 40% of a normal day." },
  { value: "full", label: "As normal", help: "You will train as usual; nothing changes." },
];
const SEVERITY = [{ value: 1, label: "Mild" }, { value: 2, label: "Moderate" }, { value: 3, label: "Severe" }];
const REFRESH = ["time-off", "overview", "insights", "planner", "trends", "outcomes"];

function Pick<T extends string | number>({ label, options, value, onPick }: { label: string; options: { value: T; label: string }[]; value: T | null; onPick: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label}>
      <p className="eyebrow mb-2">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button key={String(o.value)} type="button" role="radio" aria-checked={value === o.value} onClick={() => onPick(o.value)}
            className={clsx("min-w-16 border px-3 py-2 text-xs font-semibold tracking-wide transition-colors pointer-coarse:py-3",
              value === o.value ? "border-gold bg-gold/15 text-paper" : "border-line-strong text-mute hover:text-paper")}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

const numberOrNull = (s: string) => (s.trim() === "" ? null : Number(s));

function EntryForm({ view, item, onDone }: { view: TimeOffView; item?: TimeOffItem; onDone: () => void }) {
  const client = useQueryClient();
  const today = view.today;
  const [kind, setKind] = useState<TimeOffKind>(item?.kind ?? "sick");
  const [start, setStart] = useState(item?.start ?? today);
  const [end, setEnd] = useState(item?.end ?? "");
  const [activity, setActivity] = useState<AwayActivity | null>(item?.activity ?? null);
  const [severity, setSeverity] = useState<number | null>(item?.severity ?? 2);
  const [weeks, setWeeks] = useState(item?.return_weeks != null ? String(item.return_weeks) : "");
  const [pct, setPct] = useState(item?.return_start_pct != null ? String(item.return_start_pct) : "");
  const [note, setNote] = useState(item?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const away = kind === "travel" || kind === "vacation";
  const fallbackWeeks = away ? view.settings.away_return_weeks : view.settings.sick_return_weeks;
  const fallbackPct = away ? view.settings.away_return_pct : view.settings.sick_return_pct;
  const save = useMutation({
    mutationFn: () => {
      const body: TimeOffBody = {
        kind, start, end: end || null, activity: away ? activity : null, severity: away ? null : severity,
        return_weeks: numberOrNull(weeks), return_start_pct: numberOrNull(pct), note: note.trim() || null,
      };
      return item ? api.updateTimeOff(item.id, body) : api.createTimeOff(body);
    },
    onSuccess: () => {
      for (const k of REFRESH) client.invalidateQueries({ queryKey: [k] });
      onDone();
    },
    onError: (e: Error) => setError(e.message),
  });
  const invalid = !start || (end !== "" && end < start);
  return (
    <form className="surface space-y-5 p-4" onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }}>
      <Pick label="What is it?" options={KINDS.map((k) => ({ value: k, label: KIND_LABEL[k] }))} value={kind} onPick={setKind} />
      <div className="grid grid-cols-2 gap-4">
        <label><span className="eyebrow mb-1 block">From</span><input type="date" required className={field} value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>
          <span className="eyebrow mb-1 block">Until</span>
          <input type="date" min={start} className={field} value={end} onChange={(e) => setEnd(e.target.value)} />
          <span className="mt-1 block text-[11px] text-dim">{kind === "sick" || kind === "injury" ? "Leave empty while you're still unwell" : "Leave empty if open-ended"}</span>
        </label>
      </div>
      {away ? (
        <div>
          <Pick label="While you're away" options={ACTIVITY} value={activity ?? view.settings.away_activity} onPick={setActivity} />
          <p className="mt-2 text-[11px] text-dim">{ACTIVITY.find((a) => a.value === (activity ?? view.settings.away_activity))?.help}</p>
        </div>
      ) : (
        <div>
          <Pick label="How bad does it feel?" options={SEVERITY} value={severity} onPick={setSeverity} />
          <p className="mt-2 text-[11px] text-dim">Sets how long and how gently you ease back. Fever, chest symptoms or anything unusual: ask a clinician before training again.</p>
        </div>
      )}
      <details>
        <summary className="eyebrow cursor-pointer">Easing back afterwards · {weeks || pct ? "custom" : "from your settings"}</summary>
        <div className="mt-3 grid grid-cols-2 gap-4">
          <label><span className="eyebrow mb-1 block">Weeks</span><input type="number" inputMode="numeric" min={0} max={8} className={field} value={weeks} placeholder={`${fallbackWeeks}`} onChange={(e) => setWeeks(e.target.value)} /></label>
          <label><span className="eyebrow mb-1 block">Start at % of usual</span><input type="number" inputMode="numeric" min={20} max={100} className={field} value={pct} placeholder={`${fallbackPct}`} onChange={(e) => setPct(e.target.value)} /></label>
        </div>
        <p className="mt-2 text-[11px] text-dim">Load climbs in a straight line from the start % back to 100% over these weeks. Blank uses your settings{away ? " (and only applies after 4+ days away)" : ` scaled by how bad it felt`}.</p>
      </details>
      <label className="block"><span className="eyebrow mb-1 block">Note</span><input className={field} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional" /></label>
      {error && <p role="alert" className="text-sm text-coral">{error}</p>}
      <div className="flex gap-3">
        <button type="submit" disabled={invalid || save.isPending} className="chip text-paper disabled:opacity-40 pointer-coarse:py-3"><Check size={13} className="text-lime" /> {item ? "Save changes" : "Add"}</button>
        <button type="button" onClick={onDone} className="chip text-mute hover:text-paper pointer-coarse:py-3"><X size={13} /> Cancel</button>
      </div>
    </form>
  );
}

function Row({ item, today, onEdit }: { item: TimeOffItem; today: string; onEdit: () => void }) {
  const client = useQueryClient();
  const refresh = () => { for (const k of REFRESH) client.invalidateQueries({ queryKey: [k] }); };
  const remove = useMutation({ mutationFn: () => api.deleteTimeOff(item.id), onSuccess: refresh });
  const recover = useMutation({
    mutationFn: () => api.updateTimeOff(item.id, { kind: item.kind, start: item.start, end: today > item.start ? today : item.start, activity: item.activity, severity: item.severity, return_weeks: item.return_weeks, return_start_pct: item.return_start_pct, note: item.note }),
    onSuccess: refresh,
  });
  const Icon = item.kind === "travel" || item.kind === "vacation" ? Plane : Stethoscope;
  const upcoming = item.start > today;
  const range = item.ongoing ? `${formatShortDate(item.start)} → ongoing` : item.start === item.end ? formatShortDate(item.start) : `${formatShortDate(item.start)} → ${formatShortDate(item.end!)}`;
  return (
    <li className="flex items-start gap-3 border-b border-line/60 py-3 last:border-0">
      <Icon size={16} className="mt-1 shrink-0 text-gold" />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-paper">
          {KIND_LABEL[item.kind]} · {range} <span className="text-dim">({spanDays(item.start, item.end, today)} d{upcoming ? ", upcoming" : ""})</span>
        </p>
        <p className="mt-0.5 text-xs text-mute">{usesText(item)}</p>
        {item.note && <p className="mt-0.5 text-xs text-dim">{item.note}</p>}
        {item.ongoing && (
          <button type="button" onClick={() => recover.mutate()} disabled={recover.isPending} className="mt-2 text-xs font-semibold text-lime hover:text-paper">I'm better: end it today</button>
        )}
      </div>
      <button type="button" onClick={onEdit} aria-label="Edit" className="p-2 text-dim hover:text-paper"><Pencil size={14} /></button>
      <button type="button" onClick={() => remove.mutate()} disabled={remove.isPending} aria-label="Delete" className="p-2 text-dim hover:text-coral"><Trash2 size={14} /></button>
    </li>
  );
}

type Draft = Record<keyof Omit<PlanSettings, "away_activity">, string> & { away_activity: AwayActivity };

const SLIDERS: { key: keyof Omit<PlanSettings, "away_activity">; label: string; unit: string; step: number; help: string }[] = [
  { key: "ramp_pct", label: "Weekly ramp", unit: "% fitness / week", step: 0.5, help: "How fast load builds in a building week. Lower is gentler; still capped at 1.25 × your chronic load." },
  { key: "build_weeks", label: "Build length", unit: "weeks", step: 1, help: "Building weeks before a recovery week." },
  { key: "deload_pct", label: "Recovery week", unit: "% of usual load", step: 5, help: "How light the recovery week is." },
  { key: "away_return_weeks", label: "After a trip: ease back", unit: "weeks", step: 1, help: "Only after 4+ days away without full training." },
  { key: "away_return_pct", label: "After a trip: start at", unit: "% of usual", step: 5, help: "" },
  { key: "sick_return_weeks", label: "After illness or injury: ease back", unit: "weeks", step: 1, help: "For a moderate one; mild is half of this, severe 1.5×." },
  { key: "sick_return_pct", label: "After illness or injury: start at", unit: "% of usual", step: 5, help: "For a moderate one; mild starts higher, severe lower." },
];

function Settings({ view }: { view: TimeOffView }) {
  const client = useQueryClient();
  const toDraft = (s: PlanSettings): Draft => ({ ...Object.fromEntries(SLIDERS.map((x) => [x.key, String(s[x.key])])), away_activity: s.away_activity }) as Draft;
  const [draft, setDraft] = useState<Draft>(() => toDraft(view.settings));
  const [error, setError] = useState<string | null>(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(toDraft(view.settings));
  const atDefaults = JSON.stringify(toDraft(view.settings)) === JSON.stringify(toDraft(view.defaults));
  const save = useMutation({
    mutationFn: (reset: boolean) => api.savePlanSettings(reset
      ? Object.fromEntries([...SLIDERS.map((x) => x.key), "away_activity"].map((k) => [k, null]))
      : { ...Object.fromEntries(SLIDERS.map((x) => [x.key, Number(draft[x.key])])), away_activity: draft.away_activity }),
    onSuccess: (v) => { setDraft(toDraft(v.settings)); setError(null); for (const k of REFRESH) client.invalidateQueries({ queryKey: [k] }); },
    onError: (e: Error) => setError(e.message),
  });
  return (
    <div className="space-y-5">
      {SLIDERS.map((x) => {
        const r = view.ranges[x.key];
        const def = view.defaults[x.key];
        return (
          <label key={x.key} className="block">
            <span className="flex items-baseline justify-between gap-3 text-sm text-paper">
              {x.label}
              <span className="num text-gold">{draft[x.key]} <span className="text-[11px] text-dim">{x.unit}</span></span>
            </span>
            <input type="range" min={r.min} max={r.max} step={x.step} value={draft[x.key]} onChange={(e) => setDraft({ ...draft, [x.key]: e.target.value })} className="mt-2 w-full accent-[#d9b26a]" />
            <span className="flex justify-between text-[11px] text-dim"><span>{x.help}</span><span className="shrink-0 pl-3">usual {def}</span></span>
          </label>
        );
      })}
      <Pick label="When you travel, by default" options={ACTIVITY} value={draft.away_activity} onPick={(v) => setDraft({ ...draft, away_activity: v })} />
      {error && <p role="alert" className="text-sm text-coral">{error}</p>}
      <div className="flex gap-3">
        <button type="button" disabled={!dirty || save.isPending} onClick={() => save.mutate(false)} className="chip text-paper disabled:opacity-40 pointer-coarse:py-3"><Check size={13} className="text-lime" /> Save</button>
        <button type="button" disabled={atDefaults || save.isPending} onClick={() => save.mutate(true)} className="chip text-mute hover:text-paper disabled:opacity-40 pointer-coarse:py-3">Reset to usual</button>
      </div>
    </div>
  );
}

/** Travel, holidays, illness and injury, and how fast the plan builds and eases back. Each entry can override the defaults. */
export function TimeOffPanel() {
  const q = useQuery({ queryKey: ["time-off"], queryFn: api.timeOff });
  const [editing, setEditing] = useState<TimeOffItem | "new" | null>(null);
  if (q.isPending) return <LoadingBlock height={260} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  const view = q.data;
  const active = view.items.filter((i) => !i.end || i.end >= view.today);
  const past = view.items.filter((i) => i.end && i.end < view.today).reverse();
  return (
    <div className="space-y-8">
      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="eyebrow">Away or unwell</p>
          {!editing && <button type="button" onClick={() => setEditing("new")} className="chip text-paper pointer-coarse:py-2"><Plus size={12} className="text-gold" /> Add</button>}
        </div>
        {editing && <EntryForm key={editing === "new" ? "new" : editing.id} view={view} item={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />}
        {!editing && view.items.length === 0 && (
          <p className="text-sm text-mute">Nothing logged. Add a trip or an illness and the plan scales that week's targets and eases you back afterwards; it won't count as a miss.</p>
        )}
        {active.length > 0 && <ul className="mt-2">{active.map((i) => <Row key={i.id} item={i} today={view.today} onEdit={() => setEditing(i)} />)}</ul>}
        {past.length > 0 && (
          <details className="mt-3">
            <summary className="eyebrow cursor-pointer">Earlier · {past.length}</summary>
            <ul className="mt-2">{past.map((i) => <Row key={i.id} item={i} today={view.today} onEdit={() => setEditing(i)} />)}</ul>
          </details>
        )}
      </section>
      <section>
        <p className="eyebrow mb-1">How the plan progresses</p>
        <p className="mb-4 text-xs text-dim">Usual settings are average; change them to match how you feel. Every entry above can override its own easing back.</p>
        <Settings key={JSON.stringify(view.settings)} view={view} />
      </section>
    </div>
  );
}
