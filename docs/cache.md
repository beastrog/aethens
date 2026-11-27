# Parallel audits and the result cache

`aethens audit` can run many tasks at once and skip tasks that have not changed. This does not
change what a check reports. The report schema stays `aethens-report/v2`. Severities, thresholds
and the Docker isolation flags are unchanged (`--network none`, read-only root, non-root, all
capabilities dropped, no-new-privileges, pids and memory limits).

## Jobs

`--jobs N` is how many tasks run at once. The default is the minimum of the CPU count and 4, the
same cap the bench uses. `N` has to be an integer of at least 1.

The report lists `task_ids`, findings and coverage in the order the tasks were loaded (path
order), then in check order. That order does not depend on which task finishes first.

Each task still goes through the runner on its own: a new disposable copy, and either a new
container or, with `--unsafe-local`, a new process group. Worker threads share the check objects.
`run` must not mutate `self`.

A high `--jobs` can overload the Docker daemon. Timeouts still use the in-container clock
(D-064). The default stays at 4 so a laptop does not start dozens of 1 GiB containers.

The library default is different: `run_audit(..., jobs=1)`. The bench already has its own worker
pool and does not pass `jobs`, so it stays one task per bench worker.

## Cache

The cache stores one result per finished task. The key is the sha256 of a canonical JSON document:

- Aethens `__version__`
- a sha256 of the installed package's `.py` files (the version string is still `0.1.0.dev0`
  across behaviour changes, so the source hash is what actually invalidates a dev build)
- budget, seed, whether the run is `--unsafe-local`, runner mode (`docker` or `local`)
- the checks in order, plus each check's `cache_config()` (C004 records
  `filter_equivalent`)
- an environment fingerprint
- a hash of the task tree

The task hash covers every file and directory under the task root: relative path, kind, permission
bits and contents. Symlinks contribute their link text. mtime is not included. An escaping or
dangling symlink is an error, the same as at load time. Directory symlinks are not followed.

The environment fingerprint:

- **Docker.** `id=<image Id>;repo=<sorted RepoDigests>`. `Id` is `docker image inspect
  --format '{{.Id}}'`. `RepoDigests` are the registry digests. On Docker 28.5.2 these are
  different strings for a pulled `python:3.12-slim` (config id `sha256:d497…`, registry digest
  `sha256:1910…`). Both are in the key: a locally built image has no registry digest, and a
  republish changes the registry digest. Not verified on Podman or Docker Desktop.
- **Any other runner, including `--unsafe-local`.** The image is not executed. The fingerprint
  is the runner mode, `sys.platform`, the machine, and `sys.version`. A Docker cache entry is
  never reused for a local run.

`--cache-dir DIR` chooses the directory. The default is `$XDG_CACHE_HOME/aethens`, or
`~/.cache/aethens` when that variable is unset or empty. `--no-cache` does not read or write the
cache. The two flags cannot be combined.

Entries are JSON files in an internal `aethens-cache/v1` layout. That layout is not the report.
A corrupt or mismatched entry is ignored and the task is run again; the new result overwrites it.
Repro commands are rebuilt on a hit so they match the current working directory.

`make bench` does not use this cache. The regression gate always re-executes.

## Resume

A task is written to the cache only after every selected check for that task has finished. The
write is a temp file, `fsync`, then `os.replace`. Killing the process in the middle of a task
leaves no entry for that task. Tasks that already finished are reused when you run the same
command again.

On a failure, tasks that have not started are cancelled. Tasks that have already entered the
runner are allowed to finish, so the container or process is cleaned up and a completed task can
be stored. There is no cancel channel into a running container: an interrupt waits for those
in-flight verifier runs. A `SIGKILL` of the whole process can still leak a container, which was
already true.

`started_at` and `duration_s` in the report are the wall clock of this command. A fully cached
run is short even though the evidence was collected earlier. The report does not list cache hits;
adding that would change `aethens-report/v2`. The CLI prints the counts on stderr:

```text
aethens: 1000 tasks (980 from cache, 20 ran) jobs=4
```

The directory entry of the rename is not fsynced. A process kill after `os.replace` returns keeps
the entry. A sudden power loss could theoretically drop the last rename.
