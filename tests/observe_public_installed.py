"""No-argument JSON observer; execute with the freshly installed Linux interpreter."""
import importlib.util
import json
from pathlib import Path
import sys

spec=importlib.util.spec_from_file_location('independent_package_probe',Path(__file__).with_name('public_admission_probe.py'))
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('linux_required')
    rows=[]
    for group in probe.GROUPS:rows.extend(probe.run_group(group))
    counts={}
    for row in rows:
        category=row.get('observation',{}).get('category','failed_probe')
        counts[category]=counts.get(category,0)+1
    passed=all(row['passed'] for row in rows)
    print(json.dumps(dict(schema='hermes.public_admission.independent_observations.v1',passed=passed,families=12,variants=len(rows),categories=counts,results=rows,statistical_tasks=False,extraction_measured=False,production_qualified=False),ensure_ascii=True))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
