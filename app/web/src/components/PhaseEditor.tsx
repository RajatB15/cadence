import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { ACTIVITY_FAMILIES } from "../lib/metrics";
import {
  KIND_HELP,
  PACE_METRICS,
  KIND_LABEL,
  MEASURES,
  PHASE_COLORS,
  PHASE_EMOJI,
  defaultMetric,
  draftOf,
  pillarOf,
  templates,
  validateBody,
  type PillarDraft,
} from "../lib/phases";
import type { HabitOption, PhaseBody, PhaseDetail, PillarSpec } from "../lib/types";
import { Sheet } from "./Sheet";

const input = "w-full border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold";
const label = "eyebrow mb-1 block";
const KINDS = Object.keys(KIND_LABEL) as PillarSpec["kind"][];

function PillarEditor({ draft, habits, onChange, onRemove }: { draft: PillarDraft; habits: HabitOption[]; onChange: (d: PillarDraft) => void; onRemove: () => void }) {
  const set = (patch: Partial<PillarDraft>) => onChange({ ...draft, ...patch });
  const measures = MEASURES[draft.kind];
  const unit = measures[draft.metric]?.unit;
  const pace = draft.kind === "goal" && PACE_METRICS.has(draft.metric);
  const noFamily = draft.kind === "goal" ? draft.metric !== "longest_km" : draft.metric === "steps" || draft.metric === "sleep_h";
  return (
    <li className="surface space-y-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Pillar type">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={draft.kind === k}
              onClick={() => onChange({ ...draft, kind: k, metric: defaultMetric(k), family: "", target: k === "total" ? "100" : k === "goal" ? "" : draft.target })}
              className={clsx("border px-3 py-1.5 text-xs font-semibold tracking-widest uppercase", draft.kind === k ? "border-gold bg-gold/10 text-paper" : "border-line-strong text-mute hover:text-paper")}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <button type="button" aria-label="Remove pillar" onClick={onRemove} className="p-1 text-dim hover:text-coral">
          <X size={16} />
        </button>
      </div>
      <p className="text-xs text-dim">{KIND_HELP[draft.kind]}</p>

      {draft.kind === "habit" ? (
        habits.length === 0 ? (
          <p className="text-sm text-mute">No journal habits yet. Turn some on from the daily check-in first.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <label>
              <span className={label}>Habit</span>
              <select value={draft.behaviour} onChange={(e) => set({ behaviour: e.target.value })} className={clsx(input, "bg-coal")}>
                <option value="">Choose…</option>
                {habits.map((h) => <option key={h.key} value={h.key}>{h.label}</option>)}
              </select>
            </label>
            <label>
              <span className={label}>Keep it to</span>
              <select value={draft.want} onChange={(e) => set({ want: e.target.value as "no" | "yes" })} className={clsx(input, "bg-coal")}>
                <option value="no">No (or zero)</option>
                <option value="yes">Yes</option>
              </select>
            </label>
          </div>
        )
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <label>
            <span className={label}>Measure</span>
            <select value={draft.metric} onChange={(e) => set({ metric: e.target.value })} className={clsx(input, "bg-coal")}>
              {Object.entries(measures).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
            </select>
          </label>
          <label>
            <span className={label}>{draft.kind === "daily" ? "At least" : draft.kind === "weekly" ? "At least, per week" : draft.kind === "goal" ? "Goal" : "Target"} {unit && `(${unit})`}</span>
            <input inputMode={pace ? "text" : "decimal"} placeholder={pace ? "5:30" : undefined} value={draft.target} onChange={(e) => set({ target: e.target.value })} className={clsx(input, "num")} />
          </label>
          {!noFamily && (
            <label>
              <span className={label}>Counting</span>
              <select value={draft.family} onChange={(e) => set({ family: e.target.value })} className={clsx(input, "bg-coal")}>
                <option value="">Any activity</option>
                {Object.entries(ACTIVITY_FAMILIES).filter(([k]) => k !== "other").map(([k, f]) => <option key={k} value={k}>{f.label}</option>)}
              </select>
            </label>
          )}
        </div>
      )}

      {(draft.kind === "daily" || draft.kind === "habit") && (
        <label className="block max-w-xs">
          <span className={label}>Rest passes</span>
          <input inputMode="numeric" value={draft.passes} onChange={(e) => set({ passes: e.target.value })} className={clsx(input, "num")} />
          <span className="mt-1 block text-xs text-dim">Days you may miss and still count as on track. 0 means no breaks.</span>
        </label>
      )}
      <label className="block">
        <span className={label}>Your own wording (optional)</span>
        <input maxLength={60} value={draft.label} onChange={(e) => set({ label: e.target.value })} placeholder="Chosen for you" className={input} />
      </label>
    </li>
  );
}

/** Create or edit a phase. New phases can start from a template (Winter Arc, No Break November …). */
export function PhaseEditor({ open, onOpenChange, phase, habits, onSaved }: { open: boolean; onOpenChange: (o: boolean) => void; phase?: PhaseDetail; habits: HabitOption[]; onSaved: (p: PhaseDetail) => void }) {
  const client = useQueryClient();
  const [name, setName] = useState(phase?.name ?? "");
  const [tagline, setTagline] = useState(phase?.tagline ?? "");
  const [emoji, setEmoji] = useState(phase?.emoji ?? "🎯");
  const [color, setColor] = useState(phase?.color ?? PHASE_COLORS[0]);
  const [start, setStart] = useState(phase?.start ?? "");
  const [end, setEnd] = useState(phase?.end ?? "");
  const [pillars, setPillars] = useState<PillarDraft[]>((phase?.pillars ?? []).map((p) => draftOf(p)));
  const [error, setError] = useState<string | null>(null);

  const apply = (b: PhaseBody) => {
    setName(b.name); setTagline(b.tagline); setEmoji(b.emoji); setColor(b.color); setStart(b.start); setEnd(b.end);
    setPillars(b.pillars.map((p) => draftOf(p)));
    setError(null);
  };

  const save = useMutation({
    mutationFn: (body: PhaseBody) => (phase ? api.updatePhase(phase.id, body) : api.createPhase(body)),
    onSuccess: (saved) => {
      client.invalidateQueries({ queryKey: ["phases"] });
      client.invalidateQueries({ queryKey: ["phases-active"] });
      client.invalidateQueries({ queryKey: ["phase", saved.id] });
      onSaved(saved);
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Couldn’t save"),
  });

  const submit = () => {
    const built: PillarSpec[] = [];
    for (const d of pillars) {
      const r = pillarOf(d);
      if ("error" in r) return setError(r.error);
      built.push(r.pillar);
    }
    const body: PhaseBody = { name: name.trim(), tagline: tagline.trim(), emoji, color, start, end, pillars: built };
    const problem = validateBody(body);
    if (problem) return setError(problem);
    setError(null);
    save.mutate(body);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} eyebrow={phase ? "Edit phase" : "New phase"} title={phase ? phase.name : "Name a stretch of time"}>
      <div className="space-y-8">
        {!phase && (
          <div>
            <p className="eyebrow mb-2">Start from</p>
            <div className="flex flex-wrap gap-2">
              {templates(new Date()).map((t) => (
                <button key={t.key} type="button" onClick={() => apply(t.body)} className="chip text-mute hover:text-paper pointer-coarse:py-2">
                  <span aria-hidden>{t.body.emoji}</span> {t.label}
                </button>
              ))}
            </div>
          </div>
        )}
        <label className="block">
          <span className={label}>Name</span>
          <input maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="No Break November" className={clsx(input, "text-2xl")} />
        </label>
        <label className="block">
          <span className={label}>Tagline (optional)</span>
          <input maxLength={160} value={tagline} onChange={(e) => setTagline(e.target.value)} className={input} />
        </label>
        <div className="grid grid-cols-2 gap-4">
          <label>
            <span className={label}>Starts</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={clsx(input, "num")} />
          </label>
          <label>
            <span className={label}>Ends</span>
            <input type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} className={clsx(input, "num")} />
          </label>
        </div>
        <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
          <div>
            <p className={label}>Icon</p>
            <div className="flex flex-wrap gap-2">
              {PHASE_EMOJI.map((e) => (
                <button key={e} type="button" aria-label={`Icon ${e}`} aria-pressed={emoji === e} onClick={() => setEmoji(e)} className={clsx("h-9 w-9 border text-lg", emoji === e ? "border-gold bg-gold/10" : "border-line-strong")}>{e}</button>
              ))}
            </div>
          </div>
          <div>
            <p className={label}>Colour</p>
            <div className="flex gap-2">
              {PHASE_COLORS.map((c) => (
                <button key={c} type="button" aria-label={`Colour ${c}`} aria-pressed={color === c} onClick={() => setColor(c)} className={clsx("h-9 w-9 border-2", color === c ? "border-paper" : "border-transparent")} style={{ background: c }} />
              ))}
            </div>
          </div>
        </div>

        <div>
          <div className="mb-3 flex items-center justify-between">
            <p className="eyebrow">What you’re committing to</p>
            {pillars.length < 6 && (
              <button type="button" onClick={() => setPillars([...pillars, draftOf()])} className="chip text-mute hover:text-paper"><Plus size={12} /> Add pillar</button>
            )}
          </div>
          {pillars.length === 0 ? (
            <p className="text-sm text-mute">No pillars: the phase still tracks everything you do in it, just without targets.</p>
          ) : (
            <ul className="space-y-3">
              {pillars.map((d, i) => (
                <PillarEditor key={i} draft={d} habits={habits} onChange={(n) => setPillars(pillars.map((x, j) => (j === i ? n : x)))} onRemove={() => setPillars(pillars.filter((_, j) => j !== i))} />
              ))}
            </ul>
          )}
        </div>

        {error && <p role="alert" className="text-sm text-coral">{error}</p>}
        <div className="flex gap-3">
          <button type="button" className="pop" disabled={save.isPending} onClick={submit}>{save.isPending ? "Saving…" : phase ? "Save changes" : "Create phase"}</button>
          <button type="button" className="pop pop-ghost" onClick={() => onOpenChange(false)}>Cancel</button>
        </div>
      </div>
    </Sheet>
  );
}
