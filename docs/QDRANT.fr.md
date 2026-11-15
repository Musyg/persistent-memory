# Projection Qdrant

[English](QDRANT.md) · [Surface d'opérations](OPERATIONS.fr.md) · [Serveur MCP](MCP.fr.md)

La recherche lexicale trouve les mots tapés. Une projection vectorielle trouve aussi ce qu'on voulait dire : « firewall » peut trouver une note sur le « pare-feu ». `hermes_memory.qdrant_projection` ajoute Qdrant comme projection, par son API REST et la seule bibliothèque standard de Python ; aucune bibliothèque cliente n'est nécessaire.

## Ce qu'elle garantit

- **Qdrant ne contient jamais le contenu.** Un point porte un vecteur et une référence exacte (espace, artefact, version), rien d'autre.
- **Qdrant ne fait que proposer.** Chaque candidat est relu à travers l'autorité, puis filtré par type, fenêtre de validité et préconditions, exactement comme un candidat lexical. Une version retirée, remplacée ou invalidée est refusée même si son vecteur est encore dans Qdrant.
- **Qdrant suit l'autorité.** Après chaque écriture, les points des versions qui ne sont plus lisibles sont supprimés et les nouvelles versions lisibles ajoutées. Si Qdrant est arrêté, l'écriture réussit quand même, la projection passe à `unavailable` et la synchronisation suivante rattrape le retard.
- **Un point falsifié est ignoré.** L'identifiant d'un point dérive de sa référence ; une charge utile qui ne correspond pas à son identifiant est écartée.
- **Les parents des leçons restent dehors.** Les traces de tâches et les retours ne sont pas vectorisés ; seules les leçons et les entrées ordinaires le sont.

## L'utiliser

Il faut un serveur Qdrant et un point d'accès `/embeddings` compatible OpenAI (OpenAI, serveur llama.cpp, Ollama, vLLM, text-embeddings-inference...).

```python
from hermes_memory.persistent import PersistentMemory
from hermes_memory.qdrant_projection import OpenAIEmbeddings, QdrantProjection

memory = PersistentMemory("state/memory", "team-notes", create=True)
embed = OpenAIEmbeddings("http://127.0.0.1:8000/v1", "nomic-embed-text", api_key_env="EMBED_KEY")
memory.attach_projection(QdrantProjection(memory, "http://127.0.0.1:6333", embed, min_score=0.5))
memory.search("which port does the test machine use")
```

`search` fusionne alors les candidats lexicaux et vectoriels (fusion par rang réciproque) et indique l'état de la projection sous `semantic`. Avec le serveur MCP :

```sh
persistent-memory-mcp --store ~/.persistent-memory --create \
  --qdrant-url http://127.0.0.1:6333 \
  --embed-url http://127.0.0.1:8000/v1 --embed-model nomic-embed-text \
  --embed-query-prefix "search_query: " --embed-document-prefix "search_document: " --qdrant-min-score 0.3
```

Les clés d'API sont lues dans les variables d'environnement nommées par `--qdrant-api-key-env` et `--embed-api-key-env`, jamais sur la ligne de commande. Le fournisseur Hermes Agent prend les mêmes réglages sous `qdrant_url`, `embed_url` et `embed_model` dans sa configuration.

## Réglages

| Réglage | Défaut | Sens |
| --- | --- | --- |
| `collection` | `persistent-memory-<espace>-<empreinte du modèle>` | Changer de modèle d'embeddings utilise une nouvelle collection. |
| `min_score` | `0.5` | Score cosinus sous lequel un candidat est considéré sans rapport. Une recherche vectorielle a toujours un plus proche voisin ; ce seuil l'empêche de remplir les résultats de bruit. À ajuster selon le modèle. |
| `query_prefix`, `document_prefix` | vide | Texte placé avant les requêtes et les entrées avant vectorisation, pour les modèles qui attendent un préfixe de tâche (`search_query: ` / `search_document: `, `query: ` / `passage: `). |

Jusqu'à 5 000 entrées courantes par espace de travail sont projetées, comme pour l'index lexical.

## Observé

Le 14 novembre 2026, sous Linux, avec un serveur Qdrant 1.20.0 jetable et le modèle `nomic-embed-text-v2-moe` servi par un point d'accès compatible OpenAI :

- `tests_integration/test_qdrant_server.py` : les trois tests ont réussi (cycle de vie sur un vrai serveur, point périmé refusé par la revalidation, paraphrase trouvée puis retirée).
- Avec ce modèle et les préfixes `search_query: ` / `search_document: `, une question liée a obtenu un score d'environ 0,33 et les entrées sans rapport entre 0,08 et 0,11 ; `min_score` 0,3 a donc été utilisé. Avec la valeur par défaut 0,5, rien n'aurait été trouvé : il faut l'ajuster au modèle.
- Par `persistent-memory-mcp --transport http` et le SDK MCP officiel pour Python 2.3.0 : une question reformulée sans aucun mot commun a trouvé l'entrée, qui n'était plus renvoyée après son retrait.

Ce sont des contrôles d'intégration sur quelques entrées, pas une mesure de qualité de recherche.

## Tests

`tests/test_qdrant_projection.py` et la batterie commune des adaptateurs tournent contre une imitation en mémoire des appels REST. `tests_integration/test_qdrant_server.py` tourne contre un vrai serveur Qdrant jetable, et en option un vrai modèle d'embeddings ; sans eux, ses tests sont signalés comme sautés, avec la raison.
