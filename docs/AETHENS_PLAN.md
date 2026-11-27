# AETHENS: Plan v5 (open source only; build v0.1 in about a week, then let evidence decide)

Status: 2 Nov 2026 (v5 drafted 28 Oct). Supersedes v4. Nothing is built yet. Decisions taken by the owner: open source only for now, no employer or client names anywhere in the project, build fast with Cursor or Claude Code, push to GitHub continuously, expand only on evidence.

## 0. What changed since v4

1. **Employer and client names are out of every file.** What stays is a generic rule: no confidential material from any employer or client, and a 20-minute check of your own contract and university terms before the repo goes public (section 7). The reason is not the names; it is that a side project in the same domain as paid work can collide with IP-assignment or moonlighting clauses, and a collision found after launch is expensive.
2. **Build week replaces Phase 0 and Phase 1.** The false-reject experiment from v4 is now the third feature you build, so there is no separate pre-build gate. The gates move to after launch, where they measure demand.
3. **The wedge is restated honestly.** I found two 2026 papers that already work on the false-reject side (section 2). The idea is real and academically supported, but it is not novel. The opening is a maintained, easy-to-run tool with measured precision and recall, not a new algorithm.
4. **Launch and disclosure are separated.** You can launch the tool in about a week. You cannot responsibly name defects in other people's benchmarks until their maintainers have had 2 to 4 weeks. So the launch uses the tool's own bench numbers, and the audit post follows.
5. **The benchmark corpus lives in the same repo for v0.1** (`bench/`), split out later if it grows.
6. **Full expansion plan with evidence triggers** (section 10).

## 1. Honest verdict

- A launch-ready v0.1 in about 7 days of full-time agent-driven work, or 2 to 3 weeks at 12 to 15 hours a week alongside classes, is realistic for the narrow scope in section 4. "The whole product in a few days" is not: the whole product means traction, trusted audits and possibly paid pilots, and those take months and depend on other people.
- Nobody can promise a "boom". The reasonable six-month goals: a tool real maintainers run, a respected public audit, one or two paid audits. Everything else is upside.
- Open source is the right call for trust and distribution. It also means anyone can copy your checks. Your durable assets are the corpus, the track record and relationships with maintainers.

## 2. Prior art (checked 27 and 28 Oct 2026; I read pages and summaries, not source code, unless stated)

- **Assay** (github.com/caiotheodoro/assay). Apache-2.0, `assay audit`, 11 probe families, 9 deterministic programs plus an LLM "Challenger" that proposes attacks which programs score. 4 stars, 276 commits. Its own page reports external recall of 0.339 on tau2-bench (not statistically significant) and 0 of 12 on ScienceAgentBench. As summarized by my fetch tool, it does not test valid alternative solutions.
- **AgentSynth** (`agentsynth-ai` on PyPI). MIT, one maintainer, about 15 releases between 9 and 23 June 2026, Beta. Trivial-adversary checks on scenario packs, contamination canaries, a CI Action.
- **ABA** (arXiv 2605.26079). Agentic LLM auditor for benchmark tasks, taxonomy includes tests that are too narrow or too broad. 34,285 tasks audited, 25.7% with major issues. Licence of its repo unverified (fetch blocked).
- **SWE-ABS** (arXiv 2603.00520). Strengthens SWE-bench Verified tests with LLM-generated tests and mutants, filtered by execution and LLM judges. Strengthened 251 of 500 instances. For false rejects, its mutation stage flags tests that fail equivalent mutants; manual review found 53 instances (10.6%) with overfitting tests. Data and scripts reported public at OpenAgentEval/SWE-ABS; licence and maintenance unverified.
- **"Judging Is Not Enumerating"** (arXiv 2608.01000). LLM-authored test suites on HumanEval+ admit only 19 to 42% of oracle-correct solutions; discarding suites that reject a known-correct solution cut false rejection from 58 to 92% down to 5% or less, though only 5 to 39% of suites survived. This is direct evidence that "run the verifier against known-correct solutions" catches real, common failures in LLM-authored verifiers. I read the first 100,000 characters of the paper.
- **EvalPlus** (NeurIPS 2023). HumanEval+ and MBPP+ add tests to catch wrong solutions the original tests accepted. The false-accept side of function-level code benchmarks is therefore already well covered.
- Not verified: "Verifiable Labs" (not found in two searches). Earlier finds: an open-source CLI that scanned 112 public environments, a reward-hackability audit paper, Preference Model hiring human reviewers.

What this means: the problem is real and published. Maintained general-purpose tooling that a benchmark builder can run in CI, with honest precision and recall, is what I could not find. That is a hypothesis about the market, and the post-launch gates test it.

## 3. Positioning

"Aethens runs your task's verifier against solutions it should accept and solutions it should reject, and shows the evidence, so you can trust your tests before you train or evaluate on them."

Sharper angle given the 2026 evidence: verifier QA for LLM-authored and human-authored tasks. LLM-written tests are cheap and increasingly common, and the second paper above shows they often reject correct answers.

Buyer order: benchmark and environment maintainers, teams running RL fine-tuning on open-weight models, small data vendors, then labs (who can build this in-house).

## 4. v0.1 scope

In scope (Python code tasks, run in Docker by default):
- Task format `aethens-task/v1`: a directory with `task.yaml`, starter files, tests, a gold solution, and optional labeled candidate solutions (`valid/`, `invalid/`) as overlay directories.
- Checks:
  - C001 gold sanity: the starting state fails the verifier; the gold solution passes.
  - C002 flakiness: the gold solution run N times; mixed outcomes are a finding.
  - C003 labeled candidates: a candidate labeled valid that the verifier rejects is a false reject; a candidate labeled invalid that it accepts is a false accept. Every candidate carries a `label_source` (`human`, `oracle`, `llm-unreviewed`), and an unreviewed label produces "needs review", not "confirmed".
  - C004 mutation probes: deterministic AST mutations of the gold solution (operator swaps, off-by-one constants, negated conditions, early returns). A surviving mutant is reported as info with an explicit "may be equivalent" note; equivalent mutants are the known weakness of mutation testing.
  - C005 (stretch) exit-zero probe: a candidate that exits with status 0 before the tests run.
- Report `aethens-report/v1` as JSON and Markdown, exit codes 0/1/2/3, a GitHub Action, a bench with published precision and recall, docs.

Out of scope for v0.1 (do not build): LLM candidate generation, Gymnasium or verifiers adapters, dashboards, hosted anything, other languages, telemetry, badges.

## 5. Architecture

Python 3.11+ package, library first. Modules: `models` (typed Task, Candidate, Finding, Report), `errors`, `config`, `adapters` (task loader), `runner` (Docker default, explicit unsafe local mode), `checks` (one class per check: id, `run(task, ctx) -> list[Finding]`), `report`, `cli` (the only place that prints and sets exit codes), `plugins` later.

Runner safety: Docker with no network, memory, CPU and pids limits, non-root user, all capabilities dropped, no-new-privileges, a disposable copy of the task directory (never the original), cleanup always, argument lists only (no `shell=True`). The local mode needs an explicit flag, scrubs the environment so secrets are not inherited, and kills the process group on timeout.

Every finding carries: check id, severity, task id, evidence (what ran, what happened, output tails), seed, a one-line repro command, a confidence value, and a limits note.

## 6. Bench

`bench/` holds about 20 to 24 small original Python tasks written for the project: about 8 clean controls (including tricky-but-valid ones, such as tests that legitimately pin an exact output format) and 16 or more with planted defects across six classes: weak tests that accept a wrong solution, over-strict tests that reject a valid one, flaky tests, tests with no real assertions, a broken gold solution, and order or state dependence. Each class has at least two instances.

Metrics in CI: precision (true findings over true plus false positives, where a false positive is an error or warning on a clean control), recall (planted defects found over planted), and per-check results. A drop against `bench/baseline.json` fails the build. README numbers come from the CI report, never typed by hand.

The README must say the bench is self-authored, so its numbers show whether the tool catches what was planted, not real-world recall. Stretch after launch: use EvalPlus's base-versus-plus tests as outside ground truth for false accepts, after checking their data licences and formats.

## 7. Security, legal, licensing

- Untrusted code: never executed in the tool's own process; see section 5. The Action uses `pull_request` with read-only permissions and no secrets; never `pull_request_target` with a checkout of PR code. Pin third-party actions to commit SHAs.
- Your own terms (Day 0, about 20 minutes): read any employment, contractor or university terms that touch IP, side projects or work in this domain. If anything restricts it, stop and sort it out before the repo goes public. I have not seen those documents and cannot judge them.
- Never use confidential material from any employer or client. Public benchmarks, public environments and your own original work only.
- Third-party data: do not commit any dataset until its licence is checked and recorded in `bench/LICENSES.md`; prefer download scripts.
- Licence: Apache-2.0 from day one; do not plan to relicense. Keep dependencies permissively licensed and minimal.
- Disclosure: the agent never contacts third parties. Findings about other people's benchmarks are written to a gitignored directory; you read them, verify them, and send private notices yourself. Wait 2 to 4 weeks for non-security issues before naming anything publicly, and offer a fix. Expect some maintainers to stay silent.
- Secrets: none in the repo or in prompts. PyPI publishing uses Trusted Publishing from GitHub Actions, so the agent never holds a token.
- Money: no company formation before the first paid pilot; ask a CA about export-of-services GST.

## 8. Build week and launch

Day 0 (you, about 2 hours): choose the spelling; create the repo (private until launch); reserve the PyPI name; set up a PyPI trusted publisher; run `gh auth login` yourself; check Docker works; do the terms check from section 7 (it must be done before the repo goes public; the private build can start without it); put AGENTS.md, ROADMAP.yaml and this plan (as docs/AETHENS_PLAN.md) in the repo.
Day 1: B1 skeleton, models, CI, `make check`. B2 task format and loader.
Day 2: B3 runner and its safety tests.
Day 3: B4 C001 and C002 with fixtures.
Day 4: B5 C003 and C004, bench grows.
Day 5: B6 report, CLI, bench runner with precision and recall, C005 if time. Start choosing 2 to 3 public benchmarks for the audit and begin your own manual reading of candidates.
Day 6: B7 Action, docs, README with real bench numbers, SECURITY.md, templates. Hardening review in a fresh session.
Day 7: release prep; you create the release; repo goes public; short launch post.
Days 8 to 10: buffer for failures; send 5 outreach messages (appendix).

Launch content: the tool, the bench numbers with known misses, honest limits. No named third-party findings yet. Show HN only when the README survives a cold read by someone who has not seen the project.

## 9. Post-launch gates (all numbers are my hypotheses; set yours before you look at the data)

- **G1 build quality (day 7):** zero false positives on bench controls; each planted class caught or listed as a known miss; Action runs in a few minutes; the hardening review's findings fixed.
- **G2 traction (day 30):** at least 5 people outside your circle report running it on their own tasks; at least 3 maintainer replies on private notices; at least 5 conversations held. Without telemetry this is counted from issues, replies and DMs, which is slow but honest.
- **G3 audit (about day 35 to 45):** one public audit post with method, numbers and misses, after the disclosure window.
- **G4 paid pilot (day 90):** one paid audit or support engagement. If 15 logged conversations produce none, stop adding features and reconsider the buyer or the wedge.

## 10. Expansion plan (build only what a trigger demands)

Outcome rules at day 30 and day 60:
- **Strong pull** (G2 met plus at least one inbound request for help or an audit): offer reviewed audits (expert audits available on request, or traded for a public case study); build the adapter the most-asked-for user needs; start the public audit log.
- **Use without money** (people run it, nobody pays): stay open source, keep it as a credibility asset, add adapters on request, test sponsorship or support contracts, and do not build a product layer.
- **No use** (G2 missed at day 60): run a post-mortem; options are a reviewed-audit service only, a different failure class, or stop. The repo still stands as portfolio work.

Tracks, each unlocked by a trigger:
1. **Depth** (after launch, on feedback): differential equivalence checks that auto-label candidate validity on pure functions; a bring-your-own-key candidate generator with cost cap; patch-format candidates; more mutation operators; JavaScript or TypeScript, then Rust and C++, which fit your systems strengths.
2. **Adapters** (pull-based, build when 3 users ask): Docker repo-level tasks in SWE-bench style; verifiers environments (read the source first, the API is moving); inspect_evals; OpenEnv; Gymnasium last.
3. **Distribution:** GitHub Action and pre-commit hook; a static public audit log site (benchmarks audited, disclosure status, findings) that doubles as the corpus moat; docs PRs into adjacent projects.
4. **Revenue ladder:** A first paid pilot: entity, invoicing. B three customers for a quarter: self-hosted dashboard, a part-time reviewer. C repeat customers beyond that: hosted audit service, first hire. D three customers ask for the same new area: systems languages, then hardware and electronics verification, then agent and tool-use environments. E outside capital only if cash is the limit.
5. **Optional later:** `aethens-shield` runtime guardrails only on customer pull.

## 11. Risks

- Crowded and moving fast: at least five related open projects or papers exist. Mitigation: narrow wedge, honest numbers, interoperate rather than compete feature for feature.
- Academic prior art on false rejects: your edge must be usability, maintenance and trust.
- Mutation probes produce noise from equivalent mutants. Mitigation: info severity and clear wording.
- A self-authored bench flatters the tool. Mitigation: say so, add outside ground truth.
- Running other people's code is a real attack surface. Mitigation: Docker defaults, a fresh-session security review before release.
- Agent drift: autonomous loops can build the wrong thing quickly. Mitigation: one milestone per PR, tests first, stop conditions, STATUS file, your review at G1.
- Time: classes and placements. The plan assumes you can spare 12 to 15 hours a week at least; at less, stretch the schedule, do not cut the safety work.

## 12. Decisions assumed, and what I need

- Name "Aethens" (distinctive); "Athens" collides with the well-known Go module proxy gomods/athens and Athens-named marks. Trademark not cleared. Switching is a find-and-replace.
- Python only, Docker default, repo private until launch day.
- Needed from you: confirm the spelling, your GitHub account or org name, and that Docker runs on your machine.

## Appendix: outreach templates (edit, keep them true)

To a maintainer, only after you verified a finding by hand:
"Hi [name], I'm building an open-source tool that runs a task's tests against solutions they should accept or reject. Running it on [task id] from [benchmark], a solution that appears valid is rejected: [one-line evidence and repro command]. I may be wrong about validity, so here are the solution and the output to check. I'm happy to share my full list privately before publishing anything and to help fix them."

To a team that trains on verifiable tasks (discovery, no pitch):
"Hi [name], I'm researching how teams check that their verifiers and task sets are reliable before training. How do you do it today, and has a bad verifier ever cost you a run or a result? Happy to share what I find. I'm not selling anything yet."

## Sources

- Assay: https://github.com/caiotheodoro/assay
- AgentSynth: https://pypi.org/project/agentsynth-ai/0.8.0/
- ABA: https://arxiv.org/abs/2605.26079
- SWE-ABS: https://arxiv.org/abs/2603.00520
- Judging Is Not Enumerating: https://arxiv.org/abs/2608.01000
- EvalPlus (NeurIPS 2023): https://neurips.cc/virtual/2023/poster/72990
- OpenAI on SWE-bench Verified: https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
- gomods/athens (name collision): https://github.com/gomods/athens
