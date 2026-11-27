# Security

## Threat model

Aethens runs code it should not trust: task tests, gold solutions, candidate solutions and mutants,
often written by other people or by models. The design assumes that code may be malicious.

What Aethens does (src/aethens/runner/docker.py, tested in tests/test_runner_docker.py):

- Task code never runs in the Aethens process. By default every run is a Docker container with
  `--network none`, memory and memory-swap limits (no swap), a CPU limit, a pids limit, a read-only
  root filesystem with a size-limited `/tmp` tmpfs, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, a non-root user, and `--pull never`.
- The container sees only a disposable copy of the task (starter, then the solution overlay, then the
  tests), mounted at `/work`. The original task directory is never mounted. Symlinks are copied as
  plain files.
- Containers are removed and copies deleted after timeouts, errors, Ctrl-C and SIGTERM (the CLI
  turns SIGTERM into an exception so the runner's cleanup runs, and its message names any container
  whose removal it could not confirm). If the Aethens process itself is killed with SIGKILL (or by the OOM killer), cleanup
  cannot run: a running container then lives on until its verifier exits, which for a hung verifier
  is never. Every Aethens container carries the label `aethens.run=1`; remove leftovers with
  `docker ps -aq --filter label=aethens.run=1 | xargs -r docker rm -f`.
- Output is capped (the last 64 KiB per stream are kept in memory).
- The docker CLI is called with argument lists only; no shell. The task loader rejects symlinks that
  leave the task directory, `..` and absolute paths, special files, oversized files, and image names
  or ids that could be read as command-line options.
- The host environment is not passed into containers.

What it does not protect against:

- Container escapes through kernel or Docker vulnerabilities. Docker is not a perfect boundary. For
  hostile inputs, run Aethens in a disposable VM.
- Resource use within the limits (for example a task that burns its full CPU and time budget).
- Disk use in `/work`. The disposable copy is a bind mount of a host directory, so writes there are
  not limited by the read-only root filesystem or the `/tmp` size limit: a task can fill the disk
  that holds your temporary directory for as long as its timeout allows. Point `TMPDIR` at a
  dedicated, size-limited filesystem when auditing untrusted tasks.
- `--unsafe-local` mode, which runs code directly on your machine with only a scrubbed environment,
  rlimits and timeouts. It offers no isolation and is for trusted code only.
- Malicious Docker images named in `task.yaml`. Aethens never pulls images during a run, but whatever
  image you pulled is what runs.

## Reporting a vulnerability

Please report security problems privately, not in a public issue or discussion.

Use [GitHub private vulnerability reporting](https://github.com/beastrog/aethens/security/advisories/new)
for this repository: **Security** → **Report a vulnerability**. Include steps to reproduce, the
Aethens version (`aethens --version` or the commit), and whether the issue is in the auditor, the
sandbox, the GitHub Action, or the default examples.

You should get a reply within 7 days. Please allow up to 90 days for a fix before public disclosure.

Do not file a public issue, open a public pull request that demonstrates the exploit, or discuss the
vulnerability in Discussions while it is unfixed.

## Supported versions

Aethens is at its first release (`0.1.0`). Security fixes land on `main` and in the most recent
published release.
