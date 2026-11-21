# WEC 2026 Campus Microgrid Controller

A Python controller for the Waterloo Engineering Competition programming challenge. Every
simulated hour (24 in a day) the test server sends the campus state over a socket at
`localhost:8800`. The controller answers with how much solar, battery and grid energy each
building gets, and how much the backup generator makes. Goal: meet every building's demand
at the lowest total cost.

Standard library only: nothing to install.

## How to run

```bash
python3 main.py practice     # a made-up 24-hour day that includes every random event
python3 main.py              # competition: the server must already be running on localhost:8800
python3 test_controller.py   # rule checks
```

`grid_optimizer.py` does exactly the same as `main.py`, because the brief names the entry
file both ways.

## The 4 rules (every hour)

1. **Solar first:** free, at most 200 units, never to the lecture hall, can't be stored.
2. **Battery:** used only if the grid is down, the grid costs more than $1 (the generator's
   price, which is what stored energy cost to make), or it is the last 3 hours of the day.
   Lecture halls are served first because they can't use solar.
3. **Grid:** covers whatever is still needed.
4. **Generator:** refills the battery to a cushion that would survive a grid failure next
   hour (1.5 x the energy solar couldn't cover, at least 50, at most 100). No refills in the
   last 3 hours, because energy left at midnight is wasted money.

Before any answer is sent, `rule_checker.py` checks every constraint in the brief. If
anything is wrong, `backup_plan.py` sends a simple answer that is always valid, so the
program never crashes and never sends an invalid answer.

## Files

| Part | File | What it does |
| --- | --- | --- |
| 1 | `settings.py` | All the numbers from the brief and our strategy settings |
| 2 | `memory.py` | Battery level, hour and total cost, kept between hours |
| 3 | `decision.py` | The 4 rules: decides one hour |
| 4 | `rule_checker.py` | Checks every rule before an answer is sent |
| 5 | `backup_plan.py` | Safety net answer if anything goes wrong |
| 6 | `hourly_routine.py` | One hour: decide, check, update memory, print |
| 7 | `server_connection.py` | Socket connection to the competition server |
| 8 | `practice_day.py` | A pretend day for testing without a server |
| 9 | `main.py` | The start button (`grid_optimizer.py` is the same) |
| - | `test_controller.py` | Rule checks, run with `python3 test_controller.py` |

```
main.py / grid_optimizer.py
  ├── practice_day.py ─────┐
  └── server_connection.py ┤
                    hourly_routine.py
                      ├── decision.py
                      ├── rule_checker.py
                      └── backup_plan.py
settings.py and memory.py are shared by every file.
```

## Submission package

All files sit in one folder with no subfolders, as the brief requires. To build the zip:

```bash
zip submission.zip *.py
```

## Assumptions (to confirm with the organizers)

- The battery starts empty and holds 100 units.
- Energy the generator makes goes into the battery and can be used from the next hour.
- The forecast describes the next hour's weather.
