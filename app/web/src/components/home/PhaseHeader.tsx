import { clsx } from "clsx";
import type { ReactNode } from "react";
import { C } from "../../lib/theme";
import { CondensedTitle } from "../CondensedTitle";
import { PHASE_LABEL, phaseAccent } from "../../lib/home";

/** Greeting with an ambient accent that follows the day phase (a soft glow, no illustration). */
export function PhaseHeader({ day, greeting, subtitle, phase, hour, chip }: { day: string; greeting: string; subtitle?: string | null; phase?: string; hour: number; chip: ReactNode }) {
  const accent = C[phaseAccent(phase, hour)];
  return (
    <header className="relative">
      <span aria-hidden className="pointer-events-none absolute -top-16 -left-10 h-48 w-72 rounded-full opacity-25 blur-3xl" style={{ background: accent }} />
      <CondensedTitle title={greeting}>
      <div className="eyebrow relative mb-3 flex flex-wrap items-center gap-3">
        <span>{day}</span>
        {phase && PHASE_LABEL[phase] && <span className="chip !text-[11px] !tracking-wider" style={{ borderColor: `${accent}77`, color: accent }}>{PHASE_LABEL[phase]}</span>}
        {chip}
      </div>
      <h1 className="t-large relative sm:!text-6xl">{greeting}.</h1>
      </CondensedTitle>
      {subtitle && <p className={clsx("relative mt-3 max-w-xl text-base text-mute sm:text-lg")}>{subtitle}</p>}
    </header>
  );
}
