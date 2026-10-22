# Corrections, retraits et restauration d’une ancienne sauvegarde

[English](README.md) · [Fixture](FIXTURE.json) · [Synthèse](SUMMARY.json) · [Observations Linux A](LINUX-A.json) · [Observations Linux B](LINUX-B.json) · [Empreintes des sources](INPUTS.json)

Hermes et une référence SQLite indépendante qui conserve son autorité actuelle obtiennent **les mêmes résultats corrects** sur ces scénarios fonctionnels figés. Chacun restitue exactement les 751 lectures valides et bloque les 389 lectures interdites à chaque exécution. Une configuration SQLite qui restaure son ancienne autorité avec son ancien contenu laisse réapparaître 82 contenus retirés ou remplacés. L’essai établit ici l’utilité de conserver une autorité fraîche lors d’une restauration ; il ne démontre pas de supériorité sur une implémentation SQLite correctement protégée ni sur un autre produit de mémoire.

## Résultats par implémentation et par environnement Linux

| Observation | Hermes | SQLite, autorité conservée | SQLite, autorité restaurée à l’ancien état |
| --- | ---: | ---: | ---: |
| Cas conformes à l’oracle de l’état actuel | 100/100 | 100/100 | 80/100 |
| Lectures valides au contenu exact | 751/751 | 751/751 | 751/751 |
| Lectures interdites exposées | 0/389 | 0/389 | 82/389 |
| Contenus retirés exposés | 0/154 | 0/154 | 41/154 |
| Anciennes versions exposées | 0/123 | 0/123 | 41/123 |
| Lectures bloquées pendant la quarantaine | 92/92 | 92/92 | 92/92 |
| Vérifications d’absence du contenu actuel sans repli vers l’ancien | 20/20 | 20/20 | 20/20 |
| Rejets métier attendus correctement reconnus | 60/60 | 60/60 | 60/60 |
| Écritures tardives acceptées | 0/40 | 0/40 | 0/40 |
| Rejeux d’un retrait conservant leur reçu | 10/10 | 10/10 | 10/10 |
| Restaurations réconciliées | 20/20 | 20/20 | 20/20 |
| Erreurs inattendues / opérations non exécutées | 0 / 0 | 0 / 0 | 0 / 0 |

Les quatre catégories de lectures interdites sont disjointes et totalisent 389. Les mêmes 100 cas et 2 086 opérations par implémentation ont été exécutés dans deux environnements Linux : ordre, compteurs et observations normalisées concordent. Il s’agit de deux exécutions du même protocole, pas de 200 scénarios indépendants. Les 11 tests ciblés du produit passent aussi dans chaque environnement, y compris le lancement isolé et les contrôles négatifs de l’évaluateur. Aucun appel à un fournisseur de modèles n’a été nécessaire.

## Ce qui est comparé

Les dix familles couvrent les contrôles valides, les corrections et leurs chaînes de dépendances fortes, `indexes`, les citations documentaires `cites`, deux intentions CAS préparées depuis une même version puis validées successivement, les écritures tardives après retrait ou correction, la restauration après retrait, l’absence du contenu actuel dans une sauvegarde et l’isolation des espaces. Chaque famille comporte dix variantes explicites de contenu synthétique, de profondeur et d’ordre des opérations. La fixture a été figée avant exécution ; la graine vaut 20261022.

Un seul exécuteur rejoue les mêmes opérations sur les trois systèmes. L’oracle indépendant décrit les versions logiques et le texte exact attendu, accents et ponctuation compris. Les adaptateurs ne reçoivent jamais ces attentes. Un système qui bloque tout, renvoie le mauvais texte, fournit du contenu malgré un refus ou assimile une erreur SQLite quelconque à un rejet valide échoue aux contrôles. Les identifiants générés restent dans les observations brutes ; seule la vue utilisée pour comparer les deux exécutions les remplace par des références symboliques.

Les deux profils SQLite gèrent les versions immuables, la version courante, les marqueurs de retrait, le CAS, les retraits idempotents, les dépendances fortes et l’isolation. La comparaison principale accorde à Hermes et SQLite une autorité aussi fraîche, conservée hors des sauvegardes de contenu. Le troisième profil restaure aussi son ancienne autorité, sans preuve de fraîcheur extérieure. Ses 82 expositions restent des échecs de sûreté par rapport à l’état actuel, même si elles correspondent au fonctionnement prévisible de cette configuration. Restaurer toutes les preuves de confiance à un ancien état ne permet pas, à lui seul, de détecter ce retour en arrière.

## Reproduire sous Linux

Depuis le répertoire des sources extraites, installez le paquet dans un environnement neuf puis lancez les commandes :

```sh
python -m venv /tmp/lifecycle-check
/tmp/lifecycle-check/bin/pip install --no-deps .
/tmp/lifecycle-check/bin/python -I -B -m unittest discover -s tests -p test_product.py -v
/tmp/lifecycle-check/bin/python -I -B benchmarks/run_benchmark.py --compare-transitions --variants 10 --seed 20261022 > comparison.json
```

`--variants 1` propose un contrôle court de dix cas. `--comparison-fixture` permet de désigner explicitement la fixture. Le benchmark par défaut et le mode historique `--trajectories` gardent leur comportement antérieur. Le module SQLite est une référence de benchmark, pas un service destiné à la production.

## Portée et incident corrigé

Ces essais vérifient le cycle de vie par lecture de références, avec des opérations successives et une fermeture/réouverture logique. Ils ne mesurent ni le classement des résultats de recherche, ni des clients simultanés, ni l’arrêt brutal d’un processus, ni une coupure électrique, ni l’effacement physique, ni une supériorité de latence ou de qualité métier générale. Les injections de panne propres à l’outbox et à l’ancre Hermes restent dans les [preuves techniques séparées](../validation-20261021/TECHNICAL/README.fr.md), sans comparaison symétrique dans cet essai.

Le premier candidat natif passait dix tests ciblés, mais ne chargeait pas son module voisin sous `python -I`, avant toute observation comparative. Le correctif cible uniquement ce chargement et ajoute un vrai test du lancement isolé. La fixture, la référence indépendante et l’oracle n’ont pas changé ; seuls les résultats du candidat corrigé figurent ici. Cette étude n’ajoute aucun changement au runtime de production. L’[étude de confirmation avec et sans mémoire](../validation-20261022/README.fr.md) répond à une autre question ; ses résultats ne sont pas fusionnés avec ceux-ci.
