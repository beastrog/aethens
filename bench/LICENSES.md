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
