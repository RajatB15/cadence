"""Research feed: recent open-access papers on the reading topics, from Europe PMC.

No account, no key and no LLM. Each topic runs one public search (title/abstract phrases, open access, English, the
last 120 days, and only publication types we can label honestly: systematic reviews and meta-analyses, randomized
trials, guidelines). Only those search terms leave this machine, never anything about you. Results are filtered
(animal and in-vitro work, retractions, clinical, youth and older-adult populations, a topic keyword in the text) and ranked guidelines first, then reviews, then single trials,
turned into a title, journal, date, evidence label (from the publication type, not a quality judgement) and the
first sentences of the abstract, with a link to the paper. We store the snippet and link, never the full text.
Nothing here is reviewed by us: the page says so. Search: https://europepmc.org/RestfulWebService
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from cadence_app.models import AppSetting, ReadingFeedItem, ReadingItem

log = logging.getLogger(__name__)

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ENABLED_KEY, STATE_KEY = "reading_feed_enabled", "reading_feed_state"
REFRESH_EVERY = timedelta(days=3)
WINDOW_DAYS, KEEP_DAYS, PER_TOPIC, PAGE_SIZE = 120, 150, 8, 60
SNIPPET_CHARS = 420

_t = lambda *terms, field="TITLE_ABS": "(" + " OR ".join(f'{field}:"{x}"' for x in terms) + ")"  # noqa: E731
TOPIC_QUERIES = {
    "nutrition": _t("sports nutrition", "protein intake", "carbohydrate intake", "creatine", "caffeine", "hydration", "energy availability")
    + " AND " + _t("athletes", "endurance", "resistance training", "exercise performance", "runners"),
    "sports-science": _t("VO2max", "running economy", "heart rate variability", "training load", "critical speed", "lactate threshold", "durability")
    + " AND " + _t("athletes", "runners", "endurance", "cyclists"),
    "training": _t("endurance training", "high-intensity interval", "resistance training", "periodization", "polarized training", "running injury", "tapering")
    + " AND " + _t("performance", "athletes", "runners", "injury"),
    "recovery": _t("sleep", "post-exercise recovery", "recovery strategies", "heart rate variability")
    + " AND " + _t("athletes", "exercise performance", "training"),
    "wellbeing": _t("physical activity", "exercise", "daily steps", "step count", "walking", field="TITLE")
    + " AND " + _t("depression", "anxiety", "mental health", "well-being", "wellbeing", "mortality", "sleep quality"),
    "pushing-hard": _t("overtraining", "overreaching", "relative energy deficiency", "perceived exertion", "mental fatigue", "perception of effort", "pacing")
    + " AND " + _t("athletes", "exercise performance", "endurance"),
}
# Words a result must contain (title or abstract) to be kept for a topic.
TOPIC_WORDS = {
    "nutrition": r"protein|carbohydrate|caffeine|creatine|hydration|nutrition|energy availability|fuel",
    "sports-science": r"vo2|running economy|variability|training load|workload|critical (speed|power)|lactate|threshold|durability",
    "training": r"training|interval|periodi[sz]|taper|injur|strength|running",
    "recovery": r"sleep|recovery|variability",
    "wellbeing": r"mental|depress|anxi|well-being|wellbeing|mortality|steps|walking|physical activity",
    "pushing-hard": r"overtrain|overreach|energy deficiency|exertion|mental fatigue|effort|pacing",
}
EXCLUDE = re.compile(
    r"\b(mice|mouse|rats?|murine|rodents?|zebrafish|in vitro|cell lines?|cancer|tumou?rs?|stroke|dementia|parkinson\w*|multiple sclerosis|"
    r"cystic fibrosis|copd|heart failure|pregnan\w*|schizophreni\w*|ptsd|post-traumatic|refugees?|spinal cord|dialysis|diabet\w*|"
    r"cerebral palsy|hemodialysis|children with|preterm|neonat\w*|osteoarthritis|fibromyalgia|older adults|elderly|middle-aged|"
    r"youth|adolescents?|children|patients?|alcohol use|smoking|rehabilitation|primary care|high school|built environments?|telerehabilitation|postpartum|postmenopausal|perimenopausal|college students|university students|nurses)\b",
    re.I)
EVIDENCE_BY_TYPE = (  # first match wins, strongest label first
    ("Practice Guideline", "guideline"), ("Guideline", "guideline"), ("Consensus Development Conference", "guideline"),
    ("Meta-Analysis", "review"), ("Systematic Review", "review"), ("Randomized Controlled Trial", "trial"),
)
RANK = {"guideline": 0, "review": 1, "trial": 2}
BAD_TYPES = ("Retracted Publication", "Retraction of Publication", "Comment", "Editorial", "Letter", "Published Erratum", "Preprint")
LICENCES = {"cc by": "CC BY", "cc by-nc": "CC BY-NC", "cc by-sa": "CC BY-SA", "cc by-nc-nd": "CC BY-NC-ND", "cc by-nd": "CC BY-ND",
            "cc by-nc-sa": "CC BY-NC-SA", "cc0": "CC0"}


def enabled(session: Session) -> bool:
    row = session.get(AppSetting, ENABLED_KEY)
    return row is None or row.value == "1"


def set_enabled(session: Session, on: bool) -> None:
    row = session.get(AppSetting, ENABLED_KEY)
    if row:
        row.value = "1" if on else "0"
    else:
        session.add(AppSetting(key=ENABLED_KEY, value="1" if on else "0"))
    session.commit()


def state(session: Session) -> dict:
    row = session.get(AppSetting, STATE_KEY)
    return json.loads(row.value) if row else {}


def due(session: Session, now: datetime) -> bool:
    if not enabled(session):
        return False
    last = state(session).get("fetched_at")
    return last is None or now - datetime.fromisoformat(last) >= REFRESH_EVERY


def query_for(topic: str, today: date) -> str:
    since = today - timedelta(days=WINDOW_DAYS)
    types = " OR ".join(f'PUB_TYPE:"{t}"' for t in ("Systematic Review", "Meta-Analysis", "Randomized Controlled Trial", "Practice Guideline"))
    return (f"({TOPIC_QUERIES[topic]}) AND OPEN_ACCESS:y AND HAS_ABSTRACT:y AND LANG:eng AND ({types}) "
            f"AND FIRST_PDATE:[{since.isoformat()} TO {today.isoformat()}]")


def _plain(text: str) -> str:
    text = re.sub(r"</?(sup|sub|i|b|em|strong|italic|bold)>", "", text or "")  # inline markup stays attached: NAD+, VO2max
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\b(Background|Objectives?|Aims?|Introduction|Purpose|Methods?|Results?|Conclusions?|Context):\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def snippet(abstract: str) -> str:
    """The first sentences of the abstract, up to about SNIPPET_CHARS, ending on a sentence where possible."""
    text = _plain(abstract)
    if len(text) <= SNIPPET_CHARS:
        return text
    cut = text[:SNIPPET_CHARS]
    end = max(cut.rfind(". "), cut.rfind("? "))
    return (cut[: end + 1] if end > 150 else cut.rsplit(" ", 1)[0] + "…").strip()


def parse(result: dict, topic: str, now: datetime) -> dict | None:
    """One Europe PMC result as a feed row, or None when it should not be shown."""
    types = (result.get("pubTypeList") or {}).get("pubType") or []
    if any(t in BAD_TYPES for t in types):
        return None
    evidence = next((label for t, label in EVIDENCE_BY_TYPE if t in types), None)
    title = _plain(result.get("title") or "").rstrip(".")
    abstract = _plain(result.get("abstractText") or "")
    rid, source = result.get("id"), result.get("source")
    published = result.get("firstPublicationDate")
    if not (evidence and title and len(abstract) >= 200 and rid and source and published):
        return None
    text = f"{title} {abstract}"
    if EXCLUDE.search(text) or not re.search(TOPIC_WORDS[topic], text, re.I):
        return None
    doi = result.get("doi")
    url = f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/{source}/{rid}"
    return {"id": f"epmc:{source}:{rid}"[:80], "topic": topic, "title": title, "journal": (result.get("journalTitle") or "")[:200],
            "published": date.fromisoformat(published[:10]), "evidence": evidence, "snippet": snippet(abstract), "url": url,
            "licence": LICENCES.get(str(result.get("license") or "").lower(), "Open access"), "fetched_at": now}


def refresh(factory: sessionmaker, today: date, now: datetime, http: httpx.Client | None = None, *, force: bool = False) -> int:
    """Fetch every topic and replace the feed. Returns how many items were stored. A failed topic keeps its old items."""
    with factory() as session:
        if not enabled(session) or not (force or due(session, now)):
            return 0
    own = http is None
    http = http or httpx.Client(timeout=20, headers={"User-Agent": "Cadence-local/1.0 (personal reading feed)"})
    rows: dict[str, dict] = {}
    failed: list[str] = []
    try:
        for topic in TOPIC_QUERIES:
            try:
                r = http.get(API, params={"query": query_for(topic, today), "format": "json", "resultType": "core",
                                          "pageSize": PAGE_SIZE, "sort": "P_PDATE_D desc"})
                r.raise_for_status()
                results = r.json()["resultList"]["result"]
            except (httpx.HTTPError, ValueError, KeyError) as e:
                log.warning("Reading feed: %s failed (%s)", topic, type(e).__name__)
                failed.append(topic)
                continue
            kept = [row for res in results if (row := parse(res, topic, now)) and row["id"] not in rows]
            kept.sort(key=lambda r: (RANK[r["evidence"]], -r["published"].toordinal()))  # guidelines, then reviews, then single trials
            for row in kept[:PER_TOPIC]:
                rows[row["id"]] = row
    finally:
        if own:
            http.close()
    with factory() as session:
        touched = [t for t in TOPIC_QUERIES if t not in failed]
        if touched:
            marked = set(session.scalars(select(ReadingItem.card_id).where(ReadingItem.status.in_(("saved", "read", "skipped")))))
            session.execute(delete(ReadingFeedItem).where(ReadingFeedItem.topic.in_(touched), ReadingFeedItem.id.not_in(marked)))
            for row in rows.values():
                session.merge(ReadingFeedItem(**row))
            session.execute(delete(ReadingFeedItem).where(ReadingFeedItem.published < today - timedelta(days=KEEP_DAYS),
                                                          ReadingFeedItem.id.not_in(marked)))
        # A fully failed run isn't recorded, so the next page view tries again.
        if len(failed) < len(TOPIC_QUERIES):
            blob = json.dumps({"fetched_at": now.isoformat(), "failed": failed})
            row = session.get(AppSetting, STATE_KEY)
            if row:
                row.value = blob
            else:
                session.add(AppSetting(key=STATE_KEY, value=blob))
        session.commit()
    return len(rows)


class FeedWorker:
    """Runs `refresh` on a background thread so opening the page never waits on the network."""

    def __init__(self, run):
        self.run, self._thread, self._lock = run, None, threading.Lock()

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def kick(self) -> bool:
        with self._lock:
            if self.busy:
                return False
            self._thread = threading.Thread(target=self._go, daemon=True, name="cadence-reading-feed")
            self._thread.start()
            return True

    def _go(self) -> None:
        try:
            self.run()
        except Exception:  # pylint: disable=broad-exception-caught  # background job boundary
            log.exception("Reading feed refresh failed")
