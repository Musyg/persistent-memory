# Recherche par le sens, en local

[English](SEMANTIC.md) · [Serveur MCP](MCP.fr.md) · [Projection Qdrant](QDRANT.fr.md)

La recherche par mots-clés trouve les mots que vous avez tapés. Avec `--semantic`, `memory_search` trouve aussi ce que vous vouliez dire : « what is the pet's name » trouve « The cat is called Mika », et « quand est-ce qu'on déploie » trouve « Deploys happen on Tuesdays ». Rien d'autre à lancer : les vecteurs sont dans `vectors.db`, dans le dossier de la mémoire, et le modèle tourne dans le processus du serveur.

```sh
pip install "persistent-memory-mcp[semantic]"
persistent-memory-mcp --semantic --create < /dev/null    # premier lancement : télécharge le modèle, puis s'arrête
```

Dans `cmd` sous Windows, écrivez `< NUL` au lieu de `< /dev/null`.

L'installation de base ne change pas et n'a aucune dépendance. L'extra `semantic` ajoute [fastembed](https://github.com/qdrant/fastembed), qui fait tourner un modèle ONNX sur le processeur, et numpy avec lui.

## Ce qui est garanti

La projection locale suit les mêmes règles que la [projection Qdrant](QDRANT.fr.md) :

- **Des vecteurs, jamais de texte.** Une ligne de `vectors.db` contient un vecteur et une référence exacte (espace, artefact, version).
- **Elle ne fait que proposer.** Chaque candidat est relu par l'autorité, puis filtré par type, fenêtre de validité et préconditions, exactement comme un candidat trouvé par mots-clés. Une version retirée, remplacée ou invalidée est refusée même si son vecteur est encore là.
- **Elle suit l'autorité.** Après chaque écriture, les vecteurs des versions qui ne sont plus lisibles sont supprimés et les nouvelles versions lisibles sont calculées. Seules les nouvelles versions passent par le modèle.
- **Une ligne falsifiée est ignorée.** L'identifiant d'une ligne est dérivé de sa référence ; une ligne dont la référence ne correspond pas à l'identifiant est écartée.
- **Une panne ne casse rien.** Si le modèle ne peut pas être téléchargé ou chargé, s'il échoue sur un texte, ou si `vectors.db` est illisible, la projection passe à l'état `unavailable`, l'écriture est conservée et la recherche par mots-clés continue. Un modèle qui n'a pas pu se charger est réessayé après cinq minutes, pas à chaque écriture. Un `vectors.db` corrompu est reconstruit, de même qu'un fichier supprimé pendant que le serveur tourne. Si l'extra n'est pas installé, le serveur ne démarre pas et dit quel paquet manque.

## Brancher un client

Ajoutez `--semantic` aux arguments du serveur dans la configuration que `persistent-memory setup` a écrite, par exemple dans le `.mcp.json` de Claude Code ou le `claude_desktop_config.json` de Claude Desktop :

```json
"args": ["-m", "hermes_memory.mcp_server", "--store", "...", "--workspace", "default", "--semantic"]
```

Mettre `PERSISTENT_MEMORY_SEMANTIC=1` dans l'environnement du serveur fait la même chose. Lancez d'abord une fois la commande de préchauffage ci-dessus : le premier démarrage télécharge environ 1 Go, et certains clients n'attendent pas un serveur plus d'une minute. Les démarrages suivants chargent le modèle depuis `models/`, dans le dossier de la mémoire, en quelques secondes.

## Réglages

| Option | Par défaut | Rôle |
| --- | --- | --- |
| `--semantic` | désactivé | Fusionne une recherche vectorielle locale dans `memory_search` |
| `--embed-model` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Un modèle pris en charge par fastembed |
| `--semantic-min-score` | 0,3 avec le modèle par défaut, 0,5 sinon | Score cosinus sous lequel un candidat est ignoré |
| `--embed-url` | aucun | Utilise un service `/embeddings` compatible OpenAI au lieu du modèle intégré ; demande `--embed-model` |
| `--embed-query-prefix`, `--embed-document-prefix` | vide | Pour les modèles qui attendent un préfixe de tâche |

Avec `--embed-url`, l'extra n'est pas nécessaire : le serveur appelle le service avec la bibliothèque standard. Par exemple avec Ollama sur la même machine :

```sh
persistent-memory-mcp --semantic --embed-url http://127.0.0.1:11434/v1 --embed-model nomic-embed-text \
  --embed-query-prefix "search_query: " --embed-document-prefix "search_document: "
```

`--semantic` et `--qdrant-url` ne se combinent pas. Changer de modèle démarre un nouveau jeu de vecteurs ; les anciens restent dans `vectors.db` jusqu'à ce que vous supprimiez le fichier, ce qui est toujours sans risque : il est reconstruit à l'écriture ou au démarrage suivant. Si le modèle derrière un même nom se met à donner des vecteurs d'une autre taille, ses vecteurs sont reconstruits. Les vecteurs sont stockés en float32 petit-boutiste : le fichier se lit de la même façon sur toutes les machines.

## Choisir le modèle

Mesuré le 17 novembre 2026 dans un conteneur Linux dans le cloud (x86_64, processeur seul), fastembed 0.9.1. Douze faits synthétiques en anglais et en français, douze questions qui correspondent chacune à un fait sans reprendre ses mots-clés, quatre questions sans rapport. Le jeu est petit : c'est une indication, pas un banc d'essai.

| Modèle | Licence | Téléchargement | Bon fait classé premier | Score le plus bas d'un bon fait | Score le plus haut d'une question sans rapport | Temps par requête |
| --- | --- | --- | --- | --- | --- | --- |
| paraphrase-multilingual-mpnet-base-v2 (par défaut) | Apache-2.0 | 1,0 Go | 12 sur 12 | 0,25 | 0,22 | 20 ms |
| paraphrase-multilingual-MiniLM-L12-v2 | Apache-2.0 | 0,22 Go | 10 sur 12 | 0,15 | 0,21 | 8 ms |
| google/embeddinggemma-300m | Conditions Gemma | 1,24 Go | 12 sur 12 | 0,47 | 0,37 | 33 ms |
| Qwen/Qwen3-Embedding-0.6B-Q | Apache-2.0 | 1,12 Go | 11 sur 12 | 0,40 | 0,42 | 221 ms |

Le modèle par défaut classe le mieux, sous une licence permissive. Son seuil de 0,3 écarte les questions sans rapport au prix des correspondances les plus difficiles, que la recherche par mots-clés peut encore trouver. MiniLM se télécharge plus vite. embeddinggemma sépare plus nettement les questions liées des autres ; utilisez-le avec `--embed-model google/embeddinggemma-300m --semantic-min-score 0.42` si ses conditions vous conviennent.

## Limites

- Jusqu'à 5 000 entrées courantes par espace, comme l'index de recherche. Le calcul des scores lit tous les vecteurs de l'espace : environ 0,2 s pour 5 000 vecteurs de 768 dimensions en Python pur dans le conteneur ci-dessus, moins avec numpy, que l'extra installe.
- Les traces de tâches et les retours ne sont pas vectorisés ; les leçons et les entrées ordinaires le sont.
- Le modèle tourne sur le processeur. Le premier démarrage le télécharge ; prévoyez la place disque dans le dossier de la mémoire.
