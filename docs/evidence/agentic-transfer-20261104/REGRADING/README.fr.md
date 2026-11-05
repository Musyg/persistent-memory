# Vérifier indépendamment les notes des réponses B publiées

[English](README.md)

Depuis le dossier du rapport, exécuter `python -I -B verify.py` pour recalculer la comparaison. Exécuter ensuite `python -I -B REGRADING/verify_regrading.py` pour vérifier aussi les notes dont la réponse est publiée. Les deux commandes fonctionnent hors ligne.

`B-EVIDENCE.json` contient 32 cas B synthétiques et 128 lignes monde/bras assignées. Chaque cas fournit le seuil réel, la convention cible, les trois enregistrements d’entrée ainsi que les colonnes et lignes attendues. Le vérificateur recalcule ces lignes avec la fonction d’éligibilité existante. Chaque bras comporte un emplacement pour la première réponse et un autre pour la réponse finale. `EXACT` contient la réponse d’origine et son empreinte SHA-256 en UTF-8. `WITHHELD` signale une réponse écartée de la publication. `UNAVAILABLE` désigne une réponse introuvable ou qui n’a jamais été produite. Seules les réponses exactes entrent dans le décompte des notes revérifiées. La première réponse et la réponse finale peuvent provenir de la même génération.

Les deux réponses sont vérifiées avec le même oracle métier typé et les contrôles d’origine sur le nom de fichier et la structure de la réponse. La note du premier essai applique la règle complète, y compris à la valeur frontière. Pendant la génération, le contrôle accessible à l’agent portait sur le format et le comportement hors de cette frontière. Le parseur lit une unique affectation inerte à `RESULT` avec `ast.literal_eval`. Le vérificateur n’exécute pas le Python généré et ne lance ni modèle ni Hermès.

`ORACLE-SOURCES.json` identifie les définitions exactes réutilisées. L’annexe suit la licence MIT du dépôt public. Le manifeste lie les données publiées au registre des mondes et aux verdicts par bras. La provenance opérationnelle privée, les contrôles de droits et les requêtes modèles restent hors de ce calcul. La vérification établit que les octets publiés donnent la note attendue. Pour les réponses écartées de la publication ou indisponibles, la note reste attestée par l’étude.

## Attribution des ressources

L’expérience compte le travail A commun une fois par monde. Pour estimer les ressources d’une condition utilisée seule, présenter séparément A et les ressources propres à cette condition, puis leur somme. La trace a été construite pendant la phase ECC sans appel modèle supplémentaire. Les compteurs ne ventilent pas le travail CPU de cette phase entre la construction de la trace et ECC. Les durées et jetons publiés décrivent l’usage modèle enregistré.

Le champ `model_tool_calls` compte les opérations HTTP instrumentées vers le backend modèle. Ce décompte est distinct du nombre de générations et des outils que l’agent utilise pour accomplir sa tâche. Présenter la durée totale de la campagne séparément de la somme des latences modèle. Cette durée inclut la préparation, les démarrages, les attentes, les incidents et la clôture. Le surcoût technique partagé reste une mesure de campagne.
