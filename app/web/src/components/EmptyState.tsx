import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Database, Lock, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { api } from "../lib/api";
import { Link } from "react-router-dom";

export function EmptyState() {
  const client = useQueryClient();
  const sync = useMutation({
    mutationFn: api.syncDemo,
    onSuccess: () => client.invalidateQueries(),
  });

  return (
    <section className="relative overflow-hidden border border-line px-6 py-16 sm:px-14 sm:py-24">
      <div className="pointer-events-none absolute -top-40 -right-40 h-[480px] w-[480px] rounded-full bg-gold/10 blur-3xl" />
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="eyebrow mb-6 flex items-center gap-2"
      >
        <Lock size={12} /> Everything stays on this Mac
      </motion.p>
      <h1 className="max-w-3xl font-display text-6xl leading-[0.92] text-cream sm:text-8xl">
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
