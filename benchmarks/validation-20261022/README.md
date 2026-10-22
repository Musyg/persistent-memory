# Persistent memory: independent confirmation

This study measures how retrieved memory changes an agent’s answers on 100 new synthetic tasks, each set in a separate scenario with no memory shared across scenarios. Each task is run three times. The same questions and model settings are compared with memory, without memory, and, for the principal model, with lexical retrieval.

The [complete report](EXPECTED-REPORT/REPORT.en.md) gives successes, failures, unknown outcomes and confidence intervals. Its JSON and both language versions can be recalculated offline from the included answers and judgments.

| Generation model | With memory | Without memory | Lexical retrieval |
|---|---:|---:|---:|
| GPT-6 Luna | 298/300 (99.33%) | 29/300 (9.67%) | 294/300 (98.00%) |
| GPT-6.1 Sol | 300/300 (100%) | 30/300 (10%) | Not tested |

The primary memory/no-memory gain is 89.67 percentage points, with a nominal 95% interval of 89–90 points. The one-sided 95% lower bound for Luna’s absolute success is 98%, meeting the frozen 90%/85% quality thresholds. All 1,500 answers were delivered and all 3,000 judge responses completed; no unknown outcome or confirmed critical violation was recorded. Luna’s two memory-on failures remain in the data: scenario `V22-F09-G10-T01`, repetitions 2 and 3. This self-contained scheduling control needs no stored facts: both answers assigned the wrong person to Tuesday.

The memory/lexical-retrieval effect interval is −0.33 to +3.33 percentage points: this study does not establish an advantage over lexical retrieval. The second model’s memory/no-memory gain is 90 points on this cohort. These comparisons concern the scenarios below; they do not certify every production workload.

Ten task families cover factual recall, composition across sessions, validity windows, revisions, short procedures, source withdrawal, homonyms, unavailable facts, self-contained controls and workspace isolation. Each family has five French and five English tasks. Two AI agents prepared the questions and oracles; a separate AI reviewer checked all 100 tasks and 190 documents before the local freeze. No model answers had been observed when the cohort was frozen.

The corrected evaluator receives the exact evidence delivered to the answer model. Two judges evaluate each eligible answer without seeing the other judge’s verdict. Both must agree; disagreement, an incomplete verdict or an unavailable response remains unknown. The primary analysis compares GPT-6 Luna’s success with memory against its success without memory. Absolute quality is assessed separately: conservative success must reach 90%, and its nominal one-sided 95% lower bound must reach 85%. Nominal 95% effect intervals use 10,000 paired bootstrap resamples of scenario groups within each task family, keeping all three repetitions together. The sampling units are the 100 separate scenarios. The memory/no-memory comparison on GPT-6.1 Sol and the memory/lexical-retrieval comparison on Luna are secondary.

The [eight-case evaluator calibration](CALIBRATION/README.md) is a separate diagnostic check. The [earlier 500-task campaign](../validation-20261021/README.md) remains archived with its original outcomes and evaluator erratum.

## Recalculate locally

On Linux, from this directory, with Python 3.11 or later:

```sh
sha256sum -c SHA256SUMS
python CODE/report.py --manifest REPORTING-INPUTS.json \
  --manifest-sha256 "$(cat REPORTING-INPUTS.sha256)" \
  --output /tmp/persistent-memory-confirmation-new
```

Use a new output directory. This command performs no model call. Compare its report with `EXPECTED-REPORT/`.

The study exercises the public 0.3.0a2 memory package through its portable text consumer. The corpus contains short, structured scenarios; withdrawal coverage concerns sources, and access coverage concerns workspaces. Derived-record recovery, user ACLs and long histories require their own evidence. The judges and reviewers are AI agents; no external human quality audit was performed. Judge errors can be correlated; the intervals describe uncertainty across sampled scenarios, without covering all judging errors or establishing production representativeness. The freeze was local, with public release after measurement. All published data are synthetic.
