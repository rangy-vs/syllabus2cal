"""python -m syllabus2cal syllabus.txt|.pdf --course "CSE 30" --term-start 2026-09-24 -o cse30.ics"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .extract import extract_events
from .ics import build_ics


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="syllabus2cal", description="Turn a syllabus into calendar events (.ics)")
    ap.add_argument("syllabus", help=".txt or .pdf")
    ap.add_argument("--course", default="", help='prefix for event titles, e.g. "CSE 30"')
    ap.add_argument("--term-start", required=True, type=date.fromisoformat, help="YYYY-MM-DD, used to infer years")
    ap.add_argument("-o", "--out", default=None, help="output .ics (default: <syllabus>.ics)")
    ap.add_argument("--remind-days", type=int, default=1, help="alarm N days before (0 = none)")
    ap.add_argument("--all", action="store_true", help="include every dated line, not just deadlines/exams")
    ap.add_argument("--preview", action="store_true", help="print events and exit without writing a file")
    a = ap.parse_args(argv)

    text = read_text(Path(a.syllabus))
    events = extract_events(text, a.term_start, include_all=a.all)
    if not events:
        print("No dated deadlines found. Try --all, or check that the PDF has selectable text.", file=sys.stderr)
        return 1
    for e in events:
        when = f"{e.day:%a %b %d}" + (f" {e.start:%I:%M %p}" + (f"-{e.end:%I:%M %p}" if e.end else "") if e.start else " (all day)")
        print(f"  [{e.kind:<4}] {when:<22} {e.title}")
    if a.preview:
        return 0
    out = Path(a.out) if a.out else Path(a.syllabus).with_suffix(".ics")
    out.write_text(build_ics(events, a.course, a.remind_days or None), newline="")
    print(f"\nWrote {len(events)} events -> {out}  (import via Google Calendar > Settings > Import)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
