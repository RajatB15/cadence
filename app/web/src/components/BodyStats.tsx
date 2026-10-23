import { Info, Ruler } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router-dom";
import type { BodyEstimate } from "../lib/types";

const ZONES = [
  { from: 15, to: 18.5, color: "#6cc7ff", label: "Under" },
  { from: 18.5, to: 25, color: "#c8f560", label: "Normal" },
  { from: 25, to: 30, color: "#ffbe55", label: "Over" },
  { from: 30, to: 40, color: "#ff6a55", label: "Obese" },
];
const CATEGORY_COLOR: Record<string, string> = { underweight: "#6cc7ff", normal: "#c8f560", overweight: "#ffbe55", obese: "#ff6a55" };
const GAUGE_MIN = 15;
const GAUGE_MAX = 40;
const pct = (v: number, lo: number, hi: number) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));

export function BodyStats({ body, weightKg, goalKg, hasProfile }: { body: BodyEstimate | null; weightKg: number | null; goalKg: number | null; hasProfile: boolean }) {
  if (!hasProfile) {
    return (
      <Link to="/settings" className="surface surface-hover flex items-center gap-4 p-6">
        <Ruler size={20} className="shrink-0 text-gold" />
        <div>
          <p className="font-semibold text-paper">Add your height, birth date and sex to unlock BMI and body estimates</p>
          <p className="mt-1 text-sm text-mute">Settings → Body profile. Takes ten seconds and stays on this Mac.</p>
        </div>
      </Link>
    );
  }
  if (!body || weightKg == null) return null;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-2">Estimated from your weight, height, age and sex — not measured</p>
          <h2 className="font-display text-3xl text-cream">Body stats</h2>
        </div>
        <Link to="/settings" className="eyebrow hover:text-paper">Edit profile →</Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BmiCard body={body} />
        <RangeCard body={body} weightKg={weightKg} goalKg={goalKg} />
        <CompositionCard body={body} weightKg={weightKg} />
        <EnergyCard body={body} />
      </div>

      <details className="surface group p-6 text-sm text-mute">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-paper">
          <Info size={14} className="text-gold" /> How these are calculated
        </summary>
        <div className="mt-3 max-w-3xl space-y-2 text-xs leading-relaxed">
          <p>
            <b className="text-paper">BMI</b> is exact arithmetic (weight ÷ height²) with the WHO adult cut-offs. It ignores muscle, so it can read high for
            very muscular people. <b className="text-paper">Healthy range</b> is the weight at BMI 18.5 and 24.9 for your height.
          </p>
          <p>
            <b className="text-paper">Body fat %</b>: Deurenberg, Weststrate &amp; Seidell (1991), an age- and sex-specific prediction from BMI. Typical error
            is about ±4 percentage points and it runs high for lean or muscular people. Fat and lean mass are that percentage applied to your weight, so
            they carry the same uncertainty.
          </p>
          <p>
            <b className="text-paper">BMR</b>: Mifflin–St Jeor (1990), accurate to roughly ±10% for an individual. <b className="text-paper">Daily energy</b>{" "}
            multiplies it by the lower bound of the FAO/WHO/UNU (2004) activity bands — light 1.4, active 1.7, vigorous 2.0. A planning range, not a
            prescription. <b className="text-paper">Body surface area</b>: Mosteller (1987).
          </p>
          <p>
            Muscle %, bone mass, visceral fat, water % and metabolic age aren't shown: no credible formula derives them from weight and profile alone.
          </p>
        </div>
      </details>
    </section>
  );
}

function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="surface p-6">
      <div className="mb-5 flex items-baseline justify-between gap-3">
        <p className="eyebrow">{title}</p>
        {note && <p className="text-xs text-dim">{note}</p>}
      </div>
      {children}
    </div>
  );
}

function BmiCard({ body }: { body: BodyEstimate }) {
  const color = CATEGORY_COLOR[body.bmi_category];
  const at = pct(body.bmi, GAUGE_MIN, GAUGE_MAX);
  return (
    <Card title="Body mass index" note="exact">
      <div className="flex items-baseline gap-3">
        <span className="num text-6xl" style={{ color }}>{body.bmi.toFixed(1)}</span>
        <span className="text-lg capitalize" style={{ color }}>{body.bmi_category}</span>
      </div>
      <div className="relative mt-6 pt-3">
        <motion.div
          className="absolute top-0 -ml-1.5 h-0 w-0 border-x-[6px] border-t-[8px] border-x-transparent"
          style={{ borderTopColor: color }}
          initial={{ left: "0%" }}
          animate={{ left: `${at}%` }}
          transition={{ type: "spring", stiffness: 90, damping: 16 }}
        />
        <div className="flex h-2.5 overflow-hidden rounded-full">
          {ZONES.map((z) => (
            <div key={z.label} style={{ width: `${((z.to - z.from) / (GAUGE_MAX - GAUGE_MIN)) * 100}%`, background: z.color, opacity: z.color === color ? 1 : 0.28 }} />
          ))}
        </div>
        <div className="relative mt-2 h-4 text-[10px] text-dim">
          {[18.5, 25, 30].map((t) => (
            <span key={t} className="absolute -translate-x-1/2" style={{ left: `${pct(t, GAUGE_MIN, GAUGE_MAX)}%` }}>{t}</span>
          ))}
        </div>
      </div>
    </Card>
  );
}

function RangeCard({ body, weightKg, goalKg }: { body: BodyEstimate; weightKg: number; goalKg: number | null }) {
  const lo = Math.floor(Math.min(body.healthy_min_kg, weightKg, goalKg ?? Infinity) - 8);
  const hi = Math.ceil(Math.max(body.healthy_max_kg, weightKg, goalKg ?? -Infinity) + 8);
  const d = body.to_healthy_kg;
  const verdict = d === 0 ? "Inside the healthy range" : d < 0 ? `${Math.abs(d).toFixed(1)} kg above the range` : `${d.toFixed(1)} kg below the range`;
  return (
    <Card title="Healthy weight range" note="BMI 18.5 – 24.9">
      <div className="flex items-baseline gap-2">
        <span className="num text-4xl text-paper">{body.healthy_min_kg.toFixed(1)}–{body.healthy_max_kg.toFixed(1)}</span>
        <span className="text-mute">kg</span>
      </div>
      <p className="mt-1 text-sm" style={{ color: d === 0 ? "#c8f560" : "#ffbe55" }}>{verdict}</p>
      <div className="relative mt-7 h-2.5 rounded-full bg-line">
        <div
          className="absolute h-full rounded-full bg-lime/70"
          style={{ left: `${pct(body.healthy_min_kg, lo, hi)}%`, width: `${pct(body.healthy_max_kg, lo, hi) - pct(body.healthy_min_kg, lo, hi)}%` }}
        />
        {goalKg != null && (
          <div className="absolute -top-1.5 h-5 w-0.5 bg-lime" style={{ left: `${pct(goalKg, lo, hi)}%` }} title={`Goal ${goalKg} kg`} />
        )}
        <motion.div
          className="absolute top-1/2 -ml-2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-ink bg-gold shadow-[0_0_12px_rgba(217,178,106,0.7)]"
          initial={{ left: `${pct(lo, lo, hi)}%` }}
          animate={{ left: `${pct(weightKg, lo, hi)}%` }}
          transition={{ type: "spring", stiffness: 90, damping: 16 }}
        />
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-dim">
        <span>{lo} kg</span>
        <span className="text-gold">you {weightKg.toFixed(1)}</span>
        <span>{hi} kg</span>
      </div>
    </Card>
  );
}

function CompositionCard({ body, weightKg }: { body: BodyEstimate; weightKg: number }) {
  const fatShare = (body.fat_mass_kg / weightKg) * 100;
  return (
    <Card title="Fat vs lean mass" note={`body fat ≈ ${body.body_fat_pct.toFixed(1)}% ±4`}>
      <div className="flex h-10 overflow-hidden rounded-sm">
        <motion.div className="grid place-items-center bg-amber/80 text-xs font-semibold text-ink" initial={{ width: 0 }} animate={{ width: `${fatShare}%` }} transition={{ duration: 0.8, ease: "easeOut" }}>
          {fatShare > 12 ? `${body.body_fat_pct.toFixed(0)}%` : ""}
        </motion.div>
        <div className="grid flex-1 place-items-center bg-sky/60 text-xs font-semibold text-ink">{(100 - fatShare).toFixed(0)}%</div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4">
        <div>
          <p className="eyebrow mb-1 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber" /> Fat mass</p>
          <p className="num text-3xl text-paper">{body.fat_mass_kg.toFixed(1)}<span className="ml-1 text-base text-mute">kg</span></p>
        </div>
        <div>
          <p className="eyebrow mb-1 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-sky" /> Lean mass</p>
          <p className="num text-3xl text-paper">{body.lean_mass_kg.toFixed(1)}<span className="ml-1 text-base text-mute">kg</span></p>
        </div>
      </div>
    </Card>
  );
}

function EnergyCard({ body }: { body: BodyEstimate }) {
  const rows: { label: string; hint: string; kcal: number; color: string }[] = [
    { label: "At rest (BMR)", hint: "just staying alive", kcal: body.bmr_kcal, color: "#9b8cff" },
    { label: "Light day", hint: "mostly seated · ×1.4", kcal: body.energy_kcal.light, color: "#6cc7ff" },
    { label: "Active day", hint: "regular training · ×1.7", kcal: body.energy_kcal.active, color: "#c8f560" },
    { label: "Vigorous day", hint: "hard training · ×2.0", kcal: body.energy_kcal.vigorous, color: "#d9b26a" },
  ];
  const max = body.energy_kcal.vigorous;
  return (
    <Card title="Daily energy" note={`body surface ${body.bsa_m2.toFixed(2)} m²`}>
      <div className="space-y-3.5">
        {rows.map((r, i) => (
          <div key={r.label}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="text-paper">{r.label} <span className="ml-1 text-xs text-dim">{r.hint}</span></span>
              <span className="num text-paper">{r.kcal.toLocaleString()} <span className="text-xs text-mute">kcal</span></span>
            </div>
            <div className="h-1.5 rounded-full bg-line">
              <motion.div className="h-full rounded-full" style={{ background: r.color }} initial={{ width: 0 }} animate={{ width: `${(r.kcal / max) * 100}%` }} transition={{ duration: 0.7, delay: i * 0.08, ease: "easeOut" }} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-dim">Planning ranges, ±10% or more. Not a prescription.</p>
    </Card>
  );
}
