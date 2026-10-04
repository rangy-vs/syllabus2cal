from datetime import date, datetime, time
from pathlib import Path

import pytest

from syllabus2cal.extract import classify, extract_events, find_dates, find_time
from syllabus2cal.ics import build_ics, escape, fold

TERM = date(2026, 9, 24)


# ---- dates ----
@pytest.mark.parametrize("text,expected", [
    ("due Oct 8", date(2026, 10, 8)),
    ("due October 8th, 2026", date(2026, 10, 8)),
    ("due 10/22", date(2026, 10, 22)),
    ("due 10/22/26", date(2026, 10, 22)),
    ("due Sept. 30", date(2026, 9, 30)),
    ("due Jan 6", date(2027, 1, 6)),        # rolls into next calendar year
    ("due 1/5", date(2027, 1, 5)),
])
def test_date_parsing_and_year_inference(text, expected):
    assert find_dates(text, TERM)[0][0] == expected


def test_invalid_dates_rejected():
    assert find_dates("score 13/40", TERM) == []          # month 13
    assert find_dates("due Feb 30", TERM) == []           # impossible date
    assert find_dates("ratio 3/4 of grade", TERM)[0][0].month == 3  # parseable but only matters with a keyword


@pytest.mark.parametrize("text,expected", [
    ("by 11:59 PM", time(23, 59)), ("at 5pm", time(17, 0)), ("8:00 AM", time(8, 0)),
    ("12:00 am", time(0, 0)), ("12 pm", time(12, 0)), ("noon", time(12, 0)),
])
def test_time_parsing(text, expected):
    assert find_time(text)[0] == expected


def test_no_false_time_from_plain_numbers():
    assert find_time("Homework 12 due Oct 3") is None


def test_classify():
    assert classify("Midterm exam") == "exam"
    assert classify("Homework 3 due") == "due"
    assert classify("Introduction to arrays") == "other"


# ---- extraction on the demo syllabus ----
@pytest.fixture
def demo_events():
    text = Path("examples/cse_demo_syllabus.txt").read_text()
    return extract_events(text, TERM)


def titles(evs): return [e.title for e in evs]


def test_demo_extracts_expected_deadlines(demo_events):
    by_day = {(e.day, e.start): e for e in demo_events}
    assert (date(2026, 10, 8), time(23, 59)) in by_day                    # HW1 due
    assert (date(2026, 10, 11), time(14, 0)) in by_day                    # quiz
    assert (date(2026, 10, 22), time(17, 0)) in by_day                    # proposal (numeric date)
    assert (date(2026, 10, 31), time(18, 30)) in by_day                   # midterm
    assert (date(2026, 12, 2), time(12, 0)) in by_day                     # essay draft, "noon"
    assert (date(2026, 12, 12), time(8, 0)) in by_day                     # final exam


def test_demo_skips_noise(demo_events):
    joined = " ".join(titles(demo_events)).lower()
    assert "thanksgiving" not in joined and "office hours" not in joined      # SKIP lines
    assert date(2026, 11, 28) not in {e.day for e in demo_events}
    assert date(2027, 1, 5) not in {e.day for e in demo_events}              # "Spring quarter starts" has no keyword


def test_demo_kinds_and_sorted(demo_events):
    assert [e.day for e in demo_events] == sorted(e.day for e in demo_events)
    kinds = {e.title: e.kind for e in demo_events}
    assert any(k == "exam" for k in kinds.values()) and any(k == "due" for k in kinds.values())


def test_titles_are_clean(demo_events):
    for e in demo_events:
        assert "|" not in e.title and not e.title.endswith(("-", ":", ","))
        assert len(e.title) <= 90


def test_dedupes_repeated_lines():
    text = "Midterm Oct 31 6pm\nMidterm Oct 31 6pm\n"
    assert len(extract_events(text, TERM)) == 1


def test_include_all_flag():
    text = "Guest lecture Oct 5\n"
    assert extract_events(text, TERM) == []
    assert len(extract_events(text, TERM, include_all=True)) == 1


# ---- ICS correctness ----
NOW = datetime(2026, 9, 1, 12, 0, 0)


def ics(text, **kw):
    return build_ics(extract_events(text, TERM), course="CSE 999", now=NOW, **kw)


def test_ics_structure_and_crlf():
    out = ics("Midterm exam Oct 31 at 6:30 PM")
    assert out.startswith("BEGIN:VCALENDAR\r\n") and out.endswith("END:VCALENDAR\r\n")
    assert "\n" not in out.replace("\r\n", "")                              # no bare LF
    assert "DTSTART:20261031T183000" in out and "DTEND:20261031T193000" in out
    assert "SUMMARY:CSE 999: Midterm exam" in out
    assert out.count("BEGIN:VEVENT") == out.count("END:VEVENT") == 1


def test_all_day_event_has_exclusive_end():
    out = ics("Project proposal due Oct 22")
    assert "DTSTART;VALUE=DATE:20261022" in out and "DTEND;VALUE=DATE:20261023" in out


def test_alarm_toggle():
    assert "TRIGGER:-P2D" in ics("Quiz Oct 5 9am", remind_days=2)
    assert "VALARM" not in ics("Quiz Oct 5 9am", remind_days=None)


def test_uids_stable_and_unique():
    a = ics("Quiz Oct 5 9am\nMidterm Oct 31 6pm")
    b = ics("Quiz Oct 5 9am\nMidterm Oct 31 6pm")
    uids = [l for l in a.split("\r\n") if l.startswith("UID:")]
    assert len(set(uids)) == 2
    assert uids == [l for l in b.split("\r\n") if l.startswith("UID:")]


def test_escape_special_characters():
    assert escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"


def test_fold_respects_75_octets_and_utf8():
    long = "SUMMARY:" + "é" * 80                                           # 2-byte chars
    for part in fold(long).split("\r\n"):
        assert len(part.encode()) <= 75
    assert fold(long).replace("\r\n ", "") == long                           # unfolding round-trips


def test_cli_preview_and_write(tmp_path):
    from syllabus2cal.__main__ import main
    out = tmp_path / "x.ics"
    assert main(["examples/cse_demo_syllabus.txt", "--course", "CSE 999", "--term-start", "2026-09-24", "-o", str(out)]) == 0
    assert out.read_bytes().startswith(b"BEGIN:VCALENDAR\r\n")
    assert main(["examples/cse_demo_syllabus.txt", "--term-start", "2026-09-24", "--preview"]) == 0


# ---- regressions for bugs found while running the demo ----
def test_table_row_uses_deadline_date_not_schedule_column(demo_events):
    hw = next(e for e in demo_events if e.title.startswith("Homework 1"))
    assert hw.day == date(2026, 10, 8)                       # not "Oct 1", the Week-2 column
    demo = next(e for e in demo_events if e.title == "Final project demo")
    assert demo.day == date(2026, 11, 14)                    # date inside the keyword's own cell


def test_announcement_is_not_a_deadline(demo_events):
    assert not any("released" in e.title.lower() for e in demo_events)


def test_final_project_is_a_deliverable_not_an_exam(demo_events):
    assert next(e for e in demo_events if e.title == "Final project demo").kind == "due"
    assert next(e for e in demo_events if e.title.startswith("Final exam")).kind == "exam"


def test_time_range_sets_end_and_clean_title(demo_events):
    fin = next(e for e in demo_events if e.title == "Final exam")
    assert (fin.start, fin.end) == (time(8, 0), time(11, 0))
    out = build_ics([fin], now=NOW)
    assert "DTSTART:20261212T080000" in out and "DTEND:20261212T110000" in out


def test_no_leftover_brackets_in_titles(demo_events):
    assert all("( )" not in e.title and "()" not in e.title for e in demo_events)


def test_output_parses_with_independent_icalendar_library():
    """Cross-check our hand-written RFC 5545 writer against a third-party parser."""
    from datetime import timedelta
    from icalendar import Calendar
    evs = extract_events(Path("examples/cse_demo_syllabus.txt").read_text(), TERM)
    cal = Calendar.from_ical(build_ics(evs, "CSE, 999; \"quoted\"", now=NOW))      # nasty punctuation on purpose
    parsed = list(cal.walk("VEVENT"))
    assert len(parsed) == len(evs) == 7
    assert str(parsed[0]["SUMMARY"]).startswith('CSE, 999; "quoted": Homework 1')    # escaping round-trips
    assert parsed[0]["DTSTART"].dt == datetime(2026, 10, 8, 23, 59)
    allday = next(e for e in parsed if e["SUMMARY"].endswith("Final project demo"))
    assert allday["DTEND"].dt - allday["DTSTART"].dt == timedelta(days=1)            # exclusive end
    assert next(iter(parsed[0].walk("VALARM")))["TRIGGER"].dt == timedelta(days=-1)
