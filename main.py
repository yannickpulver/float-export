#!/usr/bin/env python3
"""Fetch Float.com department schedule and show planned/unplanned hours."""

import argparse
import os
import sys
from datetime import date, timedelta
from typing import Any

from pathlib import Path

import requests
from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "float-export"
CONFIG_FILE = CONFIG_DIR / ".env"

# Load from config dir, then cwd .env, then environment
if CONFIG_FILE.exists():
    load_dotenv(CONFIG_FILE)
else:
    load_dotenv()

BASE_URL = "https://api.float.com/v3"
TOKEN = os.getenv("FLOAT_API_TOKEN", "")
DEPARTMENT = os.getenv("FLOAT_DEPARTMENT", "")
EXCLUDE_NAMES = [
    s.strip().lower()
    for s in os.getenv("FLOAT_EXCLUDE_NAMES", "").split(",")
    if s.strip()
]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "FloatExport Script (float-export@local)",
    "Content-Type": "application/json",
}


def api_get(endpoint: str, params: dict[str, Any] | None = None) -> list[dict]:
    """GET from Float API with pagination."""
    results: list[dict] = []
    page = 1
    while True:
        p = {**(params or {}), "page": page, "per-page": 200}
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=p)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        results.extend(data)
        if len(data) < 200:
            break
        page += 1
    return results


def is_plannable(person: dict, period_start: date, period_end: date) -> bool:
    """Check if person is plannable during the given period."""
    start = date.fromisoformat(person["start_date"]) if person.get("start_date") else None
    end = date.fromisoformat(person["end_date"]) if person.get("end_date") else None
    if start and start > period_end:
        return False
    if end and end < period_start:
        return False
    return True


def get_people(department: str) -> list[dict]:
    """Get all active people in a department."""
    people = api_get("people")
    return [
        p for p in people
        if p.get("active") == 1
        and (p.get("department") or {}).get("name", "").lower() == department.lower()
        and not any(ex in p.get("name", "").lower() for ex in EXCLUDE_NAMES)
    ]


def get_projects() -> dict[int, str]:
    """Get project ID -> name mapping."""
    projects = api_get("projects")
    return {p["project_id"]: p.get("name", "Unknown") for p in projects}


def expand_recurring_tasks(tasks: list[dict], query_start: date, query_end: date) -> list[dict]:
    """Expand recurring tasks into individual weekly instances."""
    expanded: list[dict] = []
    for task in tasks:
        repeat_state = task.get("repeat_state", 0)
        if repeat_state == 0:
            expanded.append(task)
            continue

        t_start = date.fromisoformat(task["start_date"])
        t_end = date.fromisoformat(task["end_date"])
        duration = t_end - t_start
        repeat_end = date.fromisoformat(task["repeat_end_date"]) if task.get("repeat_end_date") else query_end
        interval = timedelta(weeks=repeat_state)

        occurrence_start = t_start
        while occurrence_start <= min(repeat_end, query_end):
            occurrence_end = occurrence_start + duration
            if occurrence_end >= query_start:
                expanded.append({
                    **task,
                    "start_date": str(occurrence_start),
                    "end_date": str(occurrence_end),
                    "repeat_state": 0,
                })
            occurrence_start += interval

    return expanded


def normalize_tasks(raw: list[dict], person_id: int) -> list[dict]:
    """Ensure each task has people_id set (Float uses people_ids array for multi-assignments)."""
    results: list[dict] = []
    for task in raw:
        if task.get("people_id") == person_id:
            results.append(task)
        elif person_id in (task.get("people_ids") or []):
            results.append({**task, "people_id": person_id})
    return results


def get_tasks_for_people(people: list[dict], start: date, end: date) -> list[dict]:
    """Get all tasks per person, with recurring tasks expanded.

    Fetches per-person from 52 weeks before start to catch recurring tasks
    whose base occurrence is older but still repeat into the query range.
    """
    fetch_start = start - timedelta(weeks=52)
    all_tasks: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for person in people:
        pid = person["people_id"]
        raw = api_get("tasks", {
            "people_id": pid,
            "start_date": str(fetch_start),
            "end_date": str(end),
        })
        for task in normalize_tasks(raw, pid):
            key = (task["task_id"], pid)
            if key not in seen:
                seen.add(key)
                all_tasks.append(task)
    return expand_recurring_tasks(all_tasks, start, end)


def get_timeoffs(start: date, end: date) -> list[dict]:
    """Get all time-offs in date range."""
    return api_get("timeoffs", {"start_date": str(start), "end_date": str(end)})


def working_days_in_range(
    start: date, end: date, work_days_hours: list[float]
) -> list[date]:
    """Return list of working days in range based on person's schedule."""
    days: list[date] = []
    d = start
    while d <= end:
        dow = d.isoweekday() % 7  # 0=Sun, 1=Mon, ..., 6=Sat
        if work_days_hours[dow] > 0:
            days.append(d)
        d += timedelta(days=1)
    return days


def hours_in_period(
    task: dict, period_start: date, period_end: date, work_days_hours: list[float]
) -> float:
    """Calculate task hours that fall within a period."""
    t_start = date.fromisoformat(task["start_date"])
    t_end = date.fromisoformat(task["end_date"])
    overlap_start = max(t_start, period_start)
    overlap_end = min(t_end, period_end)
    if overlap_start > overlap_end:
        return 0.0
    days = working_days_in_range(overlap_start, overlap_end, work_days_hours)
    hours_per_day = float(task.get("hours", 0))
    return hours_per_day * len(days)


def capacity_hours(
    period_start: date, period_end: date, work_days_hours: list[float]
) -> float:
    """Total capacity hours for a person in a period."""
    total = 0.0
    d = period_start
    while d <= period_end:
        dow = d.isoweekday() % 7
        total += work_days_hours[dow]
        d += timedelta(days=1)
    return total


def timeoff_hours_for_person(
    person_id: int,
    timeoffs: list[dict],
    period_start: date,
    period_end: date,
    work_days_hours: list[float],
) -> float:
    """Calculate time-off hours for a person in a period."""
    total = 0.0
    for to in timeoffs:
        if to.get("people_id") != person_id:
            continue
        to_start = date.fromisoformat(to["start_date"])
        to_end = date.fromisoformat(to["end_date"])
        overlap_start = max(to_start, period_start)
        overlap_end = min(to_end, period_end)
        if overlap_start > overlap_end:
            continue
        hours = float(to.get("hours", 0))
        if hours > 0:
            days = working_days_in_range(overlap_start, overlap_end, work_days_hours)
            total += hours * len(days)
        else:
            # Full day time-off
            d = overlap_start
            while d <= overlap_end:
                dow = d.isoweekday() % 7
                total += work_days_hours[dow]
                d += timedelta(days=1)
    return total


def week_range(ref: date, offset_weeks: int = 0) -> tuple[date, date]:
    """Get Monday-Friday of a week offset from ref date's week."""
    monday = ref - timedelta(days=ref.weekday()) + timedelta(weeks=offset_weeks)
    friday = monday + timedelta(days=4)
    return monday, friday


W = 58

# ANSI color codes
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"


def status_dot(planned: float, available: float) -> str:
    if available <= 0:
        return f"{RED}●{RESET}"
    pct = planned / available
    if pct >= 0.8:
        return f"{GREEN}●{RESET}"
    if pct >= 0.5:
        return f"{YELLOW}●{RESET}"
    return f"{RED}●{RESET}"


def fmt(h: float) -> str:
    return f"{h:5.1f}h"


DEFAULT_WDH = [0, 8, 8, 8, 8, 8, 0]


def get_work_hours(person: dict, ref_date: date) -> list[float]:
    """Get work_days_hours for a person at a given date, using history if available."""
    history = person.get("work_days_hours_history")
    if not history:
        return person.get("work_days_hours") or DEFAULT_WDH
    # History keys are date strings; pick the latest one <= ref_date
    applicable = [
        (date.fromisoformat(d), hrs)
        for d, hrs in history.items()
        if date.fromisoformat(d) <= ref_date
    ]
    if not applicable:
        return person.get("work_days_hours") or DEFAULT_WDH
    applicable.sort(key=lambda x: x[0])
    return applicable[-1][1]


def calc_person_period(
    person: dict,
    period_start: date,
    period_end: date,
    tasks: list[dict],
    timeoffs: list[dict],
    projects: dict[int, str],
) -> tuple[float, float, float, float, dict[str, float]]:
    """Return (capacity, timeoff, planned, free, task_hours) for a person in a period."""
    pid = person["people_id"]
    wdh = get_work_hours(person, period_start)
    cap = capacity_hours(period_start, period_end, wdh)
    toff = timeoff_hours_for_person(pid, timeoffs, period_start, period_end, wdh)
    available = cap - toff

    person_tasks = [t for t in tasks if t["people_id"] == pid]
    planned = 0.0
    task_map: dict[str, float] = {}

    for t in person_tasks:
        h = hours_in_period(t, period_start, period_end, wdh)
        if h <= 0:
            continue
        planned += h
        proj_name = projects.get(t.get("project_id", 0), "?")
        task_name = t.get("name") or ""
        label_str = f"{proj_name}: {task_name}" if task_name and task_name != proj_name else proj_name
        task_map[label_str] = task_map.get(label_str, 0.0) + h

    free = max(0.0, available - planned)
    return cap, toff, planned, free, task_map


def print_header(label: str, period_start: date, period_end: date) -> None:
    d1 = period_start.strftime("%b %d")
    d2 = period_end.strftime("%b %d")
    print()
    print(f"  ┌{'─' * W}┐")
    print(f"  │ {label:^{W - 2}} │")
    print(f"  │ {f'{d1} – {d2}':^{W - 2}} │")
    print(f"  └{'─' * W}┘")


def print_period(
    label: str,
    period_start: date,
    period_end: date,
    people: list[dict],
    tasks: list[dict],
    timeoffs: list[dict],
    projects: dict[int, str],
    compact: bool = False,
) -> None:
    """Print schedule for one period."""
    plannable = [p for p in people if is_plannable(p, period_start, period_end)]
    print_header(label, period_start, period_end)

    person_data = [
        (p, calc_person_period(p, period_start, period_end, tasks, timeoffs, projects))
        for p in plannable
    ]
    person_data.sort(key=lambda x: x[1][3], reverse=True)  # sort by free hours desc

    team_cap = sum(cap - toff for _, (cap, toff, *_) in person_data)
    team_planned = sum(planned for _, (_, _, planned, *_) in person_data)
    team_free = sum(free for _, (_, _, _, free, _) in person_data)
    team_pct = min(team_planned / team_cap * 100, 100) if team_cap > 0 else 0
    team_dot = status_dot(team_planned, team_cap)

    print(f"\n  {team_dot} TEAM  —  {fmt(team_planned).strip()} / {fmt(team_cap).strip()}  [{team_pct:.0f}%] free: {fmt(team_free).strip()}")

    for person, (cap, toff, planned, free, task_map) in person_data:
        available = cap - toff
        pct = min(planned / available * 100, 100) if available > 0 else 0

        toff_str = f"  (–{fmt(toff).strip()} off)" if toff > 0 else ""
        dot = status_dot(planned, available)
        summary = f"{fmt(planned).strip()} / {fmt(available).strip()}{toff_str}  [{pct:.0f}%] free: {fmt(free).strip()}"

        if compact:
            free_str = f"{free:.0f}h offen"
            print(f"    • {person['name']} ({free_str})")
        else:
            print(f"\n  {dot} {person['name']}  —  {summary}")
            for lbl, h in sorted(task_map.items(), key=lambda x: -x[1]):
                truncated = (lbl[:42] + "...") if len(lbl) > 45 else lbl
                print(f"    {truncated:<45} {fmt(h)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Float department schedule overview")
    parser.add_argument(
        "period",
        nargs="?",
        default="all",
        choices=["current", "next", "month", "all"],
        help="current = this week, next = next week, month = next 4 weeks, all = all three (default)",
    )
    parser.add_argument(
        "--compact", "-c",
        action="store_true",
        help="compact view without task details",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="re-run config setup",
    )
    return parser.parse_args()


def setup_config() -> None:
    """Interactive first-time setup."""
    print("First-time setup — creating config at", CONFIG_FILE)
    print()
    token = input("Float API token (Settings > Integrations): ").strip()
    department = input("Department name: ").strip()
    exclude = input("Exclude names (comma-separated, optional): ").strip()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        f"FLOAT_API_TOKEN={token}\n"
        f"FLOAT_DEPARTMENT={department}\n"
        f"FLOAT_EXCLUDE_NAMES={exclude}\n"
    )
    print(f"\nConfig saved to {CONFIG_FILE}")
    print("Run float-export again to see your schedule.\n")


def main() -> None:
    args = parse_args()

    if args.setup:
        setup_config()
        sys.exit(0)

    if not TOKEN or not DEPARTMENT:
        if not CONFIG_FILE.exists():
            setup_config()
            sys.exit(0)
        print(f"Error: FLOAT_API_TOKEN and FLOAT_DEPARTMENT must be set in {CONFIG_FILE}")
        sys.exit(1)
    print(f"Fetching data for department: {DEPARTMENT}...")

    people = get_people(DEPARTMENT)
    if not people:
        print(f"No active people found in '{DEPARTMENT}' department.")
        sys.exit(1)

    print(f"Found {len(people)} people.")

    today = date.today()
    this_week = week_range(today, 0)
    next_week = week_range(today, 1)
    four_weeks_start = next_week[0]
    four_weeks_end = week_range(today, 4)[1]

    # Fetch all data covering current week through 4-week range
    fetch_start = this_week[0]
    fetch_end = four_weeks_end
    projects = get_projects()
    tasks = get_tasks_for_people(people, fetch_start, fetch_end)
    timeoffs = get_timeoffs(fetch_start, fetch_end)

    c = args.compact
    if args.period in ("current", "all"):
        print_period("THIS WEEK", *this_week, people, tasks, timeoffs, projects, compact=c)
    if args.period in ("next", "all"):
        print_period("NEXT WEEK", *next_week, people, tasks, timeoffs, projects, compact=c)
    if args.period in ("month", "all"):
        print_period(
            "NEXT 4 WEEKS", four_weeks_start, four_weeks_end, people, tasks, timeoffs, projects,
            compact=c,
        )
    print()


if __name__ == "__main__":
    main()
