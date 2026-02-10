# Float Department Schedule

CLI tool that shows planned vs unplanned hours for your [Float.com](https://float.com) department.

## Output

- **This week / Next week**: Detailed view with task breakdown per person
- **Next 4 weeks**: Overview starting from next Monday
- Color-coded status dots: `●` green (80%+), yellow (50-79%), red (<50% planned)
- Team summary with total capacity and utilization
- People sorted by most free hours first

## Install

```bash
pip install git+https://github.com/yannickpulver/float-export.git
```

On first run, you'll be guided through setup (API token, department name).

## Usage

```bash
float-export              # all periods
float-export current      # this week
float-export next         # next week
float-export month        # next 4 weeks
float-export all -c       # all periods, compact view
float-export --setup      # re-run config setup
```

### Flags

| Flag | Description |
|---|---|
| `--compact`, `-c` | Compact view — names with free hours only, no task details |
| `--setup` | Re-run the config wizard to change token, department, or exclusions |

## Configuration

Config lives at `~/.config/float-export/.env` (created on first run).
You can re-run `float-export --setup` or edit the file directly.

| Variable | Description |
|---|---|
| `FLOAT_API_TOKEN` | Float API token (Settings > Integrations) |
| `FLOAT_DEPARTMENT` | Department name to filter |
| `FLOAT_EXCLUDE_NAMES` | Comma-separated substrings to exclude (e.g. `needed,placeholder`) |

## Features

- Expands recurring tasks (weekly, bi-weekly, every N weeks)
- Handles multi-person task assignments (`people_ids`)
- Respects work hours history (part-time schedule changes)
- Accounts for time-off
- Deduplicates and sums recurring task hours per period
- Filters out inactive/non-plannable people per period
- Fetches 52 weeks back to catch long-running recurring allocations
