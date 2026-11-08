import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Utensils } from "lucide-react";
import { useState } from "react";
import { clsx } from "clsx";
import { Link } from "react-router-dom";
import { AccentEdge } from "../Card";
import { Sheet } from "../Sheet";
import { CalorieRing } from "./CalorieRing";
import { READ_ONLY, api } from "../../lib/api";
import { EAT_BACK_RANGE, MANUAL_RANGE, allowance, energyState, formatClock, formatKcal, parseEatBack, parseManualKcal, projectionMissing, projectionRange } from "../../lib/home";
import { phoneMayWrite } from "../../lib/phoneWrites";
import { Sparkline } from "../Sparkline";
import { C } from "../../lib/theme";
import type { CalorieSettingsView, HomeEnergy, HomePhase } from "../../lib/types";

const FALLBACK_FOOTNOTE = "Garmin burn and food-log kcal are both estimates; individual error can be 10 to 20% or more. Trends over weeks mean more than any one day.";

// Desktop may always edit; a paired phone only when the server's allowlist (mirrored in phoneWrites) says so.
const canEditTarget = !READ_ONLY || phoneMayWrite("PUT", "/api/settings/calories");

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <section aria-label="Calories" className="surface relative overflow-hidden p-5 sm:p-7">
      <AccentEdge color={C.gold} strength={0.14} />
      {children}
    </section>
  );
}

function LogFood({ label = "Log food" }: { label?: string }) {
  return (
    <Link to="/food" className="pop pop-ghost min-h-[44px] w-full !text-[12px] sm:w-auto">
      <Utensils size={14} aria-hidden /> {label}
    </Link>
  );
}

function Cell({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "sky" | "amber" }) {
  return (
    <div className="min-w-0 border-l border-line pl-3 first:border-l-0 first:pl-0">
      <p className="eyebrow !text-[11px] !tracking-[0.12em]">{label}</p>
      <p className={`num mt-1 whitespace-nowrap text-[clamp(14px,6.8cqw,1.25rem)] leading-tight ${tone === "sky" ? "text-sky" : tone === "amber" ? "text-amber" : "text-cream"}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] leading-snug text-mute [overflow-wrap:anywhere]">{sub}</p>}
    </div>
  );
}

export function CaloriesCard({ energy, phase, isDemo, loading = false }: { energy: HomeEnergy | null | undefined; phase?: HomePhase | null; isDemo: boolean; loading?: boolean }) {
  const [open, setOpen] = useState(false);
  if (loading) return <div className="surface skeleton h-[330px]" aria-busy aria-label="Calories loading" />;
  const state = energyState(energy, phase?.hints?.calories, isDemo);
  const copy = energy?.copy ?? null;
  const footnote = copy?.footnote ?? FALLBACK_FOOTNOTE;

  if (state.kind === "missing") {
    return (
      <Shell>
        <p className="eyebrow mb-2">Calories</p>
        <p className="text-mute">Calories will appear here once your Garmin burn and food log are available.</p>
        <div className="mt-4"><LogFood /></div>
      </Shell>
    );
  }
  if (state.kind === "unsupported") {
    return (
      <Shell>
        <p className="eyebrow mb-2">Calories{state.demo ? " · demo data" : ""}</p>
        <p className="text-paper">{state.demo ? "Demo data has no calorie burn." : copy?.status ?? "Your Garmin did not report calories for today."}</p>
        <p className="mt-1 text-sm text-mute">{copy?.eaten ? `${copy.eaten}. ` : ""}You can still log what you eat; nothing is compared until a burn is available.</p>
        <div className="mt-4"><LogFood /></div>
      </Shell>
    );
  }
  if (state.kind === "just_started") {
    const y = energy!.yesterday;
    return (
      <Shell>
        <p className="eyebrow mb-2">Calories</p>
        <p className="font-extrabold text-2xl text-cream">Today just started</p>
        <p className="mt-1 text-sm text-mute">Burn so far appears once Garmin has counted a little of the day.</p>
        {y && (y.total != null || y.eaten != null) && (
          <p className="mt-3 text-sm text-mute">
            Yesterday: {y.total != null ? `about ${formatKcal(y.total)} kcal burned` : "burn unknown"}
            {y.eaten != null ? `, about ${formatKcal(y.eaten)} kcal logged` : ", nothing logged"}.
          </p>
        )}
        <div className="mt-4"><LogFood /></div>
      </Shell>
    );
  }

  const e = energy!;
  const burned = e.burned!.total!;
  const p = state.showProjection ? e.projected! : null;
  const target = allowance(e);
  const eaten = state.hasLog ? (e.eaten!.kcal as number) : null;
  const over = e.above_by != null;
  const asOf = e.burned?.as_of ?? e.as_of ?? formatClock(e.as_of_min);
  const dayTotal = phase?.hints?.calories === "day_total";
  const missing = p ? null : projectionMissing(e);
  const summary =
    `Burned about ${formatKcal(burned)} kilocalories so far` +
    (eaten != null ? `, logged ${formatKcal(eaten)} eaten` : ", nothing logged yet") +
    (p ? `, projected ${formatKcal(p.lo)} to ${formatKcal(p.hi)} by the end of the day` : "") +
    ". All figures are estimates.";

  return (
    <Shell>
      <div className="flex items-start justify-between gap-3">
        <p className="eyebrow">Calories · estimates</p>
        <button type="button" onClick={() => setOpen(true)} className="eyebrow !text-[11px] hover:text-paper pointer-coarse:py-2" aria-label="Calorie details and target">
          Details
        </button>
      </div>
      <div className="mt-4 grid items-center gap-5 sm:grid-cols-[auto_1fr] sm:gap-8">
        <CalorieRing burned={burned} active={e.burned?.active ?? null} resting={e.burned?.resting ?? null} eaten={eaten} target={target} projected={p ? { lo: p.lo, hi: p.hi } : null} asOf={asOf} summary={summary} size={208} />
        <div>
          <div className={clsx("@container grid gap-3", e.projection_state === "hidden" ? "grid-cols-[repeat(2,minmax(0,1fr))]" : "grid-cols-[repeat(3,minmax(0,1fr))]")}>
            <Cell label="Eaten" value={eaten != null ? formatKcal(eaten) : "—"} sub={eaten != null ? `${e.eaten?.entries ?? "some"} logged` : copy?.eaten ?? "nothing logged yet"} tone="sky" />
            {state.showLeft ? (
              <Cell label={over ? "Above" : "Left"} value={over ? formatKcal(e.above_by!) : formatKcal(e.left!)} sub={over ? "your estimate" : target ? `of ${formatKcal(target)}` : undefined} tone={over ? "amber" : undefined} />
            ) : (
              <Cell label="Target" value={target ? formatKcal(target) : "—"} sub={target ? "your estimate" : "not set"} />
            )}
            {e.projection_state !== "hidden" && (
              <Cell label="Projected" value={p ? formatKcal(p.value) : "—"} sub={p ? projectionRange(p) : missing ?? undefined} />
            )}
          </div>
          {dayTotal && copy?.eaten && <p className="mt-3 text-sm text-mute">{phase?.copy?.calories ? `${phase.copy.calories}: ` : ""}{copy.eaten}.</p>}
          {state.showLeft && copy?.left && <p className={clsx("mt-3 text-sm", over ? "text-amber" : "text-mute")}>{copy.left}</p>}
          {copy?.partial_log && <p className="mt-2 text-xs text-dim">{copy.partial_log}</p>}
          {copy?.refuel && <p className="mt-2 text-sm text-mute">{copy.refuel}</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            <LogFood label={eaten == null ? "Log your first meal" : "Log food"} />
            {canEditTarget && (
              <button type="button" onClick={() => setOpen(true)} className="pop pop-ghost min-h-[44px] !text-[12px]">
                <Pencil size={13} aria-hidden /> {e.target ? "Edit target" : "Set target"}
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="mt-4 text-[11px] leading-relaxed text-dim">{footnote}</p>
      <Sheet open={open} onOpenChange={setOpen} title="Calories today" eyebrow="Estimates, not measurements">
        <CalorieDetail energy={e} burned={burned} footnote={footnote} />
      </Sheet>
    </Shell>
  );
}

function CalorieDetail({ energy: e, burned, footnote }: { energy: HomeEnergy; burned: number; footnote: string }) {
  const c = e.copy ?? null;
  const totals = (e.spark ?? []).filter((d) => d.total != null && !d.partial).map((d) => d.total as number);
  return (
    <div className="space-y-7">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
        <Row k="Burned so far" v={`${formatKcal(burned)} kcal`} />
        <Row k="Resting" v={e.burned?.resting != null ? `${formatKcal(e.burned.resting)} kcal` : "not split"} />
        <Row k="Active" v={e.burned?.active != null ? `${formatKcal(e.burned.active)} kcal` : "not split"} />
        <Row k="Eaten" v={e.eaten?.logged && e.eaten.kcal != null ? `${formatKcal(e.eaten.kcal)} kcal` : "nothing logged yet"} />
        {e.eaten?.protein_g != null && e.eaten.logged && <Row k="Protein" v={`${Math.round(e.eaten.protein_g)} g`} />}
        {e.workout_active_kcal != null && e.workout_active_kcal > 0 && <Row k="From workouts" v={`${formatKcal(e.workout_active_kcal)} kcal`} />}
      </dl>
      <div className="space-y-1.5 text-sm text-mute">
        <p className="eyebrow mb-2">What this means</p>
        {[c?.burned, c?.eaten, c?.target, c?.left, c?.projection, c?.workout, c?.refuel].filter(Boolean).map((t) => <p key={t}>{t}</p>)}
        {!c?.projection && e.projection_state !== "hidden" && <p>{projectionMissing(e)}</p>}
        {(c?.target_notes ?? []).map((t) => <p key={t} className="text-dim">{t}</p>)}
      </div>
      {totals.length >= 3 && (
        <div>
          <p className="eyebrow mb-2">Garmin burn, recent days (settled days only)</p>
          <Sparkline values={totals} color={C.gold} height={40} />
        </div>
      )}
      <TargetEditor energy={e} />
      <p className="text-xs leading-relaxed text-dim">{footnote}</p>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="eyebrow !text-[11px]">{k}</dt>
      <dd className="num mt-1 text-lg text-cream">{v}</dd>
    </div>
  );
}

const fmtRange = ([lo, hi]: [number, number]) => `${lo.toLocaleString()} to ${hi.toLocaleString()}`;

/** Mirrors GET/PUT /api/settings/calories: automatic or a manual target, how much of workout burn to eat back, and the weight-goal pace. */
function TargetEditor({ energy }: { energy: HomeEnergy }) {
  const qc = useQueryClient();
  const settings = useQuery<CalorieSettingsView>({ queryKey: ["calorie-settings"], queryFn: api.calorieSettings, staleTime: 30_000 });
  const t = energy.target ?? null;
  const base = settings.data ?? (energy.settings ? { ...energy.settings, ranges: { manual_kcal: MANUAL_RANGE, eat_back_pct: EAT_BACK_RANGE }, floor_kcal: 1500 } : null);
  return (
    <div>
      <p className="eyebrow mb-2">Daily target</p>
      {!t && <p className="mb-3 text-sm text-mute">{energy.copy?.target ?? "No target yet. You can type your own."}</p>}
      {!canEditTarget ? (
        <p className="text-sm text-dim">Change the target on your Mac.</p>
      ) : settings.isPending && !base ? (
        <p className="text-sm text-mute" aria-busy>Loading your target settings…</p>
      ) : !base ? (
        <p role="alert" className="text-sm text-amber">Could not load the target settings. {settings.error instanceof Error ? settings.error.message : ""}</p>
      ) : (
        <SettingsForm key={JSON.stringify([base.mode, base.manual_kcal, base.eat_back_pct, base.pace])} base={base} onSaved={() => { void qc.invalidateQueries({ queryKey: ["overview"] }); void qc.invalidateQueries({ queryKey: ["calorie-settings"] }); }} />
      )}
    </div>
  );
}

function SettingsForm({ base, onSaved }: { base: CalorieSettingsView; onSaved: () => void }) {
  const [mode, setMode] = useState<"auto" | "manual">(base.mode);
  const [kcal, setKcal] = useState(base.manual_kcal != null ? String(base.manual_kcal) : "");
  const [eat, setEat] = useState(String(base.eat_back_pct));
  const [pace, setPace] = useState(base.pace);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (patch: Parameters<typeof api.saveCalorieSettings>[0]) => api.saveCalorieSettings(patch),
    onSuccess: () => { setError(null); onSaved(); },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save the target."),
  });
  const submit = (ev: React.FormEvent) => {
    ev.preventDefault();
    const patch: Parameters<typeof api.saveCalorieSettings>[0] = { mode, pace };
    if (mode === "manual") {
      const r = parseManualKcal(kcal, base.ranges.manual_kcal);
      if (!r.ok) return setError(r.reason);
      patch.manual_kcal = r.value;
    }
    const b = parseEatBack(eat, base.ranges.eat_back_pct);
    if (!b.ok) return setError(b.reason);
    patch.eat_back_pct = b.value;
    setError(null);
    save.mutate(patch);
  };
  const field = "num min-h-[44px] rounded-xl border border-line-strong bg-slate px-3 text-cream";
  return (
    <form className="space-y-4" onSubmit={submit}>
      <fieldset className="flex flex-wrap gap-4 text-sm text-paper">
        <legend className="sr-only">How the target is set</legend>
        <label className="flex min-h-[44px] items-center gap-2"><input type="radio" name="kcal-mode" checked={mode === "auto"} onChange={() => setMode("auto")} /> Automatic from my Garmin burn</label>
        <label className="flex min-h-[44px] items-center gap-2"><input type="radio" name="kcal-mode" checked={mode === "manual"} onChange={() => setMode("manual")} /> My own number</label>
      </fieldset>
      {mode === "manual" && (
        <div>
          <label className="eyebrow !text-[11px]" htmlFor="kcal-target">Daily target, kcal ({fmtRange(base.ranges.manual_kcal)})</label>
          <input id="kcal-target" inputMode="numeric" value={kcal} onChange={(ev) => setKcal(ev.target.value)} placeholder="e.g. 2350" className={`${field} mt-1 block w-36`} />
          <p className="mt-1 text-xs text-dim">Below about {Math.round(base.floor_kcal).toLocaleString()} kcal the card adds a note; it never blocks you.</p>
        </div>
      )}
      <div>
        <label className="eyebrow !text-[11px]" htmlFor="kcal-eatback">Eat back from workouts, percent ({fmtRange(base.ranges.eat_back_pct)})</label>
        <input id="kcal-eatback" inputMode="numeric" value={eat} onChange={(ev) => setEat(ev.target.value)} className={`${field} mt-1 block w-24`} />
      </div>
      <label className="flex min-h-[44px] items-center gap-2 text-sm text-paper"><input type="checkbox" checked={pace} onChange={(ev) => setPace(ev.target.checked)} /> Nudge the target towards my weight goal</label>
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={save.isPending} className="pop pop-lime min-h-[44px] !text-[12px]">{save.isPending ? "Saving" : "Save"}</button>
        {save.isSuccess && !error && <span className="text-sm text-mute">Saved. The card updates in a moment.</span>}
      </div>
      {error && <p role="alert" className="text-sm text-amber">{error}</p>}
    </form>
  );
}
