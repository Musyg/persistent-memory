# Persistent Memory packages

The memory core is `hermes-memory-core==0.2.0a1`. The optional policy registry is `hermes-policy-registry==0.1.0`. They install independently and have no runtime dependency on each other.

The [registry guide](https://github.com/Musyg/persistent-memory/tree/main/packages/policy-registry) and its French counterpart describe the contract and synthetic example. Registry wheels and source archives are separate release assets; a standalone core source archive does not contain the registry package.

From a checkout of the complete repository:

```sh
python3 -m pip install ./packages/policy-registry
hermes-policy-demo --directory ./new-policy-demo
```

The registry records proposals, evidence, admissions and rollbacks. It does not execute policies, select an active policy, change runtime permissions or authenticate a judge. Demo labels and durations are invented synthetic values, not measured retrieval performance. The memory core's frozen runtime is unchanged. Experimental retrieval R4 is not included.
