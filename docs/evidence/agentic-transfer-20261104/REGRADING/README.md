# Independently regrade the disclosed B responses

[Français](README.fr.md)

Run `python -I -B verify.py` from the report directory to recalculate the comparison. Run `python -I -B REGRADING/verify_regrading.py` to check the disclosed grades as well. Both commands run offline.

`B-EVIDENCE.json` contains 32 synthetic B fixtures and 128 assigned world/arm rows. Each fixture provides the actual threshold, target convention, three input records and the expected columns and rows. The verifier recomputes those rows from the stated convention using the existing eligibility function. Each assigned arm has a first and terminal response slot. `EXACT` includes the original response content and its UTF-8 SHA-256. `WITHHELD` marks a response that could not be disclosed. `UNAVAILABLE` marks a response that could not be recovered or never existed. Neither unavailable nor withheld content is counted as independently regraded. A first response and a terminal response may be the same generation.

Both response slots use the same typed business oracle and the original filename and response-shape checks. The first-attempt grade applies the complete rule, including the boundary value. During generation the agent saw a different public check, which checked format and behavior away from the boundary. The parser reads a single inert `RESULT` assignment with `ast.literal_eval`. The verifier does not execute generated Python, call a model or start Hermes.

`ORACLE-SOURCES.json` identifies the exact source definitions used. The appendix carries the public repository's MIT license. The regrading manifest covers the disclosed evidence and binds it to the published roster and arm verdicts. Private operational provenance, rights checks and model requests are outside this replay. Regrading establishes agreement with the oracle for the disclosed bytes. Unavailable or withheld grades remain attested by the study.

## Resource attribution

The experiment counts common A work once per world. To estimate the resource use of running one condition on its own, report common A plus that condition's own recorded use separately. The trace was prepared during the ECC phase without another model call. The counters do not measure how much CPU work in that phase belongs to trace construction versus ECC. The reported model time and tokens describe recorded model use.

The `model_tool_calls` field counts instrumented HTTP operations against the model backend. It is separate from generations and from tools an agent uses to complete a task. Report the campaign's elapsed time separately from summed model latency. Elapsed time includes preparation, startup, waiting, incidents and closure. Shared technical overhead remains a campaign measure.
