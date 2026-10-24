import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "./api";

/** Minimum gap between automatic Garmin syncs, so reopening the app repeatedly never hammers Garmin. */
export const AUTO_SYNC_COOLDOWN_MIN = 10;

/** The hashed entry bundle named by an index.html, or null if there is none. */
export function entryBundle(html: string): string | null {
  return html.match(/<script[^>]+src="(\/assets\/index-[^"]+\.js)"/)?.[1] ?? null;
}

export function shouldAutoSync(finishedAt: string | null | undefined, busy: boolean, now = Date.now()): boolean {
  if (busy) return false;
  if (!finishedAt) return true;
  const finished = new Date(finishedAt.endsWith("Z") ? finishedAt : `${finishedAt}Z`).getTime();
  return !Number.isFinite(finished) || now - finished > AUTO_SYNC_COOLDOWN_MIN * 60_000;
}

function loadedBundle(): string | null {
  const src = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/index-"]')?.getAttribute("src");
  return src ?? null;
}

/** Index.html is served no-cache with hashed assets, so a changed entry bundle means a new deploy. */
async function newVersionAvailable(): Promise<boolean> {
  const current = loadedBundle();
  if (!current) return false; // dev server or unhashed build
  try {
    const res = await fetch("/", { cache: "no-store" });
    if (!res.ok) return false;
    const latest = entryBundle(await res.text());
    return latest !== null && latest !== current;
  } catch {
    return false; // offline: keep running what we have
  }
}

/**
 * Every time the app opens or returns to the foreground: reload if a newer build was deployed, otherwise
 * start a quick Garmin sync when the last one is older than the cooldown. Quick syncs are idempotent,
 * rate-limited and fetch only unsettled days, so this is cheap; failures are left to the refresh chip.
 */
export function useAppLifecycle() {
  const client = useQueryClient();
  useEffect(() => {
    let running = false;
    const onOpen = async () => {
      if (document.visibilityState !== "visible" || running) return;
      running = true;
      try {
        if (await newVersionAvailable()) {
          window.location.reload();
          return;
        }
        const status = await client.fetchQuery({ queryKey: ["garmin-status"], queryFn: api.garminStatus, staleTime: 0 });
        if (shouldAutoSync(status.run?.finished_at ?? status.run?.started_at, status.busy)) {
          await api.garminSync("quick");
          client.invalidateQueries({ queryKey: ["garmin-status"] });
        }
      } catch {
        // No credential on the server, a job already running, or offline: nothing to do automatically.
      } finally {
        running = false;
      }
    };
    void onOpen();
    document.addEventListener("visibilitychange", onOpen);
    return () => document.removeEventListener("visibilitychange", onOpen);
  }, [client]);
}
