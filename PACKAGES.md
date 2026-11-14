# Persistent Memory packages

[Français](PACKAGES.fr.md)

The memory core is `hermes-memory-core==0.3.0a5`. Its [archive qualification and checksums](docs/releases/0.3.0a5/README.md) are available with the release. The optional policy registry is `hermes-policy-registry==0.2.0a2`. They install independently and have no runtime dependency on each other.

The [registry guide](https://github.com/Musyg/persistent-memory/tree/main/packages/policy-registry) and its French counterpart describe the contract and synthetic example. The registry 0.2.0a2 [release](https://github.com/Musyg/persistent-memory/releases/tag/policy-registry-v0.2.0a2) contains its own wheel, source archive and checksums. Registry wheels and source archives are separate release assets; a standalone core source archive does not contain the registry package.

From a checkout of the complete repository:

```sh
python3 -m pip install ./packages/policy-registry
hermes-policy-demo --directory ./new-policy-demo
```

The registry records proposals, evidence, admissions and rollbacks. It does not execute policies, select an active policy, change runtime permissions or authenticate a judge. Demo labels and durations are invented synthetic values, not measured retrieval performance. The core 0.3.0a2 release adds optional exact-reference contexts and a Python typed-only server mode. Registry 0.2.0a2 adds explicit workflow-effect assessment, binding immutable rule/oracle/dataset identities to independently reopened effects; a trusted host supplies verification and activation. Neither package trains model weights or changes permissions. Experimental retrieval R4 is not included.

Registry 0.2.0a2 was qualified from its installed wheel and a wheel rebuilt from its source archive: each ran 49 synthetic tests without failures, errors or skips. These are contract and installation checks, not a general memory-quality score. The existing core release assets remain unchanged.

Core 0.3.0a3 preserves full integrity verification while reducing redundant serialization and parsing. The [two-host performance and failure checks](benchmarks/efficiency-20261023/core-optimization-20261023/README.md) and [learned-experience study](benchmarks/action-20261023/experience/README.md) describe the new evidence. Earlier release assets remain unchanged.

## Hermes Agent provider

`hermes-agent-provenance==0.1.0a1`, in [packages/hermes-agent-provider](packages/hermes-agent-provider/README.md), connects the memory core to [Hermes Agent](https://github.com/NousResearch/hermes-agent) as an external memory provider named `provenance`. Unlike the registry, it depends on the core at runtime. It recalls only items the current authority still allows, stores nothing without an explicit tool call, and warns a Hermes session when a source it was already shown is withdrawn. It is an independent integration, not affiliated with Nous Research, and is not yet published as a release.

```sh
python3 -m pip install . ./packages/hermes-agent-provider
```

Run this in the environment that runs Hermes Agent, then set `memory.provider: provenance` in the profile's `config.yaml`. Its synthetic tests run without Hermes Agent and are part of `scripts/check_distributions.py`, which installs the core wheel next to it; a separate suite drives it through Hermes Agent's own memory manager.

## Remote MCP endpoint

`hermes-memory-mcp==0.1.0a1`, in [packages/remote-mcp](packages/remote-mcp/README.md), serves the same store over MCP's Streamable HTTP transport with a bearer token, standard library only. MCP clients that accept a URL and a header, such as Claude Code or Hermes Agent, can search, add and withdraw; a withdrawal warns every MCP or Hermes Agent session that was shown the source. It depends on the core and on the Hermes Agent provider, whose store and exposure ledger it shares. OAuth is not supported yet, and it is not yet published as a release.
