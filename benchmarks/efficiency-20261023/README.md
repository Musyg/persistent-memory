# Observed quality, tokens and generation cost

[Français](README.fr.md) · [Complete result](RESULT.json) · [Pinned inputs](INPUTS.json) · [Reproduction evidence](REPRODUCTION.json)

This is an **exploratory secondary analysis** of the 1,500 already-published answers from the [Fresh100 confirmation study](../validation-20261022/README.md). It adds no model requests, judgments or changes to historical scores. All 1,500 answers have complete reported token usage. The analysis joins each answer to its frozen quality outcome by model, case, arm and repetition.

## Observed footprint

Each row covers 300 answers: 100 synthetic scenario groups with three repetitions.

| Configuration | Correct / 300 | Input + output tokens | Estimated generation USD | Consumer p95 |
| --- | ---: | ---: | ---: | ---: |
| Luna, no memory | 29 | 57,000 | 0.0099552 | 1.963 s |
| Luna, memory | 298 | 118,188 | 0.0188084 | 2.514 s |
| Luna, lexical retrieval | 294 | 124,017 | 0.0195409 | 2.460 s |
| Sol, no memory | 30 | 61,124 | 0.240344 | 3.339 s |
| Sol, memory | 300 | 122,053 | 0.415418 | 3.690 s |

For Luna, memory used **4.70% fewer total tokens** and **3.75% less estimated generation cost** than lexical retrieval on these answers. Its input-token count was 5.14% lower. The observed p95 was approximately 2.16% higher. Consumer timings include preparation, retrieval, generation and checks; they are not isolated provider latencies or a controlled speed benchmark.

Quality was 298/300 versus 294/300. The original paired 95% effect interval remains **−0.33 to +3.33 percentage points**: quality superiority and non-inferiority are not established. The observed token/cost differences have no newly estimated confidence interval. They do not establish general dominance or a frontier at identical realized token expenditure.

Against no memory, both models achieved the previously reported quality gains while consuming **more** tokens and money. Memory is not a token-saving intervention relative to that control. Lower cost per conforming answer in this cohort is descriptive: it is not the price of reliably completing an arbitrary future task, and it excludes retries and human work.

## Accounting and interpretation

- Prices are the **frozen October 22, 2026 standard text rates**: Luna USD 0.10/0.50 per million input/output tokens; Sol USD 2/10. These are historical analysis assumptions, not a current-price promise. Sources are retained in `INPUTS.json`.
- The generation estimate is **USD 0.7040665 for the historical 1,500 answers**, not a new charge for this analysis and not an invoice. Judge calls, retrieval, storage, ingestion, infrastructure and human costs are excluded. The actual invoice remains unknown.
- Cache, cache-write and audio/prediction usage are zero. The 42 reported reasoning tokens are already included in completion tokens and are not added again. Unsupported nonzero categories are rejected rather than silently assigned a price.
- Memory context totalled 43,182 Python characters and 44,391 UTF-8 bytes per model; lexical context totalled 47,835 characters and 49,227 bytes. Context tokens were not separately measured. Character/byte reductions are not tokenizer measurements.
- The three within-model contrasts each contain 300 paired responses, retaining three repetitions inside the same 100 scenario groups. Their 900 response pairs are not 900 independent tasks. No new grader, bootstrap interval, winning threshold or task selection is introduced.
- Cross-model rows are descriptive. Their complete rendered prompts contain different generated reference identifiers; this is not a causal comparison holding every input byte fixed. There is no full-history, long-context, production or matched-spend baseline here.

## Reproduce on Linux

From this checkout or extracted source distribution, with the package installed in a fresh environment:

```sh
python -I -B -m unittest discover -s tests -p test_product.py -v
python -I -B benchmarks/run_benchmark.py --efficiency > efficiency.json
cmp efficiency.json benchmarks/efficiency-20261023/RESULT.json
```

The same result bytes were reproduced in two Linux environments, each passing 15 focused product tests. The default manifest is hash-pinned. A custom manifest requires both `--efficiency-inputs PATH` and `--efficiency-inputs-sha256 HASH`; references must remain inside the benchmark tree. Unknown/missing usage, misbound identities, inconsistent totals, unsupported tariff categories and invalid prices fail explicitly.

The source data and original reports remain unchanged. Earlier [lifecycle evidence](https://github.com/Musyg/persistent-memory/tree/6c18450579fce9c071808c431cdbcb345771bced/benchmarks/lifecycle-20261022) retains its original source pins in commit `6c18450`; new CLI modes do not retroactively change that study. The next separate question is whether memory helps a fresh process produce a verified task artifact. This footprint analysis does not answer it.
