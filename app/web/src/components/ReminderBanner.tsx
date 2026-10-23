import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { AlertTriangle, KeyRound, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { reminderCopy } from "../lib/format";
import { useCredentialStatus } from "../lib/useCredentialStatus";

const TONES = {
  info: "border-gold/40 text-gold",
  warn: "border-amber/50 text-amber",
  danger: "border-coral/60 text-coral",
};

export function ReminderBanner() {
  const { data } = useCredentialStatus();
  const client = useQueryClient();
  const dismiss = useMutation({
    mutationFn: api.dismissReminder,
    onSuccess: () => client.invalidateQueries({ queryKey: ["credential"] }),
  });
  const copy = data ? reminderCopy(data) : null;
  const canDismiss = data && data.level !== "expired" && data.reminder_key != null;

  return (
    <AnimatePresence>
      {copy && (
        <motion.div
          role={copy.tone === "danger" ? "alert" : "status"}
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          className={clsx(
            "surface mb-8 flex items-center gap-4 border-l-2 px-5 py-4",
            TONES[copy.tone],
          )}
        >
          {copy.tone === "danger" ? <AlertTriangle size={18} /> : <KeyRound size={18} />}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-paper">{copy.title}</p>
            <p className="text-sm text-mute">{copy.body}</p>
          </div>
          <Link to="/settings" className="eyebrow !text-current hover:underline">
            Manage
          </Link>
          {canDismiss && (
            <button
              type="button"
              aria-label="Dismiss reminder"
              className="p-1 text-mute hover:text-paper"
              onClick={() => dismiss.mutate(data.reminder_key!)}
            >
              <X size={16} />
            </button>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
