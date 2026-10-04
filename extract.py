"""Pull deadlines/exams out of syllabus text.

Strategy: scan line by line; a line becomes an event if it contains a date AND a deadline keyword
(or any date with include_all=True). Years are inferred from the term start so "Jan 10" in a fall
term lands in the following calendar year. Pure functions, no I/O."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
WORD_DATE = re.compile(rf"\b{MONTH_RE}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?\b", re.I)
NUM_DATE = re.compile(r"(?<![\d/.])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])|\b(noon|midnight)\b", re.I)

KEYWORDS = {
    "exam": r"\b(exam|midterm|final|quiz|test)\b",
    "due": r"\b(due|deadline|homework|hw\s*\d*|assignment|project|paper|essay|lab report|lab\s*\d+|"
           r"problem set|pset|presentation|submit|submission|proposal|draft)\b",
}
SKIP = re.compile(r"\b(no class|holiday|office hours?)\b", re.I)


@dataclass(frozen=True)
class Event:
    title: str
    day: date
    start: time | None  # None -> all-day
    kind: str           # "exam" | "due" | "other"
    source_line: str = ""
    end: time | None = None


def _infer_year(month: int, day: int, term_start: date, explicit: int | None) -> date | None:
    if explicit is not None:
        explicit += 2000 if explicit < 100 else 0
        year = explicit
    else:
        year = term_start.year
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    # no explicit year: anything well before the term starts belongs to the following year
    if explicit is None and d < term_start - timedelta(days=45):
        try:
            d = date(year + 1, month, day)
        except ValueError:
            return None
    return d


def find_dates(line: str, term_start: date) -> list[tuple[date, tuple[int, int]]]:
    """Return [(date, (start, end) span)] for every date mention in the line."""
    found = []
    for m in WORD_DATE.finditer(line):
        mon = MONTHS[m.group(1)[:3].lower()]
        d = _infer_year(mon, int(m.group(2)), term_start, int(m.group(3)) if m.group(3) else None)
        if d:
            found.append((d, m.span()))
    for m in NUM_DATE.finditer(line):
        mon, day = int(m.group(1)), int(m.group(2))
        if not (1 <= mon <= 12 and 1 <= day <= 31):
            continue
        d = _infer_year(mon, day, term_start, int(m.group(3)) if m.group(3) else None)
        if d:
            found.append((d, m.span()))
    return found


def find_time(line: str) -> tuple[time, tuple[int, int]] | None:
    m = TIME_RE.search(line)
    if not m:
        return None
    if m.group(4):
        t = time(12, 0) if m.group(4).lower() == "noon" else time(23, 59)
        return t, m.span()
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if not (1 <= hour <= 12 and minute < 60):
        return None
    pm = m.group(3).lower().startswith("p")
    hour = (hour % 12) + (12 if pm else 0)
    return time(hour, minute), m.span()


FINAL_DELIVERABLE = re.compile(r"\bfinal\s+(project|paper|essay|presentation|draft|report|portfolio)\b", re.I)
ANNOUNCE_ONLY = re.compile(r"\b(released?|posted|assigned|handed out|announced)\b", re.I)
DEADLINE_WORDS = re.compile(r"\b(due|deadline|submit|submission)\b", re.I)


def _all_times(line: str):
    for m in TIME_RE.finditer(line):
        r = find_time(line[m.start():m.end()])
        if r:
            yield r[0], m.span()


def classify(line: str) -> str:
    if FINAL_DELIVERABLE.search(line):
        return "due"
    for kind, pat in KEYWORDS.items():
        if re.search(pat, line, re.I):
            if kind == "due" and ANNOUNCE_ONLY.search(line) and not DEADLINE_WORDS.search(line):
                return "other"   # "Homework 1 released" announces work, it isn't a deadline
            return kind
    return "other"


def keyword_span(line: str, kind: str) -> tuple[int, int] | None:
    pats = [r"\bdue\b|\bdeadline\b|\bsubmit\w*"] if kind == "due" else []
    pats += [FINAL_DELIVERABLE.pattern, KEYWORDS.get(kind, "")] if kind != "other" else []
    for pat in pats:
        if pat and (m := re.search(pat, line, re.I)):
            return m.span()
    return None


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, max(a[0], b[0]) - min(a[1], b[1]))


def clean_title(cell: str, term_start: date) -> str:
    """Strip dates/times/weekdays from the text cell that names the event."""
    spans = [sp for _, sp in find_dates(cell, term_start)]
    spans += [sp for _, sp in _all_times(cell)]
    chars = list(cell)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    t = "".join(chars)
    t = re.sub(r"[|•\u2022*_>]+", " ", t)
    t = re.sub(r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(day|sday|nesday|rsday|urday)?\b\.?", " ", t, flags=re.I)
    t = re.sub(r"\b(week\s*\d+)\b", " ", t, flags=re.I)
    t = re.sub(r"\b(by|at|on|before|from|until)\s*(?=[,;:.\s]|$)", " ", t, flags=re.I)   # dangling prepositions
    t = re.sub(r"[(\[]\s*[)\]]", " ", t)                                              # "( )" left by a stripped time
    t = re.sub(r"\s*[,;:\-–—]\s*(?=[,;:\-–—])", " ", t)                              # ", ," runs
    t = re.sub(r"\s+([,;:])", r"\1", t)
    t = re.sub(r"^[\s,;:.\-–—]+|[\s,;:.\-–—]+$", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t[:90] or "Deadline"


def extract_events(text: str, term_start: date, include_all: bool = False) -> list[Event]:
    events: dict[tuple, Event] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or SKIP.search(line):
            continue
        kind = classify(line)
        if kind == "other" and not include_all:
            continue
        dates = find_dates(line, term_start)
        if not dates:
            continue
        # Table rows like "Week 2 | Oct 1 | ... | HW1 due Oct 8" hold several dates: the one
        # closest to the deadline keyword is the deadline, the others are just schedule columns.
        kw = keyword_span(line, kind)
        cand = dates
        if kw and "|" in line:  # prefer a date inside the same table cell as the keyword
            lo = line.rfind("|", 0, kw[0]) + 1
            hi = line.find("|", kw[1]); hi = len(line) if hi == -1 else hi
            in_cell = [d for d in dates if lo <= d[1][0] and d[1][1] <= hi]
            cand = in_cell or dates
        day, span = (min(cand, key=lambda d: (_distance(d[1], kw), d[1][0])) if kw else cand[0])
        times = list(_all_times(line))
        tm = min(times, key=lambda t: _distance(t[1], span)) if times else None
        end = None
        if tm:  # "8:00 AM - 11:00 AM": second time directly after a dash/"to" is the end
            for (t1, s1), (t2, s2) in zip(times, times[1:]):
                if (t1, s1) == tm and re.fullmatch(r"\s*(-|–|—|to)\s*", line[s1[1]:s2[0]]) and t2 > t1:
                    end = t2
        cell = next((c for c in line.split("|") if kw and re.search(KEYWORDS.get(kind, "x") + "|" + DEADLINE_WORDS.pattern + "|" + FINAL_DELIVERABLE.pattern, c, re.I)), line) if "|" in line else line
        ev = Event(clean_title(cell, term_start), day, tm[0] if tm else None, kind, line, end)
        events.setdefault((ev.title.lower(), ev.day, ev.start), ev)
    return sorted(events.values(), key=lambda e: (e.day, e.start or time(0, 0), e.title))
