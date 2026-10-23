# Recalcul hors réseau / Offline reproduction

Depuis la racine du dépôt ou de l’archive source décompressée, installez les deux paquets comme indiqué dans PACKAGES.md, puis exécutez la commande ci-dessous sous Linux. Elle vérifie les octets des observations et reproduit exactement le calcul publié. Elle ne relance aucun appel modèle. Les épisodes restent synthétiques; les données Hermes privées ne sont pas distribuées.

From the repository root or extracted source archive, install both packages as described in PACKAGES.md, then run the command below on Linux. It checks the observation bytes and exactly reproduces the published calculation. It makes no model calls. The episodes are synthetic; private Hermes data is not distributed.

```sh
python3 - <<'PY'
import gzip, hashlib, json, runpy
from pathlib import Path
root = Path.cwd()
study = root / "benchmarks/action-20261023/experience"
raw = gzip.decompress((study / "OBSERVATIONS.json.gz").read_bytes())
assert hashlib.sha256(raw).hexdigest() == "7e97bbd4b9fb476bbb887ddb2502c1cbb2f74db0aca22dcf9ad9ad11c24a89e4"
module = runpy.run_path(str(root / "benchmarks/run_benchmark.py"), run_name="offline_experience_replay")
actual = module["calculate_experience"](json.loads(raw), (study / "PLAN.json").read_bytes())
assert actual == json.loads((study / "RESULT.json").read_bytes())
assert actual["planned_cells"] == 288 and actual["actual_model_episode_summaries"] == 48
print("PASS: published analysis of 288 calls reproduced without provider calls")
PY
```

Les [sources exactes du superviseur](execution_worker.py) et de l’[évaluation Registry](registry_assessment.py) permettent de lire le protocole réellement exécuté. Ce sont des témoins de ce parcours qualifié, avec paramètres, environnement et admission explicites, pas des programmes autonomes. Les marqueurs `_LAB_`, `_BASE_`, `_PIN_` et `_HOST_` sont des paramètres du superviseur. Les manifestes opérationnels, emplacements de credentials et clés restent privés. [RUN-PROVENANCE.json](RUN-PROVENANCE.json) conserve les empreintes publiques et [REGISTRY.json](REGISTRY.json) les étiquettes revérifiées.

The exact [execution supervisor](execution_worker.py) and [Registry assessment](registry_assessment.py) expose the protocol that was run. They are witnesses of the qualified execution path, requiring explicit parameters, environment and admission, rather than standalone programs. `_LAB_`, `_BASE_`, `_PIN_` and `_HOST_` are supervisor parameters. Operational manifests, credential locations and keys remain private. [RUN-PROVENANCE.json](RUN-PROVENANCE.json) retains the public hashes and [REGISTRY.json](REGISTRY.json) the reverified labels.
