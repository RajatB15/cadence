import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { api } from "../../lib/api";
import type { GymExercise, GymSetting } from "../../lib/types";
import { Sheet } from "../Sheet";
import { LEVEL_LABEL, PATTERN_LABEL } from "./useGym";

/** Search the library and pick any exercise. Ones that need equipment you don't have in this setting are shown but can't be added. */
export function ExercisePicker({ open, setting, title = "Add an exercise", onPick, onClose }: { open: boolean; setting: GymSetting; title?: string; onPick: (ex: GymExercise) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [pattern, setPattern] = useState<string | null>(null);
  const deferred = useDeferredValue(q);
  const query = useQuery({ queryKey: ["gym", "pick", deferred, pattern, setting], queryFn: () => api.gymLibrary({ q: deferred, pattern: pattern ?? undefined, limit: 200 }), enabled: open, staleTime: 60_000 });
  const patterns = query.data?.patterns ?? Object.keys(PATTERN_LABEL);
  // The server marks availability when a setting is sent with the library call; do it per exercise from the setting query.
  const avail = useQuery({ queryKey: ["gym", "available", setting], queryFn: () => api.gymLibrary({ setting, limit: 200 }), enabled: open, staleTime: 60_000 });
  const ok = new Set((avail.data?.exercises ?? []).map((e) => e.id));
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} eyebrow={setting === "home" ? "Home equipment only" : "Full gym"} title={title}>
      <div className="space-y-4">
        <label className="flex items-center gap-2 border-b-2 border-line-strong focus-within:border-gold">
          <Search size={16} className="text-dim" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: squat, sled, band…" aria-label="Search exercises" className="w-full bg-transparent py-3 text-lg text-paper outline-none" autoFocus />
        </label>
        <div className="-mx-1 flex flex-nowrap gap-2 overflow-x-auto px-1 pb-1" role="group" aria-label="Movement">
          <button type="button" aria-pressed={pattern == null} className={`chip shrink-0 ${pattern == null ? "border-gold text-cream" : "text-mute"}`} onClick={() => setPattern(null)}>All</button>
          {patterns.map((p) => (
            <button key={p} type="button" aria-pressed={pattern === p} className={`chip shrink-0 ${pattern === p ? "border-gold text-cream" : "text-mute"}`} onClick={() => setPattern(p)}>{PATTERN_LABEL[p] ?? p}</button>
          ))}
        </div>
        {query.isError ? (
          <p role="alert" className="text-sm text-coral">Couldn’t load the library. <button type="button" className="underline" onClick={() => query.refetch()}>Retry</button></p>
        ) : query.isPending ? (
          <div className="h-40 animate-pulse rounded-2xl bg-white/5" aria-busy="true" />
        ) : query.data.exercises.length === 0 ? (
          <p className="text-sm text-mute">Nothing matches. Try another word or movement.</p>
        ) : (
          <ul className="divide-y divide-line">
            {query.data.exercises.map((e) => {
              const usable = !avail.data || ok.has(e.id);
              return (
                <li key={e.id}>
                  <button type="button" disabled={!usable} onClick={() => onPick(e)} className="flex w-full items-center justify-between gap-3 py-3 text-left disabled:opacity-40">
                    <span className="min-w-0">
                      <span className="block truncate text-paper">{e.name}</span>
                      <span className="block truncate text-xs text-dim">{PATTERN_LABEL[e.pattern]} · {LEVEL_LABEL[e.level]} · {e.needs}</span>
                    </span>
                    <span className="text-xs text-gold">{usable ? "Add" : "No kit"}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Sheet>
  );
}
