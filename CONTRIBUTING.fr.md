# Contribuer

[English](CONTRIBUTING.md)

Partez d'un cas synthétique qui échoue et précisez l'invariant concerné : versions exactes, suivi des dépendances, retrait, confiance lors d'une restauration, disponibilité, couverture ou budget. Distinguez l'absence de preuve de l'indisponibilité d'une dépendance. Ne remplacez jamais l'échec d'un contrôle de dépendance par un résultat vide présenté comme un succès.

Les contributions utiles comprennent des contre-exemples synthétiques temporels ou multilingues, des comptes rendus d'installation indépendants, des adaptateurs de stockage qui préservent les références exactes et l'identité des espaces d'embeddings, des consignes de reprise plus claires et des améliorations de performance mesurées sur un périmètre délimité, sans modifier l'oracle qui vérifie le comportement attendu.

Exécutez la suite de tests des distributions installées décrite dans [le guide des tests](docs/TESTING.fr.md). Décrivez le comportement avant et après la modification, les ressources consommées, les hypothèses et les limites. Toute modification des octets d'autorité ou de récupération dont l'empreinte est fixée exige une revue explicite de compatibilité. N'affaiblissez pas les tests et ne modifiez pas les réponses attendues dans le seul but d'améliorer un score de benchmark.

Ne soumettez aucun souvenir privé, conversation, identifiant secret, jeton de compte modèle, journal de production, détail de topologie des hôtes, sauvegarde de base de données ou embedding personnel. Utilisez des jeux de données générés minimaux. Toute contribution doit préciser sa licence et sa provenance. La licence MIT de ce projet s'applique à son code original ; les éléments tiers nécessitent leurs propres autorisations compatibles.

Le [registre de politiques](PACKAGES.fr.md), facultatif, consigne les propositions, les évaluations, les admissions explicites et les retours à une version antérieure. Aucun algorithme d'apprentissage ne peut modifier les permissions des utilisateurs, contourner la revalidation par l'autorité ou promouvoir silencieusement une politique expérimentale.
