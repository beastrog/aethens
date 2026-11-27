# Bench data licences

All tasks under `bench/tasks/` are original work written for Aethens and licensed under the
repository's Apache-2.0 licence. Third-party data must be listed here with its licence, source URL
and the date the licence was checked, before it is committed.

## External bench (D2), licences checked on 2026-11-18

| dataset | licence | where checked | how it is used | committed? |
|---|---|---|---|---|
| OpenAI HumanEval (github.com/openai/human-eval, commit b9453e8f1865df0a0057a1383767caa400acfbcf, `data/HumanEval.jsonl.gz`) | MIT, "Copyright (c) OpenAI (https://openai.com)" | the repository's LICENSE file; the Hugging Face copy `openai/openai_humaneval` is also tagged `license:mit` | prompts, original canonical solutions and original base tests become aethens tasks | a small sample only, in `bench/external/sample/tasks/`, each file with an attribution header; the full data is downloaded by `bench/external/fetch.py` (pinned sha256) into the gitignored `bench/external/data/` |
| EvalPlus HumanEval+ (huggingface.co/datasets/evalplus/humanevalplus, revision d32357cf319e50e9c8d8dab5ea876c72b0fd321b, `test.jsonl`) | Apache-2.0 (dataset card `license: apache-2.0`; the EvalPlus code repository github.com/evalplus/evalplus is also Apache-2.0) | the dataset card and the EvalPlus LICENSE file | the extended tests, used only as an outside oracle; their numpy comparison helper is replaced by a stdlib equivalent (a modification, stated in each converted file and in `bench/external/convert.py`) | a small sample only, in `bench/external/sample/oracle/`, each file with an attribution header and modification note; full data downloaded as above |

The MIT licence of HumanEval:

> Copyright (c) OpenAI (https://openai.com). Permission is hereby granted, free of charge, to any
> person obtaining a copy of this software and associated documentation files (the "Software"), to
> deal in the Software without restriction, including without limitation the rights to use, copy,
> modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
> persons to whom the Software is furnished to do so, subject to the following conditions: The above
> copyright notice and this permission notice shall be included in all copies or substantial
> portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

EvalPlus HumanEval+ is used under the Apache License 2.0 (a copy is in this repository's `LICENSE`);
the converted oracle files are modified as described above.

## Datasets considered and skipped

| dataset | why skipped |
|---|---|
| ImpossibleBench, LiveCodeBench split (huggingface.co/datasets/fjzzq2002/impossible_livecodebench) | The ImpossibleBench code repository is MIT, but the dataset card states no licence and the problems derive from LiveCodeBench (contest-site problems), so the data licence is unclear. It also has no reference solutions, which every Aethens task needs. |
| ImpossibleBench, SWE-bench split (huggingface.co/datasets/fjzzq2002/impossible_swebench) | Dataset card states no licence; each instance needs a per-repository SWE-bench environment image and network access to build, which the offline sandbox does not allow. |
| EvalPlus MBPP+ | Not attempted in D2 for time; same structure as HumanEval+ (MBPP is CC-BY-4.0, MBPP+ Apache-2.0, both to be re-checked before use). Listed in docs/IDEAS.md. |

## Real-world audits (importers), licences checked on 2026-11-27

Nothing below is committed. `bench/real/fetch_real.py` downloads each export at a pinned revision
(sha256-checked) into the gitignored `bench/real/data/`; `aethens import` turns it into task
directories at audit time. Audit results committed under `audits/public/` quote only task ids,
test ids, short code excerpts needed as evidence, and Aethens' own output.

| dataset | licence | where checked | how it is used |
|---|---|---|---|
| EvalPlus MBPP+ (huggingface.co/datasets/evalplus/mbppplus @ b2d74c91) | Apache-2.0 (dataset card); derived from Google MBPP, CC-BY-4.0 | dataset card; github.com/evalplus/evalplus LICENSE (Apache-2.0); github.com/google-research/google-research/tree/master/mbpp | reference solution = gold, EvalPlus test code = verifier (verbatim) |
| EvalPlus HumanEval+ (huggingface.co/datasets/evalplus/humanevalplus @ d32357cf) | Apache-2.0; HumanEval MIT | as in the external bench above | importer supported; not yet audited as a verifier |
| SWE-bench Verified, SWE-bench org export (huggingface.co/datasets/SWE-bench/SWE-bench_Verified @ 78f471bf), and princeton-nlp/SWE-bench_Verified @ c104f840 for comparison | SWE-bench code: MIT (github.com/SWE-bench/SWE-bench LICENSE). The dataset cards state **no licence**. Instance code and patches come from 12 upstream repositories under their own licences (Django BSD-3-Clause, SymPy BSD-3-Clause, etc.). | dataset cards (no `license` field), SWE-bench LICENSE | downloaded only; never committed. **Licence of the dataset itself is unclear: owner decision before any of it is redistributed.** |
| swebench 5.0.2 (PyPI) log parsers and grading rules | MIT, Copyright (c) 2023 Carlos E Jimenez, John Yang, Alexander Wettig, Shunyu Yao, Kexin Pei, Ofir Press, Karthik R Narasimhan | the wheel's LICENSE | vendored verbatim (imports changed) in `src/aethens/sandbox/swebench_grading.py`, licence text included in the file |
| SWE-bench per-instance images (Docker Hub `swebench/sweb.eval.x86_64.*`) | built by the SWE-bench project from the upstream repositories | Docker Hub | pulled at audit time, never redistributed |
| BigCodeBench v0.1.4 (huggingface.co/datasets/bigcode/bigcodebench @ b74c0d0b) | Apache-2.0 (dataset card; github.com/bigcode-project/bigcodebench LICENSE) | dataset card and repo LICENSE | complete prompt + canonical solution = gold, test code = verifier (verbatim); official evaluation image pulled by digest |
| Terminal-Bench 2 (github.com/harbor-framework/terminal-bench-2 @ 2fd12b88) | Apache-2.0 | repo LICENSE | static compatibility scan only (no task converted or run) |
| Prime Intellect environments (github.com/PrimeIntellect-ai/prime-environments) | Apache-2.0 (verifiers library: MIT) | repo LICENSE | read only, for the feasibility note in docs/importers.md; nothing imported |
