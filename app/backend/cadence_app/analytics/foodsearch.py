"""Forgiving food-name matching: folding, transliteration, typo tolerance and ranking. Pure functions, no database.

Method
- Folding. Text is lower-cased and stripped of diacritics (Unicode NFKD). Indic scripts (Devanagari, Bengali, Gurmukhi,
  Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam) are transliterated to Latin: those blocks share the ISCII layout, so each
  letter is mapped to its Devanagari twin and then to Latin, adding the inherent "a" after a consonant unless a vowel sign or
  virama follows and dropping the final schwa (the Hindi "schwa deletion" rule). Tamil, which has fewer letters, is
  approximate. Then spelling variants are collapsed with a small fixed rule set (w->v, z->j, q->k, ph->f, aspirates
  th/dh/bh/kh/gh/jh lose their h, sh and ch become s and c, ee->i, oo->u, aa->a, ai->ay, doubled letters become one,
  "m" before b/p becomes "n"), so chawal/chaval, aloo/alu, paneer/panir and kothimbir/kothmir meet. This is a heuristic, not a
  linguistic transliteration standard.
- Matching. Query and name are split into tokens (word order is ignored). Each query token takes the best of: identical
  (1.0), a prefix of a name token (0.92), a typo within a bounded Damerau-Levenshtein distance (1 edit for tokens of 4+
  letters, 2 for 7+; 0.75 and 0.65), the same typo-within-prefix (0.6), or a substring of 3+ letters (0.5). Every query
  token must match something or the name does not match. Fewer unmatched name tokens scores higher.
- Ranking. The best candidate string per dish counts: your own names, then the dish name, then library aliases (0.95).
  Your own names rank first when they match well (score >= 0.8); otherwise everything competes on score. A small boost
  from how often and recently you log the dish (frecency, see `foodrank`) and from how often you chose it by one of your
  own names breaks ties and lets what you actually use rise, never outweighing a clearly better text match.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

MIN_SCORE = 0.45
OWN_FIRST_SCORE = 0.8
ALIAS_WEIGHT = 0.95
FRECENCY_BOOST = 0.12
USE_BOOST = 0.08

# Indic blocks share the ISCII layout: offset from the block start -> the Devanagari letter at the same offset.
_BLOCKS = (0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80, 0x0C00, 0x0C80, 0x0D00)
_INDEPENDENT = {0x05: "a", 0x06: "aa", 0x07: "i", 0x08: "ii", 0x09: "u", 0x0A: "uu", 0x0B: "ri", 0x0F: "e", 0x10: "ai", 0x13: "o", 0x14: "au",
                0x0E: "e", 0x12: "o", 0x0C: "li", 0x04: "a"}
_SIGNS = {0x3E: "aa", 0x3F: "i", 0x40: "ii", 0x41: "u", 0x42: "uu", 0x43: "ri", 0x47: "e", 0x48: "ai", 0x4B: "o", 0x4C: "au",
          0x46: "e", 0x4A: "o", 0x45: "e", 0x49: "o"}
_CONS = {0x15: "k", 0x16: "kh", 0x17: "g", 0x18: "gh", 0x19: "n", 0x1A: "ch", 0x1B: "chh", 0x1C: "j", 0x1D: "jh", 0x1E: "n",
         0x1F: "t", 0x20: "th", 0x21: "d", 0x22: "dh", 0x23: "n", 0x24: "t", 0x25: "th", 0x26: "d", 0x27: "dh", 0x28: "n", 0x29: "n",
         0x2A: "p", 0x2B: "f", 0x2C: "b", 0x2D: "bh", 0x2E: "m", 0x2F: "y", 0x30: "r", 0x31: "r", 0x32: "l", 0x33: "l", 0x34: "l",
         0x35: "v", 0x36: "sh", 0x37: "sh", 0x38: "s", 0x39: "h", 0x5B: "j", 0x5C: "d", 0x5D: "dh", 0x5E: "f", 0x5F: "y"}
_OTHER = {0x01: "n", 0x02: "n", 0x03: "h", 0x3C: "", 0x3D: ""}  # chandrabindu, anusvara, visarga, nukta, avagraha
_VIRAMA = 0x4D


def _devanagari_offset(ch: str) -> tuple[int, int] | None:
    cp = ord(ch)
    for base in _BLOCKS:
        if base <= cp < base + 0x80:
            return base, cp - base
    return None


def _has_indic(text: str) -> bool:
    return any(0x0900 <= ord(c) < 0x0E00 for c in text)


def transliterate(text: str) -> str:
    """Latin approximation of Indic-script text (other characters pass through)."""
    out: list[str] = []
    chars = list(text)
    n = len(chars)
    i = 0
    while i < n:
        ch = chars[i]
        pos = _devanagari_offset(ch)
        if pos is None:
            out.append(ch)
            i += 1
            continue
        off = pos[1]
        if off in _CONS:
            out.append(_CONS[off])
            nxt = _devanagari_offset(chars[i + 1]) if i + 1 < n else None
            noff = nxt[1] if nxt else None
            if noff == _VIRAMA:
                i += 2
                continue
            if noff in _SIGNS:
                out.append(_SIGNS[noff])
                i += 2
                continue
            # inherent a, except at the end of a word where Hindi drops it
            following = chars[i + 1] if i + 1 < n else " "
            if _devanagari_offset(following) is not None and _devanagari_offset(following)[1] in (0x01, 0x02, 0x3C) and (
                    i + 2 >= n or _devanagari_offset(chars[i + 2]) is None):
                out.append("a")  # consonant + anusvara at the end: keep the vowel (e.g. "kam")
            elif _devanagari_offset(following) is not None or following.isalnum():
                out.append("a")
            i += 1
            continue
        if off in _INDEPENDENT:
            out.append(_INDEPENDENT[off])
        elif off in _OTHER:
            out.append(_OTHER[off])
        elif off in _SIGNS:
            out.append(_SIGNS[off])
        # digits, virama and anything else in the block are dropped
        i += 1
    return "".join(out)


_SPELL = (("ph", "f"), ("sh", "s"), ("ch", "c"), ("ck", "k"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("jh", "j"),
          ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("aa", "a"), ("ai", "ay"),
          ("ei", "ay"), ("mb", "nb"), ("mp", "np"))


@lru_cache(maxsize=60000)
def fold(text: str) -> str:
    """Lower-case, diacritic-free, transliterated, spelling-collapsed form used for matching. Words separated by one space."""
    if _has_indic(text):
        text = transliterate(text)
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    words = []
    for word in text.split():
        for a, b in _SPELL:
            word = word.replace(a, b)
        word = re.sub(r"(.)\1+", r"\1", word)
        words.append(word)
    return " ".join(words)


def tokens(text: str) -> list[str]:
    return fold(text).split()


def distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein (adjacent swap counts as one edit), stopping early once above `limit` (returns limit + 1)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] | None = None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _max_edits(n: int) -> int:
    return 2 if n >= 7 else 1 if n >= 4 else 0


def token_score(q: str, t: str) -> float:
    if q == t:
        return 1.0
    if len(q) >= 2 and t.startswith(q):
        return 0.92
    k = _max_edits(len(q))
    if k:
        if distance(q, t, k) <= k:
            return 0.75 if k == 1 else 0.65
        if len(t) > len(q) and distance(q, t[:len(q)], k) <= k:
            return 0.6
    if len(q) >= 3 and q in t:
        return 0.5
    return 0.0


def text_score(query_tokens: list[str], candidate: str) -> float:
    """0 when any query token finds nothing in the candidate; otherwise 0..1 (order of words is ignored)."""
    cand = tokens(candidate)
    if not query_tokens or not cand:
        return 0.0
    parts = []
    for q in query_tokens:
        best = max(token_score(q, t) for t in cand)
        if best == 0.0:
            return 0.0
        parts.append(best)
    base = sum(parts) / len(parts)
    coverage = min(len(query_tokens), len(cand)) / len(cand)  # shorter names beat long ones with the same hits
    score = base * (0.85 + 0.15 * coverage)
    if " ".join(query_tokens) == " ".join(cand):
        score = 1.0
    return round(min(score, 1.0), 4)


def rank(query: str, dishes: list[dict], frecency: dict[int, float] | None = None, limit: int = 20) -> list[dict]:
    """`dishes` = [{id, name, aliases[str], my_names[{id, name, use_count}]}]. Returns the matches, best first, each
    `{id, score, kind: my_name|name|alias, text, alias_id|None}`."""
    q = tokens(query)
    if not q:
        return []
    frecency = frecency or {}
    found = []
    for d in dishes:
        best: tuple[float, str, str, int | None, int] | None = None  # score, kind, text, alias id, own use count
        for a in d.get("my_names", []):
            s = text_score(q, a["name"])
            if s and (best is None or s > best[0] or (best[1] != "my_name" and s >= best[0] - 0.05)):
                best = (s, "my_name", a["name"], a["id"], a.get("use_count", 0))
        for kind, text, weight in [("name", d["name"], 1.0), *[("alias", x, ALIAS_WEIGHT) for x in d.get("aliases", [])]]:
            s = text_score(q, text) * weight
            if s and (best is None or s > best[0] + (0.05 if best[1] == "my_name" else 0)):
                best = (round(s, 4), kind, text, None, 0)
        if best is None or best[0] < MIN_SCORE:
            continue
        own_use = max([a.get("use_count", 0) for a in d.get("my_names", [])] or [0])
        boost = FRECENCY_BOOST * frecency.get(d["id"], 0.0) + USE_BOOST * min(own_use, 10) / 10
        found.append({"id": d["id"], "score": best[0], "kind": best[1], "text": best[2], "alias_id": best[3],
                      "_key": (0 if best[1] == "my_name" and best[0] >= OWN_FIRST_SCORE else 1, -(best[0] + boost), len(d["name"]), d["name"])})
    found.sort(key=lambda r: r["_key"])
    for r in found:
        del r["_key"]
    return found[:limit]
