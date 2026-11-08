/**
 * Payloads of the quick-logging endpoints in docs/food-logging-design.md section 3. Every field except the ones a chip needs to
 * log is optional: the server may send less than the proposal, or nothing at all (the page then works from local data).
 */
import type { LogItem } from "./foodRow";
import type { FoodDish, Meal } from "./types";

export interface KcalRangeValue {
  value: number;
  low: number;
  high: number;
}

export interface QuickItem {
  dish_id: number | null;
  name: string;
  servings?: number;
  grams?: number | null;
  unit?: string | null;
  kcal?: number;
  protein_g?: number | null;
}

export interface QuickChip {
  kind: "usual" | "yesterday" | "last" | "saved" | "pinned" | string;
  id?: string;
  label: string;
  items: QuickItem[];
  kcal?: KcalRangeValue | null;
  n_days?: number;
  /** Saved meal id, when kind is "saved". */
  meal_id?: number;
}

export interface FoodQuick {
  meal_guess?: Meal;
  chips?: QuickChip[];
  memory?: Record<string, { servings: number; unit?: string | null } | undefined>;
  pinned?: number[];
}

export interface FoodSuggestion {
  label: string;
  items: QuickItem[];
  kcal?: KcalRangeValue | null;
  protein_g?: number | null;
  score?: number;
  reasons?: string[];
}

export interface FoodSuggest {
  status?: "ok" | "insufficient";
  reasons_note?: string;
  needs?: string[];
  suggestions?: FoodSuggestion[];
}

export type FoodBarcodeResult = { found: true; dish: FoodDish; portion?: unknown } | { found: false; online_lookup?: "off" | "available" };

export interface FoodBatchResult {
  entries?: { id?: number }[];
  replayed?: boolean;
}

export interface FoodBulkBody {
  ids: number[];
  action: "delete" | "restore" | "move" | "scale";
  meal?: Meal;
  scale?: number;
}

/** One queued request to log a draft; the key is generated once per draft and reused on every retry. */
export interface LogOp {
  key: string;
  day: string;
  meal: Meal;
  eaten_at?: string | null;
  eating_out?: boolean;
  source?: string;
  items: LogItem[];
  created_at: number;
  attempts: number;
  status: "queued" | "needs_look";
  error?: string | null;
  /** What to show while it waits: names and ranges only. */
  preview: { name: string; low: number | null; high: number | null }[];
}
