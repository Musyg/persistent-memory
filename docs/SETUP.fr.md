# Brancher vos outils

[English](SETUP.md) · [Serveur MCP](MCP.fr.md) · [Hermes Agent](HERMES-AGENT.fr.md) · [README](../README.fr.md)

Un paquet, une commande par outil. Tous les outils branchés utilisent la même mémoire : ce qui est retenu dans l'un est retrouvé dans les autres, et un retrait fait dans l'un est signalé à chaque outil qui avait vu l'entrée retirée.

## Installer

Le paquet n'utilise que la bibliothèque standard de Python (3.11 ou plus récent). Donnez-lui son propre environnement virtuel :

```sh
python3 -m venv ~/.persistent-memory
~/.persistent-memory/bin/python -m pip install /chemin/vers/persistent-memory
```

Sous Windows, les commandes sont dans `.persistent-memory\Scripts\`. Jusqu'à la première publication sur PyPI, l'installation se fait depuis une copie du dépôt ou depuis le wheel d'une release.

Si une version précédente est installée sous son ancien nom, désinstallez-la d'abord : `pip uninstall hermes-memory-core`. Les deux noms contiennent le même module `hermes_memory`.

## Brancher un outil

```sh
~/.persistent-memory/bin/persistent-memory setup claude-code
```

| Client | Portée | Ce qui est écrit |
| --- | --- | --- |
| `claude-code` | `user` (par défaut) | `claude mcp add-json --scope user` |
| | `project` | `.mcp.json` dans le dossier du projet |
| `claude-desktop` | `user` | `claude_desktop_config.json` (macOS `~/Library/Application Support/Claude`, Windows `%APPDATA%\Claude` ou le dossier de la version Microsoft Store, Linux `~/.config/Claude`) |
| `cursor` | `user` / `project` | `~/.cursor/mcp.json` / `.cursor/mcp.json` |
| `vscode` (GitHub Copilot) | `user` / `project` | `~/.copilot/mcp-config.json` (ou `$COPILOT_HOME`) / `.mcp.json` |
| `windsurf` | `user` | `~/.codeium/windsurf/mcp_config.json` |
| `codex` | `user` | `~/.codex/config.toml` (ou `$CODEX_HOME`), table `[mcp_servers.persistent-memory]` |
| `hermes-agent` | `user` | Le fournisseur de mémoire d'Hermes Agent, ou un serveur MCP ; voir plus bas |

`claude`, `copilot` et `hermes` sont acceptés comme noms courts. Un `.mcp.json` de projet est lu à la fois par Claude Code et par Copilot.

Chaque entrée lance `python -m hermes_memory.mcp_server` avec le chemin absolu du Python de cet environnement : l'outil ne dépend donc pas du `PATH`. La page du [serveur MCP](MCP.fr.md) décrit les dix outils.

## Une seule mémoire, partagée

`setup` crée la mémoire une fois, puis chaque outil l'ouvre. Emplacement par défaut :

| Système | Mémoire |
| --- | --- |
| Linux | `$XDG_DATA_HOME/persistent-memory`, sinon `~/.local/share/persistent-memory` |
| macOS | `~/Library/Application Support/persistent-memory` |
| Windows | `%LOCALAPPDATA%\persistent-memory` |

`$PERSISTENT_MEMORY_DIR` ou `--store` en désigne une autre. Les outils qui ont la même mémoire et le même `--workspace` (par défaut `default`) partagent leurs souvenirs ; donnez un autre espace à un outil pour le tenir à part. Le serveur configuré ne crée pas une mémoire absente : si le dossier disparaît, l'outil le signale au lieu de repartir d'une mémoire vide.

## Options

| Option | Sens |
| --- | --- |
| `--scope user\|project` | Tous les projets, ou le fichier d'un projet, à versionner ou partager. |
| `--project-dir DIR` | Dossier du projet pour `--scope project`. Par défaut : le dossier courant. |
| `--store DIR`, `--workspace NAME` | Où vit la mémoire et quelle partie cet outil utilise. |
| `--name NAME` | Nom du serveur dans l'outil. Par défaut `persistent-memory`. |
| `--dry-run` | Montre ce qui changerait. Rien n'est écrit, aucune mémoire n'est créée. |
| `--remove` | Retire l'entrée. La mémoire elle-même n'est pas touchée. |
| `--force` | Remplace ou retire une entrée du même nom qui lance un autre serveur. |
| `--json` | Affiche le résultat en JSON. |

`persistent-memory status` indique la mémoire par défaut et les fichiers de configuration qui la lancent déjà. `persistent-memory mcp` lance le serveur lui-même, avec les options de `persistent-memory-mcp`.

## Ce que setup fait, et ce qu'il ne fait pas

- Les autres serveurs et réglages d'un fichier restent tels quels.
- Un fichier illisible, par exemple du JSON avec commentaires, n'est pas modifié ; l'entrée à ajouter à la main est affichée.
- Une entrée du même nom qui lance autre chose n'est pas remplacée sans `--force`. Un autre `--name` permet de garder les deux.
- Avant de modifier un fichier existant, une copie est enregistrée à côté, `<fichier>.persistent-memory-<heure>.bak`, puis le nouveau contenu est écrit dans un fichier temporaire renommé à sa place. Un lien symbolique est suivi jusqu'à sa cible.
- Relancer la même commande ne change rien.
- Pour Codex, le résultat est relu avant l'écriture ; si autre chose que cette entrée changeait, rien n'est écrit.
- La configuration utilisateur de Claude Code et celle d'Hermes Agent sont modifiées par leurs propres lignes de commande, jamais en éditant leurs fichiers.

## Hermes Agent

Installez le paquet dans l'environnement d'Hermes Agent et lancez `persistent-memory setup hermes-agent` depuis celui-ci. La commande choisit le [fournisseur de mémoire](HERMES-AGENT.fr.md) avec `hermes config set memory.provider persistent-memory` et inscrit la mémoire et l'espace de travail dans `$HERMES_HOME/persistent-memory/config.json`, sans toucher aux autres réglages. Hermes Agent rappelle alors la mémoire validée avant chaque tour, et ouvre un tour sur un avis quand une chose qu'il a vue est retirée.

Hermes Agent n'accepte qu'un fournisseur de mémoire externe. Si un autre est déjà choisi, setup s'arrête ; `--force` le remplace, `--hermes-mode mcp` ajoute plutôt le serveur MCP. Quand le paquet n'est pas dans l'environnement d'Hermes Agent, setup passe de lui-même en mode MCP : `hermes config set mcp_servers.persistent-memory ...`, et les outils apparaissent dans le jeu d'outils `mcp-persistent-memory`. `--hermes-command` donne le chemin de `hermes` quand il n'est pas trouvé.

## Observé

Le 14 novembre 2026, sous Linux, dans un environnement virtuel neuf avec Python 3.12 et le paquet installé depuis son wheel, chaque outil utilisant un dossier de configuration temporaire :

- Claude Code 2.1.289 : `setup claude-code` a enregistré le serveur par `claude mcp add-json` ; une deuxième exécution l'a indiqué inchangé ; `claude mcp list` l'a montré connecté.
- Codex CLI 0.166.0 : `codex mcp list` et `codex mcp get` ont lu l'entrée écrite par `setup codex`.
- Hermes Agent : `hermes memory status` a montré `persistent-memory` actif et disponible. Avec un modèle local de 9 milliards de paramètres, Hermes Agent a enregistré un fait avec `memory_remember` ; le serveur configuré pour Claude Code et Codex l'a retrouvé avec `memory_search`.

Le 15 novembre 2026 :

- Linux, Claude Code avec un vrai tour de modèle, depuis un `.mcp.json` de projet écrit par `setup claude-code --scope project` : Claude a enregistré un fait avec `memory_remember` ; dans une nouvelle session, il l'a retrouvé avec `memory_search` en citant son `artifact_id` ; une fois le fait retiré de l'extérieur, la session suivante n'a rien trouvé et l'a dit.
- Windows 10, Python 3.13, dans un dossier de profil temporaire : `setup` a écrit les fichiers de Claude Desktop, Cursor, VS Code (projet) et Windsurf ; une deuxième exécution les a indiqués inchangés ; `status` les a listés.

Les fichiers de Claude Desktop, Cursor, VS Code et Windsurf suivent la documentation actuelle de chaque outil ; ils ont été écrits et vérifiés par les tests, pas ouverts dans ces applications.

## Tests

`tests/test_client_setup.py` couvre le fichier ou la commande de chaque client, la mémoire par défaut sur chaque système, les refus (entrée étrangère, fichier illisible, portée non prise en charge), les copies de sauvegarde, les droits des fichiers, les liens symboliques, l'idempotence, le retrait, les essais à blanc, l'échappement en TOML, et le lancement de bout en bout de la commande configurée, qui répond en MCP. Les commandes `claude` et `hermes` sont remplacées par des substituts dans ces tests.
