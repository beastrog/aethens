# Recorded audit runs used by the site's terminal demo

Unedited stdout of two local runs, used verbatim by `src/components/AuditDemo.astro`.
Recorded 27 Nov 2026 with aethens 0.1.0.dev0 (installed from this repository at 2a80a05) on
Linux with Docker, image python:3.12-slim:

| File | Command | Exit code |
| --- | --- | --- |
| `order-alphabetical.md` | `aethens audit bench/tasks/order-alphabetical --seed 0 --budget smoke --format markdown` | 1 |
| `add-two.md` | `aethens audit examples/add-two --seed 0 --budget smoke --format markdown` | 0 |

Regenerate with the same commands from the repository root. Durations in the reports are wall
time of that machine; the site replays the output faster and says so.
