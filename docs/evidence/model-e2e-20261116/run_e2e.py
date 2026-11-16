"""End-to-end check with a real model: an OpenAI Agents SDK agent, a local model served by Ollama,
and persistent-memory-mcp from PyPI over MCP stdio. Each turn is a new agent run with no chat
history and a new server process, so whatever the agent knows comes from the memory store."""
import asyncio, json, os, sys, time
from pathlib import Path

from agents import Agent, Runner, OpenAIChatCompletionsModel, RunHooks, set_tracing_disabled
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI

HERE = Path(__file__).resolve().parent
STORE = HERE / "store"
CMD = str(HERE / "venv" / "bin" / "persistent-memory-mcp")
MODEL = os.environ.get("E2E_MODEL", "gpt-oss:20b")
set_tracing_disabled(True)
client = AsyncOpenAI(base_url="http://127.0.0.1:11434/v1", api_key="local")
model = OpenAIChatCompletionsModel(model=MODEL, openai_client=client)

INSTRUCTIONS = (
    "You have a long-term memory available through tools. "
    "Before answering a question about a fact, call memory_search. "
    "When the user states a fact to keep, call memory_remember. "
    "To change a stored fact, find it with memory_search, then call memory_correct with its artifact_id "
    "and the version_id of its ref as expected_version. "
    "To remove a fact, find it with memory_search, then call memory_withdraw with its artifact_id. "
    "Answer in one short sentence. If memory returns nothing relevant, say that you do not know."
)

TURNS = [
    ("remember", "Remember this: the staging database listens on port 6543."),
    ("ask_1", "Which port does the staging database listen on?"),
    ("correct", "Update your memory: the staging database now listens on port 6544."),
    ("ask_2", "Which port does the staging database listen on?"),
    ("withdraw", "The staging database has been decommissioned. Withdraw that fact from your memory."),
    ("ask_3", "Which port does the staging database listen on?"),
]


class Log(RunHooks):
    def __init__(self):
        self.calls = []
    async def on_tool_start(self, context, agent, tool):
        args = getattr(context, "tool_arguments", None)
        self.calls.append({"tool": tool.name, "arguments": args})
        print("  call", tool.name, str(args)[:300], flush=True)
    async def on_tool_end(self, context, agent, tool, result):
        if self.calls:
            self.calls[-1]["output"] = str(result)[:600]
        print("  out ", tool.name, str(result)[:300], flush=True)


async def turn(name, prompt):
    server = MCPServerStdio(params={"command": CMD, "args": ["--store", str(STORE), "--create"]},
                            client_session_timeout_seconds=60)
    started = time.time()
    async with server:
        agent = Agent(name="assistant", instructions=INSTRUCTIONS, model=model, mcp_servers=[server])
        log = Log()
        print("turn", name, flush=True)
        try:
            result = await Runner.run(agent, prompt, max_turns=8, hooks=log)
            answer, error = str(result.final_output), None
        except Exception as exc:
            answer, error = "", type(exc).__name__ + ": " + str(exc)
    return {"turn": name, "prompt": prompt, "tool_calls": log.calls, "answer": answer,
            "error": error, "seconds": round(time.time() - started, 1)}


async def main():
    records = []
    for name, prompt in TURNS:
        rec = await turn(name, prompt)
        records.append(rec)
        print(json.dumps(rec, ensure_ascii=False)[:900], flush=True)
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
    m = PersistentMemory(str(STORE), "default")
    left = m.search("staging database port")
    checks["store_search_empty_after_withdraw"] = left["items"] == []
    report = {"model": MODEL, "framework": "openai-agents", "transport": "stdio",
              "package": "persistent-memory-mcp", "turns": records, "checks": checks,
              "passed": all(checks.values())}
    (HERE / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(checks), "PASSED" if report["passed"] else "FAILED")

if __name__ == "__main__":
    asyncio.run(main())
