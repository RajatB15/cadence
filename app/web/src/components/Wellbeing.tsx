import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Check, HeartPulse, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import type { BriefWellbeing, RecoveryWins, WellbeingEntry } from "../lib/types";
import { NoteGrid } from "./CoachNotes";

const FEEL = ["Awful", "Flat", "Okay", "Good", "Great"];
const SORE = ["None", "Mild", "Moderate", "Severe"];
const PAIN = ["None", "Niggle", "Hurts", "Stops me"];
const ILL = ["Well", "Run down", "Properly ill"];
const STRESS = ["Light", "Normal", "Heavy"];
const LEVEL_COLOR = { rest: "#ff6a55", easy: "#ffbe55", watch: "#6cc7ff" } as const;

function Choice({ label, options, value, offset = 0, onPick }: { label: string; options: string[]; value: number | null | undefined; offset?: number; onPick: (v: number) => void }) {
  return (
    <div role="radiogroup" aria-label={label}>
      <p className="eyebrow mb-2">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o, i) => {
          const v = i + offset;
          const on = value === v;
          return (
            <button key={o} type="button" role="radio" aria-checked={on} onClick={() => onPick(v)}
              className={clsx("min-w-14 border px-3 py-2 text-xs font-semibold tracking-wide transition-colors pointer-coarse:py-3",
                on ? "border-gold bg-gold/15 text-paper" : "border-line-strong text-mute hover:text-paper")}>
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** How do you feel today? One tap saves a check-in; the details are optional and save as you go. */
export function WellbeingCard({ day, block }: { day: string; block: BriefWellbeing }) {
  const client = useQueryClient();
  const entry = block.today;
  const [more, setMore] = useState(false);
  const [area, setArea] = useState(entry?.pain_area ?? "");
  const save = useMutation({
    mutationFn: (patch: Partial<Omit<WellbeingEntry, "day">>) => api.saveWellbeing(day, patch),
    onSuccess: () => {
      for (const k of ["overview", "insights", "wellbeing", "planner", "outcomes"]) client.invalidateQueries({ queryKey: [k] });
    },
  });
  const level = block.level;
  const color = level ? LEVEL_COLOR[level] : "#c8f560";
  const summary = entry
    ? [
        entry.feel != null && `Feeling ${FEEL[entry.feel - 1].toLowerCase()}`,
        entry.soreness ? `${SORE[entry.soreness].toLowerCase()} soreness` : null,
        entry.pain_level ? `${PAIN[entry.pain_level].toLowerCase()}${entry.pain_area ? ` in your ${entry.pain_area}` : ""}` : null,
        entry.illness ? ILL[entry.illness].toLowerCase() : null,
        entry.life_stress === 3 ? "heavy life load" : null,
      ].filter(Boolean).join(" · ")
    : "";
  return (
    <section className="surface p-5 sm:p-6" style={{ borderLeft: `3px solid ${color}` }} aria-label="Check-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="eyebrow flex items-center gap-2"><HeartPulse size={14} style={{ color }} /> {entry ? "Today's check-in" : "How do you feel today?"}</p>
        {entry && !more && (
          <button type="button" className="text-xs font-semibold tracking-widest text-mute uppercase hover:text-paper" onClick={() => setMore(true)}>
            {entry.soreness == null && entry.pain_level == null && entry.illness == null ? "Add details" : "Edit"}
          </button>
        )}
      </div>
      {entry && !more ? (
        <p className="mt-2 flex items-center gap-2 text-paper"><Check size={15} className="text-lime" /> {summary || "Checked in"}</p>
      ) : (
        <div className="mt-4 space-y-5">
          <Choice label="Overall" options={FEEL} offset={1} value={entry?.feel} onPick={(v) => save.mutate({ feel: v })} />
          {!more && (
            <button type="button" className="text-xs font-semibold tracking-widest text-mute uppercase hover:text-paper" onClick={() => setMore(true)}>Soreness, pain, illness, stress</button>
          )}
          {more && (
            <>
              <Choice label="Soreness" options={SORE} value={entry?.soreness} onPick={(v) => save.mutate({ soreness: v })} />
              <Choice label="Pain" options={PAIN} value={entry?.pain_level} onPick={(v) => save.mutate({ pain_level: v })} />
              {(entry?.pain_level ?? 0) > 0 && (
                <div>
                  <label className="eyebrow" htmlFor="pain-area">Where?</label>
                  <input id="pain-area" value={area} maxLength={40} placeholder="left knee, calf, lower back…" onChange={(e) => setArea(e.target.value)}
                    onBlur={() => area !== (entry?.pain_area ?? "") && save.mutate({ pain_area: area })}
                    className="mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold" />
                </div>
              )}
              <Choice label="Illness" options={ILL} value={entry?.illness} onPick={(v) => save.mutate({ illness: v })} />
              <Choice label="Life load right now" options={STRESS} offset={1} value={entry?.life_stress} onPick={(v) => save.mutate({ life_stress: v })} />
              <button type="button" className="pop pop-ghost" onClick={() => setMore(false)}>Done</button>
            </>
          )}
          {save.isError && <p role="alert" className="text-xs text-coral">Couldn't save. Try again.</p>}
        </div>
      )}
      {level && (level === "rest" || level === "easy") && (
        <p className="mt-3 text-sm" style={{ color }}>Today's call has changed because of this.</p>
      )}
      {block.notes.length > 0 && <div className="mt-5"><NoteGrid notes={block.notes} compact /></div>}
    </section>
  );
}

export function RecoveryWinsCard({ wins }: { wins: RecoveryWins | null | undefined }) {
  if (!wins) return null;
  return (
    <section className="surface p-5 sm:p-6" style={{ borderLeft: "3px solid #5be3b0" }}>
      <p className="eyebrow mb-2 flex items-center gap-2"><Sparkles size={14} className="text-mint" /> {wins.title} · last {wins.window} days</p>
      <p className="text-sm text-mute">{wins.text}</p>
      <ul className="mt-3 space-y-1.5 text-sm text-paper">
        {wins.items.map((i) => <li key={i} className="flex items-start gap-2"><Check size={14} className="mt-0.5 shrink-0 text-lime" />{i}</li>)}
      </ul>
    </section>
  );
}
