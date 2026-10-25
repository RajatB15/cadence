import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { bannerLine, dayLine } from "../lib/phases";

/** A slim strip on Home for each phase running now (or starting within a week). Says nothing when there is none, or on error. */
export function PhaseBanner() {
  const query = useQuery({ queryKey: ["phases-active"], queryFn: api.activePhases, staleTime: 5 * 60_000 });
  const items = query.data?.items ?? [];
  if (!items.length) return null;
  return (
    <section aria-label="Current phase" className="space-y-2">
      {items.slice(0, 2).map((p) => (
        <Link key={p.id} to={`/phases/${p.id}`} className="surface surface-hover group relative flex items-center gap-4 overflow-hidden py-3 pr-4 pl-5" style={{ borderLeft: `3px solid ${p.color}` }}>
          <span className="text-2xl" aria-hidden>{p.emoji || "◎"}</span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-3">
              <span className="font-display text-xl text-cream">{p.name}</span>
              <span className="num text-xs text-mute">{dayLine(p)}</span>
            </span>
            <span className="block truncate text-sm text-mute">{bannerLine(p, query.data?.habits)}</span>
          </span>
          <ChevronRight size={18} className="shrink-0 text-dim transition-transform group-hover:translate-x-1" />
          {p.state === "active" && (
            <span aria-hidden className="absolute inset-x-0 bottom-0 h-0.5 bg-line">
              <span className="block h-full" style={{ width: `${Math.round(p.pct * 100)}%`, background: p.color }} />
            </span>
          )}
        </Link>
      ))}
    </section>
  );
}
