"""Content-addressed cache of per-task audit results.

The on-disk format is ``aethens-cache/v1``. It is not part of the report: reports stay
``aethens-report/v2``. An entry is written only after every selected check for that task
has finished, by ``os.replace`` of an fsynced temp file, so a killed process leaves no
half-written entry (D-068).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

import yaml

from aethens import __version__
from aethens.checks.base import Check, CheckContext
from aethens.errors import (
    AuditConfigError,
    CacheError,
    ContainerStartError,
    DockerUnavailableError,
    MissingFileError,
    RunnerError,
    SchemaError,
    SymlinkEscapeError,
)
from aethens.models import Coverage, Finding, Task
from aethens.runner.base import run_quiet

CACHE_SCHEMA = "aethens-cache/v1"
_SHA_RE = re.compile(r"sha256:[0-9a-f]{64}")
# id is the local image config digest; repo is zero or more registry manifest digests.
_FINGERPRINT_RE = re.compile(
    rf"id={_SHA_RE.pattern};repo=({_SHA_RE.pattern}(,{_SHA_RE.pattern})*)?"
)
_KEY_RE = re.compile(r"[0-9a-f]{64}")


def default_cache_dir() -> Path:
    """``$XDG_CACHE_HOME/aethens``, or ``~/.cache/aethens`` when that variable is unset or empty."""
    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".cache"
    return root / "aethens"


def hash_task_files(root: Path) -> str:
    """Hash of the task tree: sorted relative path, kind, mode and bytes.

    Symlinks contribute their link text, not a second copy of the target (the target is hashed
    at its own path when it lives in the tree). mtime is not included. Escaping and dangling
    symlinks raise the same errors as the loader. Directory symlinks are not followed, so a
    cycle cannot hang the hash.
    """
    root = root.resolve()
    entries = _collect(root)
    digest = hashlib.sha256()
    for rel, payload in entries:
        digest.update(os.fsencode(rel))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _collect(root: Path) -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        if rel_dir != ".":
            mode = stat.S_IMODE(current.stat().st_mode)
            found.append((rel_dir, b"dir\0" + str(mode).encode("ascii")))
        dirnames.sort()
        kept: list[str] = []
        for name in dirnames:
            path = current / name
            if path.is_symlink():
                found.append(_symlink_entry(path, root))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink():
                found.append(_symlink_entry(path, root))
            elif path.is_file():
                found.append(_file_entry(path, root))
            else:
                rel = path.relative_to(root).as_posix()
                raise SchemaError(f"{rel} is not a regular file or directory")
    found.sort(key=lambda item: item[0])
    return found


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _symlink_entry(path: Path, root: Path) -> tuple[str, bytes]:
    rel = path.relative_to(root).as_posix()
    target = path.resolve(strict=False)
    if not target.exists():
        raise MissingFileError(f"{rel} is a dangling symlink")
    if not _inside(target, root):
        raise SymlinkEscapeError(f"{rel} points outside the task directory")
    raw = os.fsencode(os.readlink(path))
    return rel, b"symlink\0" + raw


def _file_entry(path: Path, root: Path) -> tuple[str, bytes]:
    rel = path.relative_to(root).as_posix()
    try:
        data = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise CacheError(f"cannot read {rel}: {exc}") from exc
    payload = b"file\0" + str(mode).encode("ascii") + b"\0" + hashlib.sha256(data).digest()
    return rel, payload


@functools.cache
def package_code_digest() -> str:
    """Hash of the installed ``aethens`` package's ``.py`` files.

    ``__version__`` stays ``0.1.0.dev0`` across behaviour changes, so the version string alone
    would reuse results after a check change. Hashing the installed sources closes that hole.
    """
    module_file = __import__("aethens").__file__
    if not module_file:
        raise CacheError("aethens has no __file__; cannot hash the package for the cache key")
    root = Path(module_file).resolve().parent
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*.py") if p.is_file() and not p.is_symlink())
    for path in files:
        rel = path.relative_to(root).as_posix()
        digest.update(os.fsencode(rel))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def format_fingerprint(image_id: str, repo_digests: Sequence[str]) -> str:
    """Canonical image fingerprint: local image id plus sorted registry digests."""
    if not _SHA_RE.fullmatch(image_id):
        raise CacheError(f"image id {image_id!r} is not sha256:<64 hex>")
    clean: list[str] = []
    for digest in repo_digests:
        if not _SHA_RE.fullmatch(digest):
            raise CacheError(f"registry digest {digest!r} is not sha256:<64 hex>")
        if digest not in clean:
            clean.append(digest)
    clean.sort()
    return "id=" + image_id + ";repo=" + ",".join(clean)


def inspect_image_fingerprint(docker_bin: str, image: str) -> str:
    """Read ``Id`` and ``RepoDigests`` for ``image``.

    On Docker 28.5.2 these differ for a pulled ``python:3.12-slim`` (config id
    ``sha256:d497…``, registry digest ``sha256:1910…``). Both are part of the key: a locally
    built image has no registry digest, and a republish changes the registry digest. Not
    verified on Podman or Docker Desktop.
    """
    argv = [docker_bin, "image", "inspect", "--format", "{{.Id}}|{{json .RepoDigests}}", image]
    try:
        completed = run_quiet(argv, 30)
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(f"docker image inspect {image} did not answer within 30 s") from exc
    except (FileNotFoundError, PermissionError) as exc:
        raise DockerUnavailableError(f"docker CLI not usable: {exc}") from exc
    if completed.returncode != 0:
        err = completed.stderr.strip()[:300]
        hint = f" -- try: docker pull {image}" if "No such image" in completed.stderr else ""
        raise ContainerStartError(f"cannot inspect image {image!r}: {err}{hint}")
    return _parse_inspect(completed.stdout.strip(), image)


def _parse_inspect(text: str, image: str) -> str:
    image_id, sep, raw = text.partition("|")
    if not sep:
        raise CacheError(f"docker image inspect for {image!r} returned {text!r}")
    try:
        repos = json.loads(raw) if raw else []
    except json.JSONDecodeError as exc:
        raise CacheError(f"docker image inspect for {image!r} returned {text!r}") from exc
    if repos is None:
        repos = []
    if not isinstance(repos, list):
        raise CacheError(f"RepoDigests for {image!r} is not a list: {raw!r}")
    digests: list[str] = []
    for item in repos:
        if not isinstance(item, str) or "@" not in item:
            raise CacheError(f"unexpected RepoDigest {item!r} for {image!r}")
        digests.append(item.rsplit("@", 1)[1])
    return format_fingerprint(image_id, digests)


class DockerImageDigest:
    """Callable image fingerprint with a per-audit memo (one inspect per image name)."""

    def __init__(self, docker_bin: str = "docker") -> None:
        self.docker_bin = docker_bin
        self._lock = threading.Lock()
        self._memo: dict[str, str] = {}

    def __call__(self, image: str) -> str:
        with self._lock:
            found = self._memo.get(image)
        if found is not None:
            return found
        fingerprint = inspect_image_fingerprint(self.docker_bin, image)
        with self._lock:
            return self._memo.setdefault(image, fingerprint)


def task_environment(
    task: Task,
    ctx: CheckContext,
    image_fingerprint: Callable[[str], str] | None,
) -> str:
    """What the verifier actually ran on, besides the task files.

    Docker runs the image, so the fingerprint is required. Other modes do not execute
    ``task.image``; the key uses the runner mode and the host interpreter instead, and a
    docker entry is never reused for them.
    """
    if ctx.runner.mode == "docker":
        if image_fingerprint is None:
            raise AuditConfigError(
                "caching a docker audit needs an image fingerprint "
                "(docker image inspect Id and RepoDigests)"
            )
        fingerprint = image_fingerprint(task.image)
        if not _FINGERPRINT_RE.fullmatch(fingerprint):
            raise CacheError(
                f"image fingerprint for {task.image!r} is {fingerprint!r}, expected "
                "'id=sha256:<64 hex>;repo=[sha256:<64 hex>,...]'"
            )
        return fingerprint
    version = sys.version.replace("\n", " ")
    return f"{ctx.runner.mode}:{sys.platform}:{platform.machine()}:{version}"


def _host_python() -> str:
    """Host interpreter. AST checks and the loader use it even when Docker runs the verifier."""
    return sys.version.replace("\n", " ")


def _pyyaml_version() -> str:
    version = getattr(yaml, "__version__", None)
    if not isinstance(version, str) or not version:
        raise CacheError("PyYAML has no __version__; cannot build a cache key")
    return version


def cache_key(
    task: Task,
    checks: Sequence[Check],
    ctx: CheckContext,
    *,
    environment: str,
    tool_version: str | None = None,
    code_digest: str | None = None,
) -> str:
    """sha256 of the canonical description of one task audit. Hex, 64 characters."""
    described: list[dict[str, object]] = []
    for check in checks:
        config = check.cache_config()
        if not isinstance(config, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in config.items()
        ):
            raise CacheError(f"check {check.id} cache_config() must return dict[str, str]")
        described.append({"id": check.id, "config": dict(sorted(config.items()))})
    payload = {
        "schema": "aethens-cache-key/v1",
        "tool_version": __version__ if tool_version is None else tool_version,
        "code_digest": package_code_digest() if code_digest is None else code_digest,
        "budget": ctx.budget.value,
        "seed": ctx.seed,
        "unsafe_local": ctx.unsafe_local,
        "runner_mode": ctx.runner.mode,
        "checks": described,
        "environment": environment,
        "host_python": _host_python(),
        "pyyaml": _pyyaml_version(),
        "task_files": hash_task_files(task.root),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()


class ResultCache:
    """Directory of per-task results. Safe for several threads; one task per key."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            raise CacheError(f"cannot create cache directory {self.root}: {exc}") from exc
        self._require_private()
        self.hits = 0
        self.misses = 0
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key):
            raise CacheError(f"refusing cache key {key!r}")
        return self.root / key[:2] / f"{key[2:]}.json"

    def get(
        self, key: str, task_id: str
    ) -> tuple[tuple[Finding, ...], tuple[Coverage, ...]] | None:
        """Return stored findings and coverage, or None on a miss or a corrupt entry.

        A corrupt entry is not used. The next ``put`` for the same key overwrites it.
        """
        path = self._path(key)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._count(hit=False)
            return None
        except OSError as exc:
            raise CacheError(f"cannot read cache entry {path}: {exc}") from exc
        try:
            parsed = _parse_entry(json.loads(text), key, task_id)
        except (json.JSONDecodeError, SchemaError, CacheError, TypeError, ValueError):
            self._count(hit=False)
            return None
        self._count(hit=True)
        return parsed

    def put(
        self,
        key: str,
        task_id: str,
        findings: Sequence[Finding],
        coverage: Sequence[Coverage],
    ) -> None:
        path = self._path(key)
        payload = {
            "schema": CACHE_SCHEMA,
            "key": key,
            "task_id": task_id,
            "findings": [f.to_dict() for f in findings],
            "coverage": [c.to_dict() for c in coverage],
        }
        text = json.dumps(payload, indent=2) + "\n"
        tmp = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)  # os.open applies the umask; the entry must not be world-readable
            os.replace(tmp, path)
        except OSError as exc:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise CacheError(f"cannot write cache entry {path}: {exc}") from exc

    def _require_private(self) -> None:
        """Refuse a cache another local user could plant an entry in."""
        try:
            st = self.root.stat()
        except OSError as exc:
            raise CacheError(f"cannot stat cache directory {self.root}: {exc}") from exc
        if st.st_uid != os.getuid():
            raise CacheError(f"cache directory {self.root} is not owned by this user")
        mode = stat.S_IMODE(st.st_mode)
        if mode & 0o077:
            raise CacheError(
                f"cache directory {self.root} is group or world accessible ({oct(mode)}); "
                "refusing it"
            )

    def _count(self, *, hit: bool) -> None:
        with self._lock:
            if hit:
                self.hits += 1
            else:
                self.misses += 1


def _parse_entry(
    data: object, key: str, task_id: str
) -> tuple[tuple[Finding, ...], tuple[Coverage, ...]]:
    if not isinstance(data, dict):
        raise CacheError("cache entry is not an object")
    if data.get("schema") != CACHE_SCHEMA:
        raise CacheError("unsupported cache schema")
    if data.get("key") != key or data.get("task_id") != task_id:
        raise CacheError("cache entry does not match the requested task")
    raw_findings = data.get("findings")
    raw_coverage = data.get("coverage")
    if not isinstance(raw_findings, list) or not isinstance(raw_coverage, list):
        raise CacheError("cache entry findings and coverage must be lists")
    findings = tuple(Finding.from_dict(item) for item in raw_findings)
    coverage = tuple(Coverage.from_dict(item) for item in raw_coverage)
    if any(f.task_id != task_id for f in findings) or any(c.task_id != task_id for c in coverage):
        raise CacheError("cache entry contains another task id")
    return findings, coverage
