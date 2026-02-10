# Float Department Schedule

CLI tool that shows planned vs unplanned hours for your Float.com department.

## Output

- **This week / Next week**: Detailed view with task breakdown per person
- **Next 4 weeks**: Overview with free hours per person
- Color-coded status dots: green (80%+), yellow (50-79%), red (<50%)
- Team summary with total capacity and utilization

## Install

```bash
pip install git+https://github.com/yannickpulver/float-export.git
```

On first run, you'll be guided through setup (API token, department name).
Config is stored at `~/.config/float-export/.env`.

## Usage

```bash
float-export              # all periods
float-export current      # this week
float-export next         # next week
float-export month        # next 4 weeks
float-export month -c     # compact view
```

## Configuration

Config lives at `~/.config/float-export/.env` (created on first run).

| Variable | Description |
|---|---|
| `FLOAT_API_TOKEN` | Float API token (Settings > Integrations) |
| `FLOAT_DEPARTMENT` | Department name to filter |
| `FLOAT_EXCLUDE_NAMES` | Comma-separated substrings to exclude (e.g. `needed,placeholder`) |

## Features

- Expands recurring tasks (weekly, bi-weekly, etc.)
- Handles multi-person task assignments (`people_ids`)
- Respects work hours history (part-time changes)
- Accounts for time-off
- Deduplicates and sums recurring task hours
- Filters out inactive/non-plannable people per period
