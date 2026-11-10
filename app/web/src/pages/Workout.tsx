import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, ArrowLeftRight, BookOpen, Check, ChevronDown, Minus, Pencil, Plus, SkipForward, Undo2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ExerciseGuide } from "../components/gym/ExerciseGuide";
import { ExercisePicker } from "../components/gym/ExercisePicker";
import { SwapSheet } from "../components/gym/SwapSheet";
import { useGymLibrary } from "../components/gym/useGym";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { amount, exerciseIds } from "../lib/gymSteps";
import type { GymExerciseStep, GymLastLoad, GymPlanDetail, GymStep } from "../lib/types";
import { addSet, bumpLoad, clock, currentItem, finishSet, goBack, isFinished, progress, skipExercise, skipSet, startRun, swapRemaining, toEntries, volumeKg, withLastLoads, type Run, type WorkItem } from "../lib/workoutQueue";

type Saved = { run: Run; restUntil: number | null };
const storeKey = (id: number) => `cadence.workout.${id}`;
function load(id: number): Saved | null {
  try {
    const raw = localStorage.getItem(storeKey(id));
    const v = raw ? (JSON.parse(raw) as Saved) : null;
    return v && Array.isArray(v.run?.queue) ? v : null;
  } catch {
    return null;
  }
}
function save(id: number, v: Saved | null) {
  try {
    if (v) localStorage.setItem(storeKey(id), JSON.stringify(v));
    else localStorage.removeItem(storeKey(id));
  } catch {
    /* private mode: the workout still runs, it just can't be resumed after a reload */
  }
}

export function WorkoutPage() {
  const id = Number(useParams().planId);
  const q = useQuery({ queryKey: ["gym", "plan", id], queryFn: () => api.gymPlan(id), enabled: Number.isFinite(id) });
  return (
    <>
      <PageHeader eyebrow={<Link to="/plan" className="flex items-center gap-1 hover:text-paper"><ArrowLeft size={12} /> Plan</Link>} title={<>{q.data?.title ?? "Workout"}</>} />
      {q.isPending ? <LoadingBlock height={300} /> : q.isError ? <ErrorBlock error={q.error} retry={() => q.refetch()} /> : <Workout plan={q.data} />}
    </>
  );
}

function Workout({ plan }: { plan: GymPlanDetail }) {
  const client = useQueryClient();
  const lib = useGymLibrary();
  const [saved, setSaved] = useState<Saved | null>(() => load(plan.id));
  const [phase, setPhase] = useState<"overview" | "run" | "summary">("overview");
  const [run, setRun] = useState<Run | null>(null);
  const [restUntil, setRestUntil] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [confirmQuit, setConfirmQuit] = useState(false);
  const ids = useMemo(() => (plan.steps ? [...new Set(exerciseIds(plan.steps))] : []), [plan.steps]);
  const loads = useQuery({ queryKey: ["gym", "last-loads", ids.join(",")], queryFn: () => api.gymLastLoads(ids), enabled: ids.length > 0, staleTime: 60_000 });

  const begin = (resume: boolean) => {
    if (!plan.steps) return;
    if (resume && saved) {
      setRun(saved.run);
      setRestUntil(saved.restUntil);
    } else {
      setRun(withLastLoads(startRun(plan.steps, plan.setting, Date.now()), loads.data?.loads ?? {}));
      setRestUntil(null);
    }
    setPhase("run");
    window.scrollTo({ top: 0 });
  };
  const update = (next: Run, rest: number | null = null) => {
    const until = rest && rest > 0 ? Date.now() + rest * 1000 : null;
    setRun(next);
    setRestUntil(until);
    if (isFinished(next)) {
      save(plan.id, null);
      setSaved(null);
      setPhase("summary");
      window.scrollTo({ top: 0 });
    } else {
      const s = { run: next, restUntil: until };
      save(plan.id, s);
      setSaved(s);
    }
  };
  const quit = () => {
    save(plan.id, null);
    setSaved(null);
    setRun(null);
    setPhase("overview");
    setConfirmQuit(false);
  };

  if (phase === "run" && run) {
    return (
      <>
        <Runner run={run} plan={plan} lastLoads={loads.data?.loads ?? {}} restUntil={restUntil} setRestUntil={(u) => { setRestUntil(u); save(plan.id, { run, restUntil: u }); }}
          onUpdate={update} onFinishNow={() => { save(plan.id, null); setSaved(null); setPhase("summary"); }} onQuit={() => setConfirmQuit(true)} nameOf={(i) => lib.byId.get(i)?.name} />
        <ConfirmDialog open={confirmQuit} title="Quit this workout?" body="Nothing from it is saved." confirmLabel="Quit" onCancel={() => setConfirmQuit(false)} onConfirm={quit} />
      </>
    );
  }
  if (phase === "summary" && run) {
    return <Summary run={run} plan={plan} notes={notes} setNotes={setNotes} nameOf={(i) => lib.byId.get(i)?.name} onBack={() => setPhase("overview")}
      onSaved={() => { ["planner", "overview"].forEach((k) => client.invalidateQueries({ queryKey: [k] })); client.invalidateQueries({ queryKey: ["gym"] }); }} />;
  }
  return <Overview plan={plan} loads={loads.data?.loads ?? {}} saved={saved} canStart={!!plan.steps} onStart={begin} nameOf={(i) => lib.byId.get(i)?.name} />;
}

// ---------------------------------------------------------------- overview
function Overview({ plan, loads, saved, canStart, onStart, nameOf }: { plan: GymPlanDetail; loads: Record<string, GymLastLoad>; saved: Saved | null; canStart: boolean; onStart: (resume: boolean) => void; nameOf: (id: string) => string | undefined }) {
  const [guide, setGuide] = useState<string | null>(null);
  const done = saved ? progress(saved.run) : null;
  return (
    <div className="space-y-6">
      <div className="surface space-y-4 p-5 sm:p-8">
        <p className="eyebrow flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>{formatDate(plan.day)}</span><span>{plan.setting === "home" ? "Home" : "Full gym"}</span><span className="text-dim">≈ {plan.minutes} min</span>
          {plan.predicted_load != null && <span className="text-dim">predicted load {plan.predicted_load}</span>}
        </p>
        {plan.workout && (
          <p role="status" className="border-l-2 border-lime/60 pl-3 text-sm text-lime">
            Logged: {plan.workout.sets_done} of {plan.workout.sets_total} sets{plan.workout.duration_s ? ` in ${Math.round(plan.workout.duration_s / 60)} min` : ""}. You can still do it again.
          </p>
        )}
        {plan.notes && <p className="text-sm text-mute">{plan.notes}</p>}
        <div className="flex flex-wrap items-center gap-3">
          {saved && canStart && <button type="button" className="pop pop-lime" onClick={() => onStart(true)}>Resume · {done?.done}/{done?.total} sets done</button>}
          {canStart && <button type="button" className={clsx("pop", !saved && "pop-lime")} onClick={() => onStart(false)}>{saved ? "Start over" : plan.workout ? "Do it again" : "Start workout"}</button>}
          {plan.session_id && <Link to={`/gym?session=${plan.session_id}`} className="pop pop-ghost"><Pencil size={14} /> Edit the saved session</Link>}
        </div>
        {!canStart && <p className="text-sm text-mute">This session was planned before steps were kept with plans, so there is only its outline to read. Open the saved session and plan it again to follow it set by set.</p>}
      </div>
      {plan.steps ? (
        <div className="space-y-3">
          <StepsView steps={plan.steps} loads={loads} nameOf={nameOf} onGuide={setGuide} />
        </div>
      ) : (
        <pre className="surface whitespace-pre-wrap p-5 text-sm text-mute">{plan.detail}</pre>
      )}
      <ExerciseGuide id={guide} setting={plan.setting} onClose={() => setGuide(null)} />
    </div>
  );
}

function StepsView({ steps, loads, nameOf, onGuide, depth = 0 }: { steps: GymStep[]; loads: Record<string, GymLastLoad>; nameOf: (id: string) => string | undefined; onGuide: (id: string) => void; depth?: number }) {
  return (
    <ul className="space-y-2">
      {steps.map((s, i) => {
        if (s.type === "rest") return <li key={i} className="rounded-2xl border border-dashed border-line px-4 py-2 text-sm text-mute">Rest {s.seconds} s</li>;
        if (s.type === "group") {
          return (
            <li key={i} className="rounded-2xl border border-line bg-white/[0.02] p-3 sm:p-4">
              <p className="mb-3 font-display text-xl text-cream">{s.title || "Round"}{s.rounds > 1 && <span className="ml-2 text-sm text-mute">× {s.rounds} rounds</span>}</p>
              <StepsView steps={s.steps} loads={loads} nameOf={nameOf} onGuide={onGuide} depth={depth + 1} />
            </li>
          );
        }
        const e = s as GymExerciseStep;
        const name = e.exercise ? nameOf(e.exercise) ?? e.exercise : e.name ?? "Exercise";
        const last = e.exercise ? loads[e.exercise] : undefined;
        return (
          <li key={i} className="flex items-center justify-between gap-3 rounded-2xl border border-line bg-white/[0.02] px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-paper">{name}</p>
              <p className="num text-sm text-mute">{[amount(e), e.load, e.rest_s ? `rest ${e.rest_s} s` : ""].filter(Boolean).join(" · ")}</p>
              {last && <p className="text-xs text-dim">Last time {last.load}{last.reps ? ` × ${last.reps}` : ""} · {formatDate(last.day)}</p>}
            </div>
            {e.exercise && <button type="button" aria-label={`How to do ${name}`} onClick={() => onGuide(e.exercise!)} className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-mute hover:bg-white/5 hover:text-paper"><BookOpen size={16} /></button>}
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------- runner
function targetText(w: WorkItem): string {
  const t = w.target;
  if (t.reps != null) return `${t.reps} reps`;
  if (t.seconds != null) return `${t.seconds} s`;
  if (t.distance_m != null) return t.distance_m >= 1000 && t.distance_m % 100 === 0 ? `${t.distance_m / 1000} km` : `${t.distance_m} m`;
  if (t.calories != null) return `${t.calories} cal`;
  return "";
}

function Runner({ run, plan, lastLoads, restUntil, setRestUntil, onUpdate, onFinishNow, onQuit, nameOf }: {
  run: Run; plan: GymPlanDetail; lastLoads: Record<string, GymLastLoad>; restUntil: number | null; setRestUntil: (u: number | null) => void;
  onUpdate: (r: Run, rest?: number | null) => void; onFinishNow: () => void; onQuit: () => void; nameOf: (id: string) => string | undefined;
}) {
  const [now, setNow] = useState(Date.now());
  const item = currentItem(run);
  const work = item?.kind === "work" ? item : undefined;
  const [reps, setReps] = useState<number | undefined>();
  const [secs, setSecs] = useState<number | undefined>();
  const [loadText, setLoadText] = useState("");
  const [guide, setGuide] = useState<string | null>(null);
  const [swap, setSwap] = useState(false);
  const [picker, setPicker] = useState(false);
  const [more, setMore] = useState(false);
  const wake = useRef<{ release: () => Promise<void> } | null>(null);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } };
    nav.wakeLock?.request("screen").then((l) => { wake.current = l; }, () => undefined);
    return () => { void wake.current?.release(); };
  }, []);
  // Each new set starts from its target; load starts from the plan or last time.
  useEffect(() => {
    if (!work) return;
    setReps(work.target.reps);
    setSecs(work.target.seconds);
    setLoadText(work.load ?? "");
  }, [work?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (restUntil && now >= restUntil) {
      setRestUntil(null);
      try { navigator.vibrate?.(200); } catch { /* not supported */ }
    }
  }, [now, restUntil]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!work) return <LoadingBlock height={200} />;
  const name = work.exercise ? nameOf(work.exercise) ?? work.exercise : work.name ?? "Exercise";
  const prog = progress(run);
  const last = work.exercise ? lastLoads[work.exercise] : undefined;
  const resting = restUntil != null && now < restUntil;
  const nextUp = run.queue.slice(run.idx).find((q): q is WorkItem => q.kind === "work");
  const elapsed = (now - run.startedAt) / 1000;

  const complete = () => {
    const out = finishSet(run, { reps, seconds: secs, distance_m: work.target.distance_m, calories: work.target.calories, load: loadText.trim() || undefined });
    onUpdate(out.run, out.rest);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 pb-24">
      <div>
        <div className="mb-2 flex items-center justify-between text-xs text-mute">
          <span className="num">{prog.done} of {prog.total} sets{prog.skipped ? ` · ${prog.skipped} skipped` : ""}</span>
          <span className="num">{clock(elapsed)}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={prog.done + prog.skipped} aria-valuemin={0} aria-valuemax={prog.total} aria-label="Workout progress">
          <div className="h-full rounded-full bg-gold transition-[width] duration-300" style={{ width: `${((prog.done + prog.skipped) / Math.max(1, prog.total)) * 100}%` }} />
        </div>
      </div>

      {resting ? (
        <div className="surface space-y-5 p-6 text-center sm:p-10" role="timer" aria-live="off">
          <p className="eyebrow">Rest</p>
          <p className="numeral text-8xl text-cream">{clock((restUntil! - now) / 1000)}</p>
          <div className="flex justify-center gap-3">
            <button type="button" className="pop pop-ghost" onClick={() => setRestUntil(restUntil! + 15000)}><Plus size={14} /> 15 s</button>
            <button type="button" className="pop pop-lime" onClick={() => setRestUntil(null)}>Skip rest</button>
          </div>
          <div className="border-t border-line pt-4 text-left">
            <p className="eyebrow mb-1">Up next</p>
            <p className="text-paper">{nextUp ? (nextUp.exercise ? nameOf(nextUp.exercise) ?? nextUp.exercise : nextUp.name) : ""}</p>
            {nextUp && <p className="num text-sm text-mute">Set {nextUp.set} of {nextUp.sets} · {targetText(nextUp)}{nextUp.load ? ` · ${nextUp.load}` : ""}</p>}
          </div>
        </div>
      ) : (
        <div className="surface space-y-6 p-5 sm:p-8">
          <div className="space-y-2">
            <p className="eyebrow">{[work.block, work.rounds > 1 ? `Round ${work.round} of ${work.rounds}` : ""].filter(Boolean).join(" · ") || "Main"}</p>
            <h2 className="font-display text-4xl leading-tight text-cream sm:text-5xl">{name}</h2>
            <p className="num text-lg text-mute">Set {work.set} of {work.sets} · {targetText(work)}{work.note ? ` · ${work.note}` : ""}</p>
          </div>

          {work.target.reps != null && <Stepper label="Reps done" value={reps} onChange={setReps} step={1} min={0} />}
          {work.target.seconds != null && <Stepper label="Seconds" value={secs} onChange={setSecs} step={5} min={0} />}
          <div>
            <p className="eyebrow mb-2">Weight</p>
            <div className="flex items-center gap-2">
              <RoundBtn label="Lighter by 2.5 kg" onClick={() => setLoadText(bumpLoad(loadText, -2.5))}><Minus size={18} /></RoundBtn>
              <input aria-label="Weight" value={loadText} placeholder="bodyweight" maxLength={40} onChange={(e) => setLoadText(e.target.value)}
                className="num min-w-0 flex-1 border-b-2 border-line-strong bg-transparent py-2 text-center text-3xl text-paper outline-none focus:border-gold" />
              <RoundBtn label="Heavier by 2.5 kg" onClick={() => setLoadText(bumpLoad(loadText, 2.5))}><Plus size={18} /></RoundBtn>
            </div>
            {last && (
              <p className="mt-2 text-xs text-dim">
                Last time {last.load}{last.reps ? ` × ${last.reps}` : ""} · {formatDate(last.day)}
                {last.hint?.load && last.hint.kind === "increase_load" && loadText !== last.hint.load && (
                  <button type="button" className="ml-2 text-gold underline" onClick={() => setLoadText(last.hint!.load!)}>Try {last.hint.load}</button>
                )}
              </p>
            )}
            {last?.hint && <p className="mt-1 text-xs text-mute">{last.hint.text}</p>}
          </div>

          <button type="button" className="pop pop-lime w-full justify-center !py-4 text-lg" onClick={complete}><Check size={20} /> Done{nextUp && nextUp.id !== work.id ? " · next" : ""}</button>
          <div className="flex flex-wrap gap-2">
            {work.exercise && <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" onClick={() => setGuide(work.exercise!)}><BookOpen size={14} /> How to</button>}
            <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" onClick={() => onUpdate(addSet(run))}><Plus size={14} /> Extra set</button>
            {work.exercise && <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" onClick={() => setSwap(true)}><ArrowLeftRight size={14} /> Swap</button>}
            <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" onClick={() => onUpdate(skipSet(run))}><SkipForward size={14} /> Skip set</button>
            <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" disabled={run.idx === 0} onClick={() => onUpdate(goBack(run))}><Undo2 size={14} /> Back</button>
          </div>
        </div>
      )}

      <div>
        <button type="button" className="flex items-center gap-1 text-sm text-mute hover:text-paper" aria-expanded={more} onClick={() => setMore((v) => !v)}>
          More <ChevronDown size={14} className={more ? "rotate-180" : ""} />
        </button>
        {more && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" onClick={() => onUpdate(skipExercise(run))}>Skip this exercise</button>
            <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm" onClick={onFinishNow}>Finish now and save what I did</button>
            <button type="button" className="pop pop-ghost !px-3 !py-2 text-sm text-coral" onClick={onQuit}>Quit without saving</button>
          </div>
        )}
      </div>

      <ExerciseGuide id={guide} setting={plan.setting} onClose={() => setGuide(null)} />
      <SwapSheet exercise={swap && work.exercise ? work.exercise : null} name={name} setting={plan.setting} exclude={[]} onBrowse={() => { setSwap(false); setPicker(true); }} onClose={() => setSwap(false)}
        onPick={(id) => { setSwap(false); onUpdate(swapRemaining(run, id, nameOf(id))); }} />
      <ExercisePicker open={picker} setting={plan.setting} title="Do this instead" onPick={(ex) => { setPicker(false); onUpdate(swapRemaining(run, ex.id, ex.name)); }} onClose={() => setPicker(false)} />
    </div>
  );
}

function RoundBtn({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick} className="grid h-14 w-14 shrink-0 place-items-center rounded-full border border-line-strong text-paper active:bg-white/10">{children}</button>;
}

function Stepper({ label, value, onChange, step, min }: { label: string; value: number | undefined; onChange: (v: number) => void; step: number; min: number }) {
  return (
    <div>
      <p className="eyebrow mb-2">{label}</p>
      <div className="flex items-center gap-2">
        <RoundBtn label={`${label} minus ${step}`} onClick={() => onChange(Math.max(min, (value ?? 0) - step))}><Minus size={18} /></RoundBtn>
        <input aria-label={label} inputMode="numeric" value={value ?? ""} onChange={(e) => onChange(Math.max(min, Number(e.target.value.replace(/\D/g, "")) || 0))}
          className="num min-w-0 flex-1 border-b-2 border-line-strong bg-transparent py-2 text-center text-5xl text-paper outline-none focus:border-gold" />
        <RoundBtn label={`${label} plus ${step}`} onClick={() => onChange((value ?? 0) + step)}><Plus size={18} /></RoundBtn>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- summary
function Summary({ run, plan, notes, setNotes, nameOf, onBack, onSaved }: { run: Run; plan: GymPlanDetail; notes: string; setNotes: (n: string) => void; nameOf: (id: string) => string | undefined; onBack: () => void; onSaved: () => void }) {
  const entries = useMemo(() => toEntries(run, nameOf), [run]); // eslint-disable-line react-hooks/exhaustive-deps
  const prog = progress(run);
  const duration = Math.round((Date.now() - run.startedAt) / 1000);
  const vol = volumeKg(entries);
  const log = useMutation({
    mutationFn: () => api.gymLogWorkout({ name: plan.title, setting: plan.setting, plan_id: plan.id, session_id: plan.session_id, duration_s: duration, entries, notes: notes.trim() || null }),
    onSuccess: onSaved,
  });
  const ids = entries.flatMap((e) => (e.exercise ? [e.exercise] : []));
  const next = useQuery({ queryKey: ["gym", "next-time", ids.join(",")], queryFn: () => api.gymLastLoads(ids), enabled: log.isSuccess && ids.length > 0 });
  const hints = Object.entries(next.data?.loads ?? {}).filter(([, l]) => l.hint);
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="surface space-y-4 p-6 sm:p-8">
        <p className="eyebrow">{log.isSuccess ? "Saved" : "Nice work"}</p>
        <h2 className="font-display text-4xl text-cream">{prog.done} of {prog.total} sets · {clock(duration)}</h2>
        <p className="text-sm text-mute">{[prog.skipped ? `${prog.skipped} skipped` : "", vol ? `${vol.toLocaleString()} kg lifted (weight × reps, where you entered both)` : ""].filter(Boolean).join(" · ") || "Nothing skipped."}</p>
        <ul className="divide-y divide-line">
          {entries.map((e, i) => (
            <li key={i} className="py-3">
              <p className="text-paper">{e.exercise ? nameOf(e.exercise) ?? e.exercise : e.name}</p>
              <p className="num text-sm text-mute">{e.sets.map((s) => (s.done ? [s.reps != null ? `${s.reps}` : s.seconds != null ? `${s.seconds} s` : s.distance_m != null ? `${s.distance_m} m` : "✓", s.load].filter(Boolean).join(" × ") : "skipped")).join(" · ")}</p>
            </li>
          ))}
        </ul>
        {!log.isSuccess && (
          <label className="block">
            <span className="eyebrow">Notes (optional)</span>
            <textarea className="mt-2 w-full rounded-xl border border-line-strong bg-transparent p-3 text-paper outline-none focus:border-gold" rows={2} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="How it felt, what to change…" />
          </label>
        )}
        <div className="flex flex-wrap items-center gap-3">
          {log.isSuccess ? <Link to="/plan" className="pop pop-lime">Back to plan</Link> : <button type="button" className="pop pop-lime" disabled={log.isPending || prog.done === 0} onClick={() => log.mutate()}>{log.isPending ? "Saving…" : "Save to my log"}</button>}
          {!log.isSuccess && <button type="button" className="pop pop-ghost" onClick={onBack}>Discard</button>}
        </div>
        {prog.done === 0 && !log.isSuccess && <p className="text-xs text-dim">No sets were done, so there is nothing to save.</p>}
        {log.isError && <p role="alert" className="text-sm text-coral">{(log.error as Error).message || "Couldn’t save."} Your sets are still here: try again.</p>}
      </div>
      {log.isSuccess && hints.length > 0 && (
        <div className="surface space-y-3 p-6">
          <p className="eyebrow">Next time</p>
          <ul className="space-y-2 text-sm text-mute">
            {hints.map(([id, l]) => <li key={id}><span className="text-paper">{nameOf(id) ?? id}:</span> {l.hint!.text}</li>)}
          </ul>
          <p className="text-xs text-dim">Small suggestions from what you logged, not a prescription. Skip them if a set felt hard.</p>
        </div>
      )}
    </div>
  );
}
