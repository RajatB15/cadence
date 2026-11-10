import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../lib/api";
import type { GymSetting } from "../../lib/types";
import { Sheet } from "../Sheet";
import { LEVEL_LABEL } from "./useGym";

const DIRS = [
  { key: "easier", label: "Easier" },
  { key: "harder", label: "Harder" },
  { key: "different", label: "Different" },
] as const;

/** Replace one exercise with an easier or harder version, a completely different one, or anything you pick yourself. Nothing changes until you choose. */
export function SwapSheet({ exercise, name, setting, exclude, onPick, onBrowse, onClose }: {
  exercise: string | null;
  name: string;
  setting: GymSetting;
  exclude: string[];
  onPick: (id: string) => void;
  onBrowse: () => void;
  onClose: () => void;
}) {
  const [dir, setDir] = useState<(typeof DIRS)[number]["key"]>("different");
  const q = useQuery({ queryKey: ["gym", "alt", exercise, dir, setting, exclude.join(",")], queryFn: () => api.gymAlternatives({ exercise: exercise!, direction: dir, setting, exclude }), enabled: exercise != null });
  return (
    <Sheet open={exercise != null} onOpenChange={(o) => !o && onClose()} eyebrow={`Replace · ${setting === "home" ? "home kit only" : "full gym"}`} title={name}>
      <div className="space-y-5">
        <div role="radiogroup" aria-label="Direction" className="inline-flex rounded-full border border-line-strong bg-slate/50 p-1">
          {DIRS.map((d) => (
            <button key={d.key} type="button" role="radio" aria-checked={dir === d.key} onClick={() => setDir(d.key)}
              className={`rounded-full px-4 py-2 text-sm ${dir === d.key ? "bg-paper text-ink" : "text-mute"}`}>{d.label}</button>
          ))}
        </div>
        {q.isError ? (
          <p role="alert" className="text-sm text-coral">Couldn’t find options. <button type="button" className="underline" onClick={() => q.refetch()}>Retry</button></p>
        ) : q.isPending ? (
          <div className="h-32 animate-pulse rounded-2xl bg-white/5" aria-busy="true" />
        ) : q.data.alternatives.length === 0 ? (
          <p className="text-sm text-mute">Nothing {dir} is available with this kit. Try another direction, or browse everything.</p>
        ) : (
          <ul className="divide-y divide-line">
            {q.data.alternatives.map((a) => (
              <li key={a.id}>
                <button type="button" className="flex w-full items-center justify-between gap-3 py-3 text-left" onClick={() => onPick(a.id)}>
                  <span className="min-w-0">
                    <span className="block text-paper">{a.name}</span>
                    <span className="block text-xs text-dim">{a.reason} · {LEVEL_LABEL[a.level]} · {a.needs}</span>
                  </span>
                  <span className="text-xs text-gold">Use this</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="pop pop-ghost" onClick={onBrowse}>Choose any exercise…</button>
      </div>
    </Sheet>
  );
}
