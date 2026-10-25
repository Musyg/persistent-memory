# Paquets Persistent Memory

[English](PACKAGES.md)

Le noyau mémoire est `hermes-memory-core==0.3.0a4`. Le registre de politiques facultatif est `hermes-policy-registry==0.2.0a2`. Les deux paquets s'installent indépendamment et n'ont aucune dépendance d'exécution l'un envers l'autre.

Le [guide du registre en français](packages/policy-registry/README.fr.md) et sa [version anglaise](packages/policy-registry/README.md) présentent le contrat et l'exemple synthétique. La [release 0.2.0a2 du registre](https://github.com/Musyg/persistent-memory/releases/tag/policy-registry-v0.2.0a2) contient son propre wheel, son archive source et ses sommes de contrôle. Les wheels et archives sources du registre sont des fichiers de release distincts ; une archive source du noyau seul ne contient pas le paquet du registre.

Depuis une copie complète du dépôt :

```sh
python3 -m pip install ./packages/policy-registry
hermes-policy-demo --directory ./new-policy-demo
```

Le registre consigne les propositions, les preuves, les admissions et les rollbacks. Il n'exécute aucune politique, n'en sélectionne aucune comme active, ne modifie pas les permissions à l'exécution et n'authentifie pas de juge. Les labels et durées de la démonstration sont des valeurs synthétiques inventées, pas des mesures de performance de récupération. La version 0.3.0a2 du noyau ajoute, en option, des contextes à références exactes et un mode de serveur Python limité aux routes typées. La version 0.2.0a2 du registre ajoute une évaluation explicite des effets de workflow : elle relie les identités immuables de la règle, de l'oracle et du jeu de données aux effets relus indépendamment dans le stockage. Un hôte fiable fournit la vérification et l'activation. Aucun des deux paquets n'entraîne les poids d'un modèle ni ne modifie les permissions. La récupération expérimentale R4 n'est pas incluse.

Le registre 0.2.0a2 a été qualifié depuis son wheel installé et depuis un wheel reconstruit à partir de son archive source : chaque exécution a passé 49 tests synthétiques sans échec, erreur ni test ignoré. Ces contrôles vérifient le contrat et l'installation ; ils ne constituent pas un score général de qualité mémoire. Les fichiers de release existants du noyau restent inchangés.

Le noyau 0.3.0a3 conserve les vérifications intégrales d'intégrité et réduit les opérations redondantes de sérialisation et d'analyse des données. Les [mesures de performance et contrôles de panne sur deux hôtes](benchmarks/efficiency-20261023/core-optimization-20261023/README.fr.md) et l'[étude de réutilisation d'expérience](benchmarks/action-20261023/experience/README.fr.md) présentent les nouvelles preuves. Les fichiers des releases antérieures restent inchangés.
