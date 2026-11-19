# Export en notes Markdown

[English](EXPORT.md) · [Exploitation](OPERATIONS.fr.md) · [Serveur MCP](MCP.fr.md)

`persistent-memory export` écrit ce que la mémoire sert en ce moment sous forme d'un dossier de notes Markdown : une note par entrée, avec sa provenance en liens, et un index par espace de travail. Visez un dossier d'un coffre Obsidian et vous pouvez parcourir la mémoire, remonter d'une note aux faits dont elle est tirée, et voir le graphe. L'installation de base suffit, rien d'autre à installer.

```sh
persistent-memory export ~/Notes/Coffre/memoire
```

```text
2 notes in /home/moi/Notes/Coffre/memoire (obsidian): 3 written, 0 unchanged, 0 removed
```

L'export va dans un seul sens : de la mémoire vers les notes. Modifier une note ne modifie pas la mémoire. Pour corriger ou retirer une entrée, passez par la mémoire (`memory_correct`, `memory_withdraw`, ou les méthodes Python), puis relancez l'export.

## À quoi ressemble une note

```markdown
---
artifact_id: "freeze-rule"
workspace: "atlas"
version: "07e42dadd5b647ff9b072e53f27ab2b3"
state: "active"
kind: "procedure"
authority_kind: "derived"
observed_at: "2026-11-19T14:47:27Z"
derived_from: ["[[deploy-day]]"]
content_sha256: "edfa9e86ce6cbda04bbd8ed03c4eb5139de8bd189beb69141a1bef69f65ad4a5"
tags: ["persistent-memory", "kind/procedure"]
---

# Freeze main on Monday evening, before the deploy.

## Provenance

- Derived from [[deploy-day|deploy-day]]
```

- **Propriétés.** Chaque valeur est écrite en JSON, qui est aussi du YAML valide : Obsidian les affiche comme propriétés et n'importe quel lecteur YAML les relit. Les champs vides sont omis. Les fenêtres de validité (`valid_from`, `valid_until`), `confidence`, `preconditions` et `aliases` apparaissent quand l'entrée en a.
- **Titre et texte.** Le titre est la première ligne du texte, coupée à 80 caractères. Le texte complet suit, sauf s'il tient sur cette seule ligne.
- **Provenance.** « Derived from » et « Cites » pointent vers les parents. Si un parent a une version plus récente que celle dont l'entrée est tirée, la ligne le dit ; un parent que la mémoire ne sert plus est nommé sans lien. « Used by » liste les entrées tirées de celle-ci.
- **Index.** `<espace>/index.md` liste les entrées par type, avec le point de contrôle auquel elles ont été lues.

`--style markdown` écrit des liens relatifs simples (`[deploy-day](<deploy-day.md>)`) pour les éditeurs sans wikiliens ; `derived_from` contient alors les identifiants nus.

## Le relancer

L'export est fait pour être relancé, à la main ou par une tâche planifiée. Chaque passage remet le dossier en accord avec la mémoire :

- une nouvelle entrée reçoit une note, une correction réécrit la note avec la nouvelle version ;
- une entrée que la mémoire ne sert plus perd sa note : retirée, remplacée, ou tirée de quelque chose de retiré. Les dossiers laissés vides sont supprimés ;
- une note dont le contenu n'a pas changé n'est pas réécrite : sa date de modification et votre outil de synchronisation restent tranquilles.

Ce que l'export a écrit est consigné dans `.persistent-memory-export.json`, en haut du dossier, avec le SHA-256 de chaque fichier. C'est ce registre qui permet de partager le dossier avec vos propres notes :

- **Une note que vous avez modifiée est gardée.** Si le contenu d'une note ne correspond plus à ce que l'export a écrit, l'export ne l'écrase pas et ne la supprime pas, même quand son entrée est retirée. Le passage la signale et sort avec le code 3. `--force` l'écrase ou la supprime.
- **Un fichier que l'export n'a pas écrit n'est jamais touché**, même avec `--force`, même quand une entrée voudrait son nom. La note de cette entrée est sautée et signalée.
- **Un dossier que l'export n'a pas créé est refusé** s'il n'est pas vide (`export_target_not_empty`). Donnez un dossier vide ou nouveau, ou un dossier écrit par un export précédent.
- **Rien hors du dossier.** Un registre qui liste un chemin hors du dossier est refusé (`export_manifest_unreadable`) avant toute suppression, de même qu'un lien de dossier, à l'intérieur, qui mène dehors (`export_path_escapes`). Le dossier ne peut pas être dans le store (`export_inside_store`).

## Entrées retirées

Par défaut, une entrée retirée disparaît simplement des notes : l'export montre ce que la mémoire servirait à un agent, rien de plus. Avec `--include-withdrawn`, les entrées qui ne sont plus servies reçoivent aussi une courte note sous `<espace>/_withdrawn/`, avec leur identifiant, leur version, leur état et la raison donnée par la mémoire, sans leur texte. Un secret retiré par erreur ne revient pas par l'export.

## Noms de fichiers

Une note porte le nom de l'identifiant de son entrée. Un identifiant qui ne peut pas être un nom de fichier sur toutes les plateformes (caractères comme `/ : ? * [ ] #`, nom de périphérique Windows comme `CON`, plus de 100 octets) est nettoyé et reçoit un court suffixe de hachage. Deux identifiants qui ne diffèrent que par la casse partageraient un fichier sous macOS et Windows : les deux reçoivent un suffixe, et les noms ne dépendent pas de l'ordre d'écriture des entrées. Le vrai identifiant est toujours dans la propriété `artifact_id`.

## Options

| Option | Effet |
|---|---|
| `output` | Dossier à écrire : vide, nouveau, ou écrit par un export précédent |
| `--store DIR` | Store à lire ; par défaut `$PERSISTENT_MEMORY_DIR` ou le dossier de données de la plateforme |
| `--workspace NOM` | Seulement cet espace ; répétable. Par défaut : tous les espaces du store |
| `--style obsidian` | Wikiliens et propriétés (par défaut) |
| `--style markdown` | Liens Markdown relatifs |
| `--include-withdrawn` | Écrire aussi une note sans texte pour chaque entrée qui n'est plus servie |
| `--force` | Écraser ou supprimer les notes modifiées à la main |
| `--json` | Afficher le rapport en JSON |

Codes de sortie : 0 terminé ; 3 terminé, mais des fichiers ont été gardés (modifiés à la main, ou pas écrits par l'export) ; 1 refusé, avec la raison sur stderr.

Depuis Python :

```python
from persistent_memory import export_store

report = export_store("~/.local/share/persistent-memory", "~/Notes/Coffre/memoire", style="obsidian")
print(report["written"], report["removed"], report["kept_edited"])
```

## Limites

- La lecture passe par les mêmes contrôles que toute lecture : chaque note est la version que l'autorité sert à ce moment, et l'index consigne l'époque du point de contrôle. Une entrée écrite pendant l'export est reprise au passage suivant.
- L'export contient le texte des entrées qu'il écrit. Traitez le dossier comme le store lui-même quand vous le synchronisez ou le partagez, et laissez le texte retiré de côté (le défaut) sauf si vous avez besoin de la trace.
- Chaque entrée est lue à part, et chaque lecture vérifie tout le registre de l'autorité : le temps croît avec la taille du store. Mesuré sur une machine cloud à 2 CPU avec Python 3.13 : 500 entrées en 12 secondes, à peu près autant quand rien n'a changé. Il n'y a pas encore de mode incrémental ; pour un gros store, lancez-le depuis une tâche planifiée plutôt qu'à la main.
