# Provenance du contrat générique

[English](NOTICE.md)

Le fichier inclus `hermes_policy_registry/contracts/learning_records.py` est extrait de contrats génériques nouvellement écrits pour les enregistrements d'apprentissage Hermes. Ses octets ont été conservés à l'identique ; il ne s'agit pas d'un export du Learning Engine ni d'une base de données. SHA256 : `3dd069650457f2ecb7ddacf13c7cba8a7b76ef459d8bb6228d699b16fa7c720e`.

L'historique d'origine inspecté comprend le commit `d5cc810dcca1ff9df7a0a2daae1d40948bd12794` (2026-09-27, « Prepare combined LE maintenance and offline learning contracts »), suivi de `fa1f7f247fd0163c9a106de7be58d677357a164e` (2026-09-27, « feat(learning): persist versioned experiences and evaluations in local ledger »). Les deux commits indiquent `Hermes-Agency` comme auteur. Le module importe uniquement hashlib/json/math/datetime de la bibliothèque standard Python. L'inspection n'a trouvé dans ce module ni implémentation copiée d'un tiers, ni contenu privé, ni adresse de service, ni identifiants d'accès, ni configuration de la flotte.

Le propriétaire du projet a autorisé la publication sous licence MIT de ce module générique sélectionné et du nouveau code du registre dans le cadre de l'extraction open source. Cette autorisation ne change pas la licence du dépôt privé ni celle d'un code tiers. La présente notice distingue le module conservé octet pour octet du registre et de l'adaptateur nouvellement écrits ; elle ne garantit pas l'attribution au-delà de la provenance inspectée. Texte de la licence : [LICENSE](LICENSE), Copyright 2026 Musyg.

Aucun accès au dépôt privé n'est nécessaire à l'exécution. Le paquet inclut par défaut ce module exact ; un fichier de remplacement facultatif n'est accepté que si son empreinte source SHA est identique. Toute évolution du contrat exige une version examinée séparément.
