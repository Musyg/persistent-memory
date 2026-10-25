# Bibliothèque, ligne de commande et service facultatif

[English](API.md)

Les fichiers locaux sont séparés : base de l'autorité, témoin de fraîcheur, base de contenu et index typé reconstruisible. Les appels `Authority.create/open` et `Memory.create/open` sont explicites ; l'ouverture n'adopte pas automatiquement un corpus existant. Les opérations du noyau sont également accessibles par `hermes-memory rpc` au moyen de requêtes JSON. Les références exactes contiennent `workspace`, `artifact_id` et `version_id`.

## Ligne de commande typée locale

Exécutez ces commandes depuis la distribution source, après avoir installé le paquet. Choisissez un répertoire local vide pour l'état :

```sh
mkdir example-state
hermes-memory --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db init
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json put --request examples/source.json
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json sync
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json context --request examples/query.json
```

Soumettre à nouveau une source identique renvoie à sa référence existante. Une mise à jour doit fournir la version courante dans `expected_version` ; ne déduisez pas l'identité du seul texte. `put` ne rafraîchit pas l'index de recherche. `sync` vérifie les limites configurées de documents et de contenu avant la publication de l'index. Aucune synchronisation automatique n'a lieu au moment d'une requête.

API Python : `TypedMemory.put(workspace, source_id, text, attributes, expected_version=None)`, `sync(workspace, max_documents=5000, max_content_bytes=33554432)` et `search(workspace, query, as_of=None, conditions=None, evidence_kinds=None, top_k=5, max_context_chars=2000, candidate_limit=100, render_source_references=False)`.

Avec `render_source_references=True`, chaque texte complet admis est suivi de sa référence JSON exacte. Le texte, la référence et les séparateurs `\n\n` comptent dans le même budget de caractères Python. Aucun couple texte/référence n'est renvoyé partiellement.

Les seules métadonnées admises sont `evidence_kind`, `valid_from`, `valid_until`, `observed_at`, `aliases`, `preconditions` et `confidence`. Les dates et heures sont des chaînes ISO en UTC se terminant par `Z` ; l'intervalle de validité inclut sa borne de début et exclut sa borne de fin. Les préconditions exigent une correspondance exacte avec les valeurs fournies. Les dates passées filtrent les versions courantes et ne permettent pas de récupérer des versions remplacées. La confiance est une métadonnée déclarée, pas une probabilité calibrée.

Un résultat `status=completed` peut ne contenir aucune preuve admissible. Consultez `context_empty`, `coverage`, `exclusions` et `complete` ; la complétude ne porte que sur les candidats gérés présents dans l'index à l'époque courante, pas sur l'ensemble du corpus historique. `index_stale`, `epoch_changed` et `unavailable` indiquent des états distincts qui empêchent l’achèvement normal de la requête. L’appelant doit les traiter explicitement, sans les confondre avec un résultat vide valide. Un changement de l'époque globale de l'autorité peut rendre périmé l'index d'un espace de travail pourtant sans rapport avec la modification.

## HTTP facultatif

Créez un fichier de jeton appartenant à l'utilisateur du service, avec les permissions 0600, et contenant au moins 32 caractères ASCII imprimables sans espace. Cet exemple génère un jeton sans l'afficher :

```sh
python -c "import os,secrets; p=os.open('example-state/token',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(p,secrets.token_urlsafe(48).encode()); os.close(p)"
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json --host 127.0.0.1 --port 8765 --token-file example-state/token serve
```

Routes typées : `POST /typed/v1/context` et `/typed/v1/status`, avec authentification par jeton bearer, schéma JSON strict, requêtes limitées à 16 Kio et réponses à 256 Kio. L'admission typée et la synchronisation sont des appels d'administration locaux, pas des routes HTTP.

L'API Python permet aussi d'exposer un espace de travail typé fixé par la configuration avec `make_server(memory, facade, token=token, typed_only=True)`. Ce mode refuse les routes du noyau `/rpc` et `/validate`, toutes les requêtes GET et les routes inconnues ; un jeton bearer absent ou incorrect est rejeté avant l'aiguillage de la requête. Les appels locaux `admit_source` et `sync` restent des opérations d'administration. La commande CLI `serve` conserve par défaut le serveur combiné ; `typed_only` est une option de l'API serveur Python. Le rendu des références peut aussi être activé dans la configuration de politique existante.

```python
from pathlib import Path
from hermes_memory.typed_facade import Facade, Policy, make_server

policy = Policy(enabled=True, render_source_references=True)
facade = Facade(memory, Path("example-state/index.db"), policy)
# The application supplies its configured token and owns server startup/shutdown.
server = make_server(memory, facade, token=token, typed_only=True)
```

Utilisez `Client(..., render_source_references=True)` avec cette politique de rendu. La politique du serveur détermine l'espace de travail et le mode de rendu ; les requêtes ne peuvent remplacer ni l'un ni l'autre. Une incompatibilité de rendu entre client et serveur est refusée. Cette délimitation par espace de travail et jeton n'est pas une authentification humaine ou vocale ; les espaces logiques restent distincts des listes de contrôle d'accès des utilisateurs.

**Le serveur combiné conserve aussi l'API privilégiée `/rpc` du noyau.** Le même jeton bearer couvre toutes les opérations du noyau ; aucune autorisation n'est définie par utilisateur ou par espace de travail. Ne donnez pas ce jeton à un agent non fiable et n'exposez pas le service comme une passerelle destinée à plusieurs clients indépendants. Ce processus est un serveur de référence fondé sur la bibliothèque standard, pas une passerelle de production exposable directement à Internet.

```python
from hermes_memory.typed_client import Client
client = Client("http://127.0.0.1:8765", "example-state/token",
                "typed-pilot-v1", "hermes-typed-pilot-v1")
result = client.context({"query": "copper", "conditions": {"approved": True}})
```

Le client désactive les mandataires réseau, les redirections et les nouvelles tentatives automatiques. Il vérifie exactement la politique, l'espace de travail, les références, la couverture et le budget, et conserve la provenance des échecs de transport. Le contrat de transport existant limite HTTP aux adresses numériques de boucle locale ou de réseau privé superposé ; utilisez HTTPS au-delà de ce périmètre. Le chargeur de jeton exige les règles Linux de propriété, de liens et de permissions des fichiers.

`typed_memory_tool.with_tool/execute_tool` est un auxiliaire facultatif pour les outils exposés aux modèles sous forme de fonctions. Sa configuration provient de l'environnement de l'application, jamais des arguments du modèle : `HERMES_TYPED_MEMORY_ENABLED=1`, URL, TOKEN_FILE, POLICY et WORKSPACE. Les noms de mode historiquement acceptés sont `hermes` (par défaut) et `legion` ; il s'agit de sélecteurs, pas de connexions à une flotte. Un traitement en cours conserve sa place dans la limite de concurrence jusqu'à sa fin, même si l'appelant annule sa requête.

## MCP sur l'entrée et la sortie standard

`hermes-memory --authority ... --anchor ... --store ... mcp` fournit la session stdio du noyau : initialisation, liste des outils et outils de lecture, de recherche et d'explication. Le transport est local et repose sur la confiance accordée à l'application qui le lance pour l'accès au système de fichiers. Il n'expose pas l'administration HTTP typée et ne constitue pas une plateforme MCP distante complète. Les tests du noyau fournis exercent un échange réel de messages JSON-RPC délimités par des retours à la ligne.
