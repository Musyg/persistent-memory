# Operational replay of the public component

Eight fresh answers were generated in a second Linux environment: two synthetic tasks, one French and one English, two models, with and without memory. A mechanical rule fixed the tasks before this replay. All eight calls completed without retries, and returned model IDs matched the requested models.

[REPLAY.json](REPLAY.json) preserves each task, retrieval query, supplied context, answer, status and token count. Context is present with memory and empty without it. [SELECTION.json](SELECTION.json) and [SOURCE-PINS.json](SOURCE-PINS.json) record the selection and source hashes; [MANIFEST.json](MANIFEST.json) binds this projection’s files.

The reserved cap was USD0.1806336. Reported token usage gives a USD0.0061570 estimate at the retained global Standard prices, without cache discounts; the actual invoice is unknown.

This small replay demonstrates the installed public path working end to end. Its answers remain separate from the main study and do not change its results. Two tasks cannot establish general answer quality; no new statistical score, independent human quality audit or byte-identical fresh text is claimed.
