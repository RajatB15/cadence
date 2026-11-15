import { ArrowDown, ArrowLeftRight, ArrowUp, Clock, ListChecks, Pencil, Plus, SkipForward, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { GymExercise } from "../../lib/types";
import { clock } from "../../lib/workoutQueue";
import type { Run } from "../../lib/workoutQueue";
import { defaultSpec, etaSeconds, remaining, type InsertSpec, type Segment, type SegmentPatch } from "../../lib/workoutEdit";
import { Sheet } from "../Sheet";

const targetText = (t: Segment["target"]) => (t.reps != null ? `${t.reps} reps` : t.seconds != null ? `${t.seconds} s` : t.distance_m != null ? (t.distance_m >= 1000 && t.distance_m % 100 === 0 ? `${t.distance_m / 1000} km` : `${t.distance_m} m`) : t.calories != null ? `${t.calories} cal` : "");

function Row({ icon, title, hint, onClick, tone }: { icon: ReactNode; title: string; hint?: string; onClick: () => void; tone?: "danger" }) {
  return (
    <button type="button" onClick={onClick} className="flex min-h-14 w-full items-center gap-4 px-1 py-3 text-left active:bg-white/5">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full border border-line-strong ${tone === "danger" ? "text-coral" : "text-gold"}`}>{icon}</span>
      <span className="min-w-0">
        <span className={`block text-lg ${tone === "danger" ? "text-coral" : "text-paper"}`}>{title}</span>
        {hint && <span className="block text-xs text-dim">{hint}</span>}
      </span>
    </button>
  );
}

/** Everything that can be done with the exercise you are on: the "machine is busy" moves in one place. Opening it changes nothing. */
export function ChangeSheet({ open, seg, name, nextName, hasNext, onClose, onDefer, onSwap, onEdit, onAdd, onSkip, onRemove }: {
  open: boolean; seg: Segment | undefined; name: string; nextName: string | null; hasNext: boolean; onClose: () => void;
  onDefer: (where: "after_next" | "end") => void; onSwap: () => void; onEdit: () => void; onAdd: () => void; onSkip: () => void; onRemove: () => void;
}) {
  if (!seg) return null;
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} eyebrow="Machine busy, or want a change?" title={name}>
      <div className="divide-y divide-line">
        {hasNext && <Row icon={<Clock size={18} />} title={`Do it after ${nextName ?? "the next one"}`} hint="Keeps your sets so far; the rest of this exercise comes back later" onClick={() => onDefer("after_next")} />}
        {hasNext && <Row icon={<ArrowDown size={18} />} title="Do it at the end" hint="Move the rest of this exercise to the very end" onClick={() => onDefer("end")} />}
        <Row icon={<ArrowLeftRight size={18} />} title="Swap for another exercise" hint="Easier, harder or something different" onClick={onSwap} />
        <Row icon={<Pencil size={18} />} title="Change sets, reps, weight or rest" hint="Only for the sets you have not done yet" onClick={onEdit} />
        <Row icon={<Plus size={18} />} title="Add an exercise" hint="Now, after this one, or at the end" onClick={onAdd} />
        <Row icon={<SkipForward size={18} />} title="Skip the rest of this exercise" hint="Kept in your log as skipped" onClick={onSkip} />
        <Row icon={<Trash2 size={18} />} title="Take it out of today" hint="Not logged as skipped; sets already done stay" tone="danger" onClick={onRemove} />
      </div>
      <p className="mt-4 text-xs text-dim">These changes apply to today's workout only. Your saved session stays as it was.</p>
    </Sheet>
  );
}

/** The rest of the workout, in order, with each exercise's controls. Reordering here is how a busy rack is worked around. */
export function WhatsLeftSheet({ open, run, nameOf, onClose, onMove, onEdit, onRemove, onAdd }: {
  open: boolean; run: Run; nameOf: (s: Segment) => string; onClose: () => void; onMove: (id: string, dir: -1 | 1) => void; onEdit: (id: string) => void; onRemove: (id: string) => void; onAdd: () => void;
}) {
  const segs = open ? remaining(run) : [];
  const eta = open ? etaSeconds(run) : null;
  const sets = segs.reduce((n, s) => n + s.items.length, 0);
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} eyebrow={`${sets} set${sets === 1 ? "" : "s"} to go${eta != null ? ` · about ${Math.max(1, Math.round(eta / 60))} min at your pace` : ""}`} title="What's left">
      <div className="space-y-4">
        {segs.length === 0 ? <p className="text-sm text-mute">Nothing left. Finish now to save what you did.</p> : (
          <ol className="divide-y divide-line">
            {segs.map((s, i) => (
              <li key={s.id} className="py-3">
                <p className="text-lg leading-snug text-paper">{nameOf(s)}{i === 0 && <span className="ml-2 text-xs text-gold">now</span>}</p>
                <p className="num text-sm text-mute">{[s.block, s.items.length > 1 || s.doneBefore ? `${s.items.length} left` : "1 set", targetText(s.target), s.load].filter(Boolean).join(" · ")}</p>
                <div className="mt-1 flex justify-end gap-1">
                  <button type="button" aria-label={`Move ${nameOf(s)} earlier`} disabled={i === 0} onClick={() => onMove(s.id, -1)} className="grid h-11 w-12 place-items-center rounded-full text-mute disabled:opacity-30"><ArrowUp size={18} /></button>
                  <button type="button" aria-label={`Move ${nameOf(s)} later`} disabled={i === segs.length - 1} onClick={() => onMove(s.id, 1)} className="grid h-11 w-12 place-items-center rounded-full text-mute disabled:opacity-30"><ArrowDown size={18} /></button>
                  <button type="button" aria-label={`Change ${nameOf(s)}`} onClick={() => onEdit(s.id)} className="grid h-11 w-12 place-items-center rounded-full text-gold"><Pencil size={18} /></button>
                  <button type="button" aria-label={`Take ${nameOf(s)} out of today`} onClick={() => onRemove(s.id)} className="grid h-11 w-12 place-items-center rounded-full text-coral"><Trash2 size={18} /></button>
                </div>
              </li>
            ))}
          </ol>
        )}
        <button type="button" className="pop pop-ghost !py-3" onClick={onAdd}><Plus size={14} /> Add an exercise</button>
        <p className="text-xs text-dim"><ListChecks size={12} className="mr-1 inline" aria-hidden />Today only. Sets you have done are never changed. {run.edits?.length ? `${run.edits.length} change${run.edits.length === 1 ? "" : "s"} so far.` : ""}</p>
      </div>
    </Sheet>
  );
}

function Num({ label, value, onChange, step = 1, min = 1, unit }: { label: string; value: number | undefined; onChange: (v: number) => void; step?: number; min?: number; unit?: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}{unit ? ` (${unit})` : ""}</p>
      <div className="flex items-center gap-2">
        <button type="button" aria-label={`${label} minus`} onClick={() => onChange(Math.max(min, (value ?? 0) - step))} className="grid h-12 w-12 place-items-center rounded-full border border-line-strong text-xl text-paper">−</button>
        <input aria-label={label} inputMode="numeric" value={value ?? ""} onChange={(e) => onChange(Math.max(min, Number(e.target.value.replace(/\D/g, "")) || min))} className="num min-h-12 w-20 border-b-2 border-line-strong bg-transparent text-center text-3xl text-paper outline-none focus:border-gold" />
        <button type="button" aria-label={`${label} plus`} onClick={() => onChange((value ?? 0) + step)} className="grid h-12 w-12 place-items-center rounded-full border border-line-strong text-xl text-paper">+</button>
      </div>
    </div>
  );
}

/** Change what is left of one exercise. Only the fields that exercise has are shown; nothing is applied until Save. */
export function EditSegmentSheet({ seg, nameOf, onClose, onSave }: { seg: Segment | undefined; nameOf: (s: Segment) => string; onClose: () => void; onSave: (patch: SegmentPatch) => void }) {
  return (
    <Sheet open={seg != null} onOpenChange={(o) => !o && onClose()} eyebrow="Only the sets you have not done" title={seg ? nameOf(seg) : ""}>
      {seg && <EditForm key={seg.id} seg={seg} onSave={onSave} />}
    </Sheet>
  );
}

function EditForm({ seg, onSave }: { seg: Segment; onSave: (patch: SegmentPatch) => void }) {
  const t = seg.target;
  const [sets, setSets] = useState(seg.items.length + seg.doneBefore);
  const [reps, setReps] = useState(t.reps);
  const [secs, setSecs] = useState(t.seconds);
  const [dist, setDist] = useState(t.distance_m);
  const [load, setLoad] = useState(seg.load ?? "");
  const [rest, setRest] = useState(seg.restAfter);
  const submit = () => {
    const patch: SegmentPatch = { sets, rest_s: rest };
    if (reps != null) patch.reps = reps;
    if (secs != null) patch.seconds = secs;
    if (dist != null) patch.distance_m = dist;
    if ((seg.load ?? "") !== load) patch.load = load;
    onSave(patch);
  };
  return (
    <div className="space-y-5">
      <Num label="Sets in total" value={sets} onChange={setSets} min={seg.doneBefore + 1} />
      {reps != null && <Num label="Reps" value={reps} onChange={setReps} />}
      {secs != null && <Num label="Seconds" value={secs} onChange={setSecs} step={5} />}
      {dist != null && <Num label="Distance" unit="m" value={dist} onChange={setDist} step={50} />}
      <label className="block">
        <span className="eyebrow">Weight</span>
        <input value={load} onChange={(e) => setLoad(e.target.value)} placeholder="bodyweight" maxLength={40} aria-label="Weight" className="num mt-1 min-h-12 w-full border-b-2 border-line-strong bg-transparent text-3xl text-paper outline-none focus:border-gold" />
      </label>
      <Num label="Rest between sets" unit="s" value={rest} onChange={setRest} step={15} min={0} />
      <div className="flex gap-3">
        <button type="button" className="pop pop-lime !py-3" onClick={submit}>Save changes</button>
      </div>
    </div>
  );
}

/** After an exercise is picked: where it goes. The spec is the usual starting prescription for it and can be changed later in What's left. */
export function AddWhereSheet({ ex, name, onClose, onChoose }: { ex: GymExercise | null; name?: string; onClose: () => void; onChoose: (spec: InsertSpec, at: "now" | "after_current" | "end") => void }) {
  const spec = ex ? defaultSpec(ex, name) : null;
  return (
    <Sheet open={ex != null} onOpenChange={(o) => !o && onClose()} eyebrow="Add to today's workout" title={ex?.name ?? ""}>
      {ex && spec && (
        <div className="space-y-2">
          <p className="num text-mute">{spec.sets} × {spec.reps != null ? `${spec.reps} reps` : spec.seconds != null ? `${spec.seconds} s` : spec.distance_m != null ? `${spec.distance_m} m` : `${spec.calories} cal`}{spec.rest_s ? ` · rest ${clock(spec.rest_s)}` : ""}</p>
          <div className="divide-y divide-line">
            <Row icon={<Plus size={18} />} title="Do it now" hint="The exercise you are on resumes after it" onClick={() => onChoose(spec, "now")} />
            <Row icon={<Clock size={18} />} title="After this exercise" onClick={() => onChoose(spec, "after_current")} />
            <Row icon={<ArrowDown size={18} />} title="At the end" onClick={() => onChoose(spec, "end")} />
          </div>
          <p className="text-xs text-dim">You can change its sets, reps and weight from What's left.</p>
        </div>
      )}
    </Sheet>
  );
}
