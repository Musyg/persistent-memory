# Calibration de l’évaluateur avec les preuves transmises

Les deux juges ont rendu le verdict attendu sur **les huit cas synthétiques fixés : 16 jugements sur 16**. Ce petit contrôle diagnostique porte sur l’évaluateur corrigé et précède l’étude de confirmation indépendante. Ce n’est **ni** un taux de réussite de la mémoire, **ni** une estimation représentative de précision, **ni** une garantie universelle. Aucun audit humain externe de qualité n’a été réalisé.

Les cas vérifient l’acceptation de détails supplémentaires étayés, la conversion d’unités et les formulations équivalentes, le rejet d’un calcul faux et d’une réponse incomplète, l’abstention justifiée sans preuve et la détection d’une divulgation explicitement interdite. Le dernier cas contient volontairement une phrase de remise fictive. Sa détection est le contrôle positif attendu, pas un incident de sécurité en production.

`CASES.json` contient les questions, réponses fixées, oracles abrégés et preuves transmises, avec leurs valeurs originales. `PROMPTS.json` conserve les huit prompts effectivement préparés pour les deux juges. `JUDGMENTS.json` donne les 16 corps de réponse et motifs non retouchés, les modèles demandés et retournés, et les liens SHA256 vers les cas et prompts. Le juge A est `gpt-6-luna` ; le juge B est `gpt-6.1-sol`. Ils ont évalué des réponses fixées : il ne s’agit pas de huit nouvelles réponses produites par la mémoire.

Un motif commence par `L回答`. Ce mélange de langues est conservé : son sens et son verdict sont clairs ; ce n’est pas un échec de format. Aucune réponse n’a été réécrite ou rejouée. Les notes historiques V21 restent inchangées.

`PROVENANCE.json` décrit les engagements sources et la projection par liste de champs autorisés. Identifiants fournisseur, en-têtes, chemins opérationnels et identifiants secrets sont exclus. L’exposition conservatrice enregistrée est de 0,2236416 USD ; l’estimation d’usage connue atteint 0,0132789 USD pour les 16 tentatives. Aucune de ces valeurs n’est une facture ; le montant facturé reste inconnu.

La commande `sha256sum -c SHA256SUMS` vérifie les fichiers. Les chaînes JSON gardent exactement le texte source ; l’indentation et l’échappement JSON n’en changent pas le contenu. Le hash d’un cas utilise un JSON UTF-8 aux clés triées, sans espaces de séparation ni saut de ligne final, selon la provenance. Aucun compte ni appel de modèle n’est nécessaire pour examiner ces données.
