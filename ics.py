"""Minimal RFC 5545 iCalendar writer (events + display alarms).

Details that commonly break hand-rolled .ics files, handled here:
  * CRLF line endings           * TEXT escaping of  \\ ; , and newlines
  * line folding at 75 octets   * all-day events use VALUE=DATE with an EXCLUSIVE DTEND
  * stable UIDs so re-importing updates events instead of duplicating them
Times are written as floating local time, so they appear at the same wall-clock time in whatever
timezone your calendar is set to."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from .extract import Event


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
                .replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line: str) -> str:
    """Fold to <=75 octets per line (continuation lines start with one space), never splitting a
    multi-byte UTF-8 character."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur, cur_len = [], "", 0
    limit = 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if cur_len + n > limit:
            out.append(cur)
            cur, cur_len, limit = " ", 1, 75
        cur += ch
        cur_len += n
    out.append(cur)
    return "\r\n".join(out)


def uid_for(ev: Event, course: str) -> str:
    key = f"{course}|{ev.title}|{ev.day.isoformat()}|{ev.start}".lower()
    return hashlib.sha1(key.encode()).hexdigest()[:16] + "@syllabus2cal"


def build_ics(events: list[Event], course: str = "", remind_days: int | None = 1,
              now: datetime | None = None, duration_min: int = 60) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//syllabus2cal//EN", "CALSCALE:GREGORIAN"]
    for ev in events:
        title = f"{course}: {ev.title}" if course else ev.title
        lines += ["BEGIN:VEVENT", f"UID:{uid_for(ev, course)}", f"DTSTAMP:{stamp}",
                  f"SUMMARY:{escape(title)}"]
        if ev.start is None:
            lines += [f"DTSTART;VALUE=DATE:{ev.day:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{ev.day + timedelta(days=1):%Y%m%d}"]
        else:
            start = datetime.combine(ev.day, ev.start)
            end = datetime.combine(ev.day, ev.end) if ev.end else start + timedelta(minutes=duration_min)
            lines += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
        lines.append(f"CATEGORIES:{ev.kind.upper()}")
        lines.append(f"DESCRIPTION:{escape('From syllabus: ' + ev.source_line)}")
        if remind_days:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape(title)}",
                      f"TRIGGER:-P{remind_days}D", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"
