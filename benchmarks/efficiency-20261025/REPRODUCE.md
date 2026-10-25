# Reproduce the incremental workload on Linux

[Français](REPRODUCE.fr.md) · [Study](README.md) · [Protocol](PROTOCOL.json) · [Source pins](SOURCE-PINS.json)

Use a complete checkout of the **publication commit containing this page**, with Python and SQLite FTS5. The benchmark source must hash to `a2cfda65d6df85f76670af5efb413fc3f0d3d776cd8324e5251cf3b05bfa1b02`. The a4 tag and source archive contain the earlier CLI, so they cannot supply `--volume-incremental-batch`. Copy the full publication commit identifier from its GitHub permalink and verify your checkout against it before running.

The archived laboratory workload used common 0.3.0a2 support wheels with three explicit module overlays per arm. For a new comparison, the public a4 core wheel and policy-registry 0.2.0a2 wheel can provide a fresh common support environment. That is a new environment, not a reconstruction of the archived wheel bytes or a measurement of installed a4 distributions. Obtain the wheels before entering the network-isolated measurement envelope. Their release checksums must match the selected assets.

Create one fresh virtual environment for the six-cell sequence. Set `CHECKOUT`, `ENV`, `CORE_WHEEL` and `REGISTRY_WHEEL` to your own absolute paths. Within the measurement unit described below, install dependencies once without generating bytecode. Before each cell, set `ARM` to `A` or `B`, select the three corresponding modules and check their imports in a fresh process using the setup below.

```sh
python3 -m venv "$ENV"
"$ENV/bin/python" -I -B -m pip install --no-compile --no-index --no-deps \
  "$CORE_WHEEL" "$REGISTRY_WHEEL"
```

The following setup operates only inside that new environment. It selects the three already-public modules, verifies their bytes, imports them, checks the loaded bindings and rejects existing bytecode. It does not initialize a memory store. Save its JSON output with the cell's evidence.

```sh
"$ENV/bin/python" -I -B - "$CHECKOUT" "$ARM" <<'PY'
import hashlib, importlib, json, pathlib, subprocess, sys, sysconfig
checkout, arm = pathlib.Path(sys.argv[1]).resolve(), sys.argv[2]
versions = {
 'A': ('1554beda0ef3e57621eca8974c197514302f369e', [
  '35dd711acb3dd16e97237721b7332a73b4d4822a88c227fc445722256cd5cecb',
  'f6f5284dcdcd9f6530ff34973c2b453f7dc5f0d5b877a134f709ad3e03454729',
  '201795feebd7a508cbea7dcc7638341f0da946c0288017c80d55f50a34826dee']),
 'B': ('14ec99ca3eb12f801b352101d2e67508cb187de9', [
  '76dba2b15a4d33005d07abcd08306199fffa2bc2ff7b3cbe268590c7776878ce',
  '4a5d16812a68d89e47b0274d432da9816876ae2ed73409131a09495b006c103d',
  '2af69d57e66184388e0736702ead3d55575ce69c4924ea7548eeb957f4388801'])}
commit, pins = versions[arm]
names = ['core.py', 'typed_memory.py', 'typed_protocol.py']
package = pathlib.Path(sysconfig.get_paths()['purelib']).resolve() / 'hermes_memory'
assert sys.prefix != sys.base_prefix and package.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert not any((package / '__pycache__').glob('*.pyc'))
for name, pin in zip(names, pins):
    raw = subprocess.check_output(['git', '-C', str(checkout), 'show',
                                   commit + ':src/hermes_memory/' + name])
    assert hashlib.sha256(raw).hexdigest() == pin
    (package / name).write_bytes(raw)
loaded = {}
for name, pin in zip(names, pins):
    module = importlib.import_module('hermes_memory.' + name[:-3])
    path = pathlib.Path(module.__file__).resolve()
    assert path == package / name and hashlib.sha256(path.read_bytes()).hexdigest() == pin
    assert not pathlib.Path(module.__cached__).exists()
    loaded[name] = pin
from hermes_memory import typed_memory, typed_protocol
assert typed_memory.CORE_SHA == pins[0] and typed_protocol.R3_SHA == pins[1]
assert not any((package / '__pycache__').glob('*.pyc'))
runner = checkout / 'benchmarks/run_benchmark.py'
assert hashlib.sha256(runner.read_bytes()).hexdigest() == 'a2cfda65d6df85f76670af5efb413fc3f0d3d776cd8324e5251cf3b05bfa1b02'
print(json.dumps({'arm': arm, 'module_commit': commit, 'loaded_sha256': loaded,
                  'CORE_SHA': typed_memory.CORE_SHA, 'R3_SHA': typed_protocol.R3_SHA,
                  'bytecode_absent': True, 'checkout_commit': subprocess.check_output(
                  ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()}))
PY
```

Run the six cells sequentially in order **A, B, B, A, A, B**, each with a fresh process, database and RAM directory. Enclose the complete six-cell sequence in one 1,200-second transient unit: CPU quota 50%, memory 1 GiB, swap disabled, 64 tasks maximum, private network and no new privileges. Record effective unit/cgroup limits while it is active. A per-child timeout is 180 seconds. Virtual-environment creation and offline installation are included in the overall 1,200-second limit. Obtain the wheels before entering the network-isolated unit. These are the registered limits, not optional tuning suggestions.

Within that envelope, create a new private `CELL_RAM` directory under `/dev/shm` and an ordinary output directory `CELL_OUTPUT`. Run the selected environment's Python once:

```sh
TMPDIR="$CELL_RAM" timeout --signal=KILL 180s \
  "$ENV/bin/python" -I -B "$CHECKOUT/benchmarks/run_benchmark.py" \
  --documents 1000 --repetitions 50 --seed 20261021 \
  --volume-progress "$CELL_OUTPUT/progress.json" --volume-incremental-batch 10 \
  > "$CELL_OUTPUT/result.json" 2> "$CELL_OUTPUT/stderr.log"
```

Preserve the exit status, output, timeout and unstarted-cell records. Wait for every launched child before removing only its owned RAM directory. Do not replace failed cells, retry automatically or raise limits. The new sources are queried once each in admission order; the remaining 40 queries are seeded draws from the initial 1,000. The query schedule hash is `43246effb8574adaeb53eb0dff4984a1b2845f7bd2acbe8b1c204bb678c57bfe`.

Compare setup and marginal phases separately only after inspecting every oracle. Fifty searches within a cell are not fifty independent replications. The cycle includes explicit validation, withdrawal, synchronization, a valid control and telemetry. Cache state is not controlled, telemetry overhead is not isolated, and infrastructure cost and energy remain unknown. New timings will depend on the host and load. No production service, private memory, provider request or deployment step is involved.
