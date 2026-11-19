"""One-way export of a store to a folder of Markdown notes (Obsidian or plain links).

The memory stays the only authority: every note is a version the authority serves at
export time, read through PersistentMemory.read like any other reader. Running the export
again brings the folder to the current state: new and corrected entries are written,
withdrawn or superseded ones disappear. Nothing in the folder is ever read back.

The folder is managed through a manifest (.persistent-memory-export.json) that records
every file the export wrote and its SHA-256. A run only ever overwrites or deletes files
of that manifest whose bytes are still the ones it wrote: a note edited by hand is kept and
reported, a file the export did not write is never touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .core import MemoryError, require

__all__ = ["export_store", "MANIFEST", "STYLES"]

MANIFEST = ".persistent-memory-export.json"
MANIFEST_SCHEMA = "persistent-memory.export.v1"
STYLES = ("obsidian", "markdown")
WITHDRAWN_FOLDER = "_withdrawn"
INDEX = "index.md"
# Characters that break a file name on one of the three platforms or an Obsidian link.
_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*\[\]#^]')
_RESERVED = {"con", "prn", "aux", "nul", *("com%d" % i for i in range(1, 10)), *("lpt%d" % i for i in range(1, 10))}
_STEM_LIMIT = 100


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _stem(artifact_id):
    """A file name stem every platform accepts; an id that had to change gets a hash suffix."""
    text = unicodedata.normalize("NFC", artifact_id)
    safe = _UNSAFE.sub("_", text).strip(" .") or "_"
    if safe.split(".")[0].lower() in _RESERVED:
        safe = "_" + safe
    if safe != artifact_id or len(safe.encode("utf-8")) > _STEM_LIMIT:
        cut = safe.encode("utf-8")[:_STEM_LIMIT - 9].decode("utf-8", "ignore").rstrip(" .")
        safe = "%s-%s" % (cut or "_", _sha(artifact_id.encode("utf-8"))[:8])
    return safe


def _yaml(value):
    """YAML scalar or flow sequence: JSON is valid YAML, and quoting keeps every value a string."""
    if isinstance(value, list):
        return "[" + ", ".join(_yaml(v) for v in value) + "]"
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return json.dumps(str(value), ensure_ascii=False)


def _title(text):
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line if len(line) <= 80 else line[:77].rstrip() + "..."
    return "(empty)"


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pm-export-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _workspaces(root):
    from .core import Authority
    authority = Authority.open(root / "authority" / "authority.db", root / "anchor" / "checkpoint.json")
    with authority.transaction() as c:
        return [row[0] for row in c.execute("SELECT DISTINCT workspace FROM heads ORDER BY workspace")]


def _collect(memory):
    """Every current head of one workspace, read through the authority like any reader."""
    # Heads and their direct dependencies come from one verified authority transaction (the
    # same rows explain_artifact reads); each text is then read on its own, like any reader.
    with memory.memory.authority.transaction() as c:
        heads = c.execute("SELECT h.artifact_id, h.version_id, o.kind, o.dependencies FROM heads h JOIN objects o "
                          "ON o.workspace=h.workspace AND o.artifact_id=h.artifact_id AND o.version_id=h.version_id "
                          "WHERE h.workspace=? ORDER BY h.artifact_id", (memory.workspace,)).fetchall()
    entries = []
    for artifact_id, version_id, authority_kind, dependencies in heads:
        ref = {"workspace": memory.workspace, "artifact_id": artifact_id, "version_id": version_id}
        decision = memory.read(ref)
        node = {"dependencies": json.loads(dependencies)}
        entries.append({
            "workspace": memory.workspace, "artifact_id": artifact_id, "version_id": version_id,
            "authority_kind": authority_kind, "readable": decision["allowed"], "state": decision["state"],
            "reason": decision["reason"], "text": decision.get("text"), "metadata": decision.get("metadata") or {},
            "content_sha256": decision.get("content_sha256"),
            "parents": [{"artifact_id": d["ref"]["artifact_id"], "version_id": d["ref"]["version_id"],
                         "relation": d["relation"]} for d in node["dependencies"]],
        })
    return entries


def _paths(entries, include_withdrawn):
    """Relative note path per (workspace, artifact_id); stems unique case-insensitively per folder."""
    chosen = []
    for e in entries:
        if not e["readable"] and not include_withdrawn:
            continue
        folder = _stem(e["workspace"])
        if not e["readable"]:
            folder += "/" + WITHDRAWN_FOLDER
        chosen.append((e, folder, _stem(e["artifact_id"])))
    folded = [(folder.lower(), stem.lower()) for _, folder, stem in chosen]
    paths = {}
    for (e, folder, stem), key in zip(chosen, folded):
        if folded.count(key) > 1 or stem.lower() == INDEX[:-3]:
            # Ids that differ only by case (or by unsafe characters) would share one file on a
            # case-insensitive disk: each of them gets a hash suffix, whatever the order.
            # An id named like the index note gets one too.
            stem = "%s-%s" % (stem.encode("utf-8")[:_STEM_LIMIT - 9].decode("utf-8", "ignore"),
                              _sha(e["artifact_id"].encode("utf-8"))[:8])
        paths[(e["workspace"], e["artifact_id"])] = "%s/%s.md" % (folder, stem)
    return paths


class _Links:
    def __init__(self, paths, style):
        self.paths, self.style = paths, style
        stems = [p.rsplit("/", 1)[1][:-3].lower() for p in paths.values()]
        self.unique = {s for s in stems if stems.count(s) == 1}

    def __call__(self, source_path, workspace, artifact_id, label):
        target = self.paths.get((workspace, artifact_id))
        if target is None:
            return None
        if self.style == "obsidian":
            stem = target.rsplit("/", 1)[1][:-3]
            dest = stem if stem.lower() in self.unique else target[:-3]
            return "[[%s|%s]]" % (dest, label.replace("|", "/").replace("]", ")"))
        rel = os.path.relpath(target, os.path.dirname(source_path) or ".").replace(os.sep, "/")
        return "[%s](<%s>)" % (label.replace("]", ")"), rel)

    def bare(self, workspace, artifact_id):
        """A link target for a front matter property (Obsidian only)."""
        target = self.paths.get((workspace, artifact_id))
        if target is None or self.style != "obsidian":
            return artifact_id
        stem = target.rsplit("/", 1)[1][:-3]
        return "[[%s]]" % (stem if stem.lower() in self.unique else target[:-3])


def _front(fields):
    lines = ["---"]
    for key, value in fields:
        if value is None or value == [] or value == {}:
            continue
        lines.append("%s: %s" % (key, _yaml(value)))
    lines.append("---")
    return "\n".join(lines) + "\n"


def _note(entry, path, links, heads, dependents):
    ws, meta = entry["workspace"], entry["metadata"]
    kind = meta.get("evidence_kind") or entry["authority_kind"]
    title = _title(entry["text"])
    authority_kind = "source" if entry["authority_kind"] == "source" else "derived"
    front = _front([
        ("artifact_id", entry["artifact_id"]), ("workspace", ws), ("version", entry["version_id"]),
        ("state", entry["state"]), ("kind", kind), ("authority_kind", authority_kind),
        ("observed_at", meta.get("observed_at")), ("valid_from", meta.get("valid_from")),
        ("valid_until", meta.get("valid_until")), ("confidence", meta.get("confidence")),
        ("preconditions", meta.get("preconditions")), ("aliases", meta.get("aliases")),
        ("derived_from", [links.bare(ws, p["artifact_id"]) for p in entry["parents"]]),
        ("content_sha256", entry["content_sha256"]),
        ("tags", ["persistent-memory", "kind/" + re.sub(r"[^\w/-]", "_", kind)]),
    ])
    text = entry["text"].strip("\n")
    # A one-line entry is its own title; anything longer is kept whole under it.
    body = ["# " + title, ""] + ([] if text.strip() == title else [text, ""])
    lines = []
    for parent in entry["parents"]:
        link = links(path, ws, parent["artifact_id"], parent["artifact_id"])
        if link is None:
            link = "`%s` (not served now)" % parent["artifact_id"]
        note = "" if heads.get(parent["artifact_id"]) == parent["version_id"] else \
            ", from version `%s`, since replaced" % parent["version_id"][:12]
        lines.append("- %s %s%s" % ("Cites" if parent["relation"] == "cites" else "Derived from", link, note))
    for child in dependents:
        link = links(path, ws, child, child)
        if link is not None:
            lines.append("- Used by %s" % link)
    if lines:
        body += ["## Provenance", ""] + lines + [""]
    return front + "\n" + "\n".join(body)


def _stub(entry):
    front = _front([("artifact_id", entry["artifact_id"]), ("workspace", entry["workspace"]),
                    ("version", entry["version_id"]), ("state", entry["state"]), ("reason", entry["reason"]),
                    ("tags", ["persistent-memory", "state/" + entry["state"]])])
    return front + "\n# %s\n\nThe memory no longer serves this entry (state: %s). Its text is not exported.\n" % (
        entry["artifact_id"], entry["state"])


def _index(workspace, entries, path, links, epoch):
    readable = [e for e in entries if e["readable"]]
    groups = {}
    for e in readable:
        groups.setdefault(e["metadata"].get("evidence_kind") or e["authority_kind"], []).append(e)
    front = _front([("workspace", workspace), ("checkpoint_epoch", epoch), ("entries", len(readable)),
                    ("tags", ["persistent-memory", "persistent-memory/index"])])
    body = ["# Memory: %s" % workspace, "",
            "%d entr%s served by the memory at checkpoint %d. Generated by `persistent-memory export`; "
            "edit the memory, not these notes." % (len(readable), "y" if len(readable) == 1 else "ies", epoch), ""]
    for kind in sorted(groups):
        body += ["## %s (%d)" % (kind, len(groups[kind])), ""]
        for e in sorted(groups[kind], key=lambda x: (_title(x["text"]).lower(), x["artifact_id"])):
            body.append("- " + links(path, workspace, e["artifact_id"], _title(e["text"])))
        body.append("")
    # Entries not served are listed only when they are exported (--include-withdrawn).
    withdrawn = [e for e in entries if not e["readable"] and (workspace, e["artifact_id"]) in links.paths]
    if withdrawn:
        body += ["## Not served (%d)" % len(withdrawn), ""]
        for e in withdrawn:
            link = links(path, workspace, e["artifact_id"], e["artifact_id"])
            body.append("- %s (%s)" % (link or "`%s`" % e["artifact_id"], e["state"]))
        body.append("")
    return front + "\n" + "\n".join(body)


def _load_manifest(output):
    path = output / MANIFEST
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MemoryError("export_manifest_unreadable") from exc
    require(type(data) is dict and data.get("schema") == MANIFEST_SCHEMA and type(data.get("files")) is dict,
            "export_manifest_unreadable")
    for rel, digest in data["files"].items():
        require(type(rel) is str and type(digest) is str and _inside(output, rel), "export_manifest_unreadable")
    return data


def _inside(output, rel):
    target = (output / rel).resolve()
    root = output.resolve()
    return not Path(rel).is_absolute() and ".." not in Path(rel).parts and (target == root or root in target.parents)


def export_store(store, output, *, workspaces=None, style="obsidian", include_withdrawn=False, force=False):
    """Write the current state of a store as Markdown notes under output.

    Returns a report: files written, unchanged, removed, and kept because they were
    edited by hand (overwritten only with force=True) or not written by the export.
    """
    from .persistent import PersistentMemory
    require(style in STYLES, "invalid_export_style")
    root, output = Path(store).expanduser().absolute(), Path(output).expanduser().absolute()
    require((root / "authority" / "authority.db").is_file(), "store_missing")
    require(output != root and root not in output.parents, "export_inside_store")
    previous = _load_manifest(output) if output.exists() else None
    if output.exists():
        require(output.is_dir(), "export_target_not_a_folder")
        require(previous is not None or not any(output.iterdir()), "export_target_not_empty")
    names = sorted(_workspaces(root)) if not workspaces else sorted(set(workspaces))
    entries, epochs = [], {}
    for workspace in names:
        memory = PersistentMemory(root, workspace)
        epochs[workspace] = memory.checkpoint()["epoch"]
        entries += _collect(memory)
    paths = _paths(entries, include_withdrawn)
    links = _Links(paths, style)
    files = {}
    for workspace in names:
        mine = [e for e in entries if e["workspace"] == workspace]
        heads = {e["artifact_id"]: e["version_id"] for e in mine}
        children = {}
        for e in mine:
            if e["readable"]:
                for parent in e["parents"]:
                    children.setdefault(parent["artifact_id"], []).append(e["artifact_id"])
        for e in mine:
            path = paths.get((workspace, e["artifact_id"]))
            if path is None:
                continue
            files[path] = (_note(e, path, links, heads, sorted(set(children.get(e["artifact_id"], []))))
                           if e["readable"] else _stub(e))
        index_path = _stem(workspace) + "/" + INDEX
        files[index_path] = _index(workspace, mine, index_path, links, epochs[workspace])
    return _apply(output, previous, {k: v.encode("utf-8") for k, v in files.items()}, force,
                  {"style": style, "workspaces": names, "checkpoint_epochs": epochs,
                   "include_withdrawn": bool(include_withdrawn)})


def _apply(output, previous, files, force, info):
    from . import __version__
    from .persistent import utc_now
    old = previous["files"] if previous else {}
    report = {"written": [], "unchanged": [], "removed": [], "kept_edited": [], "kept_foreign": []}
    manifest = {}
    output.mkdir(parents=True, exist_ok=True)
    for rel in sorted(files):
        require(_inside(output, rel), "export_path_escapes")  # a linked folder must not lead outside
        data, target = files[rel], output / rel
        digest = _sha(data)
        if target.exists():
            current = _sha(target.read_bytes())
            if rel not in old:
                report["kept_foreign"].append(rel)  # never written by the export: never touched
                continue
            if current != old[rel] and not force:
                report["kept_edited"].append(rel)
                manifest[rel] = old[rel]  # still ours; the next run still sees the edit
                continue
            if current == digest:
                report["unchanged"].append(rel)
                manifest[rel] = digest
                continue
        _atomic_write(target, data)
        report["written"].append(rel)
        manifest[rel] = digest
    for rel in sorted(set(old) - set(files)):
        target = output / rel
        if not target.exists():
            continue
        if _sha(target.read_bytes()) != old[rel] and not force:
            report["kept_edited"].append(rel)  # released: no longer managed by the export
            continue
        target.unlink()
        report["removed"].append(rel)
        parent = target.parent
        while parent != output and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    record = {"schema": MANIFEST_SCHEMA, "generator": "persistent-memory " + __version__,
              "exported_at": utc_now(), **info, "files": manifest}
    _atomic_write(output / MANIFEST, (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    report.update(info)
    report["output"] = str(output)
    report["notes"] = sum(1 for rel in manifest if not rel.endswith("/" + INDEX))
    return report
