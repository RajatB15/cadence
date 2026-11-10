import { Dumbbell, TriangleAlert } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { GymExercise, GymSetting } from "../../lib/types";
import { Sheet } from "../Sheet";
import { LEVEL_LABEL, PATTERN_LABEL } from "./useGym";

/** How to do one exercise: the cues in order, the usual mistakes, what it works, and what it needs. */
export function ExerciseGuide({ id, setting, onClose, onPick }: { id: string | null; setting?: GymSetting; onClose: () => void; onPick?: (ex: { id: string; name: string }) => void }) {
  const q = useQuery({ queryKey: ["gym", "exercise", id, setting], queryFn: () => api.gymExercise(id!, setting), enabled: id != null });
  const ex = q.data;
  return (
    <Sheet open={id != null} onOpenChange={(o) => !o && onClose()} eyebrow={ex ? `${PATTERN_LABEL[ex.pattern] ?? ex.pattern} · ${LEVEL_LABEL[ex.level]}` : "Exercise"} title={ex?.name ?? "Loading…"}>
      {q.isError ? (
        <p role="alert" className="text-sm text-coral">Couldn’t load this exercise. <button type="button" className="underline" onClick={() => q.refetch()}>Retry</button></p>
      ) : !ex ? (
        <div className="h-40 animate-pulse rounded-2xl bg-white/5" aria-busy="true" />
      ) : (
        <Body ex={ex} onPick={onPick} />
      )}
    </Sheet>
  );
}

function Body({ ex, onPick }: { ex: GymExercise; onPick?: (ex: { id: string; name: string }) => void }) {
  return (
    <div className="space-y-6">
      <p className="flex flex-wrap items-center gap-2 text-sm text-mute">
        <Dumbbell size={14} className="text-gold" /> {ex.needs}
        {ex.available === false && <span className="chip !border-coral/40 !text-coral">not available in this setting</span>}
      </p>
      <section>
        <h3 className="eyebrow mb-3">How to do it</h3>
        <ol className="space-y-3">
          {ex.cues.map((c, i) => (
            <li key={i} className="flex gap-3 text-paper">
              <span className="num mt-0.5 text-gold">{i + 1}</span>
              <span>{c}</span>
            </li>
          ))}
        </ol>
      </section>
      <section>
        <h3 className="eyebrow mb-3">Common mistakes</h3>
        <ul className="space-y-2 border-l border-coral/40 pl-4 text-mute">
          {ex.mistakes.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </section>
      <p className="text-sm text-mute">
        Works <span className="text-paper">{ex.muscles.primary.join(", ")}</span>
        {ex.muscles.secondary.length > 0 && <> and, less, {ex.muscles.secondary.join(", ")}</>}.
      </p>
      {(ex.easier.length > 0 || ex.harder.length > 0) && (
        <div className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
          {ex.easier.length > 0 && <p className="text-mute">Easier: {ex.easier.map((e) => <button key={e.id} type="button" className="mr-2 text-gold underline" onClick={() => onPick?.(e)} disabled={!onPick}>{e.name}</button>)}</p>}
          {ex.harder.length > 0 && <p className="text-mute">Harder: {ex.harder.map((e) => <button key={e.id} type="button" className="mr-2 text-gold underline" onClick={() => onPick?.(e)} disabled={!onPick}>{e.name}</button>)}</p>}
        </div>
      )}
      <p className="flex gap-2 border-t border-line pt-4 text-xs text-dim">
        <TriangleAlert size={14} className="mt-0.5 shrink-0" />
        <span>Technique notes, not medical advice. Start lighter than you think, keep the movement controlled, and stop if you feel sharp pain. Cadence doesn’t know your limits or injuries.</span>
      </p>
    </div>
  );
}
