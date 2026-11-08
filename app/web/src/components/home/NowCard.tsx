import { phaseAccent, type NowView } from "../../lib/home";
import { C } from "../../lib/theme";

/** The phase-aware card: renders the copy the backend chose for this part of the day. */
export function NowCard({ view, phase, hour }: { view: NowView; phase?: string; hour: number }) {
  const color = C[phaseAccent(phase, hour)];
  return (
    <section aria-label="Now" className="surface relative overflow-hidden p-5 sm:p-7">
      <span aria-hidden className="pointer-events-none absolute -top-20 -right-12 h-56 w-56 rounded-full opacity-20 blur-3xl" style={{ background: color }} />
      <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: color }} />
      <div className="relative">
        {view.eyebrow && <p className="eyebrow mb-1" style={{ color }}>Now · {view.eyebrow}</p>}
        {view.headline && <h2 className="text-2xl leading-tight font-extrabold text-cream sm:text-3xl">{view.headline}</h2>}
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
