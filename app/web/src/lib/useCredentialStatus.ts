import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "./api";

const HOUR = 60 * 60 * 1000;

/** Recomputed on focus/resume, hourly, and right after local midnight so day changes are never missed. */
export function useCredentialStatus() {
  const client = useQueryClient();

  useEffect(() => {
    let timer: number;
    const schedule = () => {
      const now = new Date();
      const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 5);
      timer = window.setTimeout(() => {
        client.invalidateQueries({ queryKey: ["credential"] });
        schedule();
      }, midnight.getTime() - now.getTime());
    };
    schedule();
    const onVisible = () => {
      if (document.visibilityState === "visible") client.invalidateQueries({ queryKey: ["credential"] });
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [client]);

  return useQuery({
    queryKey: ["credential"],
    queryFn: api.credentialStatus,
    refetchInterval: HOUR,
    refetchOnWindowFocus: true,
  });
}
