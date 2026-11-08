// Theme: dark or light, following the system until the user picks one in Settings.
// The choice is applied before first paint by the inline script in index.html (same logic as resolveTheme).
// JS colours (charts, inline SVG) come from `C`, resolved once per page load; switching theme reloads the page so
// module-level colour tables never go stale. CSS reads the same palette through the --color-* tokens in index.css.

export type Theme = "dark" | "light";
export type ThemeChoice = Theme | "system";

export const THEME_KEY = "cadence-theme";

/** Pure: a stored choice (anything unrecognised means system) and the system preference give the theme to show. */
export function resolveTheme(stored: string | null | undefined, systemPrefersLight: boolean): Theme {
  if (stored === "dark" || stored === "light") return stored;
  return systemPrefersLight ? "light" : "dark";
}

export function readChoice(storage: Pick<Storage, "getItem"> | null = safeStorage()): ThemeChoice {
  try {
    const v = storage?.getItem(THEME_KEY);
    return v === "dark" || v === "light" ? v : "system";
  } catch {
    return "system";
  }
}

/** Persist a choice; "system" clears it. Returns false when storage is unavailable (private window, blocked data). */
export function writeChoice(choice: ThemeChoice, storage: Pick<Storage, "setItem" | "removeItem"> | null = safeStorage()): boolean {
  try {
    if (!storage) return false;
    if (choice === "system") storage.removeItem(THEME_KEY);
    else storage.setItem(THEME_KEY, choice);
    return true;
  } catch {
    return false;
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function systemLight(): boolean {
  try {
    return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches;
  } catch {
    return false;
  }
}

export function currentTheme(): Theme {
  if (typeof document !== "undefined") {
    const t = document.documentElement.dataset.theme;
    if (t === "dark" || t === "light") return t;
  }
  return resolveTheme(readChoice(), systemLight());
}

/** Apply a choice to the document, and reload so JS-resolved colours (charts) match. */
export function applyChoice(choice: ThemeChoice): void {
  writeChoice(choice);
  if (typeof window !== "undefined") window.location.reload();
}

export interface Palette {
  ink: string; coal: string; slate: string; line: string; lineStrong: string; grid: string; faint: string;
  cream: string; paper: string; mute: string; dim: string;
  gold: string; lime: string; violet: string; coral: string; sky: string; amber: string; mint: string;
}

// Keep in step with the tokens in index.css. Light accents are deeper so text and marks reach 4.5:1 on white cards.
export const PALETTES: Record<Theme, Palette> = {
  dark: {
    ink: "#080a12", coal: "#10121d", slate: "#191c2b", line: "#252940", lineStrong: "#363b5c", grid: "#1b1e30", faint: "#6b7094",
    cream: "#fff3df", paper: "#eceef8", mute: "#9a9fbd", dim: "#8d92b2",
    gold: "#ff8a3d", lime: "#b8f53d", violet: "#a78bfa", coral: "#ff5d73", sky: "#55b8ff", amber: "#ffc247", mint: "#38e8c0",
  },
  light: {
    ink: "#f5f3ee", coal: "#ffffff", slate: "#ebe8e0", line: "#dedacd", lineStrong: "#c4bfaf", grid: "#e8e4da", faint: "#7a7c88",
    cream: "#14151c", paper: "#1c1e29", mute: "#555868", dim: "#626574",
    gold: "#c2410c", lime: "#3f7d00", violet: "#6741d9", coral: "#c81e48", sky: "#0b64bd", amber: "#965800", mint: "#00765f",
  },
};

/** Resolved colours for the current page load (charts and inline styles). */
export const C: Palette = PALETTES[currentTheme()];
