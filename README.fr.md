# Mémoire persistante pour agents IA

Persistent Memory propose deux paquets Python installables séparément : le noyau mémoire présenté ici et un [registre de politiques facultatif](PACKAGES.md). Leurs identifiants techniques restent `hermes-memory-core` et `hermes-policy-registry`. Le registre facultatif 0.2.0a2 évalue aussi les effets de workflow versionnés avec vérification indépendante par l'hôte ; voir [paquets et versions](PACKAGES.md).

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

## Rendre des faits vérifiés et contrôler leur remise

Le [rendu structuré](docs/STRUCTURED.fr.md), facultatif, transforme des faits explicitement revus en gabarits français finis, conserve les extraits et versions des sources et vérifie les contraintes de mots et de citations. La [frontière d'admission](docs/ADMISSION.fr.md) ajoute un dossier de dépendances revu par l'hôte, des contrôles d'autorité avant préparation et remise, des notices utiles et un résultat de livraison explicite.

```sh
python -m hermes_memory.admission_demo
```

Cette démonstration synthétique couvre une fiche revue, une information inconnue ou contradictoire, un retrait, une autorité absente, un tampon modifié, une limite de mots impossible à satisfaire et un effet sans accusé de réception. Ces API synchrones sont activées explicitement. Elles n'extraient pas les faits d'un brief libre et n'en vérifient pas la vérité sémantique. Un accusé de réception ne prouve pas la consommation en aval ; autorité et publication ne sont pas atomiques. Lire les contrats liés avant de brancher une autorité ou un consommateur réel.

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

La politique livrée conserve le contrat de recherche R3 avec un rendu facultatif des références exactes. Elle a amélioré la sélection de preuves dans une comparaison synthétique bornée, mais a dépassé son seuil de latence relative. Aucun gain de production, recherche sémantique, raisonnement sur graphe, accès aux versions historiques ou apprentissage automatique n'est revendiqué. R4 expérimental n'est pas inclus.

Avec `render_source_references=True` dans `TypedMemory.search`, chaque texte complet porte sa référence immuable validée. Texte, référence JSON et séparateurs partagent le budget de caractères ; un élément trop long est exclu entier. Le texte seul reste le mode par défaut.

## Interfaces et vérification

`hermes-memory` fournit initialisation, RPC, HTTP et MCP stdio. `hermes-memory-typed` ajoute inscription explicite, synchronisation, contexte et service facultatif. Les [commandes de l'API](docs/API.md) fonctionnent en local avec des chemins génériques.

L’API Python ajoute `make_server(..., typed_only=True)` : seules les routes POST typées authentifiées sont disponibles ; `/rpc`, `/validate` et les routes GET sont refusées. Configurez ensemble `Policy(render_source_references=True)` et `Client(..., render_source_references=True)` pour les contextes référencés. Ces options lient un espace configuré et un jeton porteur ; elles n’authentifient ni une personne ni une voix. Voir [API.md](docs/API.md).

Les routes HTTP typées et leur client sont en lecture seule. Le serveur combiné expose aussi le **RPC privilégié du noyau sous le même jeton** : il convient à une application de confiance, pas à un service multiutilisateur sans contrôle d'accès supplémentaire. Un espace logique n'est pas une ACL utilisateur. Aucun adaptateur public Qdrant ou LanceDB n'est annoncé.

```sh
python -m pip install build
python -m build
python3 -m venv /tmp/hermes-memory-check
/tmp/hermes-memory-check/bin/python -m pip install dist/hermes_memory_core-0.3.0a2-py3-none-any.whl
SOURCE="$PWD"
cd /tmp
/tmp/hermes-memory-check/bin/python -m unittest discover -s "$SOURCE/tests" -v
/tmp/hermes-memory-check/bin/python "$SOURCE/benchmarks/run_benchmark.py"
```

Les tests importent le paquet installé. Ils conservent 47 tests du noyau, 35 de recherche typée et 36 d'intégration portable, auxquels s'ajoutent les tests d'assemblage du paquet. Un test de branchement AST propre à une application privée est exclu du périmètre public et de ce compte. Le benchmark génère 24 notes synthétiques ; ses durées sont des observations, pas une supériorité générale.

La [démonstration LanceDB synthétique optionnelle](docs/BENCHMARK-LANCE.fr.md) vérifie la recherche explicite vecteur/texte et les contrôles de version courante et de retrait avec des vecteurs prédéfinis. Ses dépendances sont facultatives ; le benchmark par défaut reste inchangé.

## Limites à prendre en compte

- Conservez l'autorité actuelle et son témoin hors des sauvegardes de contenu restaurables seules.
- Une dépendance indisponible ou un index périmé doit rester visible ; une réponse vide ne signifie pas un système sain.
- Admission et synchronisation sont explicites et bornées, sans ingestion ou migration globale automatique.
- Le budget est exprimé en caractères Python, pas en tokens. R3 peut reparcourir le journal d'autorité à chaque opération ; sa montée en charge n'est pas illimitée.
- Un retrait bloque les futures lectures par la bibliothèque, sans rappeler les copies déjà transmises.
- L'application reste responsable du consentement, des droits, de la rétention et de la protection de ses fichiers.

Licence MIT. `PROVENANCE.json` décrit la sélection et les transformations. Le registre de politiques facultatif est une distribution séparée : voir [PACKAGES.md](PACKAGES.md). Il n'active aucune politique et n'accorde aucun droit d'exécution.

## Comparaison observée avec et sans mémoire

L’[étude de confirmation](benchmarks/validation-20261022/README.fr.md) porte sur 100 scénarios synthétiques distincts, répétés trois fois dans chaque configuration : les 1 500 réponses ont été remises et les 3 000 jugements IA sont complets. GPT-6 Luna réussit 298 réponses sur 300 avec mémoire (99,33 %), contre 29 sur 300 sans mémoire ; GPT-6.1 Sol atteint 300 sur 300, contre 30 sur 300. Le gain principal de Luna est de 89,67 points de pourcentage, avec un intervalle nominal à 95 % de 89 à 90 points ; la borne inférieure unilatérale à 95 % de sa réussite est de 98 %. La recherche lexicale réussit 294 réponses sur 300 : l’intervalle d’effet mémoire/recherche lexicale à 95 %, de −0,33 à +3,33 points, n’établit pas de supériorité de la mémoire.

La page de l’étude détaille la méthode, les échecs, les limites et le recalcul hors réseau. Ces scénarios courts et structurés ont été évalués par deux juges IA, sans audit humain externe de qualité. La [campagne antérieure de 500 tâches et son erratum d’évaluation](benchmarks/validation-20261021/README.fr.md), les [résultats de fiabilité et de charge](benchmarks/validation-20261021/TECHNICAL/README.fr.md) et le [pilote applicatif exploratoire de huit tâches](docs/MEMORY-COMPARISON.md#français) apportent des éléments distincts ; leurs comptes et leur périmètre ne sont pas fusionnés avec cette étude de confirmation.

Le [comparatif du cycle de vie](benchmarks/lifecycle-20261022/README.fr.md) rejoue séparément 100 trajectoires figées sur trois implémentations, dans deux environnements Linux. Hermes et SQLite avec autorité conservée préservent chacun les 751 lectures valides et bloquent les 389 lectures interdites par exécution ; restaurer l’ancienne autorité avec l’ancien contenu expose 82 contenus retirés ou remplacés. La comparaison principale aboutit à une égalité sur ces garanties ; les observations synthétiques complètes sont disponibles pour vérification et reproduction.

L’[analyse secondaire d’efficacité](benchmarks/efficiency-20261023/README.fr.md) relie les 1 500 réponses historiques à leur usage déclaré. Luna avec mémoire consomme 4,70 % de tokens en moins et coûte 3,75 % de moins en génération estimée que la recherche lexicale, avec un p95 légèrement plus élevé et une supériorité de qualité non établie. C’est une empreinte observée, sans comparaison à dépense identique ni dominance générale ; l’analyse n’effectue aucun nouvel appel fournisseur.

L’[étude de transfert vers des fichiers](benchmarks/action-20261023/README.fr.md) vérifie des actions CSV/JSON entre trois processus distincts. Sur 24 mondes issus de 12 structures, Luna avec mémoire réussit 66/72 tâches contre 35/72 sans mémoire, avec une réponse indisponible dans ce dernier bras ; Sol atteint 72/72 contre 36/72. La référence lexicale versionnée obtient 67/72 et 72/72 : aucun avantage sur cette référence n’est établi. Données synthétiques, échecs initiaux, calibration et amendement du protocole sont conservés avec les commandes de reproduction.
