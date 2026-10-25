# Persistent Memory packages

[Français](PACKAGES.fr.md)

The memory core is `hermes-memory-core==0.3.0a4`. The optional policy registry is `hermes-policy-registry==0.2.0a2`. They install independently and have no runtime dependency on each other.

The [registry guide](https://github.com/Musyg/persistent-memory/tree/main/packages/policy-registry) and its French counterpart describe the contract and synthetic example. The registry 0.2.0a2 [release](https://github.com/Musyg/persistent-memory/releases/tag/policy-registry-v0.2.0a2) contains its own wheel, source archive and checksums. Registry wheels and source archives are separate release assets; a standalone core source archive does not contain the registry package.

From a checkout of the complete repository:

```sh
python3 -m pip install ./packages/policy-registry
hermes-policy-demo --directory ./new-policy-demo
```

The registry records proposals, evidence, admissions and rollbacks. It does not execute policies, select an active policy, change runtime permissions or authenticate a judge. Demo labels and durations are invented synthetic values, not measured retrieval performance. The core 0.3.0a2 release adds optional exact-reference contexts and a Python typed-only server mode. Registry 0.2.0a2 adds explicit workflow-effect assessment, binding immutable rule/oracle/dataset identities to independently reopened effects; a trusted host supplies verification and activation. Neither package trains model weights or changes permissions. Experimental retrieval R4 is not included.

Registry 0.2.0a2 was qualified from its installed wheel and a wheel rebuilt from its source archive: each ran 49 synthetic tests without failures, errors or skips. These are contract and installation checks, not a general memory-quality score. The existing core release assets remain unchanged.

Core 0.3.0a3 preserves full integrity verification while reducing redundant serialization and parsing. The [two-host performance and failure checks](benchmarks/efficiency-20261023/core-optimization-20261023/README.md) and [learned-experience study](benchmarks/action-20261023/experience/README.md) describe the new evidence. Earlier release assets remain unchanged.
