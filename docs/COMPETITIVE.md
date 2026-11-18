# Competitive landscape

Researched 18 Nov 2026 from public sources only: GitHub repository pages and READMEs, arXiv, and
project blogs. Star counts are what GitHub showed on 18 Nov 2026 and change quickly. Where a claim
comes from a project's own README, it is that project's claim and has not been reproduced here.
"Not verified" means I could not confirm it. This file is analysis only: it changes no code, check
semantics, schema or roadmap, and nothing in it is approved for building (see docs/IDEAS.md and
AGENTS.md).

## Headline

The space filled up fast in Oct–Nov 2026. One tool, **rlgate**, already ships most of what
this file was asked to evaluate as "differentiators": deterministic reward-hacking probes (exit 0
early, `conftest.py` / `sitecustomize` hooks, always-equal objects, hardcoded visible answers),
leak detection, mutation and stub probes, Harbor and SWE-bench adapters, an optional LLM layer
that writes wrong and alternative solutions, SARIF and badge output, waivers, a GitHub Action and
a PyPI 1.0.0 release. It is MIT-licensed, has 1 star, and was created in Oct 2026. Its README
says "Not yet built: dedup and calibration."

So Aethens can't win by adding probe families. Competitors already have them, and anyone can copy
an open-source check. What nobody has yet:

1. Measured precision and recall per check against outside ground truth.
2. Test-order and isolation dependence checks.
3. Deterministic (no-LLM) detection of over-strict tests, which is where OpenAI found most of the
   damage in SWE-bench Verified.
4. A maintained, disclosure-respecting public record of audited benchmarks.

## 1. Competitors and what they cover

Legend for the coverage columns: **GS** gold/baseline sanity, **FL** flakiness, **OR** test-order
or isolation dependence, **FA** false accepts (weak tests), **FR** false rejects (over-strict tests),
**RH** reward-hacking / grader-tampering probes, **LK** solution or answer leakage, **CT**
contamination, **EX** findings proven by execution (not just LLM opinion), **CAL** published
precision/recall of the tool itself. ✓ = covered, ~ = partly or only with an LLM, blank = not seen.

### Direct competitors: tools that audit verifiers, graders or environments

| Project | Stars | Licence | What it actually does | GS | FL | OR | FA | FR | RH | LK | CT | EX | CAL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [rlgate](https://github.com/deepak-foundryai/rlgate) | 1 | MIT | Python CLI for coding tasks (Harbor/Terminal-Bench, SWE-bench `.jsonl`, MiMo, or a YAML layout). Six steps, 76 rules: build, baseline (gold passes and do-nothing fails, 5 runs each), leaks (solution in image, git history, `.orig` files), grader (remove/stub/mutate the fix, hardcode visible answers), cheating (exit 0, fake reports, always-equal, conftest/sitecustomize/.pth, changed test selection), fairness. Findings are "Proven" or "Needs your judgment", each with a repro. Optional `--deep-review` uses LLM judges and agents (needs keys). Docker, Daytona or local backends. JSON/MD/SARIF/HTML/badge output. On PyPI as 1.0.0. | ✓ | ✓ | | ✓ | ~ | ✓ | ✓ | | ✓ | |
| [Assay](https://github.com/caiotheodoro/assay) | 4 | Apache-2.0 | `assay audit`: a probe battery plus an LLM "auditor" that emits an Environment Card, with every claim tied to a probe. Scores itself as expected loss under four cost profiles on its own 33-environment, 54-planted-defect corpus. Reports deterministic precision 0.757 on that corpus and finds that the LLM arms tie with random flagging. Browser demo via WebAssembly. | ~ | | | ✓ | | ✓ | | | ✓ | ✓ (own corpus) |
| [BenchJack](https://github.com/benchjack/benchjack) ([paper](https://arxiv.org/abs/2605.12673)) | 54 | Apache-2.0 | Hackability scanner for agent benchmark repos. Static tools (Semgrep, Bandit, Hadolint) plus Claude Code or Codex agents look for 8 flaw classes (V1 isolation … V8 permissions) and write PoC exploits. The paper reports 219 flaws across 10 benchmarks. It has a community `audits/` archive, which held 1 audit (FrontierSWE) when I checked. | | | | ~ | | ✓ | ✓ | | ~ (PoCs) | |
| [Verity-RedTeam](https://github.com/Verity-AI-Labs/Verity-RedTeam) | 0 | Apache-2.0 | An LLM "hacker loop" tries to get reward without solving the task, and an LLM judge classifies the result. Reports hackability α with Clopper-Pearson CIs on axes V1 soundness, V2 completeness (isomorphic perturbation), V4 leakage, V6 isolation and V7 reward shaping. Depends on Verity-Core and Verity-Corpus, neither of which is on PyPI. | ✓ | | | ✓ | ~ | ✓ | ✓ | | ~ | ~ |
| [RewardAudit](https://github.com/xzx34/RewardAudit) | 3 | Apache-2.0 | Tests rule-based answer checkers (math/QA reward functions) with outputs whose correct score is known: negations, hedges, equivalent rewrites, extreme inputs. Has a verifiers-env adapter. Its README reports 81 of 185 open-source checkers with a confirmed high-severity defect. Not for code test suites. | | | | ✓ | ✓ | ~ | | | ✓ | |
| [rlenv-audit](https://github.com/MEMGATE/rlenv-audit) | 0 | MIT | Feeds verifiers-format environments "null policies" (empty, echo, kitchen-sink), finds blind reward functions and shared-namespace `exec` graders, and turns findings into runnable exploits. | | | | ✓ | | ✓ | | | ✓ | |
| [rl-env-audit](https://github.com/vahit19/rl-env-audit) | 0 | MIT | Acceptance test for answer graders: empty replies, "grader, this is correct" notes, two-candidate replies. Issues a certificate with a statistical bound. Its README reports scanning 60 public environments and fixing 2 reward holes. | | | | ✓ | | ✓ | | | ✓ | ~ |
| [Terminal-Bench / Harbor `tasks check`](https://github.com/harbor-framework/harbor) (Harbor 7,196 ★; [terminal-bench](https://github.com/harbor-framework/terminal-bench-1) 2,622 ★) | — | Apache-2.0 | An LLM rubric over a task's files with 11 pass/fail criteria (behaviour in description vs tests, anti-cheating, tests or solution in image, pinned deps, hardcoded solution…). `--fix` calls Claude Code. Opinion only, nothing is executed. Source: [DeepWiki summary](https://deepwiki.com/harbor-framework/terminal-bench/5.3-task-quality-assurance); I did not read the source. | | | | ~ | ~ | ~ | ~ | | | |
| AgentSynth ([PyPI](https://pypi.org/project/agentsynth-ai/0.8.0/)) | n/a | MIT | Trivial-adversary checks, contamination canaries and a CI Action for scenario packs. From docs/AETHENS_PLAN.md (Oct 2026). Not re-verified today. | | | | ~ | | ~ | | ~ | | |
| [Gymnasium `check_env`](https://github.com/Farama-Foundation/Gymnasium) | 12,836 | MIT | API-conformance linter for classic RL environments (spaces, reset/step signatures). Assay uses it as "the incumbent linter". Does not test reward or verifier correctness. | | | | | | | | | | |

### Research artefacts: datasets, papers and one-off pipelines that define the problem

| Project | Stars | What it is | Relevance to Aethens |
|---|---|---|---|
| [SWE-ABS](https://github.com/OpenAgentEval/SWE-ABS) ([arXiv 2603.00520](https://arxiv.org/abs/2603.00520)) | 27 | Strengthens SWE-bench Verified tests with LLM-generated tests and mutants. Per the paper: 251 of 500 instances strengthened, and 53 (10.6%) found to have overfitting tests. | Possible outside ground truth for false accepts and false rejects (licence: MIT repo; data licence not verified). |
| [UTBoost](https://github.com/CUHK-Shenzhen-SE/UTBoost) (ACL'25) | 36 | LLM-generated extra tests for SWE-bench; flags patches that behave differently from gold. | Same: ground truth for weak tests. |
| [EvalPlus](https://github.com/evalplus/evalplus) | 1,839 | HumanEval+ (80x more tests) and MBPP+ (35x). | Base-vs-plus tests give labelled weak-test cases, already in the plan as a stretch goal. |
| [Terminal Wrench](https://github.com/few-sh/terminal-wrench) ([arXiv 2604.17596](https://arxiv.org/abs/2604.17596)) | 54 | 331 reward-hackable Terminal-Bench-style tasks, 3,632 hack trajectories, 11 exploit categories (hollow implementation 2,243, output spoofing 1,071, …). | Best public labelled set of hackable verifiers; a recall test for hacking probes. Apache-2.0. |
| [ImpossibleBench](https://github.com/safety-research/impossiblebench) ([arXiv 2510.20270](https://arxiv.org/abs/2510.20270)) | 82 | Mutates tests so they contradict the spec; any pass is cheating. Measures model propensity, not verifier quality. | Its "conflicting tests" variants are a free set of verifiers known to be wrong. |
| [EvilGenie](https://github.com/JonathanGabor/evilgenie_inspect) | 8 | Reward-hacking benchmark in Inspect. | Measures models, not verifiers. |
| [Agentic Benchmark Checklist](https://github.com/uiuc-kang-lab/agentic-benchmarks) ([arXiv 2507.02825](https://arxiv.org/abs/2507.02825)) | 65 | NeurIPS'25 checklist (task validity, outcome validity, reporting), applied by hand to 10 benchmarks. | A vocabulary Aethens findings could map to. |
| OpenAI SWE-bench Verified work ([2024 creation](https://openai.com/index/introducing-swe-bench-verified/), [Feb 2026 retirement post](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)) | — | Human annotation campaigns. In 2026 OpenAI audited 27.6% of Verified and found at least 59.4% of the audited problems had tests that reject functionally correct submissions; it also found gold patches reproduced by frontier models (contamination). Pipelines not open-sourced. | Strongest public evidence that false rejects and contamination are the expensive failures. |
| [SWE-Bench+](https://arxiv.org/abs/2410.06992) | — | Paper: 32.67% of "resolved" patches copied solutions leaked in issue text; 31.08% passed through weak tests. | Evidence for leakage and weak-test checks. |
| ABA ([arXiv 2605.26079](https://arxiv.org/abs/2605.26079)), "Judging Is Not Enumerating" ([arXiv 2608.01000](https://arxiv.org/abs/2608.01000)) | — | LLM auditor over 34,285 tasks; evidence that LLM-written suites reject correct solutions. From docs/AETHENS_PLAN.md, not re-read today. | Prior art on false rejects. |

### Adjacent infrastructure: produces or runs tasks, doesn't audit verifiers

| Project | Stars | Notes |
|---|---|---|
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | 6,216 | Harness runs FAIL_TO_PASS / PASS_TO_PASS tests in Docker. Validation happens at dataset-build time (gold must flip tests); it does not probe test strength or determinism. |
| [SWE-smith](https://github.com/SWE-bench/SWE-smith) | 835 | Synthesises SWE tasks at scale; validates that injected bugs break tests. A task *producer*, so a natural Aethens user. |
| [SWE-Gym](https://github.com/SWE-Gym/SWE-Gym) | 764 | 2.4K real Python tasks from 11 repos plus learned verifiers (reward models) for best-of-n. "Verifier" here means a reward model, not a test-suite audit. |
| [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) / [R2E](https://github.com/r2e-project/r2e) | 353 / 152 | 8.1K procedurally curated problems from commits; hybrid execution plus execution-free verifiers. Producer, not auditor. |
| [Prime Intellect verifiers](https://github.com/PrimeIntellect-ai/verifiers) / [community-environments](https://github.com/PrimeIntellect-ai/community-environments) | 4,792 / 270 | Library for RL environments and evals; the community repo describes itself as "lightly-reviewed". No built-in verifier audit found. A large, under-audited target. |
| [reasoning-gym](https://github.com/open-thought/reasoning-gym) | 1,555 | Procedural reasoning environments with built-in verifiers. Answer checkers, closer to RewardAudit's domain. |
| [OpenEnv](https://github.com/openenv/OpenEnv), [inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) / [inspect_evals](https://github.com/UKGovernmentBEIS/inspect_evals), [openai/evals](https://github.com/openai/evals) | 2,864 / 3,281 / 748 / 19,767 | Environment and eval frameworks; possible adapter targets. |
| [mutmut](https://github.com/boxed/mutmut), [cosmic-ray](https://github.com/sixty-north/cosmic-ray) | 1,546 / 667 | General Python mutation testing. Not task-aware: no gold/starter/candidate notion, no sandbox for untrusted code. |
| [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), [detect-test-pollution](https://github.com/asottile/detect-test-pollution), [pytest-flakefinder](https://github.com/dropbox/pytest-flakefinder), [iDFlakies](https://github.com/UT-SE-Research/iDFlakies) | 723 / 208 / 159 / 34 | General flaky and order-dependent test tooling (iDFlakies is Java). Nobody packages these for verifier audits. |
| [llm-decontaminator](https://github.com/lm-sys/llm-decontaminator), [Contamination_Detector](https://github.com/liyucheng09/Contamination_Detector) | 327 / 52 | Corpus- or web-level contamination detection. Not task- or verifier-aware. |
| [reward-bench](https://github.com/allenai/reward-bench) | 749 | Evaluates reward *models*, not programmatic verifiers. |

## 2. Overlap with Aethens today

| Aethens v0.1 | Who else does it |
|---|---|
| C001 gold sanity (starter fails, gold passes) | rlgate (baseline, 5 runs each), Verity precheck, SWE-bench build-time validation. **Parity.** |
| C002 flakiness (rerun gold, vary `PYTHONHASHSEED`) | rlgate RG003 (5 reruns). **Parity.** Nobody gives a statistical bound on flake rate for code verifiers. |
| C003 labelled candidates with `label_source` | Unusual. rlgate and Verity generate candidates with LLMs rather than consuming user labels. The explicit "needs review" handling of unreviewed labels is distinctive but small. |
| C004 AST mutation probes (info) | rlgate (mutate/stub/remove parts of the fix), mutmut and cosmic-ray (generic), SWE-ABS (research). **Behind rlgate**, which also stubs functions and hardcodes visible answers. |
| Docker sandbox, read-only, no network, non-root | rlgate (Docker or Daytona), BenchJack (WIP). **Parity.** |
| JSON/Markdown report, one-line repro, exit codes, GitHub Action | rlgate has all of these plus SARIF, HTML, badge, waivers and a pre-commit hook. **Behind.** |
| Published bench precision/recall in README | Assay publishes on its own corpus; rlgate has a "planted-defect self-test" but no published numbers. **Ahead, but self-authored**, so it is not yet a moat. |
| Exit-code-only harness bypass (`os._exit(0)`) | rlgate RG202 already catches it; Aethens lists it as a known miss. **Behind.** |
| Task formats | Aethens: own `aethens-task/v1` only. rlgate: Harbor, SWE-bench, MiMo, YAML. **Behind.** |

Honest summary: in its current form Aethens is a cleaner, smaller subset of rlgate plus an honest
self-authored bench. Its distinctive traits are restraint (no LLM in the core, explicit limits on
every finding) and measurement culture. These are real but not yet a moat.

## 3. Gaps no one fills (as far as these searches found)

1. **Calibrated precision and recall per check on outside ground truth.** rlgate says calibration
   is not built. Assay calibrates on its own corpus. Nobody scores a verifier auditor against public
   labelled data (EvalPlus base-vs-plus, SWE-ABS overfitting instances, Terminal Wrench hackable
   tasks, ImpossibleBench conflicting variants).
2. **Test-order, isolation and state-pollution dependence of verifiers.** Every auditor reruns the
   same order. Generic tools (pytest-randomly, detect-test-pollution) exist but are not
   task-aware. This is also Aethens's own known miss.
3. **Deterministic false-reject detection.** The expensive failure in the OpenAI 2026 audit (at least
   59.4% of audited Verified problems rejected correct code) is found today only by humans or LLM
   agents (rlgate L3 RG408, Verity V2, SWE-ABS). No tool generates semantically equivalent variants
   of the gold solution by program transformation and checks the verifier accepts them.
4. **Statistical guarantees on determinism.** Flakiness checks use fixed rerun counts. None report
   "flake rate below x% at 95% confidence" or add runs adaptively. Verity and rl-env-audit use
   bounds, but for hackability and graders, not code-test determinism.
5. **A maintained public record of audited open benchmarks with a disclosure process.**
   BenchJack's archive holds one audit; Terminal Wrench is a one-time dataset. Nobody runs a
   versioned, reproducible "verifier quality" ledger that waits for maintainers before naming
   anything.
6. **Code-verifier audits for the Prime Intellect verifiers / Environments Hub ecosystem.** RewardAudit
   and rlenv-audit cover answer checkers there. Nobody audits the code-execution environments'
   test suites.

## 4. Differentiators, ranked by impact versus effort

Ranking: highest impact per unit of effort first. Sizes: S ≈ a milestone (days), M ≈ 1–2 weeks,
L ≈ a month or more, for one person with an agent. Each item would change check semantics or scope,
so each needs the owner's approval under AGENTS.md.

### D1. Test-order and isolation dependence check (S)
Rerun the gold solution's verifier with tests reversed, shuffled under recorded seeds, and each test
run alone in a fresh process. Report any verdict change with the exact order and a repro command.
Where a pair of tests interact, bisect to the minimal pair (the way detect-test-pollution does). It
is defensible because no verifier auditor does it (gap 2). It also closes Aethens's own two known
bench misses (`order-alphabetical`, `order-generated`), so recall moves from 12/14 towards 14/14
with evidence. It is cheap because the runner and bench already exist. Needs harness hooks for
unittest and pytest; other harnesses report "doesn't apply".

### D2. Outside-ground-truth calibration bench and per-check precision/recall in CI (M)
Build `bench/external/` download scripts, with each licence checked and recorded in
`bench/LICENSES.md`, that turn public labelled data into Aethens tasks with known answers:
- EvalPlus base-vs-plus weak tests;
- SWE-ABS's overfitting and strengthened instances;
- ImpossibleBench's conflicting-test variants;
- a Terminal Wrench subset for hackability.

Publish precision, recall and CIs per check, regenerated by CI, next to the self-authored numbers. This
is the hardest thing to copy: the corpus, labels and track record build over time, and rlgate
says calibration isn't built. It also turns the existing "honest numbers" habit into a claim
nobody else can make: "measured on data we didn't write." Effort is mostly adapters and licence
checks, not new checks.

### D3. Deterministic equivalent-rewrite probes for false rejects (M)
Apply semantics-preserving transformations to the gold solution and require the verifier to accept
every variant. Examples:
- rename private helpers and locals;
- reorder independent statements and dict-literal keys;
- swap `for` loops for comprehensions;
- inline or extract small functions;
- change the formatting of non-specified error messages, only where the task spec leaves them open.

A rejection is a candidate over-strict test, reported with the diff. No LLM and no labels needed. It
is defensible because false rejects are the costliest real failure (OpenAI's 59.4%), and today
only LLM agents or humans find them (gap 3). A deterministic, reproducible version fits Aethens's
no-LLM core and its measurement culture. The risk is transformations that aren't truly
equivalent, so start with a small, provably safe set and measure false positives with D2.

### D4. Adaptive flakiness with a stated statistical bound (S)
Replace "N runs" with sequential sampling: keep running until either a disagreement appears or the
run count supports "flake probability below p at confidence c". Fold in the C001 gold run as a
sample (already in docs/IDEAS.md), and print the bound in every C002 result. It is defensible
because no one reports determinism as a bound for code verifiers (gap 4). It is also the kind of
claim reviewers and paper authors can cite, it fixes the documented 1-in-16 miss rate, and it's
small. This changes check semantics and thresholds, so it needs the owner's decision.

### D5. Reward-hacking probe pack, done measurably (M)
Planted, deterministic adversarial candidates:
- exit 0 before tests;
- `conftest.py`, `sitecustomize`, `.pth` and pytest-plugin hooks;
- objects whose `__eq__` always returns True;
- monkeypatching the module under test or `builtins`;
- special-casing the visible test inputs, read from the test file;
- editing test data;
- fake result files.

This is table stakes rather than a moat, because rlgate already ships most of these (RG104,
RG201–RG2xx). Aethens should still have it: the README already admits the `os._exit(0)` gap, and
users will compare feature lists. Aethens's edge here is that each probe comes with measured
recall on the Terminal Wrench categories from D2, plus explicit "harness robustness"
recommendations. Without those, this is parity work and should not be marketed as unique.

### D6. Public audit ledger of open benchmarks with disclosure (M, then ongoing)
A static site or repo directory with one entry per audited open benchmark. Each entry pins:
- the upstream commit, the Aethens version and the seed;
- the exact repro command and the findings;
- the disclosure status (notified, fixed, or public after the 2–4 week window in
  docs/DISCLOSURE.md).

It starts with tasks the owner verified by hand. This is defensible because the corpus,
maintainer relationships and track record are the assets the plan already names as durable (plan
§1). BenchJack's archive has one entry and Terminal Wrench is a one-time dataset (gap 5). Effort is
mostly human: verification and outreach, which the agent must never do.

### D7. Adapters for Harbor/Terminal-Bench, SWE-bench and verifiers code environments (L total, M each)
Read the existing formats natively so users don't have to convert to `aethens-task/v1`. Harbor and
SWE-bench are parity with rlgate. A **verifiers code-environment adapter** is open ground (gap 6),
because existing tools there audit answer checkers, not test suites. Defensibility is
low for the first two and medium for the third. The value is distribution: every other
differentiator only matters if people can run it on the tasks they already have. Plan §10 says to
build an adapter when 3 users ask; that rule still applies.

### D8. Verifier quality score, severity-weighted and calibrated (S, after D2)
One number per task and per benchmark, computed from findings weighted by measured per-check
precision from D2, with a confidence interval and the list of checks that couldn't run ("unscored
is not zero", as Verity puts it). Defensible only once D2 exists: without calibration it's an
arbitrary badge (rlgate already has a badge), and Assay's README shows how naive scores mislead.
Low effort, high marketing value, real risk of overclaiming, so it comes last.

### Evaluated and not recommended now
- **LLM-generated wrong solutions with an optional key.** rlgate L3 and Verity already do this. Assay
  reports its LLM arms did no better than random flagging. If built, it should only *propose*
  candidates that execution and D3-style differential testing then label, never judge. M size, low
  differentiation.
- **Solution leakage scanning** (gold or tests in the agent's image, git history, `.orig` files).
  rlgate RG3xx and BenchJack V2 cover it. Only relevant once Aethens reads Docker-image task formats
  (D7). Parity work.
- **Contamination / memorisation detection** (can a model reproduce the gold patch?). Needs model
  access and keys, conflicts with the no-LLM, no-network positioning, and OpenAI's pipeline isn't
  public. Better done as an optional separate plugin later, if ever.
- **Spec-test consistency.** Harbor's `tasks check` and rlgate RG401–404 do it with LLMs. A
  deterministic version (every name or string asserted in tests appears in the spec) is cheap but
  noisy; it could be an info-level lint inside D3. Not a headline.

## Sources

All links are inline above. Star counts and README claims were read on 18 Nov 2026. Items marked
"from docs/AETHENS_PLAN.md" were checked 27–28 Oct 2026 and not re-verified today.
