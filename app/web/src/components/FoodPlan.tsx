import { Link } from "react-router-dom";
import { bandPositions, PHASE_LABEL, STATE_COLOR, stateFor } from "../lib/food";
import { formatDate } from "../lib/format";
import type { FoodPlan, FoodView, Meal } from "../lib/types";

const fmt = (n: number) => Math.round(n).toLocaleString("en-US");
const MEAL_NAME: Record<Meal, string> = { breakfast: "Breakfast", lunch: "Lunch", snack: "Snacks", dinner: "Dinner" };

/** A target band with the day's logged range and best guess on the same scale. */
function RangeBar({ target, logged, point, color }: { target: [number, number] | null; logged: [number, number] | null; point: number | null; color: string }) {
  const p = bandPositions(target, logged, point);
  return (
    <div className="relative mt-4 h-3 bg-line/60" aria-hidden>
      {p.target && <div className="absolute inset-y-0 bg-white/15" style={{ left: `${p.target[0]}%`, width: `${p.target[1] - p.target[0]}%` }} />}
      {p.logged && <div className="absolute top-1/2 h-1.5 -translate-y-1/2" style={{ left: `${p.logged[0]}%`, width: `${Math.max(p.logged[1] - p.logged[0], 1)}%`, background: `${color}66` }} />}
      {p.point != null && <div className="absolute top-[-3px] h-[18px] w-0.5" style={{ left: `${p.point}%`, background: color }} />}
    </div>
  );
}

/** Shown instead of targets when something the targets need isn't there yet. */
export function PlanNeeds({ plan }: { plan: FoodPlan }) {
  return (
    <section className="surface p-6">
      <div className="eyebrow">Targets</div>
      <p className="mt-2 font-display text-3xl text-cream">Targets need a little more from you</p>
      <ul className="mt-3 space-y-2 text-sm text-mute">
        {plan.needs.includes("weight") && (
          <li>
            A recent weigh-in, so protein and the energy range can scale to your body. <Link to="/weight?log=1" className="text-gold underline-offset-4 hover:underline">Log weight</Link>
          </li>
        )}
        {plan.needs.includes("profile") && (
          <li>
            Your height, birth date and sex, for a resting-energy estimate until there is a week of Garmin data. <Link to="/weight" className="text-gold underline-offset-4 hover:underline">Add them on Weight</Link>
          </li>
        )}
      </ul>
      <p className="mt-3 text-xs text-dim">Nothing is made up in the meantime: totals below are only what you logged.</p>
    </section>
  );
}

export function EnergyCard({ data }: { data: FoodView }) {
  const { plan, summary: s } = data;
  const t = plan.targets;
  const ref = plan.reference_energy;
  const isToday = data.day === data.today;
  const state = plan.today?.state ?? "not_logged";
  const color = STATE_COLOR[state];
  const statusText =
    state === "within"
      ? "In your range"
      : state === "under"
        ? isToday && plan.today?.remaining_kcal
          ? `About ${fmt(plan.today.remaining_kcal[0])}–${fmt(plan.today.remaining_kcal[1])} kcal to go`
          : "Under your range"
        : state === "over"
          ? "Above your range"
          : null;
  return (
    <section className="surface p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="eyebrow">Energy {isToday ? "today" : formatDate(data.day)}</div>
        {t && <span className="chip !text-[10px]">{PHASE_LABEL[plan.phase]}</span>}
      </div>
      {s.logged ? (
        <>
          <p className="num mt-2 font-display text-5xl text-cream">{fmt(s.kcal ?? 0)}<span className="ml-2 text-base text-mute">kcal</span></p>
          <p className="num text-sm text-mute">likely {fmt(s.kcal_low ?? 0)}–{fmt(s.kcal_high ?? 0)}</p>
        </>
      ) : (
        <p className="mt-2 text-sm text-mute">Not logged yet. A day with nothing logged is left out, not counted as zero.</p>
      )}
      {t?.kcal ? (
        <>
          <RangeBar target={t.kcal} logged={s.logged ? [s.kcal_low ?? 0, s.kcal_high ?? 0] : null} point={s.logged ? s.kcal : null} color={color} />
          <p className="num mt-3 text-sm text-paper">Target {fmt(t.kcal[0])}–{fmt(t.kcal[1])} kcal{statusText && <span style={{ color }}> · {statusText}</span>}</p>
          {t.pace_pct_week && t.pace_kg_week && (
            <p className="mt-1 text-xs text-dim">
              Pace guide: {t.pace_pct_week[0]}–{t.pace_pct_week[1]}% of body weight a week ({t.pace_kg_week[0]}–{t.pace_kg_week[1]} kg) {plan.phase === "cut" ? "to lose" : "to gain"}.
              {plan.goal_kg != null && plan.weight_kg != null && ` Goal ${plan.goal_kg} kg, trend ${plan.weight_kg.toFixed(1)} kg.`}
            </p>
          )}
          {ref && (
            <p className="mt-2 text-xs text-dim">
              Built from {ref.source === "garmin" ? `Garmin's average burn over ${ref.days} days (${fmt(ref.low)}–${fmt(ref.high)} kcal)` : "a formula estimate from your height, age, sex and weight (Garmin needs 7 days of data)"}. Both are estimates, about ±10%.
            </p>
          )}
        </>
      ) : (
        t && <p className="mt-3 text-xs text-dim">No energy range yet: it needs your profile or a week of Garmin data. Protein targets below still apply.</p>
      )}
    </section>
  );
}

export function ProteinCard({ data }: { data: FoodView }) {
  const { plan, summary: s } = data;
  const t = plan.targets;
  const g = s.protein_g;
  const mealMax = t?.protein_per_meal_g[1] ?? 0;
  const status = g == null || !t ? null : g < t.protein_g[0] ? "below" : g > t.protein_g[1] ? "above" : "within";
  const color = status === "within" ? STATE_COLOR.within : status === "below" ? STATE_COLOR.under : STATE_COLOR.over;
  const byMeal = (Object.keys(MEAL_NAME) as Meal[]).filter((m) => plan.meal_protein[m] != null);
  return (
    <section className="surface p-6">
      <div className="eyebrow">Protein {data.day === data.today ? "today" : formatDate(data.day)}</div>
      {g != null ? (
        <p className="num mt-2 font-display text-5xl text-cream">{fmt(g)}<span className="ml-2 text-base text-mute">g{s.protein_g_per_kg != null && ` · ${s.protein_g_per_kg.toFixed(2)} g/kg`}</span></p>
      ) : (
        <p className="mt-2 text-sm text-mute">{s.logged ? "No protein figures on today's entries." : "Not logged yet."}</p>
      )}
      {t && (
        <>
          <RangeBar target={t.protein_g} logged={g != null ? [g, g] : null} point={g} color={color} />
          <p className="num mt-3 text-sm text-paper">
            Target {t.protein_g[0]}–{t.protein_g[1]} g
            {status && <span style={{ color }}> · {status === "within" ? "In range" : status === "below" ? `${Math.round(t.protein_g[0] - (g ?? 0))} g to the low end` : "Above range"}</span>}
          </p>
          <p className="mt-1 text-xs text-dim">1.6–2.2 g per kg of body weight a day for people who lift (Morton 2018; Iraki 2019). A guide to compare against, not a prescription.</p>
          {byMeal.length > 0 && (
            <div className="mt-4 space-y-2" role="img" aria-label="Protein by meal">
              {byMeal.map((m) => {
                const v = plan.meal_protein[m] ?? 0;
                const inRange = v >= t.protein_per_meal_g[0];
                return (
                  <div key={m} className="flex items-center gap-3 text-xs">
                    <span className="w-16 shrink-0 text-mute">{MEAL_NAME[m]}</span>
                    <div className="relative h-2 flex-1 bg-line/60">
                      <div className="absolute inset-y-0 left-0" style={{ width: `${Math.min(100, (v / (mealMax * 1.3)) * 100)}%`, background: inRange ? STATE_COLOR.within : STATE_COLOR.under }} />
                      <div className="absolute inset-y-[-2px] w-0.5 bg-white/40" style={{ left: `${(t.protein_per_meal_g[0] / (mealMax * 1.3)) * 100}%` }} />
                    </div>
                    <span className="num w-10 shrink-0 text-right text-paper">{Math.round(v)} g</span>
                  </div>
                );
              })}
              <p className="text-[11px] text-dim">Tick marks {t.protein_per_meal_g[0]} g: about 0.4–0.55 g/kg per meal, spread over 3–6 meals works best (Iraki 2019).</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function WeekCard({ data }: { data: FoodView }) {
  const { plan, trail } = data;
  const target = plan.targets?.kcal ?? null;
  const top = Math.max(1, target?.[1] ?? 0, ...trail.map((t) => Math.max(t.kcal_high ?? 0, t.burn ?? 0)));
  const max = top * 1.1;
  const W = 280, H = 120, base = 104, plot = 92;
  const y = (v: number) => base - (v / max) * plot;
  const slot = W / trail.length;
  const label = trail.map((t) => `${formatDate(t.day)}: ${t.logged ? `${t.kcal} kcal` : "not logged"}`).join("; ");
  const b = plan.balance;
  return (
    <section className="surface p-6">
      <div className="eyebrow">Last 7 days</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-4 w-full" role="img" aria-label={`Calories logged per day. ${label}`}>
        {target && <rect x={0} y={y(target[1])} width={W} height={y(target[0]) - y(target[1])} fill="white" opacity={0.1} />}
        {trail.map((t, i) => {
          const cx = i * slot + slot / 2;
          const state = stateFor(t, target);
          const c = STATE_COLOR[state];
          return (
            <g key={t.day}>
              {t.logged && t.kcal != null && t.kcal_low != null && t.kcal_high != null ? (
                <>
                  <rect x={cx - 9} y={y(t.kcal)} width={18} height={base - y(t.kcal)} fill={c} opacity={0.75} />
                  <line x1={cx} x2={cx} y1={y(t.kcal_high)} y2={y(t.kcal_low)} stroke={c} strokeWidth={1.5} />
                </>
              ) : (
                <line x1={cx - 9} x2={cx + 9} y1={base - 1} y2={base - 1} stroke={STATE_COLOR.not_logged} strokeDasharray="3 3" />
              )}
              {t.burn != null && <line x1={cx - 12} x2={cx + 12} y1={y(t.burn)} y2={y(t.burn)} stroke="#ecebe6" strokeWidth={1} strokeDasharray="2 2" opacity={0.7} />}
              <text x={cx} y={H - 2} textAnchor="middle" fontSize={8} fill="#8d8a82">{formatDate(t.day).slice(0, 3)}</text>
            </g>
          );
        })}
      </svg>
      <p className="mt-1 text-[11px] text-dim">Bars: calories logged, with the likely range. Shaded band: your target. Dashed tick: Garmin's burn estimate. Dashed baseline: not logged.</p>
      {b ? (
        <dl className="num mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt className="eyebrow">Mean intake</dt><dd className="text-paper">{fmt(b.intake)} kcal</dd><dd className="text-xs text-dim">likely {fmt(b.intake_range[0])}–{fmt(b.intake_range[1])}</dd></div>
          <div><dt className="eyebrow">Garmin burn</dt><dd className="text-paper">{fmt(b.burn)} kcal</dd><dd className="text-xs text-dim">±10%</dd></div>
          <div className="col-span-2"><dt className="eyebrow">Difference over {b.days} logged days</dt><dd className="text-paper">{b.balance > 0 ? "+" : ""}{fmt(b.balance)} kcal a day <span className="text-xs text-dim">(somewhere between {fmt(b.balance_range[0])} and {b.balance_range[1] > 0 ? "+" : ""}{fmt(b.balance_range[1])})</span></dd></div>
        </dl>
      ) : (
        <p className="mt-4 text-xs text-dim">An average needs at least 4 logged days that also have a Garmin energy figure.</p>
      )}
      {plan.implied && (
        <p className="num mt-4 border-t border-line pt-4 text-sm text-mute">
          Your logs and weight trend imply you burn about <span className="text-paper">{fmt(plan.implied.kcal)} kcal</span> a day ({fmt(plan.implied.range[0])}–{fmt(plan.implied.range[1])}), from {plan.implied.days} logged days and a trend of {plan.implied.trend_kg_week > 0 ? "+" : ""}{plan.implied.trend_kg_week.toFixed(2)} kg a week.
        </p>
      )}
    </section>
  );
}
