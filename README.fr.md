# Talos Memory

Talos Memory propose deux paquets Python installables séparément : le noyau mémoire présenté ici et un [registre de politiques facultatif](PACKAGES.md). Leurs identifiants techniques restent `hermes-memory-core` et `hermes-policy-registry`.

[English](README.md) · [API et service](docs/API.md) · [Contrat de reprise](docs/RECOVERY.md) · [Contribuer](CONTRIBUTING.md)

Une bibliothèque de mémoire versionnée pour les applications et les agents qui doivent savoir **de quelles preuves dépend une réponse, si elles restent valables et ce qui se passe après un retrait ou une restauration ancienne**.

Python 3.11+, SQLite avec FTS5, bibliothèque standard uniquement. Linux est la plateforme qualifiée. Aucun modèle, poids, compte, serveur permanent ni base externe n'est nécessaire. Cette version alpha contient du code réutilisable et des exemples synthétiques ; elle ne distribue pas un système mémoire privé ni ses données.

## Essayer un parcours complet

Depuis la distribution source, dans un environnement neuf :

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/hermes-memory-demo --directory /tmp/hermes-memory-exemple
```

Choisissez un répertoire inexistant. Un premier acteur inscrit deux sources synthétiques et un compte rendu qui dépend de leurs références exactes. Un second acteur rouvre le stockage, retire une source et vérifie que le compte rendu devient illisible, alors que la source indépendante reste accessible. La restauration d'une ancienne copie du contenu démarre en quarantaine ; après contrôle avec l'autorité actuelle conservée, elle ne réadmet pas la source retirée.

Le résultat détaille les invariants vérifiés. Il ne promet ni effacement physique, ni désapprentissage d'un modèle, ni détection d'un retour arrière simultané du contenu, de l'autorité et de son témoin de fraîcheur.

## Utiliser la bibliothèque

```python
from pathlib import Path
from hermes_memory import Authority, Memory
from hermes_memory.typed_memory import TypedMemory

root = Path("etat-exemple")
root.mkdir()
authority = Authority.create(root / "autorite.db", root / "temoin.json")
memory = Memory.create(root / "contenu.db", authority)
typed = TypedMemory(memory, root / "recherche.db")
ref = typed.put("demo", "procedure", "Cuivre : suivre la procédure approuvée.", {
    "evidence_kind": "procedure", "preconditions": {"hors_tension": True}
})["ref"]
typed.sync("demo")
result = typed.search("demo", "cuivre", conditions={"hors_tension": True},
                      max_context_chars=1000)
assert result["items"][0]["ref"] == ref
```

Chaque référence contient un espace, une identité d'objet stable et une version immuable. Les mises à jour vérifient la version attendue. Les dérivés déclarent leurs parents exacts. Les lectures contrôlent versions et retraits ; l'index est reconstructible et ne constitue jamais une autorité.

Les enveloppes typées distinguent document, observation, hypothèse, procédure, tâche et feedback. Elles peuvent porter des intervalles de validité, alias et préconditions exactes. La recherche lexicale FTS5 retourne un contexte borné, ses références, sa couverture et ses exclusions. Une hypothèse reste présentée comme telle ; la confiance déclarée ne devient ni score de qualité appris ni poids de classement.

La politique livrée est R3, figée. Elle a amélioré la sélection de preuves dans une comparaison synthétique bornée, mais a dépassé son seuil de latence relative. Aucun gain de production, recherche sémantique, raisonnement sur graphe, accès aux versions historiques ou apprentissage automatique n'est revendiqué. R4 expérimental n'est pas inclus.

## Interfaces et vérification

`hermes-memory` fournit initialisation, RPC, HTTP et MCP stdio. `hermes-memory-typed` ajoute inscription explicite, synchronisation, contexte et service facultatif. Les [commandes de l'API](docs/API.md) fonctionnent en local avec des chemins génériques.

Les routes HTTP typées et leur client sont en lecture seule. Le serveur combiné expose aussi le **RPC privilégié du noyau sous le même jeton** : il convient à une application de confiance, pas à un service multiutilisateur sans contrôle d'accès supplémentaire. Un espace logique n'est pas une ACL utilisateur. Aucun adaptateur public Qdrant ou LanceDB n'est annoncé.

```sh
python -m pip install build
python -m build
python3 -m venv /tmp/hermes-memory-check
/tmp/hermes-memory-check/bin/python -m pip install dist/hermes_memory_core-0.2.0a1-py3-none-any.whl
SOURCE="$PWD"
cd /tmp
/tmp/hermes-memory-check/bin/python -m unittest discover -s "$SOURCE/tests" -v
/tmp/hermes-memory-check/bin/python "$SOURCE/benchmarks/run_benchmark.py"
```

Les tests importent le paquet installé. Ils conservent 47 tests du noyau, 35 de recherche typée et 36 d'intégration portable, auxquels s'ajoutent les tests du produit. Un test de branchement AST propre à une application privée est exclu du périmètre public et de ce compte. Le benchmark génère 24 notes synthétiques ; ses durées sont des observations, pas une supériorité générale.

## Limites à prendre en compte

- Conservez l'autorité actuelle et son témoin hors des sauvegardes de contenu restaurables seules.
- Une dépendance indisponible ou un index périmé doit rester visible ; une réponse vide ne signifie pas un système sain.
- Admission et synchronisation sont explicites et bornées, sans ingestion ou migration globale automatique.
- Le budget est exprimé en caractères Python, pas en tokens. R3 peut reparcourir le journal d'autorité à chaque opération ; sa montée en charge n'est pas illimitée.
- Un retrait bloque les futures lectures par la bibliothèque, sans rappeler les copies déjà transmises.
- L'application reste responsable du consentement, des droits, de la rétention et de la protection de ses fichiers.

Licence MIT. `PROVENANCE.json` décrit la sélection et les transformations. Le registre de politiques facultatif est une distribution séparée : voir [PACKAGES.md](PACKAGES.md). Il n'active aucune politique et n'accorde aucun droit d'exécution.
