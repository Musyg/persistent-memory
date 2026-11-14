# Point d'accès MCP distant

[English](README.md)

`hermes-memory-mcp` expose la mémoire de provenance par le transport Streamable HTTP de MCP : tout client MCP qui accepte une URL et un jeton Bearer peut y chercher, y ajouter et en retirer. Uniquement la bibliothèque standard de Python, comme le cœur de mémoire.

Distribution `hermes-memory-mcp` 0.1.0a1, commande `hermes-memory-mcp`. Version alpha.

Il utilise la même mémoire et le même registre d'exposition que le [provider pour Hermes Agent](../hermes-agent-provider/README.fr.md). Pointés sur le même dossier, une source retirée par MCP avertit aussi les sessions Hermes Agent qui l'ont vue, et inversement.

## Outils

| Outil | Effet | Annotation |
|---|---|---|
| `provenance_search` | Recherche lexicale parmi les éléments lisibles, avec leur `source_id` | lecture seule |
| `provenance_explain` | Versions, lisibilité et dépendants d'une source ; métadonnées seulement | lecture seule |
| `provenance_remember` | Admet un élément typé | écriture |
| `provenance_withdraw` | Retire une source et tout ce qui en dérive ; ce n'est pas un effacement physique | destructif |

`--read-only` n'expose que les deux premiers ; `--no-withdraw` masque le dernier.

**Avis de retrait.** Le serveur note quelles sources ont été montrées à chaque session MCP. Quand l'une d'elles est retirée, d'où que ce soit, le résultat d'outil suivant de cette session porte un `withdrawn_notice` qui liste les identifiants, une seule fois par source, avec la consigne de ne plus s'y fier.

## Lancement

```sh
python3 -m pip install . ./packages/hermes-agent-provider ./packages/remote-mcp
umask 077 && python3 -c "import secrets; print(secrets.token_urlsafe(32))" > mcp-token
hermes-memory-mcp --store-dir ./memory-store --create --token-file ./mcp-token
```

Le point d'accès est `http://127.0.0.1:8766/mcp`. Pour partager la mémoire avec Hermes Agent, passer `--store-dir $HERMES_HOME/provenance`.

- Le fichier du jeton doit être un fichier ordinaire, lisible par son seul propriétaire, d'au moins 32 caractères.
- Écouter ailleurs que sur la boucle locale exige un jeton. Le serveur parle HTTP sans chiffrement : hors d'une seule machine, il faut le placer derrière TLS (un reverse proxy, ou un réseau privé superposé).
- Les en-têtes `Origin` des navigateurs sont refusés sauf s'ils sont listés avec `--allow-origin`, contre les attaques par rebinding DNS.

## Brancher un client

Claude Code :

```sh
claude mcp add --transport http provenance http://127.0.0.1:8766/mcp --header "Authorization: Bearer $(cat mcp-token)"
```

Hermes Agent, dans le `config.yaml` du profil :

```yaml
mcp_servers:
  provenance:
    url: http://127.0.0.1:8766/mcp
    headers:
      Authorization: "Bearer <jeton>"
```

Les autres clients qui acceptent une URL MCP en HTTP et des en-têtes personnalisés se configurent de la même façon.

## Protocole

- POST `/mcp` porte un seul message JSON-RPC et reçoit une réponse `application/json`. Les lots sont refusés.
- `initialize` ouvre une session et renvoie `Mcp-Session-Id`, que les requêtes suivantes doivent fournir. DELETE ferme une session. GET répond 405 : aucun flux initié par le serveur n'est proposé.
- Les versions de l'ère de la poignée de main `2025-11-25`, `2025-06-18` et `2025-03-26` sont servies ; une version demandée inconnue reçoit `2025-11-25`. Une sonde `server/discover` d'un client récent reçoit « méthode inconnue », ce qui le fait revenir à la poignée de main.

## Vérifications

`tests/` démarre de vrais serveurs sur des ports locaux éphémères et couvre la poignée de main, les sessions, l'authentification, les origines, les limites, le mode lecture seule, les avis entre sessions, et un retrait par MCP qui avertit une session du provider Hermes Agent sur la même mémoire. Il fait partie de `scripts/check_distributions.py`, qui installe à côté les wheels du cœur et du provider.

L'interopérabilité a été observée une fois, sur un hôte Linux le 14 novembre 2026. Le client officiel du SDK MCP Python 2.3.0, dans son mode automatique par défaut, est revenu à la poignée de main en `2025-11-25`, a listé les quatre outils, a enregistré, cherché, et reçu une erreur d'outil pour une source inconnue. Hermes Agent au commit `d93e9ba4`, configuré avec l'URL et un en-tête Bearer, a découvert les quatre outils et répondu à une question depuis la mémoire avec les `source_id`, avec un Qwen3.5-9B local.

## Limites

- Jetons Bearer uniquement. Les clients qui exigent OAuth, comme les connecteurs web, ne peuvent pas encore se brancher.
- Les sessions vivent en mémoire : un redémarrage les ferme, et les clients se reconnectent. Les avis sont liés aux sessions MCP, qui ne sont pas des conversations.
- Pas de message initié par le serveur : un avis arrive avec le résultat d'outil suivant de la session.
- La recherche est lexicale. Le retrait bloque les lectures futures via cette bibliothèque ; il ne peut pas rappeler ce qu'un client a déjà copié.

Licence MIT, voir [LICENSE](LICENSE). La provenance des fichiers est consignée dans [PROVENANCE.json](PROVENANCE.json).
