# Disclosure policy for findings about other people's benchmarks

Aethens can find defects in public benchmarks and environments maintained by others. The project
handles those findings as follows.

1. **Private first.** Findings about third-party benchmarks are written only to the gitignored
   `audits/private/` directory. Nothing is published, and no issues, pull requests or comments are
   opened on other repositories by tools or agents.
2. **Human verification.** The maintainer checks every finding by hand before contacting anyone, and
   notes how it could be wrong (for example, a rejected candidate that is not actually valid).
3. **Private notice.** The maintainer sends a private notice to the benchmark's maintainers with the
   evidence and repro command, and offers to help with a fix.
4. **Waiting period.** Nothing is named publicly for 2 to 4 weeks after the notice, longer if the
   maintainers are actively fixing it. Security-relevant issues follow SECURITY.md timelines.
5. **Public write-up.** Afterwards, a public post may describe method, numbers, misses and disclosure
   status. It credits maintainers who responded and does not shame those who did not.

Launch material uses only the project's own bench numbers, never named third-party findings.

The maintainer filed two findings himself on 27 Nov 2026 and asked for a reproduction page before launch: [Terminal-Bench 2 issue 107](https://github.com/harbor-framework/terminal-bench-2/issues/107) and [SWE-bench issue 733](https://github.com/SWE-bench/SWE-bench/issues/733). [reproduce-findings.md](reproduce-findings.md) restates only what those issues already say, including which harness confirmed them. It is not a new audit. Every other third-party finding stays in `audits/private/` until the steps above are done.
