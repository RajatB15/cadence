import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { formatMicro, macroSplit, microCoverage, microState, type MicroState } from "../lib/food";
import type { FoodMicro, FoodView } from "../lib/types";

const MACRO_COLOR = { protein: "#c8f560", carbs: "#6cc7ff", fat: "#ffbe55" } as const;

const STATE_WORD: Record<MicroState, string> = {
  unknown: "not reported",
  partial: "may be low",
  reached: "reference reached",
  building: "building",
  under: "below reference",
  over: "over the limit",
  no_reference: "",
};
const STATE_COLOR: Record<MicroState, string> = {
  unknown: "#5c5a55",
  partial: "#d9b26a",
  reached: "#c8f560",
  building: "#6cc7ff",
  under: "#6cc7ff",
  over: "#ffbe55",
  no_reference: "#d9b26a",
};

/** Macros as a share of the day's calories, then micronutrients against cited references. Missing is shown as unknown, never zero. */
export function NutrientsCard({ data }: { data: FoodView }) {
  const s = data.summary;
  const split = macroSplit(s);
  const [open, setOpen] = useState(false);
  const reported = data.micros.filter((m) => m.amount != null);
  const shown = open ? data.micros : data.micros.filter((m) => ["fibre_g", "sodium_mg", "iron_mg", "calcium_mg"].includes(m.key));
  return (
    <section className="surface p-6">
      <div className="eyebrow">Macros and micros</div>
      {!s.logged ? (
        <p className="mt-2 text-sm text-mute">Not logged. Nutrients appear once the day has an entry.</p>
      ) : (
        <>
          <dl className="mt-3 grid grid-cols-3 gap-3 text-center">
            {([["protein", "Protein", s.protein_g], ["carbs", "Carbs", s.carbs_g], ["fat", "Fat", s.fat_g]] as const).map(([k, label, grams]) => (
              <div key={k}>
                <dt className="eyebrow">{label}</dt>
                <dd className="num mt-1 text-xl text-paper">{grams == null ? "—" : `${Math.round(grams)} g`}</dd>
                <dd className="num text-xs text-dim">{split ? `${split[k]}% of kcal` : " "}</dd>
              </div>
            ))}
          </dl>
          {split ? (
            <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-line" role="img" aria-label={`Calories from protein ${split.protein}%, carbs ${split.carbs}%, fat ${split.fat}%`}>
              {(["protein", "carbs", "fat"] as const).map((k) => (
                <span key={k} style={{ width: `${split[k]}%`, background: MACRO_COLOR[k] }} />
              ))}
            </div>
          ) : (
            s.partial_macros && <p className="mt-3 text-xs text-dim">Some entries have calories only, so the split is not shown.</p>
          )}

          <div className="mt-6 flex items-center justify-between">
            <div className="eyebrow">Micronutrients</div>
            <button type="button" aria-expanded={open} className="chip pointer-coarse:py-2" onClick={() => setOpen(!open)}>
              {open ? "Fewer" : "All"} <ChevronDown size={12} className={open ? "rotate-180" : ""} />
            </button>
          </div>
          {reported.length === 0 ? (
            <p className="mt-2 text-sm text-mute">None of today's foods has a nutrient table (quick entries and your own dishes don't), so micronutrients are unknown, not zero.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {shown.map((m) => (
                <MicroRow key={m.key} m={m} />
              ))}
            </ul>
          )}
          <p className="mt-4 text-[11px] leading-relaxed text-dim">
            Amounts add up the foods that reported each nutrient; the source tables are calculated from recipes, so a low total can simply mean a food didn't list it. References are WHO
            guidelines for adults and the US FDA Daily Value, shown for context, not as your personal need or medical advice.
          </p>
        </>
      )}
    </section>
  );
}

function MicroRow({ m }: { m: FoodMicro }) {
  const state = microState(m);
  const coverage = microCoverage(m);
  const width = m.pct == null ? 0 : Math.min(100, m.pct);
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-paper">{m.label}</span>
        <span className="num text-sm text-paper">{formatMicro(m)}</span>
      </div>
      {m.reference != null && (
        <div className="relative mt-1.5 h-1.5 rounded-full bg-line" role="img" aria-label={`${m.label}: ${m.pct ?? 0}% of ${m.reference} ${m.unit}`}>
          <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${width}%`, background: STATE_COLOR[state] }} />
        </div>
      )}
      <p className="num mt-1 text-[11px] text-dim">
        {m.reference != null ? `${m.kind === "limit" ? "limit" : "reference"} ${m.reference.toLocaleString("en-US")} ${m.unit} (${m.source})` : "no reference amount"}
        {STATE_WORD[state] && ` · ${STATE_WORD[state]}`}
        {coverage && ` · ${coverage}`}
      </p>
    </li>
  );
}
