# Frameworks d'agents

[English](FRAMEWORKS.md) · [Serveur MCP](MCP.fr.md) · [Brancher vos outils](SETUP.fr.md) · [README](../README.fr.md)

persistent-memory ne dépend d'aucun framework d'agents. Un agent en Python peut utiliser directement la bibliothèque (`from persistent_memory import PersistentMemory`). Tout framework qui parle MCP peut utiliser le serveur, en stdio ou en HTTP (Streamable HTTP), depuis n'importe quel langage.

## Frameworks vérifiés

Le 15 novembre 2026, sous Linux avec Python 3.13, l'intégration MCP propre à chaque framework a chargé les dix outils et exécuté la même suite : mémoriser un fait, le retrouver, le retirer, chercher à nouveau. Dans tous les cas, l'entrée retirée n'était plus renvoyée. Aucun modèle n'a été appelé : ces contrôles portent sur la couche des outils, pas sur les choix d'un agent.

| Framework | Version vérifiée | Intégration | Transport |
| --- | --- | --- | --- |
| LangChain / LangGraph | langchain-mcp-adapters 0.3.2, langgraph 1.2.22 | `MultiServerMCPClient` | stdio |
| OpenAI Agents SDK | openai-agents 0.24.0 | `MCPServerStdio`, `MCPServerStreamableHttp` | stdio, HTTP |
| Pydantic AI | pydantic-ai-slim 2.68.0 | `MCPToolset` | stdio, HTTP |
| CrewAI | crewai, crewai-tools 1.15.41 | `MCPServerAdapter` | stdio |
| LlamaIndex | llama-index-tools-mcp 0.7.0 | `McpToolSpec` | stdio |
| Microsoft AutoGen | autogen-ext 0.7.5 | `mcp_server_tools` | stdio |
| smolagents | smolagents 1.26.0 | `ToolCollection.from_mcp` | stdio |
| SDK MCP officiel pour Python | mcp 2.3.0 (et 1.30.0) | `ClientSession` | stdio, HTTP |

Remarques :

- L'adaptateur de CrewAI envoie chaque argument facultatif non renseigné avec la valeur `null`. Le serveur traite un argument facultatif `null` comme absent ; les arguments inconnus restent refusés.
- AutoGen 0.7.5 et smolagents 1.26.0 ne s'importent pas avec la version 2.x du SDK MCP pour Python ; installez-les avec `"mcp<2"` (smolagents demande aussi `mcp[ws]`). Le serveur fonctionne avec des clients sur les deux versions du SDK.
- Les résultats reviennent sous la forme propre à chaque framework : texte JSON, dictionnaire déjà lu ou blocs de contenu.

Dans les extraits, `CMD` est le chemin de `persistent-memory-mcp` dans l'environnement où persistent-memory est installé, et `STORE` un dossier de mémoire (`persistent-memory status` indique celui par défaut).

## LangChain / LangGraph

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({"memory": {"transport": "stdio", "command": CMD,
                                          "args": ["--store", STORE, "--create"]}})
tools = await client.get_tools()            # dix outils LangChain
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

En HTTP : `MCPServerStreamableHttp(params={"url": "http://127.0.0.1:8766/mcp"})`, avec `persistent-memory-mcp --transport http` lancé.

## Pydantic AI

```python
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

memory = MCPToolset(StdioTransport(CMD, ["--store", STORE, "--create"]))
agent = Agent("openai:gpt-5", toolsets=[memory])
```

En HTTP : `MCPToolset("http://127.0.0.1:8766/mcp")`.

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

## Sans MCP

En Python, la bibliothèque donne les mêmes opérations sans serveur ; la [surface d'opérations](OPERATIONS.fr.md) les décrit.

```python
from persistent_memory import PersistentMemory

memory = PersistentMemory(STORE, "my-agent", create=True)
memory.remember("The staging database listens on port 6543.", source_id="staging-db")
memory.search("staging database port", session="run-42")
```

Les lignes qui confient les outils à un agent (en commentaire, ou les appels `Agent(...)`) demandent un modèle et n'ont pas été exécutées pendant ces contrôles ; le chargement des outils et les appels qui les précèdent l'ont été.
