import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import type { WhatIfCard as Card } from "../lib/types";

/** An encouraging, honest nudge from the what-if replay: what an easier day would have bought, or praise when there was nothing to fix. */
export function WhatIfCard({ card }: { card: Card | null | undefined }) {
  if (!card) return null;
  const color = card.tone === "good" ? "#c8f560" : "#6cc7ff";
  return (
    <section className="surface flex items-start gap-4 p-5 sm:p-6" style={{ borderLeft: `3px solid ${color}` }}>
      <Sparkles size={20} className="mt-0.5 shrink-0" style={{ color }} />
      <div className="min-w-0">
        <p className="eyebrow mb-1">What if</p>
        <h3 className="font-display text-2xl text-cream">{card.title}</h3>
        <p className="mt-2 max-w-3xl text-sm text-paper">{card.text}</p>
        {card.lines && card.lines.length > 0 && (
          <ul className="mt-2 max-w-3xl list-disc space-y-1 pl-5 text-sm text-mute">{card.lines.map((l) => <li key={l}>{l}</li>)}</ul>
        )}
        {card.action && <p className="mt-2 text-sm text-gold">Next time: {card.action}</p>}
        {card.sessions && card.sessions.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-mute">
            {card.sessions.slice(0, 4).map((s) => (
              <li key={s.id}>
                <Link to={`/activities/${s.id}`} className="hover:text-paper">{s.name}</Link> · load {s.load} → {s.load_after}
              </li>
            ))}
          </ul>
        )}
        <Link to={card.link} className="mt-3 inline-block text-xs font-semibold tracking-widest text-mute uppercase hover:text-paper">See the replay →</Link>
        <p className="mt-2 text-xs text-dim">The model's view of your training load, not a measurement.</p>
      </div>
    </section>
  );
}
