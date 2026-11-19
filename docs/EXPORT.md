# Export to Markdown notes

[Français](EXPORT.fr.md) · [Operations](OPERATIONS.md) · [MCP server](MCP.md)

`persistent-memory export` writes what the memory serves now as a folder of Markdown notes: one note per entry, with its provenance as links, and an index per workspace. Point it at a folder inside an Obsidian vault and you can browse the memory, follow a note back to the facts it was derived from, and see the graph. The base install is enough; nothing else to install.

```sh
persistent-memory export ~/Notes/Vault/memory
```

```text
2 notes in /home/me/Notes/Vault/memory (obsidian): 3 written, 0 unchanged, 0 removed
```

The export goes one way: memory to notes. Changing a note does not change the memory. To correct or withdraw an entry, use the memory (`memory_correct`, `memory_withdraw`, or the Python methods), then run the export again.

## What a note looks like

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

- **Properties.** Every value is written as JSON, which is also valid YAML, so Obsidian shows them as properties and any YAML parser reads them back. Empty fields are left out. Validity windows (`valid_from`, `valid_until`), `confidence`, `preconditions` and `aliases` appear when the entry has them.
- **Title and text.** The title is the first line of the text, cut at 80 characters. The full text follows, unless it is that single line.
- **Provenance.** "Derived from" and "Cites" link to the parents. If a parent has a newer version than the one this entry was derived from, the line says so; a parent the memory no longer serves is named without a link. "Used by" lists the entries derived from this one.
- **Index.** `<workspace>/index.md` lists the entries by kind, with the checkpoint they were read at.

`--style markdown` writes plain relative links (`[deploy-day](<deploy-day.md>)`) for editors without wikilinks; `derived_from` then holds bare ids.

## Run it again

The export is meant to be run again, by hand or from a scheduled task. Each run brings the folder in line with the memory:

- a new entry gets a note, a correction rewrites the note with the new version;
- an entry the memory no longer serves loses its note: withdrawn, superseded, or derived from something withdrawn. Folders left empty are removed;
- a note whose content did not change is not rewritten, so its modification time and your sync tool stay quiet.

What the export wrote is recorded in `.persistent-memory-export.json`, at the top of the folder, with the SHA-256 of each file. That record is what makes it safe to share the folder with your own notes:

- **A note you edited is kept.** If a note's content no longer matches what the export wrote, the export does not overwrite it and does not delete it, even when its entry is withdrawn. The run lists it and exits with code 3. `--force` overwrites or removes it.
- **A file the export did not write is never touched**, even with `--force`, even when an entry would want its name. That entry's note is skipped and listed.
- **A folder the export did not create is refused** if it is not empty (`export_target_not_empty`). Give an empty or new folder, or one written by an earlier export.
- **Nothing outside the folder.** A record listing a path outside the folder is refused (`export_manifest_unreadable`) before anything is deleted, and so is a folder link inside it that leads outside (`export_path_escapes`). The folder cannot be inside the store (`export_inside_store`).

## Withdrawn entries

By default, a withdrawn entry simply disappears from the notes: the export shows what the memory would serve to an agent, nothing more. With `--include-withdrawn`, entries no longer served also get a short note under `<workspace>/_withdrawn/`, with their id, version, state and the reason the memory gives, and without their text. A secret withdrawn by mistake does not come back through the export.

## File names

A note is named after its artifact id. An id that cannot be a file name on every platform (characters such as `/ : ? * [ ] #`, a Windows device name such as `CON`, more than 100 bytes) is cleaned and gets a short hash suffix. Two ids that differ only by case would share a file on macOS and Windows, so both get a suffix; the names do not depend on the order entries were written. The real id is always in the `artifact_id` property.

## Options

| Option | Effect |
|---|---|
| `output` | Folder to write: empty, new, or written by an earlier export |
| `--store DIR` | Store to read; default `$PERSISTENT_MEMORY_DIR` or the platform data folder |
| `--workspace NAME` | Only this workspace; repeatable. Default: every workspace in the store |
| `--style obsidian` | Wikilinks and properties (default) |
| `--style markdown` | Relative Markdown links |
| `--include-withdrawn` | Also write a note without text for each entry no longer served |
| `--force` | Overwrite or remove notes edited by hand |
| `--json` | Print the report as JSON |

Exit codes: 0 done; 3 done, but some files were kept (edited by hand, or not written by the export); 1 refused, with the reason on stderr.

From Python:

```python
from persistent_memory import export_store

report = export_store("~/.local/share/persistent-memory", "~/Notes/Vault/memory", style="obsidian")
print(report["written"], report["removed"], report["kept_edited"])
```

## Limits

- Reading goes through the same checks as any read: each note is the version the authority serves at that moment, and the index records the checkpoint epoch. An entry written while the export runs is picked up by the next run.
- The export holds the text of the entries it writes. Treat the folder like the store itself when you sync or share it, and leave withdrawn text out (the default) unless you need the trace.
- Each entry is read on its own, and each read checks the whole authority ledger, so the time grows with the size of the store. Measured on a 2-CPU cloud machine with Python 3.13: 500 entries in 12 seconds, about the same when nothing changed. There is no incremental mode yet; for a large store, run it from a scheduled task rather than by hand.
