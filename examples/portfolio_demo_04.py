"""Record the 0.4.0a4 portfolio scenario through the real MCP server.

Five steps on one synthetic store, each one a real stdio session of
persistent-memory-mcp or a real `persistent-memory review` command:

1. Agent A remembers a fact and derives a rule from it.
2. Agent A writes nearly the same fact again: the result names the close
   entry, and the agent withdraws its duplicate.
3. Agent A asks in French for a fact stored in English (--semantic); the
   same question to a server without --semantic finds nothing.
4. Agent B, in review mode, proposes a correction; nothing changes until a
   person approves it with `persistent-memory review approve`.
5. Agent A comes back: the derived rule is no longer served, and the
   result carries notices for both versions it was shown.

    python examples/portfolio_demo_04.py --store NEW_DIR --output trace.json \
        [--models DIR_WITH_FASTEMBED_CACHE]

It needs persistent-memory-mcp 0.4.0a4 with the semantic extra. Without
--models, the first semantic session downloads the default model (about 1 GB).

The trace holds tool names, arguments, the result fields the page shows and
checked Boolean assertions. No paths, host names or identities.
"""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA = "persistent-memory.portfolio-demo.release-0.4.v1"
BIN = Path(sys.executable).parent  # the console scripts installed with the package


def command(name):
    found = shutil.which(name, path=str(BIN))
    if found is None:
        raise SystemExit("%s not found next to %s" % (name, sys.executable))
    return found
EXPECTED_VERSION = "0.4.0a4"


class Server:
    """One stdio MCP session: one server process, one ledger session."""

    def __init__(self, store, session, *extra):
        self.process = subprocess.Popen(
            [command("persistent-memory-mcp"), "--store", str(store), "--workspace", "atlas", "--session", session, *extra],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")
        self.next_id = 0
        init = self.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                           "clientInfo": {"name": "portfolio-demo", "version": "1"}})
        self.instructions = init["result"].get("instructions", "")
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        line = self.process.stdout.readline()
        if not line:
            raise SystemExit("server stopped: " + self.process.stderr.read())
        return json.loads(line)

    def call(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})["result"]
        return result["structuredContent"], result["isError"]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=60)


def short(ref):
    return {"artifact_id": ref["artifact_id"], "version": ref["version_id"][:12]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--models", help="existing fastembed cache to link as the store's models folder")
    options = parser.parse_args()
    store, output = Path(options.store), Path(options.output)
    if store.exists() or output.exists():
        raise SystemExit("choose a new store directory and a new output file")
    version = importlib.metadata.version("persistent-memory-mcp")
    if version != EXPECTED_VERSION:
        raise SystemExit("persistent-memory-mcp %s is installed, %s expected" % (version, EXPECTED_VERSION))
    subprocess.run([command("persistent-memory-mcp"), "--store", str(store), "--create", "--workspace", "atlas"], stdin=subprocess.DEVNULL, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if options.models:
        os.symlink(Path(options.models).resolve(), store / "models", target_is_directory=True)

    steps, checks = [], {}

    # 1. Agent A: a fact and a rule derived from it.
    a = Server(store, "agent-a", "--semantic")
    fact, _ = a.call("memory_remember", {"text": "Deploys happen on Tuesdays.", "source_id": "deploy-day"})
    rule, _ = a.call("memory_derive", {"text": "Freeze the main branch on Monday evening, before the deploy.",
                                       "parents": [fact["ref"]], "artifact_id": "freeze-rule"})
    steps.append({"step": "remember", "actor": "agent-a", "calls": [
        {"tool": "memory_remember", "arguments": {"text": "Deploys happen on Tuesdays.", "source_id": "deploy-day"},
         "result": {"ref": short(fact["ref"])}},
        {"tool": "memory_derive", "arguments": {"text": "Freeze the main branch on Monday evening, before the deploy.",
                                                "parents": ["deploy-day"], "artifact_id": "freeze-rule"},
         "result": {"ref": short(rule["ref"]), "parents": [short(fact["ref"])]}}]})
    checks["rule_names_exact_parent"] = rule["ref"]["artifact_id"] == "freeze-rule"

    # 2. Near-duplicate.
    dup, _ = a.call("memory_remember", {"text": "Deploys happen on Tuesday.", "source_id": "deploy-day-2"})
    similar = [{"artifact_id": s["artifact_id"], "text": s["text"], "overlap": s["overlap"]}
               for s in dup.get("similar", [])]
    gone, _ = a.call("memory_withdraw", {"artifact_id": "deploy-day-2", "reason": "duplicate of deploy-day"})
    steps.append({"step": "near_duplicate", "actor": "agent-a", "calls": [
        {"tool": "memory_remember", "arguments": {"text": "Deploys happen on Tuesday.", "source_id": "deploy-day-2"},
         "result": {"ref": short(dup["ref"]), "similar": similar, "similar_hint": dup.get("similar_hint")}},
        {"tool": "memory_withdraw", "arguments": {"artifact_id": "deploy-day-2", "reason": "duplicate of deploy-day"},
         "result": {"blocked": sorted({(r.get("artifact_id") if isinstance(r, dict) else r)
                                        for r in gone.get("blocked", [])})}}]})
    checks["duplicate_named_original"] = any(s["artifact_id"] == "deploy-day" for s in similar)
    checks["write_not_refused"] = dup.get("ref", {}).get("artifact_id") == "deploy-day-2"

    # 3. Search by meaning, in another language.
    query = "Quand déployons-nous ?"
    found, _ = a.call("memory_search", {"query": query})
    hits = [item["artifact_id"] for item in found["items"]]
    a.close()
    keywords = Server(store, "keywords-only")  # the same query without --semantic, for comparison
    lexical, _ = keywords.call("memory_search", {"query": query})
    keywords.close()
    steps.append({"step": "semantic_search", "actor": "agent-a", "calls": [
        {"tool": "memory_search", "arguments": {"query": query},
         "result": {"items": [{"artifact_id": i["artifact_id"], "text": i["text"]} for i in found["items"]],
                    "semantic": found.get("semantic")}},
        {"tool": "memory_search", "server": "without --semantic", "arguments": {"query": query},
         "result": {"items": [{"artifact_id": i["artifact_id"], "text": i["text"]} for i in lexical["items"]]}}]})
    checks["found_by_meaning"] = "deploy-day" in hits and (found.get("semantic") or {}).get("candidates", 0) > 0
    checks["keywords_alone_find_nothing"] = lexical["items"] == []

    # 4. Agent B in review mode proposes a correction; a person approves it.
    b = Server(store, "agent-b", "--review")
    seen, _ = b.call("memory_search", {"query": "deploys"})
    fact_ref = next(i["ref"] for i in seen["items"] if i["artifact_id"] == "deploy-day")
    current = fact_ref["version_id"]
    proposal, _ = b.call("memory_correct", {"artifact_id": "deploy-day", "text": "Deploys happen on Thursdays.",
                                            "expected_version": current})
    before, _ = b.call("memory_read", {"ref": fact_ref})
    b.close()
    approve = subprocess.run([command("persistent-memory"), "review", "--store", str(store),
                              "approve", proposal["proposal_id"]], capture_output=True, text=True)
    steps.append({"step": "review", "actor": "agent-b", "calls": [
        {"tool": "memory_correct", "arguments": {"artifact_id": "deploy-day", "text": "Deploys happen on Thursdays.",
                                                 "expected_version": current[:12]},
         "result": {"status": proposal.get("status"), "proposal_id": proposal.get("proposal_id")}},
        {"tool": "memory_read", "arguments": {"ref": short(fact_ref)},
         "result": {"allowed": before.get("allowed"), "text": before.get("text")}},
        {"command": "persistent-memory review approve " + proposal["proposal_id"], "actor": "person",
         "exit_code": approve.returncode}]})
    checks["proposal_pending"] = proposal.get("status") == "pending_review"
    checks["nothing_changed_before_approval"] = before.get("allowed") is True and \
        before.get("text") == "Deploys happen on Tuesdays."
    checks["approved"] = approve.returncode == 0

    # 5. Agent A comes back: cascade and notices.
    a = Server(store, "agent-a", "--semantic")
    after, _ = a.call("memory_search", {"query": "freeze the main branch before the deploy"})
    rule_read, _ = a.call("memory_read", {"ref": rule["ref"]})
    notices = [{"artifact_id": n["artifact_id"], "state": n["state"]} for n in after.get("memory_notices", [])]
    steps.append({"step": "cascade_and_notices", "actor": "agent-a", "calls": [
        {"tool": "memory_search", "arguments": {"query": "freeze the main branch before the deploy"},
         "result": {"items": [{"artifact_id": i["artifact_id"], "text": i["text"]} for i in after["items"]],
                    "memory_notices": notices}},
        {"tool": "memory_read", "arguments": {"ref": short(rule["ref"])},
         "result": {"allowed": rule_read.get("allowed"), "reason": rule_read.get("reason")}}]})
    a.close()
    checks["rule_not_served"] = "freeze-rule" not in [i["artifact_id"] for i in after["items"]] \
        and rule_read.get("allowed") is False
    checks["notice_for_fact"] = any(n["artifact_id"] == "deploy-day" for n in notices)
    checks["notice_for_rule"] = any(n["artifact_id"] == "freeze-rule" for n in notices)

    script = Path(__file__).read_bytes()
    trace = {
        "schema": SCHEMA, "scenario": "deploy-day-v1", "synthetic": True,
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": {"package": "persistent-memory-mcp", "installed_version": version,
                       "fastembed": importlib.metadata.version("fastembed"),
                       "python": "%d.%d" % sys.version_info[:2], "platform": sys.platform,
                       "script_sha256": hashlib.sha256(script).hexdigest()},
        "steps": steps, "checks": checks, "all_checks_passed": all(checks.values()),
    }
    output.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=2))
    if not trace["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
