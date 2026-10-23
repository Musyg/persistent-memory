# Contrat de reprise et hypothèses de confiance

[English](RECOVERY.md)

Conservez le contenu des sources séparément de l'autorité et de son témoin de fraîcheur. Une sauvegarde du contenu ne peut être restaurée qu'en la confrontant à l'autorité actuellement reconnue comme fiable. À son ouverture, un ancien stockage est mis en quarantaine jusqu'à sa réconciliation par `restore_verify(authority.checkpoint())`. Les sources retirées et les enregistrements qui en dépendent restent illisibles.

Le journal de l'autorité, les contrôles de version par comparaison et échange (compare-and-swap) et les identifiants d'opération idempotents empêchent la publication à partir d'un état périmé. Reconstruisez les projections à partir des références admissibles ; un résultat d'index ne doit jamais être utilisé directement dans une réponse sans validation par l'autorité. Les enregistrements dérivés doivent désigner les versions exactes de leurs parents au moyen des relations de dépendance forte `derives` ou `indexes`. La relation `cites` consigne une référence documentaire ; elle ne propage ni l'invalidation ni le retrait. Si une application omet de déclarer une dépendance forte réelle, elle ne peut pas compter sur le retrait transitif des enregistrements qui en dépendent.

Le témoin détecte une divergence avec une sauvegarde de l'autorité. Il ne peut pas détecter un retour coordonné de toutes les autorités de confiance et de tous leurs témoins à un état antérieur. Un déploiement qui exige cette protection doit conserver un point d'ancrage de confiance externe plus récent. La durabilité de SQLite et des répertoires dépend des garanties de synchronisation du système de fichiers. L'arrêt brutal d'un processus ne simule pas toutes les défaillances matérielles ou de stockage.

Dans le noyau, la révocation détermine si une information peut encore être utilisée ; elle ne garantit pas sa suppression physique partout. D'anciennes sauvegardes, des copies externes, des journaux et des réponses déjà affichées peuvent encore contenir le texte. Chaque application reste responsable de sa politique de conservation et d'effacement. La prise en charge de la révocation par cette bibliothèque ne dispense pas d'obtenir le consentement nécessaire avant de stocker des données.

Exécutez `hermes-memory-demo --directory NEW_PATH` pour reproduire un parcours avec deux sources indépendantes, une transmission dépendante, un redémarrage, un retrait et la restauration d'un ancien contenu. La démo utilise uniquement du texte synthétique, sans réseau ni modèle.
