# Bilan de la campagne historique et erratum d’évaluation

La campagne a été close les 21–22 octobre 2026. Ses réponses, jugements, scores, inconnus et seuils d’origine sont conservés. **Elle n’a pas atteint l’exigence de qualité absolue.** Cette archive permet d’inspecter et de recalculer exactement une étude automatique ; elle ne certifie ni une qualité métier calibrée, ni tous les usages de production Hermes.

## Résultat enregistré

Le bras mémoire principal compte 1 290 succès confirmés, 76 échecs confirmés et 134 inconnus sur 1 500 épisodes de génération : **86,00 %** de réussite conservatrice et une borne haute descriptive de **94,93 %**. La borne inférieure unilatérale nominale à 95 % vaut **83,67 %**. Les deux exigences absolues échouent : 86,00 % < 90 %, et 83,67 % < 85 %. Les inconnus ne sont pas transformés en réussites.

Selon le protocole automatique initial, l’intervalle conservateur nominal à 95 % de l’effet apparié mémoire moins absence de mémoire est de **+61,00 à +77,33 points de pourcentage**. Le second modèle de génération, sur le sous-ensemble gelé de 100 tâches, donne **+56,67 à +77,33 points**. Face à la récupération lexicale, l’intervalle **−2,67 à +26,67 points** comprend zéro : la supériorité n’est pas établie. Ces intervalles n’intègrent pas le biais de l’évaluateur.

Les 500 tâches synthétiques sont réparties en **100 groupes de scénarios** ; ce ne sont pas 500 mondes indépendants. Les trois répétitions restent ensemble dans le bootstrap stratifié par groupes. Les 3 900 épisodes de génération sont complets. Sur 3 900 paires de jugements, 223 sont en désaccord et trois comportent un jugement absent ou invalide. Les 226 inconnus (5,79 %) ne désignent pas des pannes de mémoire : ils peuvent venir d’une erreur de réponse, d’évaluation, d’une ambiguïté ou d’un verdict indisponible. Les juges initiaux n’ont confirmé aucune violation critique ; cette observation n’est pas une garantie universelle de sûreté.

## Défaut démontré de l’évaluateur

Le prompt de jugement initial contenait la question, la réponse, un oracle abrégé et les identifiants des preuves disponibles, **sans les textes de preuves transmis au modèle qui répondait**. Un détail étayé, mais absent de l’oracle abrégé, pouvait ainsi être déclaré inventé. La comparaison directe établit trois pénalités de ce type :

| Identifiant public de l’épisode | Détail rejeté par un juge | Preuve réellement transmise |
|---|---|---|
| `V21-L-F04-G04-T04-R1-ON` | Livraison jeudi | `F04-G04-D03` prévoit explicitement la livraison à Hall Three le jeudi. |
| `V21-L-F05-G01-T01-R2-ON` | Prise de test, horaires de Mila et autre agent | `F05-G01-D02` fournit les trois informations. |
| `V21-L-F08-G01-T04-R3-ON` | Diagnostic de panne non reçu | `F08-G01-D01` indique explicitement que le diagnostic n’est pas encore reçu. |

Ces exemples prouvent un défaut, sans en mesurer la fréquence sur toute l’étude. Ils n’autorisent ni à convertir les inconnus historiques en succès, ni à calculer un taux corrigé. Les deux corps JSON incomplets de juges et l’unique dépassement de délai restent eux aussi inchangés.

## Des erreurs de réponse réelles subsistent

- `V21-L-F04-G06-T03-R2-ON` dispose du prix de 90 couronnes pour dix semaines, mais n’en déduit pas les neuf couronnes hebdomadaires et déclare le prix inconnu.
- `V21-L-F09-G06-T03-R1-ON` accepte un planning avec une seule personne après midi alors que deux sont requises en permanence.
- `V21-L-F10-G01-T03-R2-ON` ne rattache pas le budget disponible à l’espace courant et déclare « notre » budget inconnu.

Les faits disponibles sont mal exploités dans ces réponses. Ce constat ne suffit pas à attribuer la cause au stockage, à la recherche ou à la génération. Les exemples sont descriptifs ; ils n’estiment pas la fréquence de chaque cause.

## Interprétation et reproductibilité

Le contraste positif face à l’absence de mémoire dépend de ce corpus et de l’évaluation automatique initiale, imparfaite. Ce n’est pas une estimation calibrée de la qualité métier. L’étude ne bénéficie d’**aucun audit humain externe de qualité** ; les deux juges sont des modèles IA dont les erreurs peuvent être corrélées. Le gel local avant appels est documenté, mais une publication après mesure n’est pas une prérégistration externe horodatée.

Le recalcul hors réseau reproduit ces résultats historiques ; il ne corrige pas leur évaluateur. Une future validation nécessiterait des juges qualifiés recevant les textes exacts des preuves livrées, une couverture question/oracle vérifiée et une nouvelle cohorte gelée avant les appels. Cette validation corrigée **n’est pas un résultat de cette archive**. Aucun ancien score, réponse ou oracle n’a été remplacé.

Le [bilan d’exécution et de coût](EXECUTION.json) distingue l’étude gelée d’un rejeu opérationnel séparé de huit appels. Le plafond conservateur d’exposition, les estimations d’usage connues et la facture réelle sont des grandeurs différentes.
