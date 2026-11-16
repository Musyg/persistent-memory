# End-to-end runs with real models, 16 November 2026

[README](https://github.com/Musyg/persistent-memory/blob/main/README.md) · [MCP server](https://github.com/Musyg/persistent-memory/blob/main/docs/MCP.md)

The framework checks of 15 November called no model. These runs put a real model in front of the MCP server, on Linux with Python 3.12, persistent-memory-mcp installed in a new virtual environment.

Six turns, each a new agent run with no chat history and a new server process, so that whatever the agent knows comes from the store:

1. "Remember this: the staging database listens on port 6543."
2. "Which port does the staging database listen on?"
3. "Update your memory: the staging database now listens on port 6544."
4. "Which port does the staging database listen on?"
5. "The staging database has been decommissioned. Withdraw that fact from your memory."
6. "Which port does the staging database listen on?"

Eight checks follow (`checks` in each report): the right tool called at turns 1, 2, 3 and 5, the right port at turns 2 and 4, no port at turn 6, and an empty search in the store at the end.

| Client and model | Server | Checks passed |
| --- | --- | --- |
| Claude Code 2.1.325 headless, model `claude-opus-5` | this branch | 8 of 8 (two runs, the second is `claude-code-run.json`) |
| OpenAI Agents SDK 0.24.0, `gpt-oss:20b` through Ollama | 0.4.0a3 from PyPI | 4 of 8, only the checks passed by doing nothing: no fact was ever stored (`gpt-oss-20b-with-0.4.0a3.log`) |
| same | this branch | 4, 6 and 4 of 8 in three runs (`gpt-oss-20b-run*.json`) |

What the 20B model got wrong with 0.4.0a3, and what this branch changes:

- It filled unused fields with `""`, `[]` or `{}`. An empty `valid_until` was refused as a malformed time, and `kinds: []` filtered out every result. Empty optional values now count as absent.
- It used kinds that do not exist (`fact`, `info`, `config`) and the refusal only said `invalid_evidence_kind`. Refusals now list the allowed values, the expected type and range, or the time format, and in every case the model fixed its call within two tries.
- It invented `valid_from` times later than its own searches, and conditions it never supplied again, so its facts became invisible to it. The tool descriptions now say to leave those fields out unless the user gave them.
- It sent `max_chars: 0` and got an empty result. A number outside the advertised range is now refused, with the range.

What remains is the model's own choice of tools: in two runs out of three it stored the new port as a new fact instead of calling `memory_correct`, and in all three it found the fact to withdraw but did not call `memory_withdraw`. Claude Code followed the same instructions without a miss. These runs are not a benchmark: one scenario, few runs, one local model.

To run them again: `run_e2e.py` needs `openai-agents` and an OpenAI-compatible endpoint (Ollama at `127.0.0.1:11434` here); `cc_e2e.py` needs a logged-in `claude` command. Both expect `persistent-memory-mcp` in `./venv`.

---

# Essais de bout en bout avec de vrais modèles, 16 novembre 2026

Les contrôles des frameworks du 15 novembre n'appelaient aucun modèle. Ici, un vrai modèle utilise le serveur MCP, sous Linux avec Python 3.12, persistent-memory-mcp installé dans un environnement virtuel neuf. Six tours, chacun sans historique et avec un nouveau processus serveur : retenir le port 6543, le demander, le corriger en 6544, le redemander, retirer le fait, le redemander. Huit contrôles par essai.

- Claude Code en mode headless, modèle `claude-opus-5` : 8 sur 8, deux fois.
- `gpt-oss:20b` via Ollama et l'OpenAI Agents SDK, avec la 0.4.0a3 : 4 sur 8, uniquement les contrôles qu'on passe sans rien faire, aucun fait enregistré. Avec cette branche : 4, 6 et 4 sur 8.

La branche traite les valeurs vides comme absentes, indique dans chaque refus comment corriger l'appel, refuse les nombres hors de l'intervalle annoncé, et précise dans les descriptions de laisser de côté les champs facultatifs que l'utilisateur n'a pas donnés. Ce qui reste vient du choix d'outils du modèle de 20 milliards de paramètres : il enregistre souvent une correction comme un nouveau fait, et ne retire pas le fait qu'il a pourtant trouvé. Ce n'est pas un banc d'essai : un seul scénario, peu d'essais, un seul modèle local.
