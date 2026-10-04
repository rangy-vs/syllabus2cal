# syllabus2cal

![ci](../../actions/workflows/ci.yml/badge.svg)

Turn a course syllabus (text or PDF) into calendar events you can import into Google/Apple/Outlook Calendar: every exam, quiz and assignment deadline, with reminders.

```bash
pip install -r requirements.txt
python -m syllabus2cal examples/cse_demo_syllabus.txt --course "CSE 999" --term-start 2026-09-24 --preview
#   [due ] Thu Oct 08 11:59 PM    Homework 1 due
#   [exam] Sun Oct 11 02:00 PM    Quiz 1 in lecture
#   [due ] Thu Oct 22 05:00 PM    Project proposal due
#   [exam] Sat Oct 31 06:30 PM    Midterm exam, Room 101
#   [due ] Sat Nov 14 (all day)   Final project demo
#   [due ] Wed Dec 02 12:00 PM    Essay draft due
#   [exam] Sat Dec 12 08:00 AM-11:00 AM Final exam

python -m syllabus2cal syllabus.pdf --course "CSE 30" --term-start 2026-09-24 -o cse30.ics   # write the file
```
Import the `.ics` via Google Calendar → Settings → Import & export.

## How it works
- **Extraction (rule-based, deterministic, fully offline):** a line becomes an event if it has a date *and* a deadline/exam keyword. Handles `Oct 8`, `October 8th, 2026`, `10/22`, `10/22/26`, times like `11:59 PM`, `noon`, and ranges like `8:00 AM - 11:00 AM`.
- **Year inference:** given `--term-start`, "Jan 6" in a fall term lands in the *next* calendar year.
- **Table rows:** in `Week 2 | Oct 1 | ... | HW1 due Oct 8` the deadline is the date nearest the keyword (in the same cell), not the schedule column.
- **Filters:** "released/posted" lines aren't deadlines; "final project" is a deliverable, not an exam; "no class"/"holiday"/"office hours" lines are skipped.
- **ICS writer (hand-written, RFC 5545):** CRLF endings, text escaping, 75-octet UTF-8-safe line folding, all-day events with exclusive end dates, stable UIDs (re-importing updates instead of duplicating), optional reminders. Output is cross-checked in tests with the third-party `icalendar` parser.

## Limits (read before trusting a real syllabus)
- Tested on a **fictional** syllabus and 35 unit tests, not on a corpus of real syllabi: always run `--preview` first and compare to the original.
- Relative dates ("Week 5 Friday") and scanned/image PDFs aren't supported; the tool says so when it finds nothing.
- Times are written as *floating* local time, so they show at the same wall-clock time in your calendar's timezone.
- Next steps: relative-week resolution from the term start, an optional LLM pass for messy layouts, and a regression corpus of anonymised real syllabi.
