# Reusing experience across tasks and agents

26 October 2026 · [Français](README.fr.md)

Two integration observations complement the [comparative experience-learning study](../../../benchmarks/action-20261023/experience/README.md). They check the connection to real agents and are kept separate from that study's counts. Both use the same thirteen-scenario oracle; their scenario counts are not added into a larger set of distinct cases.

## A different task, with and without experience

Two sessions of the same agent received the same prompt, source code, model and limits. One had no stored experience; the other automatically received two lessons from an earlier task.

| Measure | Without experience | With experience |
| --- | ---: | ---: |
| Business contract tests passed | 7 of 7 | 7 of 7 |
| Scenarios covered | 13 | 13 |
| Observed provider requests | 2 | 2 |
| Added memory context | 0 characters | 873 characters |
| Request duration | 5.57 s | 6.74 s |

Hashes of the actual serialized system message confirm the absence of memory context in the first session and its addition in the second. Both proposals were tested without edits. The pair tied on quality: it verifies automatic delivery of the experience, without establishing an additional quality or efficiency gain. Independent review passed all 29 checks.

## A second agent retrieves the experience

A different agent then retrieved a memory from an earlier task and produced a 1,905-byte code proposal in one user request, with no retry. The request took 21.54 seconds. Generation used a local model with cloud fallback disabled.

The returned code was tested unchanged against the fixed oracle. All seven methods passed, covering thirteen scenarios, including ten labeled subtests, with no failures or skips. This is one task, not thirteen independent tasks. Review verified the exact retrieved memory, the actual returned artifact, native checks and cleanup of temporary resources. All 44 review checks passed; services started for the observation were returned to their stopped state.

The retrieved memory is attested in the second agent's result. Its connection to the prompt was qualified structurally; the serialized outbound prompt was not captured during this task. Without a memory on/off comparison for this second agent, the observation does not establish a causal gain.

The oracle checks specific contracts. In the generated proposal, some metrics and secondary text still represented missing information with defaults such as `False` or `0`. This issue falls outside the fixed assertions and is documented. The proposal was not deployed, and passing these seven tests does not establish complete code correctness.

## Published scope

This note publishes verified aggregates only. Private memories, prompts, application traces and code proposals are excluded. The separate [reproducible synthetic campaign](../../../benchmarks/action-20261023/experience/README.md) provides public observations and offline recalculation commands. Gains measured in that campaign and the completed functional 12/12 milestone remain separate results.
