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

The write-up for the notices the maintainer has already sent is the Findings section of the README
and <https://beastrog.github.io/aethens/findings/>. It covers a Terminal-Bench 2 full-reward result
and [SWE-bench Verified issue #733](https://github.com/SWE-bench/SWE-bench/issues/733). The harness
commands for those two notices are in [reproduce-findings.md](reproduce-findings.md). Later findings
still follow steps 1–4 before they are named.

Bench numbers elsewhere on the site and in the README are the project's own measurements. A
third-party finding is named only in that write-up, after the notice above.
