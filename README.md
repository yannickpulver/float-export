# Float Department Schedule

CLI tool that shows planned vs unplanned hours for your Float.com department.

## Output

- **This week / Next week**: Detailed view with task breakdown per person
- **Next 4 weeks**: Compact overview with free hours per person
- Color-coded status dots: green (80%+), yellow (50-79%), red (<50%)
- Team summary with total capacity and utilization

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your Float API token (Settings > Integrations) and department name.

## Usage

```bash
.venv/bin/python main.py          # all periods
.venv/bin/python main.py current  # this week
.venv/bin/python main.py next     # next week
.venv/bin/python main.py month    # next 4 weeks
```

## Configuration

| Variable | Description |
|---|---|
| `FLOAT_API_TOKEN` | Float API token |
| `FLOAT_DEPARTMENT` | Department name to filter |
| `FLOAT_EXCLUDE_NAMES` | Comma-separated substrings to exclude (e.g. `needed,placeholder`) |

## Features

- Expands recurring tasks (weekly, bi-weekly, etc.)
- Handles multi-person task assignments (`people_ids`)
- Respects work hours history (part-time changes)
- Accounts for time-off
- Deduplicates and sums recurring task hours
- Filters out inactive/non-plannable people per period
