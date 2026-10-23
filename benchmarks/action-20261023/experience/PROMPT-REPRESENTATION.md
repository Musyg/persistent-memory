# Représentation de la trace complète / Full-trace representation

23 octobre 2026. Ajustement prospectif avant tout appel modèle de cette étude. Les tentatives factices précédentes et les données scellées restent inchangées.

## Français

XPQ03 a montré que sérialiser la trace JSON comme une chaîne dans une seconde requête ajoutait un niveau d’échappement. Le nouveau parcours expose ces seules sources JSON canoniques comme objets structurés dans le prompt, après vérification que leur sérialisation reconstitue exactement le texte source. Les octets stockés, les identifiants, les références et le contenu de la trace restent identiques. Le bras brut reçoit l’entrée complète de l’extracteur.

XPQ04 a ensuite exécuté neuf épisodes complets sur douze. Trois requêtes brutes valides occupaient encore 10 650, 10 459 et 10 261 octets, au-delà de la limite de 10 240. Leur contexte restait inférieur à 8 000 caractères. Le texte générique des instructions XP a donc été condensé de 971 à 521 octets, sans changer les champs, les données, les droits ni les contraintes. Les règles de format, de contrôle positif, de taille, de dépendance courante et de traitement des consignes hostiles sont conservées. Aucun exemple n’a été remplacé, aucune trace résumée et aucune limite relevée.

Le contrôle factice vérifie uniquement le parcours technique. La campagne réelle conservera les erreurs, leçons erronées et épisodes indisponibles, sans nouvelle tentative ni sélection de résultats favorables. Les études historiques et leur prompt ne changent pas.

## English

XPQ03 showed that putting a JSON trace inside a string in another request introduced an extra escaping layer. The new path renders these canonical JSON sources as structured objects in the prompt, after checking that serialization reconstructs the exact source text. Stored bytes, identifiers, references and trace content remain unchanged. The raw-history arm receives the extractor’s complete input.

XPQ04 then completed nine of twelve mock episodes. Three valid raw-history requests still occupied 10,650, 10,459 and 10,261 bytes, above the 10,240-byte limit. Their contexts remained below 8,000 characters. The generic XP instructions were therefore condensed from 971 to 521 bytes while preserving all fields, data, permissions and constraints. Format rules, the positive control, size limits, current-source dependencies and hostile-instruction handling remain intact. No case was replaced, no trace summarized and no limit increased.

The mock check tests the technical path only. The actual study will retain errors, wrong lessons and unavailable episodes, without retries or selection for favorable outcomes. Historical studies and their prompt remain unchanged.
