# Provider de provenance pour Hermes Agent

[English](README.md)

Un fournisseur de mémoire pour [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research), construit sur le cœur de mémoire de ce dépôt. Hermes Agent garde ses fichiers intégrés `MEMORY.md` et `USER.md` ; ce provider ajoute une mémoire à long terme dont chaque rappel est revalidé au moment de la lecture.

Distribution `hermes-agent-provenance` 0.1.0a1, module `hermes_agent_provenance`, nom du provider `provenance`. Version alpha. C'est une intégration indépendante, sans lien avec Nous Research.

## Ce qu'il fait

- **Rappel revalidé.** Avant chaque tour, le provider cherche dans la mémoire et n'injecte que les éléments que l'autorité courante autorise encore. Une source retirée ou remplacée n'atteint jamais le modèle.
- **Admission explicite.** Rien n'est enregistré automatiquement : `sync_turn` est volontairement vide. Le modèle n'enregistre un fait qu'en appelant `provenance_remember`.
- **Avis de retrait par session.** Le provider note quelles sources ont été montrées à quelle session Hermes. Quand l'une d'elles est retirée, depuis cette session ou d'ailleurs, le tour suivant de cette session commence par un avis qui demande au modèle de ne plus s'en servir, y compris dans ses propres réponses précédentes. Chaque session est avertie une seule fois par source.
- **Rapport d'exposition.** `hermes-provenance-exposure` liste toutes les sessions qui ont vu une source retirée depuis. Code de sortie 1 dès qu'une session est exposée.

Outils proposés au modèle :

| Outil | Effet |
|---|---|
| `provenance_search` | Recherche lexicale parmi les éléments lisibles, avec leur `source_id` |
| `provenance_remember` | Admet un élément typé (`observation`, `document`, `procedure`, `task`, `hypothesis`, `feedback`) |
| `provenance_withdraw` | Retire une source et tout ce qui en dérive. Ce n'est pas un effacement physique |
| `provenance_explain` | Versions, lisibilité et dépendants d'une source ; métadonnées seulement |

Les sous-agents et les tâches planifiées (`agent_context` autre que `primary`) n'ont que les deux outils de lecture.

## Installation

Le provider s'installe dans l'environnement Python qui exécute Hermes Agent, à côté du cœur de mémoire. Depuis une copie de ce dépôt :

```sh
python -m pip install . ./packages/hermes-agent-provider
```

Puis on le choisit dans le `config.yaml` du profil Hermes, ou avec `hermes memory setup` :

```yaml
memory:
  provider: provenance
```

`hermes memory status` doit afficher `provenance` comme installé et actif. Hermes Agent le trouve par le point d'entrée `hermes_agent.memory_providers` ; aucun fichier n'est copié dans Hermes.

Hermes Agent épingle lui-même ses dépendances pour Python 3.14 et les résout depuis son `uv.lock`. Une copie des sources installée avec `uv sync --locked` (plus l'extra `mcp` si des serveurs MCP sont utilisés) a fonctionné ; un simple `pip install -e` de la copie ne se résolvait pas.

## Stockage et réglages

L'état vit dans le profil, sous `$HERMES_HOME/provenance/` : `authority/`, `anchor/`, `content.db`, `index.db` et `exposure.db`. Les réglages sont lus dans `$HERMES_HOME/provenance/config.json` :

| Clé | Défaut | Sens |
|---|---|---|
| `workspace` | `hermes` | Espace de mémoire de ce profil |
| `prefetch` | `true` | Rappel avant chaque tour |
| `top_k` | `5` | Éléments rappelés par tour |
| `max_context_chars` | `2000` | Budget en caractères du bloc rappelé |
| `allow_withdraw` | `true` | Proposer `provenance_withdraw` au modèle |

Les garanties de reprise du cœur exigent de garder l'autorité et son témoin de fraîcheur hors des sauvegardes qui ne contiennent que le contenu ; voir [RECOVERY.md](../../docs/RECOVERY.md).

## Vérifications

`tests/` s'exécute sans Hermes Agent, avec les remplaçants de `_compat.py` ; il fait partie de la vérification des distributions installées de ce dépôt (`scripts/check_distributions.py`). `tests_hermes_agent/` fait passer le provider par le `MemoryManager` de Hermes Agent et doit être lancé depuis un environnement Hermes Agent ; ailleurs, il est rapporté SKIPPED avec sa raison.

Une observation de bout en bout, sur un hôte Linux le 14 novembre 2026, avec Hermes Agent au commit `d93e9ba4` et un Qwen3.5-9B local servi par llama.cpp : dans une même session, l'agent a enregistré un numéro de port avec `provenance_remember`, puis l'a donné depuis le bloc rappelé avec son `source_id`. La source a ensuite été retirée hors de la session. Interrogé de nouveau dans cette session, dont l'historique contenait encore deux fois l'ancienne réponse, l'agent a répondu que l'information avait été retirée, sans appeler d'outil. C'est une observation unique, pas un benchmark.

## Limites

- L'avis ne retire pas le texte du stockage de sessions de Hermes Agent, qui garde la transcription. La révocation contrôle les lectures futures via cette bibliothèque ; elle ne peut pas rappeler ce qui a déjà été copié ailleurs.
- La recherche est lexicale (FTS5). Pas d'embeddings, pas de recherche sémantique.
- Hermes Agent n'accepte qu'un seul provider de mémoire externe à la fois.
- Le retrait bloque les lectures futures ; ce n'est pas un effacement physique.
- Les modules `agent` et `tools` sont importés depuis Hermes Agent quand il est présent ; un autre paquet qui exposerait ces noms serait pris pour lui.

Licence MIT, voir [LICENSE](LICENSE). La provenance des fichiers est consignée dans [PROVENANCE.json](PROVENANCE.json).
