# Hermes Policy Registry

[English](README.md)

Ce registre conserve des politiques immuables, leurs preuves d'évaluation, les admissions explicites et les retraits. Il utilise SQLite et la bibliothèque standard Python. Il fonctionne indépendamment de `hermes-memory-core`, sans modèle, service ni données privées.

Cinq familles peuvent être représentées : prompt, récupération, routage, workflow et compétence. Cette version fournit **un adaptateur d'évaluation de rapports de récupération**. Elle ne fournit pas cinq optimiseurs.

## Installer et essayer

Python3.11 ou ultérieur. L'installation, les permissions de fichiers et les exemples sont qualifiés sur Linux.

```sh
python3 -m pip install ./packages/policy-registry
hermes-policy-demo --directory ./nouvelle-demo-politiques
```

Depuis le dossier de ce paquet, utiliser `python3 -m pip install .`. La démonstration refuse un dossier de sortie existant. Elle crée des expériences et évaluations synthétiques avec leurs empreintes, propose et évalue une politique, l'admet avec un validateur de fixture explicitement approuvé, rouvre SQLite puis révoque une source. L'état effectif passe de `admitted` à `rollback` ; aucune politique n'est activée à l'exécution.

La fixture incluse `fixtures/demo.json` contient des **labels, durées et identifiants inventés**. Ce ne sont pas des mesures de récupération. La démonstration n'appelle aucun modèle ni moteur de recherche. Son callback est un exemple pour des entrées synthétiques maîtrisées, pas un adaptateur d'autorité destiné à la production.

```sh
python3 -m unittest discover -s tests -v
hermes-policy --help
```

La distribution source contient20 tests auteur,14 tests indépendants et2 tests de démonstration publique. Tous utilisent des données synthétiques, sans chemin privé ni service réel.

## Contrats

`Registry.create(path, load_learning_records(), protocol)` crée exclusivement une nouvelle base sous un parent privé existant. Les opérations sont `propose`, `add_report`, `add_record`, `evaluate_retrieval_reports`, `admit`, `revoke`, `rollback` et `inspect`. Toute transition vérifie la séquence attendue avant écriture.

La configuration immuable désigne les empreintes exactes des politiques exécutées, budgets compris. Toutes les variantes déclarées doivent avoir été exercées. L'adaptateur vérifie les liens entre exécution, politique, sources, résultats, empreintes d'enregistrements, grille et révision du juge. Coût et qualité portent sur le même jeu de données ; les durées candidat et référence sont appariées par cas et répétition. Les doublons ne peuvent pas gonfler le nombre d'observations.

Un résultat observé faux ou nul reste un échec observé. Une donnée indisponible, non échantillonnée ou retirée reste non observée. Une correction ou un retrait invalide l'ancienne évaluation ; la révocation d'une source rend l'admission dépendante inefficace. Les enregistrements sont conservés. Un rollback est terminal pour cet artefact ; un code ou une configuration révisés ont une nouvelle identité.

L'admission exige une revalidation fraîche des dépendances par un callback externe. Son raccordement à une autorité fiable relève de l'appelant. Le registre n'authentifie ni ce callback ni le juge ; il ne déploie, n'exécute et ne sélectionne aucune politique active. Les droits ne sont pas modifiés par l'apprentissage.

La commande existante `hermes-policy pilot --r3-report ... --r4-report ... --output ...` attend le format versionné précis de l'adaptateur. Elle importe les mesures fournies et refuse toute activation automatique. Ces rapports ne sont pas inclus : la démonstration synthétique ci-dessus est autonome. Les tests illustrent leurs contrats exacts. L'option `--learning-records` n'accepte qu'un fichier dont l'empreinte correspond au contrat inclus.

## Limites

Les empreintes prouvent une identité et une cohérence, pas une signature ni l'authenticité d'une mesure. Le système de fichiers local est supposé maîtrisé. Cette version ne protège pas contre une restauration ancienne de la base complète, n'offre ni transaction distribuée, ni ACL par utilisateur, ni garantie de transport « exactement une fois ». Une panne peut laisser l'issue d'un commit SQLite incertaine.

Chaque rapport canonique est limité à8Mio et une évaluation à256 liens d'exécution. Aucun quota complet ne borne la taille totale de la base ; les performances sur un grand historique ne sont pas qualifiées. Linux est la plateforme testée. Provenance du contrat générique dans [NOTICE.md](NOTICE.md), licence MIT dans [LICENSE](LICENSE).
