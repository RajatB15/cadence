/**
 * In-memory dish index and the ranking of docs/food-logging-design.md section 2a, then `parseLine`: typed text to draft rows.
 * Pure, offline, no network. Deviation from the doc's formula: an edit-distance match within the limit adds a base of 30 before
 * the 8-per-edit penalty (otherwise a one-letter typo could never score above zero); transpositions count as one edit.
 */
import { foldKey, foldWords, parseRaw } from "./foodParse";
import { KCAL_ONLY_SPREAD_PCT, newRowId, resolveAmount, settle, type FoodRow, type RowDish } from "./foodRow";

interface Entry {
  dish: RowDish;
  nameKey: string;
  aliasKeys: string[];
  /** Names the user gave the dish: matched first, ahead of the library's own. */
  mine: { text: string; key: string; words: string[]; sorted: string }[];
  /** Library aliases as written, with their keys, for the "matched: x" hint. */
  aliasInfo: { text: string; key: string; words: string[] }[];
  words: string[];
  trigrams: Set<string>[];
}

/** Why a dish matched: your own name, a library alias, or the dish's name itself. */
export interface MatchVia {
  kind: "mine" | "alias";
  text: string;
}

export interface FoodIndex {
  entries: Entry[];
  byId: Map<number, Entry>;
  dishById: Map<number, RowDish>;
  /** trigram -> entries; candidate generation for fuzzy matching. */
  grams: Map<string, number[]>;
  /** distinct words -> entry positions, for prefix scans. */
  words: Map<string, number[]>;
}

const trigramsOf = (key: string): Set<string> => {
  const p = `^${key}$`;
  const out = new Set<string>();
  for (let i = 0; i + 3 <= p.length; i++) out.add(p.slice(i, i + 3));
  return out;
};

export function buildIndex(dishes: RowDish[]): FoodIndex {
  const entries: Entry[] = [];
  const grams = new Map<string, number[]>();
  const words = new Map<string, number[]>();
  for (const dish of dishes) {
    const nameKey = foldKey(dish.name);
    if (!nameKey) continue;
    const aliasKeys = (dish.aliases ?? []).map(foldKey).filter((k) => k && k !== nameKey);
    const mine = (dish.my_names ?? [])
      .map((m) => ({ text: m?.name ?? "", words: foldWords(m?.name ?? "") }))
      .filter((m) => m.words.length)
      .map((m) => ({ ...m, key: m.words.join(""), sorted: [...m.words].sort().join("") }));
    const aliasInfo = (dish.aliases ?? []).map((text) => ({ text, words: foldWords(text) })).map((a) => ({ ...a, key: a.words.join("") })).filter((a) => a.key && a.key !== nameKey);
    const ws = new Set([...foldWords(dish.name), ...(dish.aliases ?? []).flatMap(foldWords), ...mine.flatMap((m) => m.words)]);
    const at = entries.length;
    const tg = [nameKey, ...aliasKeys, ...mine.map((m) => m.key)].map(trigramsOf);
    entries.push({ dish, nameKey, aliasKeys, mine, aliasInfo, words: [...ws], trigrams: tg });
    const seen = new Set<string>();
    for (const t of tg) for (const g of t) if (!seen.has(g)) {
      seen.add(g);
      const l = grams.get(g);
      if (l) l.push(at);
      else grams.set(g, [at]);
    }
    for (const w of ws) {
      const l = words.get(w);
      if (l) l.push(at);
      else words.set(w, [at]);
    }
  }
  return { entries, byId: new Map(entries.map((e) => [e.dish.id, e])), dishById: new Map(entries.map((e) => [e.dish.id, e.dish])), grams, words };
}

/** Optimal-string-alignment distance (insert, delete, substitute, adjacent swap), early exit above `max`. */
export function editDistance(a: string, b: string, max = 3): number {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

const jaccard = (a: Set<string>, b: Set<string>): number => {
  let inter = 0;
  for (const x of a) if (b.has(x)) inter++;
  return inter / (a.size + b.size - inter || 1);
};

export interface Scored {
  dish: RowDish;
  score: number;
  /** Set when your own name or a library alias, not the dish's name, is what matched. */
  via?: MatchVia;
}

/** How well one key (a name of yours or an alias) matches the query; 0 when it does not. Order of words does not matter. */
function keyStrength(q: string, qWords: string[], qSorted: string, k: { key: string; words: string[]; sorted?: string }, limitEd: number): number {
  const sorted = k.sorted ?? [...k.words].sort().join("");
  if (k.key === q || sorted === qSorted) return 4;
  if (q.length >= 2 && k.key.startsWith(q)) return 3;
  if (qWords.every((qw) => k.words.some((w) => w.startsWith(qw)))) return 3;
  // Half-typed "meeth" folds to "mith" (th before a vowel folds to t); the finished word is "mita".
  const open = q.replace(/([bdgkt])h$/, "$1");
  if (open !== q && open.length >= 2 && k.key.startsWith(open)) return 3;
  const ed = Math.min(editDistance(q, k.key, limitEd), editDistance(qSorted, sorted, limitEd));
  return ed >= 1 && ed <= limitEd ? 1 : 0;
}

export const ACCEPT_SCORE = 20;

/** Ranks dishes for a query (higher is better). `frecency` is 0..1 per dish id. Top `limit` only. */
export function rank(index: FoodIndex, query: string, frecency?: Map<number, number>, limit = 5): Scored[] {
  const qWords = foldWords(query);
  const q = qWords.join("");
  if (!q) return [];
  const cand = new Set<number>();
  const openWords = qWords.map((w) => w.replace(/([bdgkt])h$/, "$1"));
  for (const [w, at] of index.words) if (qWords.some((qw, i) => w.startsWith(qw) || (openWords[i] !== qw && w.startsWith(openWords[i])))) for (const i of at) cand.add(i);
  if (q.length >= 3) {
    const qt = trigramsOf(q);
    const hits = new Map<number, number>();
    for (const g of qt) for (const i of index.grams.get(g) ?? []) hits.set(i, (hits.get(i) ?? 0) + 1);
    const need = Math.max(2, Math.floor(qt.size * 0.3));
    for (const [i, n] of hits) if (n >= need) cand.add(i);
  }
  const qSorted = [...qWords].sort().join("");
  const limitEd = q.length <= 5 ? 1 : 2;
  // A swapped or dropped letter can share no trigram with the right dish: when nothing close was found, scan names of similar length.
  const hasStrong = [...cand].some((i) => index.entries[i].nameKey.startsWith(q) || index.entries[i].mine.some((m) => m.key.startsWith(q)));
  if (!hasStrong && q.length >= 3) {
    index.entries.forEach((e, i) => {
      if (!cand.has(i) && [e.nameKey, ...e.aliasKeys, ...e.mine.map((m) => m.key), ...e.mine.map((m) => m.sorted)].some((k) => Math.abs(k.length - q.length) <= limitEd && editDistance(q, k, limitEd) <= limitEd)) cand.add(i);
    });
  }
  const qTri = q.length >= 3 ? trigramsOf(q) : null;
  const out: Scored[] = [];
  for (const i of cand) {
    const e = index.entries[i];
    const keys = [e.nameKey, ...e.aliasKeys];
    let score = 0;
    let matched = false;
    if (e.nameKey === q) { score += 100; matched = true; }
    if (q.length >= 2 && e.nameKey.startsWith(q)) { score += 70; matched = true; }
    if (qWords.every((qw) => e.words.some((w) => w.startsWith(qw)))) { score += 50; matched = true; }
    if (e.aliasKeys.includes(q)) { score += 35; matched = true; }
    if (qTri) {
      const j = Math.max(...e.trigrams.map((t) => jaccard(qTri, t)));
      if (j >= 0.35) { score += 25 * j; matched = true; }
    }
    let ed = limitEd + 1;
    if (!matched || score < 100) for (const k of keys) ed = Math.min(ed, k === q ? 0 : editDistance(q, k, limitEd));
    if (ed >= 1 && ed <= limitEd && score < 100) { score += 30 - 8 * ed; matched = true; }
    // Your own name outranks everything the library calls the dish.
    let via: MatchVia | undefined;
    const base = score;
    let bestMine = 0;
    for (const m of e.mine) {
      const st = keyStrength(q, qWords, qSorted, m, limitEd);
      if (st > bestMine) {
        bestMine = st;
        via = { kind: "mine", text: m.text };
      }
    }
    if (bestMine) {
      const mineScore = [0, 90, 0, 190, 260][bestMine];
      if (mineScore > base) { score = mineScore; matched = true; } else via = undefined;
    }
    if (!matched) continue;
    if (!via) {
      // Say which library alias matched, only when the dish's own name did not.
      const nameHit = e.nameKey === q || e.nameKey.startsWith(q) || qWords.every((qw) => foldWords(e.dish.name).some((w) => w.startsWith(qw))) || editDistance(q, e.nameKey, limitEd) <= limitEd;
      if (!nameHit) {
        let best = 0;
        for (const a of e.aliasInfo) {
          const st = keyStrength(q, qWords, qSorted, a, limitEd);
          if (st > best) { best = st; via = { kind: "alias", text: a.text }; }
        }
      }
    }
    if (e.dish.source === "mine" || e.dish.basis === "label") score += 18;
    score += 30 * (frecency?.get(e.dish.id) ?? 0);
    out.push({ dish: e.dish, score, via });
  }
  out.sort((a, b) => b.score - a.score || a.dish.name.length - b.dish.name.length || a.dish.name.localeCompare(b.dish.name));
  return out.slice(0, limit);
}

export interface ParseContext {
  frecency?: Map<number, number>;
  /** Last portion used per dish id (portion memory). */
  memory?: Record<number, { servings: number; unit?: string | null } | undefined>;
  eatingOut?: boolean;
}

/** Typed line to rows. A number alone is not an item; an unmatched name keeps its row ("No match") so nothing is silently dropped. */
export function parseLine(line: string, index: FoodIndex, ctx: ParseContext = {}): FoodRow[] {
  const rows: FoodRow[] = [];
  for (const item of parseRaw(line)) {
    if (!foldKey(item.name)) continue;
    const cands = rank(index, item.name, ctx.frecency, 3);
    const candidates = cands.map((c) => ({ id: c.dish.id, name: c.dish.name, score: Math.round(c.score), via: c.via }));
    const top = cands[0];
    const base = { id: newRowId(), text: item.name, qty: item.qty, unit: item.unit, candidates, via: top?.via, grams: null, servings: null, out: ctx.eatingOut };
    if (top && top.score >= ACCEPT_SCORE) {
      rows.push(settle({ ...base, kind: "dish", dish: top.dish, dishId: top.dish.id, ...resolveAmount(top.dish, item.qty, item.unit, ctx.memory?.[top.dish.id]) }));
    } else if (item.qty != null && item.qty >= 50 && item.unit == null) {
      // "biryani 450" or "450 biryani": a calories-only item, with a wide range because nothing is known about it.
      rows.push(settle({ ...base, kind: "kcal", dish: null, dishId: null, kcal: item.qty, portionIdx: -2, amount: 1, flags: [] }));
    } else {
      rows.push({ ...base, kind: "none", dish: null, dishId: null, portionIdx: -2, amount: item.qty ?? 1, flags: [] });
    }
  }
  return rows;
}

/** Re-resolve one row against another dish (a "Did you mean" tap), keeping the typed amount. */
export function rowForDish(row: FoodRow, dish: RowDish): FoodRow {
  return settle({ ...row, via: undefined, kind: "dish", dish, dishId: dish.id, kcal: undefined, ...resolveAmount(dish, row.qty, row.unit) });
}

export const KCAL_SPREAD = KCAL_ONLY_SPREAD_PCT;
