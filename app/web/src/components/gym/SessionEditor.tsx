import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { formatDate } from "../../lib/format";
import { ArrowLeftRight, BookOpen, ChevronDown, ChevronUp, Pencil, Plus, Timer, Trash2, X } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { api } from "../../lib/api";
import { amount, appendTo, defaultStep, exerciseIds, moveAt, pathKey, removeAt, updateAt } from "../../lib/gymSteps";
import type { GymDraft, GymExercise, GymExerciseStep, GymGroupStep, GymSetting, GymStep } from "../../lib/types";
import { Segmented } from "../Shell";
import { ExerciseGuide } from "./ExerciseGuide";
import { ExercisePicker } from "./ExercisePicker";
import { SwapSheet } from "./SwapSheet";
import { PATTERN_LABEL, useGymLibrary } from "./useGym";

type Picker = { mode: "add"; group: number[] | null } | { mode: "group" } | { mode: "replace"; path: number[] };
const SETTINGS = [{ value: "gym" as GymSetting, label: "Full gym" }, { value: "home" as GymSetting, label: "Home" }];
const input = "num w-full border-b-2 border-line-strong bg-transparent py-2 pointer-coarse:py-3 text-lg text-paper outline-none focus:border-gold";

function rest(s: number | undefined) {
  return s ? `rest ${s >= 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : `${s} s`}` : "";
}

function Num({ label, value, onChange, max }: { label: string; value: number | undefined; onChange: (v: number | undefined) => void; max?: number }) {
  return (
    <label className="block min-w-[5.5rem] flex-1">
      <span className="eyebrow">{label}</span>
      <input className={input} inputMode="numeric" value={value ?? ""} aria-label={label}
        onChange={(e) => { const t = e.target.value.replace(/[^0-9.]/g, ""); onChange(t === "" ? undefined : Math.min(Number(t), max ?? 99999)); }} />
    </label>
  );
}

export function SessionEditor({ draft, onChange, onSave, saving, saveLabel, dirty, onDelete, onPlan, planning, planned, scheduled = [], onRemoveScheduled, onRefreshScheduled, scheduleBusy, error }: {
  draft: GymDraft;
  onChange: (d: GymDraft) => void;
  onSave: () => void;
  saving: boolean;
  saveLabel: string;
  dirty: boolean;
  onDelete?: () => void;
  onPlan: (day: string, hour: number | null) => void;
  planning: boolean;
  planned?: string | null;
  scheduled?: { plan_id: number; day: string; start_hour: number | null; logged: boolean }[];
  onRemoveScheduled?: (planId: number) => void;
  onRefreshScheduled?: (planId: number) => void;
  scheduleBusy?: boolean;
  error?: string | null;
}) {
  const lib = useGymLibrary();
  const [editing, setEditing] = useState<string | null>(null);
  const [guide, setGuide] = useState<string | null>(null);
  const [swap, setSwap] = useState<{ path: number[]; id: string } | null>(null);
  const [picker, setPicker] = useState<Picker | null>(null);
  const [converted, setConverted] = useState<{ changes: { from: string; to: string | null; why: string }[]; prev: GymDraft } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const taken = new Set(scheduled.map((p) => p.day));
  const [day, setDay] = useState(() => Array.from({ length: 8 }, (_, i) => localDay(i)).find((d) => !taken.has(d)) ?? localDay(0));
  const [hour, setHour] = useState<number | null>(null);
  const steps = draft.steps;
  const deferred = useDeferredValue(steps);
  const preview = useQuery({ queryKey: ["gym", "preview", JSON.stringify(deferred)], queryFn: () => api.gymPreview(deferred), enabled: deferred.length > 0, staleTime: 30_000, retry: false });
  const set = (next: GymStep[]) => onChange({ ...draft, steps: next });
  const run = (p: Promise<unknown>) => p.catch((e: Error) => setFailed(e.message || "That didn’t work."));

  const changeSetting = (setting: GymSetting) => {
    if (setting === draft.setting) return;
    if (steps.length === 0) return onChange({ ...draft, setting });
    setFailed(null);
    run(api.gymConvert(steps, setting).then((r) => {
      setConverted({ changes: r.changes, prev: draft });
      onChange({ ...draft, setting, steps: r.steps });
    }));
  };
  const swapTo = (path: number[], id: string) => {
    setFailed(null);
    run(api.gymSwap({ steps, path, exercise: id, setting: draft.setting }).then((r) => { set(r.steps); setSwap(null); setPicker(null); }));
  };
  const picked = (ex: GymExercise) => {
    if (!picker) return;
    if (picker.mode === "replace") return swapTo(picker.path, ex.id);
    const step = defaultStep(ex);
    set(picker.mode === "group" ? [...steps, { type: "group", title: "Round", rounds: 3, steps: [step] }] : appendTo(steps, picker.group, step));
    setPicker(null);
  };
  const nameOf = (s: GymExerciseStep) => (s.exercise ? lib.byId.get(s.exercise)?.name ?? s.exercise : s.name ?? "Exercise");

  const renderList = (list: GymStep[], base: number[]) => (
    <ul className="space-y-2">
      {list.map((s, i) => {
        const path = [...base, i];
        const key = pathKey(path);
        const controls = (
          <span className="flex shrink-0 items-center gap-0.5">
            <IconBtn label="Move up" onClick={() => set(moveAt(steps, path, -1))} disabled={i === 0}><ChevronUp size={16} /></IconBtn>
            <IconBtn label="Move down" onClick={() => set(moveAt(steps, path, 1))} disabled={i === list.length - 1}><ChevronDown size={16} /></IconBtn>
            <IconBtn label="Remove" onClick={() => set(removeAt(steps, path))}><Trash2 size={16} /></IconBtn>
          </span>
        );
        if (s.type === "rest") {
          return (
            <li key={key} className="flex items-center justify-between gap-3 rounded-2xl border border-dashed border-line px-4 py-3 text-sm text-mute">
              <span className="flex items-center gap-2"><Timer size={14} /> Rest
                <input aria-label="Rest seconds" className="num w-16 border-b border-line-strong bg-transparent text-center text-paper outline-none" inputMode="numeric" value={s.seconds}
                  onChange={(e) => set(updateAt(steps, path, () => ({ type: "rest", seconds: Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1) })))} /> s</span>
              {controls}
            </li>
          );
        }
        if (s.type === "group") {
          const g = s as GymGroupStep;
          return (
            <li key={key} className="rounded-2xl border border-line bg-white/[0.02] p-3 sm:p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
                  <input aria-label="Block name" className="min-w-[8rem] flex-1 border-b border-line-strong bg-transparent py-2 pointer-coarse:py-3 font-display text-xl text-cream outline-none focus:border-gold" value={g.title} maxLength={60} placeholder="Block name"
                    onChange={(e) => set(updateAt(steps, path, (x) => ({ ...(x as GymGroupStep), title: e.target.value })))} />
                  <label className="flex items-center gap-2 text-sm text-mute">Rounds
                    <input aria-label="Rounds" className="num w-16 border-b border-line-strong bg-transparent py-2 pointer-coarse:py-3 text-center text-paper outline-none" inputMode="numeric" value={g.rounds}
                      onChange={(e) => set(updateAt(steps, path, (x) => ({ ...(x as GymGroupStep), rounds: Math.min(50, Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1)) })))} />
                  </label>
                </div>
                {controls}
              </div>
              {renderList(g.steps, path)}
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className="chip text-mute hover:text-paper" onClick={() => setPicker({ mode: "add", group: path })}><Plus size={12} /> Exercise</button>
                <button type="button" className="chip text-mute hover:text-paper" onClick={() => set(appendTo(steps, path, { type: "exercise", exercise: "run", sets: 1, distance_m: 400 }))}><Plus size={12} /> Run</button>
              </div>
            </li>
          );
        }
        const ex = s.exercise ? lib.byId.get(s.exercise) : undefined;
        const open = editing === key;
        return (
          <li key={key} className="rounded-2xl border border-line bg-white/[0.02] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <button type="button" className="block truncate text-left text-paper underline-offset-4 hover:underline" onClick={() => s.exercise && setGuide(s.exercise)} disabled={!s.exercise}>{nameOf(s)}</button>
                <p className="num text-sm text-mute">{[amount(s), s.load, rest(s.rest_s)].filter(Boolean).join(" · ")}{s.note ? ` · ${s.note}` : ""}</p>
              </div>
              <span className="flex shrink-0 items-center">
                {s.exercise && <IconBtn label={`How to do ${nameOf(s)}`} onClick={() => setGuide(s.exercise!)}><BookOpen size={16} /></IconBtn>}
                {s.exercise && <IconBtn label={`Replace ${nameOf(s)}`} onClick={() => setSwap({ path, id: s.exercise! })}><ArrowLeftRight size={16} /></IconBtn>}
                <IconBtn label="Edit" onClick={() => setEditing(open ? null : key)}><Pencil size={16} /></IconBtn>
                {controls}
              </span>
            </div>
            {open && <ExerciseEdit step={s} unit={ex?.unit} onChange={(next) => set(updateAt(steps, path, () => next))} onDone={() => setEditing(null)} />}
          </li>
        );
      })}
    </ul>
  );

  const ids = exerciseIds(steps);
  const days = Array.from({ length: 8 }, (_, i) => localDay(i));
  return (
    <div className="space-y-6">
      <div className="surface space-y-5 p-5 sm:p-8">
        <label className="block">
          <span className="eyebrow">Session name</span>
          <input className="mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 font-display text-3xl text-cream outline-none focus:border-gold" value={draft.name} maxLength={80} placeholder="Name it"
            onChange={(e) => onChange({ ...draft, name: e.target.value })} />
        </label>
        <div className="flex flex-wrap items-center gap-4">
          <Segmented label="Where" options={SETTINGS} value={draft.setting} onChange={changeSetting} />
          <span className="chip">{draft.format}</span>
          <span className="num text-sm text-mute">{preview.data ? `≈ ${preview.data.minutes} min` : steps.length ? "…" : ""}{ids.length ? ` · ${ids.length} exercises` : ""}</span>
        </div>
        {preview.data && preview.data.patterns.length > 0 && <p className="text-xs text-dim">Covers {preview.data.patterns.map((p) => PATTERN_LABEL[p] ?? p).join(", ")}. The time is a rough estimate from reps, distances and the rests you set.</p>}
        {converted && (
          <div role="status" className="border-l-2 border-gold/60 bg-gold/5 p-3 text-sm text-mute">
            {converted.changes.length === 0 ? "Everything already works with this kit." : (
              <>
                <p className="mb-1 text-paper">Swapped for the closest fit:</p>
                <ul className="space-y-0.5">{converted.changes.map((c) => <li key={c.from}>{c.from} → {c.to ?? "kept (nothing similar available)"} <span className="text-dim">({c.why})</span></li>)}</ul>
              </>
            )}
            <button type="button" className="mt-2 text-gold underline" onClick={() => { onChange(converted.prev); setConverted(null); }}>Undo</button>
            <button type="button" className="ml-4 text-dim underline" onClick={() => setConverted(null)}>Dismiss</button>
          </div>
        )}
      </div>

      {steps.length === 0 ? (
        <div className="surface p-10 text-center text-mute">Nothing here yet. Add an exercise, a run, a rest or a block to start.</div>
      ) : renderList(steps, [])}

      <div className="flex flex-wrap gap-2" role="group" aria-label="Add to session">
        <button type="button" className="pop pop-ghost" onClick={() => setPicker({ mode: "add", group: null })}><Plus size={14} /> Exercise</button>
        <button type="button" className="pop pop-ghost" onClick={() => set([...steps, { type: "exercise", exercise: "run", sets: 1, distance_m: 1000 }])}><Plus size={14} /> Run</button>
        <button type="button" className="pop pop-ghost" onClick={() => set([...steps, { type: "rest", seconds: 60 }])}><Plus size={14} /> Rest</button>
        <button type="button" className="pop pop-ghost" onClick={() => setPicker({ mode: "group" })}><Plus size={14} /> Block (repeat)</button>
      </div>

      <div className="surface space-y-5 p-5 sm:p-8">
        <label className="block">
          <span className="eyebrow">Notes (optional)</span>
          <textarea className="mt-2 w-full rounded-xl border border-line-strong bg-transparent p-3 text-paper outline-none focus:border-gold" rows={2} maxLength={2000} value={draft.notes ?? ""} placeholder="Tempo, target loads, what to watch…"
            onChange={(e) => onChange({ ...draft, notes: e.target.value || null })} />
        </label>
        <div className="sticky bottom-[5.75rem] z-10 -mx-2 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-ink/95 p-3 backdrop-blur md:static md:mx-0 md:border-0 md:bg-transparent md:p-0">
          <button type="button" className="pop pop-lime !py-3" disabled={saving || steps.length === 0 || !draft.name.trim()} onClick={onSave}>{saving ? "Saving…" : saveLabel}</button>
          {dirty && !saving && <span role="status" className="flex items-center gap-2 text-sm text-gold"><span className="h-2 w-2 rounded-full bg-gold" aria-hidden /> Unsaved changes</span>}
          {onDelete && <button type="button" className="pop pop-ghost !py-3 md:ml-auto" onClick={onDelete}><Trash2 size={14} /> Delete</button>}
        </div>
        <div className="border-t border-line pt-5">
          {scheduled.length > 0 && (
            <div className="mb-6">
              <p className="eyebrow mb-3">On your plan</p>
              <ul className="space-y-2">
                {scheduled.map((p) => (
                  <li key={p.plan_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-white/[0.02] px-4 py-3">
                    <div>
                      <p className="text-paper">{p.day === localDay(0) ? "Today" : p.day === localDay(1) ? "Tomorrow" : formatDate(p.day)}{p.start_hour != null ? ` · ${String(p.start_hour).padStart(2, "0")}:00` : ""}</p>
                      <p className="text-xs text-dim">{p.logged ? "Done and logged" : p.day < localDay(0) ? "Past, not logged" : "Planned"}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/workout/${p.plan_id}`} className="pop pop-ghost !px-3 !py-2 text-sm">View</Link>
                      {!p.logged && onRefreshScheduled && <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" disabled={scheduleBusy || dirty} title={dirty ? "Save your changes first" : "Make that day match this session"} onClick={() => onRefreshScheduled(p.plan_id)}>Update to match</button>}
                      {!p.logged && onRemoveScheduled && <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm text-coral" disabled={scheduleBusy} onClick={() => onRemoveScheduled(p.plan_id)}>Remove</button>}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-dim">Each day holds its own copy. Editing this session doesn’t change them until you press Update to match.</p>
            </div>
          )}
          <p className="eyebrow mb-3">{scheduled.length > 0 ? "Plan it on another day" : "Put it on the plan"}</p>
          <div className="flex flex-wrap items-end gap-4">
            <label className="block"><span className="eyebrow">Day</span>
              <select className="mt-1 block rounded-lg border border-line-strong bg-slate px-3 py-2 text-paper" value={day} onChange={(e) => setDay(e.target.value)}>
                {days.map((d, i) => <option key={d} value={d}>{(i === 0 ? "Today" : i === 1 ? "Tomorrow" : new Date(`${d}T12:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" })) + (taken.has(d) ? " (already planned)" : "")}</option>)}
              </select></label>
            <label className="block"><span className="eyebrow">Start</span>
              <select className="mt-1 block rounded-lg border border-line-strong bg-slate px-3 py-2 text-paper" value={hour ?? ""} onChange={(e) => setHour(e.target.value === "" ? null : Number(e.target.value))}>
                <option value="">Usual time</option>
                {Array.from({ length: 17 }, (_, i) => i + 5).map((h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
              </select></label>
            <button type="button" className="pop" disabled={planning || steps.length === 0 || !draft.name.trim()} onClick={() => onPlan(day, hour)}>{planning ? "Adding…" : scheduled.length > 0 ? "Add another" : "Add to plan"}</button>
          </div>
          <p className="mt-3 text-xs text-dim">A copy goes on that day as a strength session; later edits here don’t change it. It isn’t sent to your watch.</p>
          {planned && <p role="status" className="mt-3 text-sm text-lime">Added for {new Date(`${planned}T12:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" })}.</p>}
        </div>
        {(error || failed) && <p role="alert" className="text-sm text-coral">{error || failed}</p>}
      </div>

      <ExerciseGuide id={guide} setting={draft.setting} onClose={() => setGuide(null)} />
      <SwapSheet exercise={swap?.id ?? null} name={swap ? lib.byId.get(swap.id)?.name ?? swap.id : ""} setting={draft.setting} exclude={ids}
        onPick={(id) => swap && swapTo(swap.path, id)} onBrowse={() => swap && setPicker({ mode: "replace", path: swap.path })} onClose={() => setSwap(null)} />
      <ExercisePicker open={picker != null} setting={draft.setting} title={picker?.mode === "replace" ? "Replace with any exercise" : picker?.mode === "group" ? "First exercise of the block" : "Add an exercise"} onPick={picked} onClose={() => setPicker(null)} />
    </div>
  );
}

function IconBtn({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} disabled={disabled} className="grid h-10 w-10 place-items-center rounded-full text-mute transition hover:bg-white/5 hover:text-paper disabled:opacity-25 pointer-coarse:h-12 pointer-coarse:w-12">
      {children}
    </button>
  );
}

function ExerciseEdit({ step, unit, onChange, onDone }: { step: GymExerciseStep; unit?: string; onChange: (s: GymExerciseStep) => void; onDone: () => void }) {
  const measure: "reps" | "seconds" | "distance_m" | "calories" = step.reps != null ? "reps" : step.seconds != null ? "seconds" : step.distance_m != null ? "distance_m" : step.calories != null ? "calories" : unit === "time" ? "seconds" : unit === "distance" ? "distance_m" : "reps";
  const patch = (p: Partial<GymExerciseStep>) => onChange({ ...step, ...p });
  const labels = { reps: "Reps", seconds: "Seconds", distance_m: "Metres", calories: "Calories" };
  return (
    <div className="mt-4 space-y-4 border-t border-line pt-4">
      <div className="flex flex-wrap gap-4">
        <Num label="Sets" value={step.sets} max={20} onChange={(v) => patch({ sets: v })} />
        <Num label={labels[measure]} value={step[measure]} onChange={(v) => patch({ [measure]: v } as Partial<GymExerciseStep>)} />
        <Num label="Rest (s)" value={step.rest_s} max={900} onChange={(v) => patch({ rest_s: v })} />
      </div>
      <div className="flex flex-wrap gap-4">
        <label className="block min-w-[8rem] flex-1"><span className="eyebrow">Load</span>
          <input className={input} placeholder="20 kg, bodyweight…" maxLength={40} value={step.load ?? ""} onChange={(e) => patch({ load: e.target.value || undefined })} /></label>
        <label className="block min-w-[10rem] flex-[2]"><span className="eyebrow">Note</span>
          <input className={input} placeholder="Tempo, pace, cue…" maxLength={200} value={step.note ?? ""} onChange={(e) => patch({ note: e.target.value || undefined })} /></label>
      </div>
      <button type="button" className="pop pop-ghost" onClick={onDone}><X size={14} /> Close</button>
    </div>
  );
}

function localDay(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
