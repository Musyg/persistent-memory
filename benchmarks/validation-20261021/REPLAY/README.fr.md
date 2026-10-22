# Générer de nouvelles réponses avec le composant public

Ce répertoire optionnel reprend à l'octet près les quatre modules de génération déjà qualifiés. Il n'ajoute ni runner, ni client HTTP, ni registre de budget, ni dépendance à la flotte. Les empreintes figurent dans `SOURCE-PROVENANCE.json`. La copie a passé les cinq tests existants sous Linux avec le runtime public pinné, dont six requêtes simulées et le refus des deux budgets inactifs avant lecture d'une clé. Les versions et la portée de cette vérification figurent dans `NATIVE-QUALIFICATION.json`.

Le rapport de l'étude se recalcule hors ligne avec la commande d'analyse de l'archive parente. La commande ci-dessous demande, elle, **de nouvelles réponses payantes et stochastiques**. Elle ne remplace pas les réponses enregistrées et ne promet pas de les reproduire à l'identique. Les modèles peuvent évoluer derrière leur alias ; les identifiants demandés et retournés sont enregistrés et contrôlés.

## Préparer une petite sélection

Utiliser Linux, le Python 3.12 qualifié, `httpx` et la distribution publique vérifiée `hermes-memory-core==0.3.0a2`. Installer le projet public dans un environnement virtuel dédié, par exemple avec `python3 -m pip install /chemin/vers/persistent-memory-verifie httpx`. La qualification native finale doit consigner les versions exactes des dépendances. Aucun module Hermes privé, tokenizer interne, orchestrateur, accès SSH ou grant Root historique n'est nécessaire. Garder ce répertoire exempt de modules Python sans rapport.

Vérifier d'abord les `SHA256SUMS` de l'archive publiée. [CONFIGURATION.md](CONFIGURATION.md) fournit une transformation commune : elle sélectionne **un seul** bloc du plan public non exécutable et crée un profil, un budget inactif et un paquet contenant uniquement les cas concernés. Tâches, requêtes, documents et cellules sont conservés ; le nouveau paquet reçoit son propre SHA256. Cette transformation ne lit ni oracle, ni labels de métadonnées, ni jugements.

`DEV/` reprend les quatre fixtures synthétiques jetables existantes ; ce n'est pas la campagne de 500 tâches. Chaque profil d'exemple sélectionne seulement le premier cas de développement dans trois conditions : mémoire typée, absence de mémoire et comparateur lexical existant. Chaque budget réserve au plus trois appels par modèle et **ne peut rien envoyer dans son état livré**. Les résultats restent explicitement des essais de développement.

## Autoriser un essai borné

Le contrat gelé accepte `volume_luna6_none_v1` (`gpt-6-luna`, raisonnement `none`) et `volume_sol61_low_v1` (`gpt-6.1-sol`, raisonnement `low`). Récupération des preuves, prompt et API texte sont communs. Les limites sont : 1 à 3 appels sélectionnés, 300 secondes pour le lot, 90 secondes par requête, requête complète limitée à 10 240 octets UTF-8 avec une marge de 1 024 tokens de cadrage, au plus 11 264 tokens d'entrée et 2 048 de sortie. La température est omise. Aucun nouvel essai automatique ni modèle de remplacement.

Aux tarifs gelés de la campagne, la réservation maximale par génération est de `0.0021504` USD pour Luna ou `0.043008` USD pour Sol ; les exemples de trois appels totalisent `0.0064512` ou `0.129024` USD. Ces bornes décrivent le contrat tarifaire historique ; **elles ne vérifient ni le tarif du jour ni la facture du compte**. Avant activation, l'opérateur doit vérifier les prix actuels et les bornes qualifiées d'octets, tokens et raisonnement. Si ce contrat ne borne plus le coût, utiliser une version requalifiée ; ne pas contourner le contrôle ni modifier les limites figées.

Après cette revue, copier le fichier `*-budget.INACTIVE.json` choisi vers `budget.json` ; passer uniquement `authorized_for_execution`, `price_verified`, `tokenizer_bound_verified`, `reasoning_total_bound_verified` à `true`, puis fixer `expires_at_epoch` à un timestamp Unix futur fini. Conserver profil, cellules, prix et options. Figer les octets obtenus avec `sha256sum budget.json`. Cette autorisation appartient au nouvel opérateur, pas à la campagne historique.

Enregistrer sa propre clé API dans un fichier régulier appartenant à l'utilisateur courant, mode `0600`. Ne jamais l'inclure dans l'archive ou l'historique du shell. Depuis ce répertoire, après préparation de `work/profile.json`, `work/inputs.json` et `work/budget.json` :

```sh
PYTHONPATH="$PWD/CODE" python3 -P -B CODE/run_pilot.py \
  --consumer public_portable \
  --inputs "$PWD/work/inputs.json" \
  --dataset-sha256 "$(sha256sum work/inputs.json | cut -d ' ' -f1)" \
  --profile "$PWD/work/profile.json" \
  --budget "$PWD/work/budget.json" \
  --budget-sha256 "$(sha256sum work/budget.json | cut -d ' ' -f1)" \
  --api-key-file "$HOME/.config/memory-replay/openai.key" \
  --output "$PWD/work/new-attempt"
```

Seul `CODE/` est ajouté au chemin d'import ; `-P` évite l'import implicite du répertoire de travail. Le répertoire de sortie et son fichier voisin `new-attempt-budget.sqlite` doivent être absents. Ne pas effacer un ledger pour relancer après un envoi incertain. Le fournisseur existant réserve durablement le coût maximal avant l'unique envoi de chaque cellule ; les appels incomplets ou échoués conservent trace et réservation sans relance silencieuse. Lire les statuts individuels : le résumé CLI n'est pas un score de qualité.

L'essai conserve `report.json`, traces requête/réponse, tentatives et contrôles d'autorité/révocation. Les traces locales brutes peuvent contenir identifiants fournisseur et chemins : **leur publication n'est pas admise**. Séparer ces sorties de l'étude publiée et utiliser la normalisation/export existante après revue. Chaque cas, politique et répétition utilise une mémoire fraîche ; la requête provient de la fixture, pas d'un planner autonome évalué.
