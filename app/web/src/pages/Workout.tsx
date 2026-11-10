import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, ArrowLeftRight, BookOpen, Check, Minus, MoreHorizontal, Pencil, Play, Plus, SkipForward, Undo2 } from "lucide-react";
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
import { beep, unlockSound } from "../lib/beep";
import { amount, exerciseIds } from "../lib/gymSteps";
import type { GymExercise, GymExerciseStep, GymLastLoad, GymLoggedSet, GymPlanDetail, GymStep } from "../lib/types";
import { addSet, bumpLoad, clock, currentItem, finishSet, goBack, isFinished, markStart, parseKg, progress, seedLoad, skipExercise, skipSet, startRun, swapRemaining, toEntries, usesLoad, volumeKg, withLastLoads, type Run, type WorkItem } from "../lib/workoutQueue";

type Saved = { run: Run; restUntil: number | null; phase?: "run" | "summary"; savedAt?: number; notes?: string; rpe?: number | null };
const RESUME_WITHIN_MS = 12 * 3600 * 1000; // a workout left longer than this is offered, not entered
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
    if (v) localStorage.setItem(storeKey(id), JSON.stringify({ ...v, savedAt: Date.now() }));
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
  // A workout in progress (or finished but not yet saved) from the last 12 hours reopens straight into itself.
  const fresh = saved && Date.now() - (saved.savedAt ?? 0) < RESUME_WITHIN_MS;
  const [phase, setPhase] = useState<"overview" | "run" | "summary">(fresh ? (saved!.phase === "summary" ? "summary" : "run") : "overview");
  const [run, setRun] = useState<Run | null>(fresh ? saved!.run : null);
  const [restUntil, setRestUntil] = useState<number | null>(fresh ? saved!.restUntil : null);
  const [notes, setNotes] = useState(fresh ? saved!.notes ?? "" : "");
  const [rpe, setRpe] = useState<number | null>(fresh ? saved!.rpe ?? null : null);
  const [confirm, setConfirm] = useState<"quit" | "restart" | "discard" | null>(null);
  const ids = useMemo(() => (plan.steps ? [...new Set(exerciseIds(plan.steps))] : []), [plan.steps]);
  const loads = useQuery({ queryKey: ["gym", "last-loads", ids.join(",")], queryFn: () => api.gymLastLoads(ids), enabled: ids.length > 0, staleTime: 60_000 });
  const persist = (v: Saved | null) => { save(plan.id, v); setSaved(v); };

  const begin = (resume: boolean) => {
    if (!plan.steps) return;
    unlockSound();
    if (resume && saved) {
      setRun(markStart(saved.run, Date.now()));
      setRestUntil(saved.restUntil);
      setPhase(saved.phase === "summary" ? "summary" : "run");
    } else {
      persist(null);
      setRun(withLastLoads(startRun(plan.steps, plan.setting, Date.now()), loads.data?.loads ?? {}));
      setRestUntil(null);
      setNotes("");
      setRpe(null);
      setPhase("run");
    }
    window.scrollTo({ top: 0 });
  };
  const goSummary = (r: Run) => {
    setRun(r);
    setRestUntil(null);
    persist({ run: r, restUntil: null, phase: "summary", notes, rpe }); // kept until it is saved, so a reload or a locked phone can't lose it
    setPhase("summary");
    window.scrollTo({ top: 0 });
  };
  const update = (next: Run, rest: number | null = null) => {
    const until = rest && rest > 0 ? Date.now() + rest * 1000 : null;
    if (isFinished(next)) return goSummary(next);
    setRun(next);
    setRestUntil(until);
    persist({ run: next, restUntil: until, phase: "run" });
  };
  const mark = (now: number) => {
    if (!run) return;
    const next = markStart(run, now);
    setRun(next);
    persist({ run: next, restUntil: null, phase: "run" });
  };
  const changeRest = (u: number | null) => {
    setRestUntil(u);
    if (run) persist({ run, restUntil: u, phase: "run" });
  };
  const leave = () => {
    persist(null);
    setRun(null);
    setPhase("overview");
    setConfirm(null);
  };
  const exOf = (id: string): GymExercise | undefined => lib.byId.get(id);

  if (phase === "run" && run) {
    return (
      <>
        <Runner run={run} plan={plan} lastLoads={loads.data?.loads ?? {}} restUntil={restUntil} setRestUntil={changeRest} onUpdate={update} onMark={mark}
          onFinishNow={() => goSummary(run)} onQuit={() => setConfirm("quit")} nameOf={(i) => lib.byId.get(i)?.name} exOf={exOf} />
        <ConfirmDialog open={confirm === "quit"} title="Quit this workout?" body="Nothing from it is saved." confirmLabel="Quit" onCancel={() => setConfirm(null)} onConfirm={leave} />
      </>
    );
  }
  if (phase === "summary" && run) {
    return (
      <>
        <Summary run={run} plan={plan} notes={notes} rpe={rpe} setNotes={(n) => { setNotes(n); persist({ run, restUntil: null, phase: "summary", notes: n, rpe }); }}
          setRpe={(v) => { setRpe(v); persist({ run, restUntil: null, phase: "summary", notes, rpe: v }); }} nameOf={(i) => lib.byId.get(i)?.name} onDiscard={() => setConfirm("discard")}
          onSaved={() => { persist(null); ["planner", "overview"].forEach((k) => client.invalidateQueries({ queryKey: [k] })); client.invalidateQueries({ queryKey: ["gym"] }); }} />
        <ConfirmDialog open={confirm === "discard"} title="Discard this workout?" body="The sets you did won't be saved." confirmLabel="Discard" onCancel={() => setConfirm(null)} onConfirm={leave} />
      </>
    );
  }
  return (
    <>
      <Overview plan={plan} loads={loads.data?.loads ?? {}} saved={saved} canStart={!!plan.steps} onStart={(resume) => (resume ? begin(true) : saved ? setConfirm("restart") : begin(false))} nameOf={(i) => lib.byId.get(i)?.name} />
      <ConfirmDialog open={confirm === "restart"} title="Start over?" body="The workout you have in progress will be thrown away." confirmLabel="Start over" onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); begin(false); }} />
    </>
  );
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
          {saved && canStart && <button type="button" className="pop pop-lime !py-3" onClick={() => onStart(true)}>Resume · {done?.done}/{done?.total} sets done</button>}
          {canStart && <button type="button" className={clsx("pop !py-3", !saved && "pop-lime")} onClick={() => onStart(false)}>{saved ? "Start over" : plan.workout ? "Do it again" : "Start workout"}</button>}
          {plan.session_id && <Link to={`/gym?session=${plan.session_id}`} className="pop pop-ghost !py-3"><Pencil size={14} /> Edit the saved session</Link>}
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

/** The workout, full screen: no banner or tab bar, a thin header, and Done pinned at the bottom where a thumb is. */
function Runner({ run, plan, lastLoads, restUntil, setRestUntil, onUpdate, onMark, onFinishNow, onQuit, nameOf, exOf }: {
  run: Run; plan: GymPlanDetail; lastLoads: Record<string, GymLastLoad>; restUntil: number | null; setRestUntil: (u: number | null) => void;
  onUpdate: (r: Run, rest?: number | null) => void; onMark: (now: number) => void; onFinishNow: () => void; onQuit: () => void;
  nameOf: (id: string) => string | undefined; exOf: (id: string) => GymExercise | undefined;
}) {
  const [now, setNow] = useState(Date.now());
  const item = currentItem(run);
  const work = item?.kind === "work" ? item : undefined;
  const [reps, setReps] = useState<number | undefined>();
  const [secs, setSecs] = useState<number | undefined>();
  const [loadText, setLoadText] = useState("");
  const [holdStart, setHoldStart] = useState<number | null>(null); // a running countdown for a timed set
  const [guide, setGuide] = useState<string | null>(null);
  const [swap, setSwap] = useState(false);
  const [picker, setPicker] = useState(false);
  const [more, setMore] = useState(false);
  const wake = useRef<{ release: () => Promise<void> } | null>(null);
  const beeped = useRef<string>("");

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } };
    nav.wakeLock?.request("screen").then((l) => { wake.current = l; }, () => undefined);
    return () => { void wake.current?.release(); };
  }, []);
  useEffect(() => {
    document.body.style.overflow = "hidden"; // the runner scrolls inside itself
    return () => { document.body.style.overflow = ""; };
  }, []);
  // Each new set starts from its target; the weight carries over from the set before, then last time, then the plan.
  useEffect(() => {
    if (!work) return;
    setReps(work.target.reps);
    setSecs(work.target.seconds);
    setLoadText(seedLoad(run, work));
    setHoldStart(null);
  }, [work?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const resting = restUntil != null && now < restUntil;
  // Rest ending: a tone at 3 s, 2 s, 1 s and a longer one at zero; then the next set's split clock starts.
  useEffect(() => {
    if (restUntil == null) return;
    const left = Math.ceil((restUntil - now) / 1000);
    const tag = `r${restUntil}:${Math.max(0, left)}`;
    if (beeped.current !== tag && left <= 3 && left >= 1) { beeped.current = tag; beep(1, 660, 90); }
    if (now >= restUntil) {
      beeped.current = `r${restUntil}:0`;
      beep(2, 988, 160);
      setRestUntil(null);
      onMark(now);
    }
  }, [now, restUntil]); // eslint-disable-line react-hooks/exhaustive-deps

  const ex = work?.exercise ? exOf(work.exercise) : undefined;
  const complete = (overrideSecs?: number) => {
    if (!work) return;
    unlockSound();
    const out = finishSet(run, { reps, seconds: overrideSecs ?? secs, distance_m: work.target.distance_m, calories: work.target.calories, load: loadText.trim() || undefined }, Date.now());
    onUpdate(out.run, out.rest);
  };
  // A timed hold: counts down, tones in the last three seconds, and records itself when it reaches zero.
  const holdLeft = holdStart != null && work?.target.seconds != null ? Math.ceil((holdStart + (secs ?? work.target.seconds) * 1000 - now) / 1000) : null;
  useEffect(() => {
    if (holdLeft == null || !work) return;
    if (holdLeft <= 3 && holdLeft >= 1) {
      const tag = `h${work.id}:${holdLeft}`;
      if (beeped.current !== tag) { beeped.current = tag; beep(1, 660, 90); }
    }
    if (holdLeft <= 0) {
      beep(2, 988, 160);
      setHoldStart(null);
      complete(secs ?? work.target.seconds);
    }
  }, [holdLeft]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!work) return <div className="fixed inset-0 z-[70] grid place-items-center bg-ink"><LoadingBlock height={200} /></div>;
  const name = work.exercise ? nameOf(work.exercise) ?? work.exercise : work.name ?? "Exercise";
  const prog = progress(run);
  const last = work.exercise ? lastLoads[work.exercise] : undefined;
  const nextUp = run.queue.slice(run.idx + 1).find((q): q is WorkItem => q.kind === "work");
  const nextName = nextUp ? (nextUp.exercise ? nameOf(nextUp.exercise) ?? nextUp.exercise : nextUp.name) : null;
  const elapsed = (now - run.startedAt) / 1000;
  const split = run.mark != null ? (now - run.mark) / 1000 : null;
  const showLoad = usesLoad(ex?.pattern, ex?.unit);
  const timed = work.target.seconds != null;
  const segment = work.target.distance_m != null || ex?.pattern === "cardio";
  const startKg = parseKg(last?.load) ?? 10;

  return (
    <div className="fixed inset-0 z-[70] flex flex-col bg-ink" role="region" aria-label="Workout">
      <header className="shrink-0 border-b border-line px-4 pt-[max(0.75rem,env(safe-area-inset-top))] pb-3">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
          <p className="num text-sm text-mute">{prog.done}/{prog.total} sets{prog.skipped ? ` · ${prog.skipped} skipped` : ""}</p>
          <p className="num text-sm text-paper">{clock(elapsed)}</p>
          <button type="button" aria-label="More options" aria-expanded={more} onClick={() => setMore((v) => !v)} className="grid h-11 w-11 place-items-center rounded-full text-mute hover:bg-white/5 hover:text-paper"><MoreHorizontal size={20} /></button>
        </div>
        <div className="mx-auto mt-2 h-1.5 max-w-2xl overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={prog.done + prog.skipped} aria-valuemin={0} aria-valuemax={prog.total} aria-label="Workout progress">
          <div className="h-full rounded-full bg-gold transition-[width] duration-300" style={{ width: `${((prog.done + prog.skipped) / Math.max(1, prog.total)) * 100}%` }} />
        </div>
        {more && (
          <div className="mx-auto mt-3 flex max-w-2xl flex-wrap gap-2">
            <button type="button" className="pop pop-ghost !py-2.5 text-sm" onClick={() => { setMore(false); onUpdate(skipExercise(run)); }}>Skip this exercise</button>
            <button type="button" className="pop pop-ghost !py-2.5 text-sm" onClick={() => { setMore(false); onFinishNow(); }}>Finish now and save</button>
            <button type="button" className="pop pop-ghost !py-2.5 text-sm text-coral" onClick={onQuit}>Quit without saving</button>
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        <div className="mx-auto max-w-2xl space-y-6">
          {resting ? (
            <div className="space-y-6 text-center" role="timer">
              <p className="eyebrow">Rest</p>
              <p className="numeral text-[7rem] leading-none text-cream">{clock((restUntil! - now) / 1000)}</p>
              <div className="flex justify-center gap-3">
                <button type="button" className="pop pop-ghost !py-3" onClick={() => setRestUntil(Math.max(Date.now() + 1000, restUntil! - 15000))}><Minus size={14} /> 15 s</button>
                <button type="button" className="pop pop-ghost !py-3" onClick={() => setRestUntil(restUntil! + 15000)}><Plus size={14} /> 15 s</button>
              </div>
              <div className="border-t border-line pt-5 text-left">
                <p className="eyebrow mb-1">Up next</p>
                <p className="font-display text-3xl text-cream">{nextName ?? name}</p>
                {(() => { const n = (nextUp && nextUp.id !== work.id ? nextUp : work); return <p className="num text-lg text-mute">Set {n.set} of {n.sets} · {targetText(n)}{loadText && n === work ? ` · ${loadText}` : n.load ? ` · ${n.load}` : ""}</p>; })()}
              </div>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <p className="eyebrow">{[work.block, work.rounds > 1 ? `Round ${work.round} of ${work.rounds}` : ""].filter(Boolean).join(" · ") || "Main"}</p>
                <h2 className="font-display text-4xl leading-tight text-cream sm:text-5xl">{name}</h2>
                <p className="num text-3xl text-paper">{targetText(work)} <span className="text-lg text-mute">· set {work.set} of {work.sets}</span></p>
                {work.note && <p className="text-sm text-mute">{work.note}</p>}
                {segment && split != null && <p className="num text-lg text-gold" aria-label="Time on this segment">{clock(split)} <span className="text-sm text-mute">this segment</span></p>}
              </div>

              {timed && (
                <div className="rounded-2xl border border-line p-4 text-center">
                  {holdLeft != null ? (
                    <>
                      <p className="numeral text-7xl text-lime" role="timer">{clock(holdLeft)}</p>
                      <button type="button" className="pop pop-ghost mt-3 !py-3" onClick={() => setHoldStart(null)}>Stop</button>
                    </>
                  ) : (
                    <button type="button" className="pop w-full justify-center !py-4 text-lg" onClick={() => { unlockSound(); setHoldStart(Date.now()); }}><Play size={18} /> Start {secs ?? work.target.seconds} s timer</button>
                  )}
                  <p className="mt-2 text-xs text-dim">The set records itself at zero. Or do it your own way and tap Done.</p>
                </div>
              )}
              {work.target.reps != null && <Stepper label="Reps done" value={reps} onChange={setReps} step={1} min={0} />}
              {timed && <Stepper label="Seconds" value={secs} onChange={setSecs} step={5} min={0} />}
              {showLoad && (
                <div>
                  <p className="eyebrow mb-2">Load</p>
                  <div className="flex items-center gap-2">
                    <RoundBtn label="Lighter by 2.5 kg" onClick={() => setLoadText(bumpLoad(loadText, -2.5, startKg))}><Minus size={18} /></RoundBtn>
                    <input aria-label="Load" value={loadText} placeholder="bodyweight" maxLength={40} onChange={(e) => setLoadText(e.target.value)}
                      className="num min-h-14 min-w-0 flex-1 border-b-2 border-line-strong bg-transparent py-2 text-center text-3xl text-paper outline-none focus:border-gold" />
                    <RoundBtn label="Heavier by 2.5 kg" onClick={() => setLoadText(bumpLoad(loadText, 2.5, startKg))}><Plus size={18} /></RoundBtn>
                  </div>
                  {last && (
                    <p className="mt-2 text-xs text-dim">
                      Last time {last.load}{last.reps ? ` × ${last.reps}` : ""} · {formatDate(last.day)}
                      {last.hint?.load && last.hint.kind === "increase_load" && loadText !== last.hint.load && (
                        <button type="button" className="ml-2 py-2 text-gold underline" onClick={() => setLoadText(last.hint!.load!)}>Try {last.hint.load}</button>
                      )}
                    </p>
                  )}
                  {last?.hint && <p className="mt-1 text-xs text-mute">{last.hint.text}</p>}
                </div>
              )}
              {nextName && <p className="text-sm text-mute">Next: <span className="text-paper">{nextName}</span>{nextUp ? ` · ${targetText(nextUp)}` : ""}{work.restAfter ? ` (rest ${work.restAfter} s first)` : ""}</p>}
              <div className="flex flex-wrap gap-2">
                {work.exercise && <button type="button" className="pop pop-ghost !py-3 text-sm" onClick={() => setGuide(work.exercise!)}><BookOpen size={14} /> How to</button>}
                <button type="button" className="pop pop-ghost !py-3 text-sm" onClick={() => onUpdate(addSet(run))}><Plus size={14} /> Extra set</button>
                {work.exercise && <button type="button" className="pop pop-ghost !py-3 text-sm" onClick={() => setSwap(true)}><ArrowLeftRight size={14} /> Swap</button>}
                <button type="button" className="pop pop-ghost !py-3 text-sm" onClick={() => onUpdate(skipSet(run))}><SkipForward size={14} /> Skip set</button>
                <button type="button" className="pop pop-ghost !py-3 text-sm" disabled={run.idx === 0} onClick={() => onUpdate(goBack(run))}><Undo2 size={14} /> Back</button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="shrink-0 border-t border-line bg-ink px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="mx-auto max-w-2xl">
          {resting ? (
            <button type="button" className="pop pop-lime w-full justify-center !py-4 text-lg" onClick={() => { unlockSound(); setRestUntil(null); onMark(Date.now()); }}>Skip rest</button>
          ) : (
            <button type="button" className="pop pop-lime w-full justify-center !py-4 text-lg" onClick={() => complete()}><Check size={20} /> Done{nextName ? " · next" : ""}</button>
          )}
        </div>
      </div>

      <ExerciseGuide id={guide} setting={plan.setting} onClose={() => setGuide(null)} />
      <SwapSheet exercise={swap && work.exercise ? work.exercise : null} name={name} setting={plan.setting} exclude={[]} note="Only the sets you haven't done yet change." onBrowse={() => { setSwap(false); setPicker(true); }} onClose={() => setSwap(false)}
        onPick={(id) => { setSwap(false); onUpdate(swapRemaining(run, id, nameOf(id))); }} />
      <ExercisePicker open={picker} setting={plan.setting} title="Do this instead" onPick={(e) => { setPicker(false); onUpdate(swapRemaining(run, e.id, e.name)); }} onClose={() => setPicker(false)} />
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
          className="num min-h-14 min-w-0 flex-1 border-b-2 border-line-strong bg-transparent py-2 text-center text-5xl text-paper outline-none focus:border-gold" />
        <RoundBtn label={`${label} plus ${step}`} onClick={() => onChange((value ?? 0) + step)}><Plus size={18} /></RoundBtn>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- summary
function setText(s: GymLoggedSet): string {
  if (!s.done) return "skipped";
  const dist = s.distance_m != null ? (s.distance_m >= 1000 ? `${s.distance_m / 1000} km` : `${s.distance_m} m`) : null;
  const amountText = s.reps != null ? String(s.reps) : s.seconds != null ? `${s.seconds} s` : dist ?? "✓";
  const split = s.took_s != null && s.distance_m != null ? clock(s.took_s) : null;
  return [amountText, s.load, split].filter(Boolean).join(" × ");
}

function Summary({ run, plan, notes, rpe, setNotes, setRpe, nameOf, onDiscard, onSaved }: { run: Run; plan: GymPlanDetail; notes: string; rpe: number | null; setNotes: (n: string) => void; setRpe: (v: number | null) => void; nameOf: (id: string) => string | undefined; onDiscard: () => void; onSaved: () => void }) {
  const entries = useMemo(() => toEntries(run, nameOf), [run]); // eslint-disable-line react-hooks/exhaustive-deps
  const prog = progress(run);
  const duration = Math.round(((run.mark ?? Date.now()) - run.startedAt) / 1000);
  const vol = volumeKg(entries);
  const log = useMutation({
    mutationFn: () => api.gymLogWorkout({ name: plan.title, setting: plan.setting, plan_id: plan.id, session_id: plan.session_id, duration_s: duration, rpe, entries, notes: notes.trim() || null }),
    onSuccess: onSaved,
  });
  const ids = entries.flatMap((e) => (e.exercise ? [e.exercise] : []));
  const next = useQuery({ queryKey: ["gym", "next-time", ids.join(",")], queryFn: () => api.gymLastLoads(ids), enabled: log.isSuccess && ids.length > 0 });
  const hints = Object.entries(next.data?.loads ?? {}).filter(([, l]) => l.hint);
  const all = prog.total > 0 && prog.done === prog.total;
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="surface space-y-4 p-6 sm:p-8">
        <p className="eyebrow">{log.isSuccess ? "Saved" : all ? "Workout complete" : "Session summary"}</p>
        <h2 className="font-display text-4xl text-cream">{prog.done} of {prog.total} sets · {clock(duration)}</h2>
        <p className="text-sm text-mute">{[prog.skipped ? `${prog.skipped} skipped` : "", vol ? `${vol.toLocaleString()} kg lifted (weight × reps, where you entered both)` : ""].filter(Boolean).join(" · ") || "Nothing skipped."}</p>
        <ul className="divide-y divide-line">
          {entries.map((e, i) => (
            <li key={i} className="py-3">
              <p className="text-paper">{e.exercise ? nameOf(e.exercise) ?? e.exercise : e.name}{e.block ? <span className="text-dim"> · {e.block}</span> : null}</p>
              <p className="num text-sm text-mute">{e.sets.map(setText).join(" · ")}</p>
            </li>
          ))}
        </ul>
        {!log.isSuccess && (
          <>
            <div>
              <p className="eyebrow mb-2">How hard did it feel? <span className="text-dim">(optional)</span></p>
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Effort from 1 to 10">
                {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                  <button key={n} type="button" role="radio" aria-checked={rpe === n} onClick={() => setRpe(rpe === n ? null : n)} className={clsx("num grid h-11 w-11 place-items-center rounded-full border text-sm", rpe === n ? "border-gold bg-gold/15 text-cream" : "border-line-strong text-mute")}>{n}</button>
                ))}
              </div>
              <p className="mt-1 text-xs text-dim">1 is very easy, 10 is as hard as you could go.</p>
            </div>
            <label className="block">
              <span className="eyebrow">Notes (optional)</span>
              <textarea className="mt-2 w-full rounded-xl border border-line-strong bg-transparent p-3 text-paper outline-none focus:border-gold" rows={2} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="How it felt, what to change…" />
            </label>
          </>
        )}
        <div className="flex flex-wrap items-center gap-3">
          {log.isSuccess ? <Link to="/plan" className="pop pop-lime !py-3">Back to plan</Link> : <button type="button" className="pop pop-lime !py-3" disabled={log.isPending || prog.done === 0} onClick={() => log.mutate()}>{log.isPending ? "Saving…" : log.isError ? "Try saving again" : "Save to my log"}</button>}
          {!log.isSuccess && <button type="button" className="pop pop-ghost !py-3" onClick={onDiscard}>Discard</button>}
        </div>
        {prog.done === 0 && !log.isSuccess && <p className="text-xs text-dim">No sets were done, so there is nothing to save.</p>}
        {log.isError && <p role="alert" className="text-sm text-coral">{(log.error as Error).message || "Couldn’t save."} Your sets are kept on this phone: try again, even after closing the app.</p>}
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
