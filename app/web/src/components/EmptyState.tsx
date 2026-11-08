import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Database, Lock, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { api } from "../lib/api";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { C } from "../lib/theme";

/** Concentric rings with open gaps and one small spark: the brand motif, drawn empty. No stock art. */
export function RingsIllustration({ size = 132 }: { size?: number }) {
  const rings = [
    { r: 54, color: C.mint, w: 7, dash: 0.62, rot: -90 },
    { r: 40, color: C.violet, w: 7, dash: 0.45, rot: -60 },
    { r: 26, color: C.gold, w: 7, dash: 0.3, rot: -120 },
  ];
  return (
    <svg width={size} height={size} viewBox="0 0 132 132" aria-hidden className="settle">
      {rings.map((g) => (
        <g key={g.r} transform={`rotate(${g.rot} 66 66)`}>
          <circle cx="66" cy="66" r={g.r} fill="none" stroke={C.grid} strokeWidth={g.w} />
          <circle cx="66" cy="66" r={g.r} fill="none" stroke={g.color} strokeOpacity="0.5" strokeWidth={g.w} strokeLinecap="round" pathLength={1} strokeDasharray={`${g.dash} 2`} />
        </g>
      ))}
      <circle cx="66" cy="66" r="3" fill={C.cream} opacity="0.85" />
    </svg>
  );
}

/** Compact empty state for a card or section: illustration, one line of what is missing, one calm next step. */
export function EmptyCard({ title, children, action, compact = false }: { title: string; children?: ReactNode; action?: ReactNode; compact?: boolean }) {
  return (
    <div className={`surface flex flex-col items-center text-center ${compact ? "px-5 py-8" : "px-6 py-12"}`}>
      <RingsIllustration size={compact ? 84 : 120} />
      <p className="t-title mt-4">{title}</p>
      {children && <p className="mt-1.5 max-w-sm text-sm text-mute">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function EmptyState() {
  const client = useQueryClient();
  const sync = useMutation({
    mutationFn: api.syncDemo,
    onSuccess: () => client.invalidateQueries(),
  });

  return (
    <section className="surface relative overflow-hidden px-6 py-14 sm:px-14 sm:py-24">
      <div className="pointer-events-none absolute -top-40 -right-40 h-[480px] w-[480px] rounded-full bg-gold/10 blur-3xl" />
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="eyebrow mb-6 flex items-center gap-2"
      >
        <Lock size={12} /> Everything stays on this Mac
      </motion.p>
      <div className="absolute top-8 right-6 hidden opacity-90 sm:block"><RingsIllustration size={170} /></div>
      <h1 className="t-large max-w-3xl !text-[clamp(2.75rem,9vw,6rem)]">
        Your body,
        <br />
        <em className="text-gold">in high resolution.</em>
      </h1>
      <p className="mt-8 max-w-xl text-lg text-mute">
        Connect your Garmin wellness history, or explore with a year of clearly labelled demo data.
      </p>
      <div className="mt-12 flex flex-wrap items-center gap-6">
        <Link to="/settings" className="pop">Connect Garmin <ArrowRight size={16} /></Link>
        <button
          type="button"
          className="pop pop-lime"
          disabled={sync.isPending}
          onClick={() => sync.mutate()}
        >
          <Sparkles size={16} />
          {sync.isPending ? "Generating…" : "Load demo year"}
          <ArrowRight size={16} />
        </button>
        <span className="flex items-center gap-2 text-sm text-dim">
          <Database size={14} /> Removable anytime from Settings
        </span>
      </div>
      {sync.isError && (
        <p role="alert" className="mt-6 text-sm text-coral">
          Import failed. Check the local service and try again.
        </p>
      )}
    </section>
  );
}
