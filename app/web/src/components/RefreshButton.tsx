import * as Tooltip from "@radix-ui/react-tooltip";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { RefreshCw } from "lucide-react";
import { useEffect, useRef } from "react";
import { api } from "../lib/api";

function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso.endsWith("Z") ? iso : `${iso}Z`).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
}

/** Quick Garmin sync on demand; refreshes every view when the job finishes. */
export function useGarminRefresh() {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["garmin-status"],
    queryFn: api.garminStatus,
    refetchInterval: (q) => (q.state.data?.busy ? 1500 : 60_000),
  });
  const wasBusy = useRef(false);
  useEffect(() => {
    const busy = status.data?.busy ?? false;
    if (wasBusy.current && !busy) {
      client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "garmin-status" });
    }
    wasBusy.current = busy;
  }, [status.data, client]);
  const sync = useMutation({
    mutationFn: () => api.garminSync("quick"),
    onSettled: () => client.invalidateQueries({ queryKey: ["garmin-status"] }),
  });
  const run = status.data?.run ?? null;
  const busy = Boolean(status.data?.busy) || sync.isPending;
  return {
    ready: status.isSuccess,
    busy,
    label: busy ? run?.message || "Syncing…" : `Synced ${ago(run?.finished_at ?? run?.started_at)}`,
    error: sync.error?.message ?? (run?.status === "failed" ? run.error : null),
    refresh: () => !busy && sync.mutate(),
  };
}

export function RefreshChip() {
  const g = useGarminRefresh();
  if (!g.ready) return null;
  return (
    <button
      type="button"
      onClick={g.refresh}
      disabled={g.busy}
      title={g.error ?? "Pull the latest from Garmin. Your watch must have synced to Garmin Connect first."}
      className={clsx("chip gap-1.5 transition-colors hover:!text-paper", g.error ? "!border-coral/50 !text-coral" : "!text-lime")}
    >
      <RefreshCw size={11} className={clsx(g.busy && "animate-spin")} />
      <span className="max-w-[16rem] truncate normal-case">{g.error ? "Sync failed · retry" : g.label}</span>
    </button>
  );
}

export function RefreshRailButton() {
  const g = useGarminRefresh();
  if (!g.ready) return null;
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          type="button"
          onClick={g.refresh}
          disabled={g.busy}
          aria-label="Refresh from Garmin"
          className={clsx("grid h-12 w-12 place-items-center transition-colors", g.error ? "text-coral" : g.busy ? "text-lime" : "text-mute hover:text-paper")}
        >
          <RefreshCw size={19} strokeWidth={1.75} className={clsx(g.busy && "animate-spin")} />
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="right"
          sideOffset={14}
          className="z-50 max-w-60 border border-line-strong bg-coal px-3 py-2 text-xs text-paper"
        >
          <p className="font-semibold tracking-widest uppercase">{g.busy ? "Syncing" : "Refresh from Garmin"}</p>
          <p className="mt-1 text-mute">{g.error ?? g.label}</p>
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
