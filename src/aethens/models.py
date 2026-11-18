"""Typed core models and their JSON (de)serialisation.

Models are frozen dataclasses. ``to_dict`` returns JSON-ready data; ``from_dict`` validates and
raises :class:`aethens.errors.SchemaError` on anything unexpected (fail loudly, no defaults for
required fields).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from aethens.errors import SchemaError

REPORT_SCHEMA = "aethens-report/v2"
# Older report versions Report.from_dict still reads (v1 had no coverage list).
READABLE_REPORT_SCHEMAS = ("aethens-report/v1", REPORT_SCHEMA)
TASK_SCHEMA = "aethens-task/v1"

JSONDict = dict[str, Any]

_E = TypeVar("_E", bound=StrEnum)


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 3, "warning": 2, "info": 1}[self.value]


class Confidence(StrEnum):
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs-review"


class Label(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class LabelSource(StrEnum):
    HUMAN = "human"
    ORACLE = "oracle"
    LLM_UNREVIEWED = "llm-unreviewed"


class Budget(StrEnum):
    SMOKE = "smoke"
    STANDARD = "standard"
    DEEP = "deep"


def confidence_for(source: LabelSource) -> Confidence:
    """AGENTS.md rule 3: an unreviewed label never produces a confirmed finding."""
    if source is LabelSource.LLM_UNREVIEWED:
        return Confidence.NEEDS_REVIEW
    return Confidence.CONFIRMED


# --- validation helpers -----------------------------------------------------------------------


def _req(data: JSONDict, key: str, typ: type | tuple[type, ...], where: str) -> Any:
    if not isinstance(data, dict):
        raise SchemaError(f"{where}: expected an object, got {type(data).__name__}")
    if key not in data:
        raise SchemaError(f"{where}: missing required field '{key}'")
    value = data[key]
    # bool is a subclass of int; never accept it where a number is expected.
    if isinstance(value, bool) and bool not in (typ if isinstance(typ, tuple) else (typ,)):
        raise SchemaError(f"{where}: field '{key}' must be {typ}, got bool")
    if not isinstance(value, typ):
        raise SchemaError(f"{where}: field '{key}' must be {typ}, got {type(value).__name__}")
    return value


def _enum(cls: type[_E], value: Any, where: str) -> _E:
    try:
        return cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        raise SchemaError(f"{where}: {value!r} is not one of: {allowed}") from None


def _str_tuple(value: Any, key: str, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SchemaError(f"{where}: field '{key}' must be a list of strings")
    return tuple(value)


# --- models -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """A candidate solution: an overlay directory with a validity label and where it came from."""

    name: str
    path: Path
    label: Label
    label_source: LabelSource

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "path": self.path.as_posix(),
            "label": self.label.value,
            "label_source": self.label_source.value,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> Candidate:
        w = "candidate"
        return cls(
            name=_req(data, "name", str, w),
            path=Path(_req(data, "path", str, w)),
            label=_enum(Label, _req(data, "label", str, w), w),
            label_source=_enum(LabelSource, _req(data, "label_source", str, w), w),
        )


@dataclass(frozen=True)
class Task:
    """A loaded aethens-task/v1 task. ``root`` is absolute; every other path is relative to it."""

    id: str
    root: Path
    language: str
    image: str
    statement: Path
    starter: Path
    tests: Path
    verifier: tuple[str, ...]
    timeout_s: int
    gold: Path
    candidates: tuple[Candidate, ...] = ()

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "root": self.root.as_posix(),
            "language": self.language,
            "image": self.image,
            "statement": self.statement.as_posix(),
            "starter": self.starter.as_posix(),
            "tests": self.tests.as_posix(),
            "verifier": list(self.verifier),
            "timeout_s": self.timeout_s,
            "gold": self.gold.as_posix(),
            "candidates": [c.to_dict() for c in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> Task:
        w = "task"
        cands = _req(data, "candidates", list, w)
        return cls(
            id=_req(data, "id", str, w),
            root=Path(_req(data, "root", str, w)),
            language=_req(data, "language", str, w),
            image=_req(data, "image", str, w),
            statement=Path(_req(data, "statement", str, w)),
            starter=Path(_req(data, "starter", str, w)),
            tests=Path(_req(data, "tests", str, w)),
            verifier=_str_tuple(_req(data, "verifier", list, w), "verifier", w),
            timeout_s=_req(data, "timeout_s", int, w),
            gold=Path(_req(data, "gold", str, w)),
            candidates=tuple(Candidate.from_dict(c) for c in cands),
        )


@dataclass(frozen=True)
class Evidence:
    """What was run and what was observed. Output tails are truncated by the runner."""

    subject: str
    command: tuple[str, ...]
    observed: str
    exit_codes: tuple[int | None, ...]
    timed_out: bool
    stdout_tail: str
    stderr_tail: str
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "subject": self.subject,
            "command": list(self.command),
            "observed": self.observed,
            "exit_codes": list(self.exit_codes),
            "timed_out": self.timed_out,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> Evidence:
        w = "evidence"
        codes = _req(data, "exit_codes", list, w)
        if not all(c is None or (isinstance(c, int) and not isinstance(c, bool)) for c in codes):
            raise SchemaError(f"{w}: exit_codes must be integers or null")
        extra = _req(data, "extra", dict, w)
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in extra.items()):
            raise SchemaError(f"{w}: extra must map strings to strings")
        return cls(
            subject=_req(data, "subject", str, w),
            command=_str_tuple(_req(data, "command", list, w), "command", w),
            observed=_req(data, "observed", str, w),
            exit_codes=tuple(codes),
            timed_out=_req(data, "timed_out", bool, w),
            stdout_tail=_req(data, "stdout_tail", str, w),
            stderr_tail=_req(data, "stderr_tail", str, w),
            extra=dict(extra),
        )


@dataclass(frozen=True)
class Finding:
    """One problem, with the evidence needed to reproduce and judge it."""

    id: str
    check_id: str
    severity: Severity
    task_id: str
    title: str
    detail: str
    evidence: Evidence
    repro: str
    seed: int
    confidence: Confidence
    limits: str

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "check_id": self.check_id,
            "severity": self.severity.value,
            "task_id": self.task_id,
            "title": self.title,
            "detail": self.detail,
            "evidence": self.evidence.to_dict(),
            "repro": self.repro,
            "seed": self.seed,
            "confidence": self.confidence.value,
            "limits": self.limits,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> Finding:
        w = "finding"
        return cls(
            id=_req(data, "id", str, w),
            check_id=_req(data, "check_id", str, w),
            severity=_enum(Severity, _req(data, "severity", str, w), w),
            task_id=_req(data, "task_id", str, w),
            title=_req(data, "title", str, w),
            detail=_req(data, "detail", str, w),
            evidence=Evidence.from_dict(_req(data, "evidence", dict, w)),
            repro=_req(data, "repro", str, w),
            seed=_req(data, "seed", int, w),
            confidence=_enum(Confidence, _req(data, "confidence", str, w), w),
            limits=_req(data, "limits", str, w),
        )


@dataclass(frozen=True)
class Coverage:
    """What a check established when it found nothing, e.g. C002's flake-rate bound (v2)."""

    check_id: str
    task_id: str
    statement: str
    stats: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "check_id": self.check_id,
            "task_id": self.task_id,
            "statement": self.statement,
            "stats": dict(self.stats),
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> Coverage:
        w = "coverage"
        stats = _req(data, "stats", dict, w)
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in stats.items()):
            raise SchemaError(f"{w}: stats must map strings to strings")
        return cls(
            check_id=_req(data, "check_id", str, w),
            task_id=_req(data, "task_id", str, w),
            statement=_req(data, "statement", str, w),
            stats=dict(stats),
        )


@dataclass(frozen=True)
class Report:
    """The result of one audit. Serialised as aethens-report/v2 (v1 plus ``coverage``)."""

    tool_version: str
    task_ids: tuple[str, ...]
    checks_run: tuple[str, ...]
    budget: Budget
    seed: int
    findings: tuple[Finding, ...]
    started_at: str
    duration_s: float
    coverage: tuple[Coverage, ...] = ()
    schema: str = REPORT_SCHEMA

    def to_dict(self) -> JSONDict:
        return {
            "schema": self.schema,
            "tool_version": self.tool_version,
            "task_ids": list(self.task_ids),
            "checks_run": list(self.checks_run),
            "budget": self.budget.value,
            "seed": self.seed,
            "findings": [f.to_dict() for f in self.findings],
            "coverage": [c.to_dict() for c in self.coverage],
            "started_at": self.started_at,
            "duration_s": self.duration_s,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> Report:
        w = "report"
        schema = _req(data, "schema", str, w)
        if schema not in READABLE_REPORT_SCHEMAS:
            raise SchemaError(f"{w}: unsupported schema {schema!r}, expected {REPORT_SCHEMA!r}")
        coverage: tuple[Coverage, ...] = ()
        if schema == REPORT_SCHEMA:
            coverage = tuple(Coverage.from_dict(c) for c in _req(data, "coverage", list, w))
        return cls(
            schema=schema,
            tool_version=_req(data, "tool_version", str, w),
            task_ids=_str_tuple(_req(data, "task_ids", list, w), "task_ids", w),
            checks_run=_str_tuple(_req(data, "checks_run", list, w), "checks_run", w),
            budget=_enum(Budget, _req(data, "budget", str, w), w),
            seed=_req(data, "seed", int, w),
            findings=tuple(Finding.from_dict(f) for f in _req(data, "findings", list, w)),
            started_at=_req(data, "started_at", str, w),
            duration_s=float(_req(data, "duration_s", (int, float), w)),
            coverage=coverage,
        )
