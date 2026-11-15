import { useEffect } from "react";
import { hasUnsavedWork } from "./useAppLifecycle";
import { autoTheme, minutesOf, skyStage } from "./sky";
import { readChoice } from "./theme";

const LIGHT_BAR = "#f5f3ee";
const DARK_BAR = "#080a12";

/**
 * Sets the sky stage for this moment and, when the theme is on automatic, light or dark. Returns true when the page flipped between
 * light and dark (CSS follows at once; the colours charts were drawn with only catch up on the next load).
 */
export function syncSky(root: HTMLElement = document.documentElement, now: Date = new Date(), choice = readChoice()): boolean {
  const min = minutesOf(now);
  root.dataset.sky = skyStage(min);
  if (choice !== "auto") return false;
  const want = autoTheme(min);
  if (root.dataset.theme === want) return false;
  root.dataset.theme = want;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", want === "light" ? LIGHT_BAR : DARK_BAR);
  return true;
}

/** Keeps the sky and the automatic light/dark current while the app is open. A flip is finished with a reload the next time the app comes to the front, never under unsaved work or a workout in progress. */
export function useLivingTheme() {
  useEffect(() => {
    let flipped = false;
    const tick = () => { if (syncSky()) flipped = true; };
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      tick();
      if (flipped && !hasUnsavedWork() && !window.location.pathname.startsWith("/workout")) window.location.reload();
    };
    tick();
    const timer = setInterval(tick, 60_000);
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, []);
}
