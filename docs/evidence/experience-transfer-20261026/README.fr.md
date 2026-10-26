# Réutiliser une expérience dans une autre mission et avec un autre agent

26 octobre 2026 · [English](README.md)

Deux observations d'intégration complètent l'[étude comparative d'apprentissage entre missions](../../../benchmarks/action-20261023/experience/README.fr.md). Elles vérifient le raccord à des agents réels ; elles ne sont pas ajoutées aux comptes de cette étude. Toutes deux reprennent le même oracle de treize scénarios : leurs comptes ne s'additionnent pas en scénarios distincts.

## Une nouvelle mission, avec et sans expérience

Deux sessions du même agent ont reçu le même message, le même code source, le même modèle et les mêmes limites. L'une travaillait sans expérience mémorisée ; l'autre recevait automatiquement deux enseignements d'une mission antérieure.

| Mesure | Sans expérience | Avec expérience |
| --- | ---: | ---: |
| Tests métier réussis | 7 sur 7 | 7 sur 7 |
| Scénarios couverts | 13 | 13 |
| Requêtes fournisseur observées | 2 | 2 |
| Contexte mémoire ajouté | 0 caractère | 873 caractères |
| Durée de la requête | 5,57 s | 6,74 s |

Les empreintes du système effectivement sérialisé confirment l'absence de contexte mémoire dans la première session et son ajout dans la seconde. Les deux propositions ont été testées sans retouche. Cette paire aboutit à une égalité : elle vérifie la transmission automatique, sans établir de gain supplémentaire de qualité ou d'efficacité. La revue indépendante valide 29 contrôles.

## Un second agent reprend l'expérience

Un autre agent a ensuite récupéré un souvenir issu d'une mission antérieure et produit une proposition de code de 1 905 octets en une requête utilisateur, sans nouvelle tentative. La requête a duré 21,54 secondes. La génération utilisait un modèle local, avec repli cloud désactivé.

Le code retourné a été soumis tel quel au banc figé : sept méthodes, treize scénarios, dont dix sous-tests balisés, passent sans échec ni saut. Il s'agit d'une mission, pas de treize tâches indépendantes. La revue vérifie l'identité exacte du souvenir relu, l'artefact réellement retourné, les contrôles natifs et la libération des ressources temporaires. Ses 44 contrôles passent ; les services lancés pour l'essai sont revenus à l'arrêt.

Le souvenir est attesté dans le résultat du second agent. Son raccord au prompt est qualifié structurellement ; le prompt sortant sérialisé n'a pas été capturé pendant cette mission. Sans comparaison avec et sans mémoire sur ce second agent, aucun gain causal n'est attribué à cette observation.

Le banc porte sur des contrats ciblés. Dans la proposition générée, certaines métriques et un texte secondaire représentaient encore une information absente par des valeurs telles que `False` ou `0`. Ce point, hors des assertions figées, est documenté. La proposition n'a pas été déployée et ces sept tests ne valent pas conformité complète du code.

## Périmètre publié

Cette note publie uniquement des agrégats vérifiés. Les souvenirs, prompts, traces applicatives et propositions de code privées restent exclus. La [campagne synthétique reproductible](../../../benchmarks/action-20261023/experience/README.fr.md) fournit séparément ses observations publiques et ses commandes de recalcul. Les gains déjà mesurés dans cette campagne et le jalon fonctionnel 12/12 restent des résultats distincts.
