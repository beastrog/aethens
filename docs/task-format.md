# Task format: aethens-task/v1

A task is a directory. Aethens never reads anything outside it.

```
my-task/
  task.yaml
  statement.md            # what the solver is asked to do
  starter/                # the unsolved starting state
  tests/                  # the verifier's tests
  gold/                   # reference solution, overlaid onto starter/
  candidates/             # optional
    valid/<name>/         # a solution the verifier SHOULD accept (overlay)
    valid/<name>.label.yaml
    invalid/<name>/       # a solution the verifier SHOULD reject (overlay)
    invalid/<name>.label.yaml
```

## task.yaml

| key | required | type | meaning |
|---|---|---|---|
| `schema` | yes | string | must be `aethens-task/v1` |
| `id` | yes | string | `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`, unique across a run |
| `language` | yes | string | `python` (the only language in v0.1) |
| `image` | no | string | Docker image, default `python:3.12-slim`; must match `^[a-z0-9][A-Za-z0-9._/:@-]{0,254}$` |
| `statement` | yes | path | file |
| `starter` | yes | path | directory |
| `tests` | yes | path | directory |
| `verifier` | yes | list of strings | the command, as an argument list (never a shell string), run in the work directory |
| `timeout_s` | no | integer | wall-clock limit per verifier run, 1 to 3600, default 60 |
| `gold` | yes | path | directory |

Unknown keys and duplicate keys are errors. Paths must be relative, must not contain `..`, and must
resolve inside the task directory.

## How a run is assembled

For each verifier run Aethens builds a fresh, disposable work directory by copying, in order:
the contents of `starter/`, then the contents of the solution overlay (`gold/` or one candidate
directory; nothing for the starting-state run), then `tests/` to the same relative path it has in the
task. The verifier command runs in that work directory, so it sees the solution files at the top level
and the tests where task.yaml says they are. Later layers overwrite earlier files with the same
relative path. Candidates are overlays of whole files; patch files are not supported in v0.1.

## Label sidecars

Every candidate directory needs a sidecar `<name>.label.yaml` next to it:

```yaml
label_source: human   # human | oracle | llm-unreviewed
note: optional free text
```

`llm-unreviewed` labels only ever produce `needs-review` findings, never `confirmed` ones.

## Validation errors

| error | when |
|---|---|
| `MissingFileError` | task.yaml, a path field, or a label sidecar is missing; a symlink dangles |
| `SchemaError` | wrong schema, unknown or duplicate keys, wrong types, bad id or image, empty verifier, special files (FIFOs, devices) |
| `DuplicateIdError` | two tasks share an id, or two candidates share a name |
| `UnsafePathError` | an absolute path or `..` in a path field |
| `SymlinkEscapeError` | any symlink in the task directory (including task.yaml) resolves outside it |
| `OversizedFileError` | any file is larger than 5 MiB |

## Examples

See `examples/add-two` and `examples/word-format`.
