# Agent frameworks

[Français](FRAMEWORKS.fr.md) · [MCP server](MCP.md) · [Connect your tools](SETUP.md) · [README](../README.md)

persistent-memory does not depend on an agent framework. A Python agent can use the library directly (`from persistent_memory import PersistentMemory`). Any framework that speaks MCP can use the server, over stdio or Streamable HTTP, from any language.

## Checked frameworks

On 15 November 2026, on Linux with Python 3.13, each framework's own MCP integration loaded the ten tools and ran the same sequence: remember a fact, find it, withdraw it, search again. In every case the withdrawn entry was no longer returned. No model was called: these checks cover the tool layer, not an agent's choices.

| Framework | Version checked | Integration | Transport |
| --- | --- | --- | --- |
| LangChain / LangGraph | langchain-mcp-adapters 0.3.2, langgraph 1.2.22 | `MultiServerMCPClient` | stdio |
| OpenAI Agents SDK | openai-agents 0.24.0 | `MCPServerStdio`, `MCPServerStreamableHttp` | stdio, HTTP |
| Pydantic AI | pydantic-ai-slim 2.68.0 | `MCPToolset` | stdio, HTTP |
| CrewAI | crewai, crewai-tools 1.15.41 | `MCPServerAdapter` | stdio |
| LlamaIndex | llama-index-tools-mcp 0.7.0 | `McpToolSpec` | stdio |
| Microsoft AutoGen | autogen-ext 0.7.5 | `mcp_server_tools` | stdio |
| smolagents | smolagents 1.26.0 | `ToolCollection.from_mcp` | stdio |
| Official MCP Python SDK | mcp 2.3.0 (and 1.30.0) | `ClientSession` | stdio, HTTP |

Notes:

- CrewAI's adapter sends every unset optional argument as `null`. The server treats a `null` optional argument as absent; unknown arguments are still refused.
- AutoGen 0.7.5 and smolagents 1.26.0 do not import with the MCP Python SDK 2.x; install them with `"mcp<2"` (smolagents also needs `mcp[ws]`). The server works with clients on both SDK versions.
- Results come back in each framework's own shape: JSON text, a parsed dictionary, or content blocks.

In the snippets, `CMD` is the path of `persistent-memory-mcp` in the environment where persistent-memory is installed, and `STORE` a store folder (`persistent-memory status` shows the default one).

## LangChain / LangGraph

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({"memory": {"transport": "stdio", "command": CMD,
                                          "args": ["--store", STORE, "--create"]}})
tools = await client.get_tools()            # ten LangChain tools
# from langgraph.prebuilt import create_react_agent
# agent = create_react_agent(model, tools)
```

## OpenAI Agents SDK

```python
from agents import Agent
from agents.mcp import MCPServerStdio

server = MCPServerStdio(params={"command": CMD, "args": ["--store", STORE, "--create"]})
async with server:
    agent = Agent(name="assistant", instructions="...", mcp_servers=[server])
```

Over HTTP: `MCPServerStreamableHttp(params={"url": "http://127.0.0.1:8766/mcp"})` with `persistent-memory-mcp --transport http` running.

## Pydantic AI

```python
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

memory = MCPToolset(StdioTransport(CMD, ["--store", STORE, "--create"]))
agent = Agent("openai:gpt-5", toolsets=[memory])
```

Over HTTP: `MCPToolset("http://127.0.0.1:8766/mcp")`.

## CrewAI

```python
from crewai import Agent
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

params = StdioServerParameters(command=CMD, args=["--store", STORE, "--create"])
with MCPServerAdapter(params) as tools:
    agent = Agent(role="...", goal="...", backstory="...", tools=list(tools))
```

## LlamaIndex

```python
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

tools = await McpToolSpec(BasicMCPClient(CMD, args=["--store", STORE, "--create"])).to_tool_list_async()
# FunctionAgent(tools=tools, llm=llm)
```

## Microsoft AutoGen

```python
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools

tools = await mcp_server_tools(StdioServerParams(command=CMD, args=["--store", STORE, "--create"]))
# AssistantAgent("assistant", model_client=model_client, tools=tools)
```

## smolagents

```python
from mcp import StdioServerParameters
from smolagents import ToolCollection

params = StdioServerParameters(command=CMD, args=["--store", STORE, "--create"])
with ToolCollection.from_mcp(params, trust_remote_code=True) as collection:
    tools = [*collection.tools]          # CodeAgent(tools=tools, model=model)
```

## Without MCP

In Python, the library gives the same operations without a server; the [operations surface](OPERATIONS.md) describes them.

```python
from persistent_memory import PersistentMemory

memory = PersistentMemory(STORE, "my-agent", create=True)
memory.remember("The staging database listens on port 6543.", source_id="staging-db")
memory.search("staging database port", session="run-42")
```

The lines that hand the tools to an agent (commented out, or the `Agent(...)` calls) need a model and were not run in these checks; the tool loading and the calls above them were.
