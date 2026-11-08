/**
 * Deterministic text to food items: folding (spelling, diacritics, Devanagari), number words and the multi-item grammar of
 * docs/food-logging-design.md section 2a. Pure and offline; no dish data here (matching is in foodIndex.ts). No LLM.
 * The synonym list below is hand-written, original text.
 */

const DEV_CONS: Record<string, string> = {
  क: "k", ख: "kh", ग: "g", घ: "gh", ङ: "n", च: "ch", छ: "chh", ज: "j", झ: "jh", ञ: "n", ट: "t", ठ: "th", ड: "d", ढ: "dh", ण: "n",
  त: "t", थ: "th", द: "d", ध: "dh", न: "n", प: "p", फ: "f", ब: "b", भ: "bh", म: "m", य: "y", र: "r", ल: "l", ळ: "l", व: "v",
  श: "sh", ष: "sh", स: "s", ह: "h",
};
const DEV_VOWEL: Record<string, string> = { अ: "a", आ: "aa", इ: "i", ई: "ee", उ: "u", ऊ: "oo", ए: "e", ऐ: "ai", ओ: "o", औ: "au", ऑ: "o" };
const DEV_MATRA: Record<string, string> = { "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o" };

/** Devanagari to a Latin approximation (inherent vowel dropped at word end); other characters pass through. */
export function translit(input: string): string {
  const s = input.normalize("NFD").replace(/[०-९]/g, (d) => String(d.charCodeAt(0) - 0x966));
  if (!/[ऀ-ॿ]/.test(s)) return input;
  const chars = [...s];
  let out = "";
  let pend = false;
  let prevVowel = false; // was the consonant awaiting its vowel preceded by a vowel? (medial schwa deletion)
  for (let i = 0; i < chars.length; i++) {
    const c = chars[i];
    const next = chars[i + 1];
    if (DEV_CONS[c]) {
      const nextIsVowel = next !== undefined && (DEV_MATRA[next] !== undefined || DEV_VOWEL[next] !== undefined);
      if (pend && !(prevVowel && nextIsVowel)) out += "a";
      prevVowel = /[aeiou]$/.test(out);
      out += DEV_CONS[c];
      pend = true;
    } else if (DEV_MATRA[c]) {
      out += DEV_MATRA[c];
      pend = false;
    } else if (DEV_VOWEL[c]) {
      if (pend) out += "a";
      out += DEV_VOWEL[c];
      pend = false;
    } else if (c === "्") {
      pend = false;
    } else if (c === "ं" || c === "ँ") {
      if (pend) out += "a";
      pend = false;
      out += next && /[पफबभम]/.test(next) ? "m" : "n";
    } else if (c === "़" || c === "ः" || c === "ऽ") {
      /* nukta, visarga, avagraha: ignored */
    } else {
      pend = false;
      out += c === "।" ? "," : c;
    }
  }
  return out;
}

/** Folds one word: lowercase, no diacritics, common spelling variants collapsed ("sambhar", "sambaar" and "sambar" agree). */
function foldWord(w: string): string {
  return w
    .replace(/ph/g, "f")
    .replace(/([bdgkt])h(?=[aeiouy])/g, "$1")
    .replace(/w/g, "v")
    .replace(/z/g, "j")
    .replace(/q/g, "k")
    .replace(/c(?!h)/g, "k")
    .replace(/aa/g, "a")
    .replace(/ee|ii/g, "i")
    .replace(/oo|uu/g, "u")
    .replace(/([^aeiou])y$/, "$1i")
    .replace(/(.)\1+/g, "$1");
}

const normalizeText = (s: string) =>
  translit(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").trim();

/** Original, hand-written synonyms (alias, canonical word). Both sides of every comparison go through them. */
const SYNONYM_PAIRS: [string, string][] = [
  ["kaapi", "coffee"], ["kapi", "coffee"], ["chai", "tea"], ["chaay", "tea"], ["dahi", "curd"], ["yogurt", "curd"], ["yoghurt", "curd"],
  ["chawal", "rice"], ["bhaat", "rice"], ["bhat", "rice"], ["chapati", "roti"], ["chapatti", "roti"], ["phulka", "roti"], ["rotli", "roti"],
  ["anda", "egg"], ["ande", "egg"], ["eggs", "egg"], ["doodh", "milk"], ["dudh", "milk"], ["aloo", "potato"], ["alu", "potato"],
  ["pyaz", "onion"], ["pyaaz", "onion"], ["tamatar", "tomato"], ["makhan", "butter"], ["paani", "water"], ["pani", "water"],
  ["daal", "dal"], ["dhal", "dal"], ["lentils", "dal"], ["bhindi", "okra"], ["gobi", "cauliflower"], ["gobhi", "cauliflower"],
  ["mirch", "chilli"], ["nimbu", "lemon"], ["shakkar", "sugar"], ["cheeni", "sugar"], ["namak", "salt"], ["saunf", "fennel"],
  ["badam", "almonds"], ["almond", "almonds"], ["kela", "banana"], ["seb", "apple"], ["aam", "mango"], ["murgh", "chicken"],
  ["machli", "fish"], ["dosai", "dosa"], ["panir", "paneer"], ["pannir", "paneer"], ["idly", "idli"], ["idlee", "idli"],
  ["vadai", "vada"], ["wada", "vada"], ["sabji", "sabzi"], ["subji", "sabzi"], ["sabzee", "sabzi"],
];
const SYN = new Map<string, string>(SYNONYM_PAIRS.map(([a, c]) => [foldWord(a), foldWord(c)]));

/** Folded words of a text, synonyms applied. */
export function foldWords(s: string): string[] {
  return normalizeText(s)
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => {
      const f = foldWord(w);
      return SYN.get(f) ?? f;
    });
}

/** One matching key: folded words joined with no spaces. */
export const foldKey = (s: string): string => foldWords(s).join("");

// ---- numbers, units ----------------------------------------------------------------------------------------------------

const NUMBER_WORDS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, half: 0.5, quarter: 0.25, a: 1, an: 1,
  ek: 1, do: 2, teen: 3, char: 4, paanch: 5, aadha: 0.5, adha: 0.5,
};
const GLYPHS: Record<string, string> = { "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8" };

const UNIT_ALIASES: Record<string, string> = {
  katori: "katori", katoris: "katori", bowl: "bowl", bowls: "bowl", cup: "cup", cups: "cup",
  piece: "piece", pieces: "piece", pc: "piece", pcs: "piece", nos: "piece",
  glass: "glass", glasses: "glass", plate: "plate", plates: "plate", tsp: "tsp", teaspoon: "tsp", teaspoons: "tsp",
  tbsp: "tbsp", tablespoon: "tbsp", tablespoons: "tbsp", spoon: "tbsp", spoons: "tbsp",
  slice: "slice", slices: "slice", ladle: "ladle", ladles: "ladle", g: "g", gm: "g", gms: "g", gram: "g", grams: "g",
  ml: "ml", handful: "handful", handfuls: "handful", scoop: "scoop", scoops: "scoop",
};

/** Canonical unit for a word, or null. */
export const canonicalUnit = (w: string): string | null => UNIT_ALIASES[w] ?? null;

/** Rough volume or weight of a household unit in grams (1 g per ml assumed); used only when the dish has no such portion. */
export const UNIT_GRAMS: Record<string, number> = { katori: 150, bowl: 200, cup: 240, glass: 250, tsp: 5, tbsp: 15, ladle: 60, handful: 30, scoop: 30 };

const NUM_RE = /^(\d+(?:\.\d+)?|\d+\/\d+)$/;
const parseNum = (t: string): number | null => {
  if (!NUM_RE.test(t)) return null;
  if (t.includes("/")) {
    const [a, b] = t.split("/").map(Number);
    return b ? a / b : null;
  }
  return Number(t);
};

export interface RawItem {
  /** Name words as typed (translated to Latin if Devanagari). */
  name: string;
  qty: number | null;
  unit: string | null;
}

interface Cur {
  name: string[];
  before: number | null;
  after: number | null;
  unit: string | null;
}

const SEPARATORS = /\s*(?:[,;+&\n]|\band\b|\bwith\b|\baur\b|\bplus\b)\s*/i;

/** Splits a typed line into items: "idli 2, sambar, coffee", "2 idli + sambar", and runs with no separator ("idli 2 sambar 1 katori"). */
export function parseRaw(line: string): RawItem[] {
  const text = translit(line).replace(/(\d)\s*([½¼¾⅓⅔⅛])/g, "$1 $2").replace(/[½¼¾⅓⅔⅛]/g, (g) => ` ${GLYPHS[g]} `);
  const items: RawItem[] = [];
  for (const seg of text.split(SEPARATORS)) {
    let cur: Cur = { name: [], before: null, after: null, unit: null };
    const flush = () => {
      if (cur.name.length) items.push({ name: cur.name.join(" "), qty: cur.before ?? cur.after, unit: cur.unit });
      cur = { name: [], before: null, after: null, unit: null };
    };
    const tokens = normalizeSeg(seg);
    for (let i = 0; i < tokens.length; i++) {
      const t = tokens[i];
      if (t === "of") continue;
      const num = parseNum(t);
      const word = NUMBER_WORDS[t];
      const isAN = t === "a" || t === "an";
      const asQty = num ?? (word !== undefined && !(isAN && cur.name.length) ? word : null);
      if (asQty !== null) {
        if (cur.name.length && cur.before == null && cur.after == null) cur.after = asQty;
        else if (!cur.name.length && cur.before != null && cur.unit == null && asQty > 0 && asQty < 1 && cur.before >= 1) cur.before += asQty; // 1 1/2
        else {
          if (cur.name.length) flush();
          cur.before = asQty;
        }
        continue;
      }
      const unit = canonicalUnit(t);
      if (unit && (cur.name.length || cur.before != null || cur.after != null) && cur.unit == null) {
        cur.unit = unit;
        continue;
      }
      if (cur.after != null && cur.name.length) flush(); // "idli 2 sambar": the number closed the first item
      cur.name.push(t);
    }
    flush();
  }
  return items;
}

/** Lowercased tokens of a segment with attached forms split: "3x", "x3", "200g", "1.5katori". */
function normalizeSeg(seg: string): string[] {
  const out: string[] = [];
  for (const raw of seg.toLowerCase().replace(/[()"“”]/g, " ").split(/\s+/).filter(Boolean)) {
    let m: RegExpMatchArray | null;
    if ((m = raw.match(/^(\d+(?:\.\d+)?)x$/)) || (m = raw.match(/^x(\d+(?:\.\d+)?)$/))) out.push(m[1]);
    else if ((m = raw.match(/^(\d+(?:\.\d+)?)([a-z]+)$/)) && canonicalUnit(m[2])) out.push(m[1], m[2]);
    else if (raw === "x" || raw === "×") continue;
    else out.push(raw.replace(/[.:!?]+$/g, "").replace(/^[.:!?]+/, "") || raw);
  }
  return out.filter(Boolean);
}
