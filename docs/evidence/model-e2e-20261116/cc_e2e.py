"""The same six turns with Claude Code in headless mode (claude -p) and persistent-memory-mcp over stdio.
Each turn is a new claude process with no session history, so what it knows comes from the store."""
import json, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE / "store-cc"
CMD = str(HERE / "venv" / "bin" / "persistent-memory-mcp")
sys.path.insert(0, str(HERE))
from run_e2e import INSTRUCTIONS, TURNS  # noqa: E402  same prompts and instructions

CONFIG = HERE / "cc-mcp.json"
CONFIG.write_text(json.dumps({"mcpServers": {"memory": {
    "command": CMD, "args": ["--store", str(STORE), "--create"]}}}), encoding="utf-8")
TOOLS = ",".join("mcp__memory__memory_" + t for t in
                 ("search", "read", "remember", "correct", "explain", "plan_withdrawal", "withdraw"))


def turn(name, prompt):
    work = tempfile.mkdtemp(prefix="cc-e2e-")
    started = time.time()
    proc = subprocess.run(["claude", "-p", prompt, "--mcp-config", str(CONFIG), "--strict-mcp-config",
                           "--allowedTools", TOOLS, "--append-system-prompt", INSTRUCTIONS,
                           "--output-format", "stream-json", "--verbose", "--max-turns", "8"],
                          cwd=work, capture_output=True, text=True, timeout=300)
    calls, answer, model = [], "", None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            model = event.get("model")
        if event.get("type") == "assistant":
            for block in event["message"].get("content", []):
                if block.get("type") == "tool_use":
                    calls.append({"tool": block["name"].split("__")[-1], "arguments": block.get("input")})
                    print("  call", calls[-1]["tool"], json.dumps(block.get("input"))[:250], flush=True)
        if event.get("type") == "user":
            for block in event["message"].get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result" and calls:
                    calls[-1]["output"] = str(block.get("content"))[:600]
                    print("  out ", calls[-1]["output"][:250], flush=True)
        if event.get("type") == "result":
            answer = str(event.get("result", ""))
    return {"turn": name, "prompt": prompt, "model": model, "tool_calls": calls, "answer": answer,
            "returncode": proc.returncode, "stderr": proc.stderr[-400:], "seconds": round(time.time() - started, 1)}


def main():
    records = []
    for name, prompt in TURNS:
        print("turn", name, flush=True)
        rec = turn(name, prompt)
        records.append(rec)
        print("  answer:", rec["answer"][:300], flush=True)
    by = {r["turn"]: r for r in records}
    names = lambda r: [c["tool"] for c in r["tool_calls"]]
    checks = {
        "remember_called": "memory_remember" in names(by["remember"]),
        "ask_1_searched": "memory_search" in names(by["ask_1"]),
        "ask_1_says_6543": "6543" in by["ask_1"]["answer"],
        "correct_called": "memory_correct" in names(by["correct"]),
        "ask_2_says_6544_not_6543": "6544" in by["ask_2"]["answer"] and "6543" not in by["ask_2"]["answer"],
        "withdraw_called": "memory_withdraw" in names(by["withdraw"]),
        "ask_3_no_port": "6543" not in by["ask_3"]["answer"] and "6544" not in by["ask_3"]["answer"],
    }
    from persistent_memory import PersistentMemory
    left = PersistentMemory(str(STORE), "default").search("staging database port")
    checks["store_search_empty_after_withdraw"] = left["items"] == []
    report = {"client": "claude-code", "turns": records, "checks": checks, "passed": all(checks.values())}
    (HERE / "report-cc.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(checks), "PASSED" if report["passed"] else "FAILED")


if __name__ == "__main__":
    main()
