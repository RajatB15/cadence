import { AccentEdge } from "../Card";
import { phaseAccent, type NowView } from "../../lib/home";
import { C } from "../../lib/theme";

/** The phase-aware card: renders the copy the backend chose for this part of the day. */
export function NowCard({ view, phase, hour }: { view: NowView; phase?: string; hour: number }) {
  const color = C[phaseAccent(phase, hour)];
  return (
    <section aria-label="Now" className="surface relative overflow-hidden p-5 sm:p-7">
      <AccentEdge color={color} strength={0.18} />
      <div className="relative">
        {view.eyebrow && <p className="eyebrow mb-1" style={{ color }}>Now · {view.eyebrow}</p>}
        {view.headline && <h2 className="text-2xl leading-[1.1] font-extrabold tracking-tight text-cream sm:text-3xl">{view.headline}</h2>}
        {view.session && (
          <div className="mt-3">
            <p className="font-semibold text-paper">{view.session.title}</p>
            {view.session.detail && <p className="mt-1 text-mute">{view.session.detail}</p>}
          </div>
        )}
        {view.notes.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm text-dim">
            {view.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        )}
      </div>
    </section>
  );
}
