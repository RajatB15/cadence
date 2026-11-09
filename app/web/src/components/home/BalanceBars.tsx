import { motion, useReducedMotion } from "motion/react";
import { useId } from "react";
import { CountUp } from "../CountUp";
import { formatKcal } from "../../lib/home";
import type { TodayBars, WeekBalance } from "../../lib/balance";

const pct = (f: number) => `${Math.max(0, Math.min(1, f)) * 100}%`;

/** A bar that grows from the left; `left` and `width` are 0..1 shares of the track. */
function Seg({ left = 0, width, color, delay = 0, className = "", style }: { left?: number; width: number; color: string; delay?: number; className?: string; style?: React.CSSProperties }) {
  const reduce = useReducedMotion();
  if (!(width > 0)) return null;
  return (
    <motion.span
      aria-hidden
      className={`absolute inset-y-0 ${className}`}
      style={{ left: pct(left), background: color, ...style }}
      initial={{ width: reduce ? pct(width) : 0 }}
      animate={{ width: pct(width) }}
      transition={{ duration: reduce ? 0 : 0.9, delay: reduce ? 0 : delay, ease: [0.16, 1, 0.3, 1] }}
    />
  );
}

const track = "relative h-4 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--color-paper)_9%,transparent)]";

/** Burned and eaten as two bars on one scale, so the space between their ends is the balance. Target is a tick on the eaten bar. */
export function BalanceBars({ bars, summary }: { bars: TodayBars; summary: string }) {
  const id = useId();
  const over = bars.gap != null && bars.gap < 0;
  const tickAt = bars.allowanceFrac;
  const tickAlign = tickAt == null ? "" : tickAt > 0.72 ? "-translate-x-full" : tickAt < 0.28 ? "" : "-translate-x-1/2";
  return (
    <div role="img" aria-label={summary}>
      {bars.gap != null ? (
        <div className="mb-5">
          <p className="eyebrow">{over ? "Eaten more than burned so far" : "Deficit so far"}</p>
          <p className="numeral mt-1 text-[clamp(40px,13vw,56px)] leading-none" style={{ color: over ? "var(--color-amber)" : "var(--color-mint)" }}>
            <CountUp value={Math.abs(bars.gap)} format={formatKcal} immediate />
            <span className="ml-1.5 text-base font-semibold text-mute">kcal</span>
          </p>
          <p className="num mt-1.5 text-xs text-mute">{formatKcal(bars.burned)} burned − {formatKcal(bars.eaten!)} eaten</p>
        </div>
      ) : (
        <div className="mb-5">
          <p className="eyebrow">Burned so far</p>
          <p className="numeral mt-1 text-[clamp(40px,13vw,56px)] leading-none text-cream"><CountUp value={bars.burned} format={formatKcal} immediate /><span className="ml-1.5 text-base font-semibold text-mute">kcal</span></p>
          <p className="mt-1.5 text-xs text-mute">Log what you eat to see the balance.</p>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <div className="mb-1.5 flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-2 text-sm font-bold text-cream"><i aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-gold)" }} />Burned</span>
            <span className="num text-sm text-cream">{formatKcal(bars.burned)}</span>
          </div>
          <div className={track} data-bar="burned">
            {bars.projLoFrac != null && bars.projHiFrac != null && (
              <Seg left={bars.burnedFrac} width={Math.max(0, bars.projHiFrac - bars.burnedFrac)} color="repeating-linear-gradient(135deg, color-mix(in srgb, var(--color-gold) 38%, transparent) 0 4px, transparent 4px 8px)" delay={0.5} />
            )}
            {bars.restingFrac != null ? (
              <>
                <Seg width={bars.restingFrac} color="color-mix(in srgb, var(--color-gold) 55%, transparent)" />
                <Seg left={bars.restingFrac} width={bars.burnedFrac - bars.restingFrac} color="var(--color-gold)" delay={0.15} />
              </>
            ) : (
              <Seg width={bars.burnedFrac} color="var(--color-gold)" />
            )}
          </div>
          <p className="mt-1 text-[11px] text-dim">
            {bars.restingFrac != null ? `${formatKcal(bars.resting!)} resting + ${formatKcal(bars.active!)} active` : "resting and active not split"}
            {bars.projected ? ` · hatched: where the day may end, ${formatKcal(bars.projected.lo)} to ${formatKcal(bars.projected.hi)}` : ""}
          </p>
        </div>

        <div>
          <div className="mb-1.5 flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-2 text-sm font-bold text-cream"><i aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-sky)" }} />Eaten</span>
            <span className="num text-sm text-cream">{bars.eaten != null ? formatKcal(bars.eaten) : "nothing logged"}</span>
          </div>
          <div className="relative">
            <div className={track} data-bar="eaten">
              {bars.eatenFrac != null && <Seg width={bars.eatenFrac} color="var(--color-sky)" delay={0.1} />}
              {bars.eatenFrac != null && bars.eatenLow != null && bars.eatenHigh != null && bars.eatenHigh > bars.eatenLow && (
                <Seg left={Math.min(bars.eatenFrac, bars.eatenLow / bars.scale)} width={Math.max(0, (bars.eatenHigh - bars.eatenLow) / bars.scale)} color="color-mix(in srgb, var(--color-sky) 45%, transparent)" delay={0.6} />
              )}
            </div>
            {tickAt != null && (
              <span aria-hidden className="pointer-events-none absolute -top-1 -bottom-1 w-[3px] -translate-x-1/2 rounded-full bg-[var(--color-cream)]" style={{ left: pct(tickAt) }} />
            )}
          </div>
          {tickAt != null && bars.allowance != null && (
            <div className="relative mt-1 h-4" id={id}>
              <span className={`num absolute whitespace-nowrap text-[11px] text-mute ${tickAlign}`} style={{ left: pct(tickAt) }}>target {formatKcal(bars.allowance)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const initial = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { weekday: "narrow" });

/** Last seven settled days: a bar up for a deficit, down for a surplus, a dot where a side is unknown. */
export function WeekStrip({ week }: { week: WeekBalance }) {
  const reduce = useReducedMotion();
  const H = 38; // px each side of the baseline
  const sum = week.total != null
    ? `${week.total >= 0 ? "Deficit" : "Surplus"} ${formatKcal(Math.abs(week.total))} kcal over ${week.counted} days`
    : `Not enough days yet: ${week.counted} of the last ${week.days.length} have both Garmin burn and a food log`;
  const label = `${sum}. ${week.days.map((d) => `${initial(d.day)} ${d.deficit == null ? (d.reason === "no_log" ? "nothing logged" : "no burn") : `${d.deficit >= 0 ? "deficit" : "surplus"} ${formatKcal(Math.abs(d.deficit))}`}`).join(", ")}`;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="eyebrow">Last 7 days</p>
        <p className="num text-xs text-mute">{week.counted} of {week.days.length} days logged</p>
      </div>
      {week.total != null ? (
        <div className="mt-1">
          <p className="numeral text-[32px] leading-none" style={{ color: week.total >= 0 ? "var(--color-mint)" : "var(--color-amber)" }}>{formatKcal(Math.abs(week.total))}</p>
          <p className="mt-1 text-sm text-mute">
            kcal {week.total >= 0 ? "deficit" : "surplus"}
            {week.kg != null && Math.abs(week.kg) >= 0.05 ? ` · roughly ${Math.abs(week.kg).toFixed(1)} kg of fat-equivalent` : ""}
          </p>
        </div>
      ) : (
        <p className="mt-1 text-sm text-mute">Log meals on {Math.max(1, 3 - week.counted)} more {3 - week.counted <= 1 ? "day" : "days"} to see your weekly balance.</p>
      )}
      <div role="img" aria-label={label} className="mt-3 grid grid-cols-7 gap-1.5">
        {week.days.map((d, i) => {
          const h = d.deficit == null ? 0 : Math.max(3, (Math.abs(d.deficit) / week.maxAbs) * H);
          return (
            <div key={d.day} className="flex flex-col items-center">
              <div className="relative w-full" style={{ height: H * 2 }}>
                <span aria-hidden className="absolute inset-x-0 top-1/2 h-px bg-[var(--color-line-strong)]" />
                {d.deficit == null ? (
                  <span aria-hidden className="absolute top-1/2 left-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[var(--color-dim)]" />
                ) : (
                  <motion.span
                    aria-hidden
                    className="absolute inset-x-[18%] rounded-[5px]"
                    style={{ background: d.deficit >= 0 ? "var(--color-mint)" : "var(--color-amber)", [d.deficit >= 0 ? "bottom" : "top"]: "50%", transformOrigin: d.deficit >= 0 ? "bottom" : "top" }}
                    initial={{ height: reduce ? h : 0 }}
                    animate={{ height: h }}
                    transition={{ duration: reduce ? 0 : 0.7, delay: reduce ? 0 : 0.1 + i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                  />
                )}
              </div>
              <span className="mt-1 text-[11px] text-mute">{initial(d.day)}</span>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] leading-snug text-dim">
        Up is a deficit, down a surplus. A day with nothing logged is left out, and a day with missed meals looks like a bigger deficit than it was. The kg figure is a rough 7,700 kcal per kg.
      </p>
    </div>
  );
}
