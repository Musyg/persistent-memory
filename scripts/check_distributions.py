"""Build and check installed wheels and rebuilt sdists outside the checkout."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def run(argv, cwd, env):
    subprocess.run([str(x) for x in argv], cwd=cwd, env=env, check=True)


def check_install(wheel, source, module, destination, env):
    venv.EnvBuilder(with_pip=True).create(destination / 'venv')
    python = destination / 'venv/bin/python'
    run([python, '-m', 'pip', 'install', '--no-index', '--no-deps', wheel], destination, env)
    run([python, '-c',
         'import importlib,pathlib,sys; m=importlib.import_module(sys.argv[1]); '
         'p=pathlib.Path(m.__file__).resolve(); '
         'assert p.is_relative_to(pathlib.Path(sys.prefix).resolve()), p; print(p)', module], destination, env)
    inventory = subprocess.run([str(python), '-c',
        'import json,sys,unittest; '
        'flatten=lambda s: sum((flatten(x) if isinstance(x,unittest.TestSuite) else [x.id()] for x in s),[]); '
        'print(json.dumps(sorted(flatten(unittest.defaultTestLoader.discover(sys.argv[1])))))',
        str(source / 'tests')], cwd=destination, env=env, text=True, capture_output=True, check=True)
    test_ids = json.loads(inventory.stdout)
    if not test_ids or len(test_ids) != len(set(test_ids)):
        raise RuntimeError('Empty or duplicated discovered tests')
    run([python, '-m', 'unittest', 'discover', '-s', source / 'tests', '-v'], destination, env)
    if module == 'hermes_memory':
        run([destination / 'venv/bin/hermes-memory-demo', '--directory', destination / 'demo'], destination, env)
        run([python, source / 'benchmarks/run_benchmark.py'], destination, env)
    else:
        run([destination / 'venv/bin/hermes-policy', '--help'], destination, env)
        run([destination / 'venv/bin/hermes-policy-demo', '--directory', destination / 'demo'], destination, env)
    return test_ids


def extract_sources(archive, destination):
    destination.mkdir()
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 500 or sum(m.size for m in members) > 32 * 1024 * 1024:
            raise RuntimeError('Unexpected source archive size')
        for member in members:
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()) or not (member.isfile() or member.isdir()):
                raise RuntimeError('Unsafe archive member')
        tar.extractall(destination, members=members, filter='data')
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise RuntimeError('Expected one source root')
    return roots[0]


def main():
    if sys.platform != 'linux':
        raise SystemExit('This verification recipe requires Linux.')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    packages = [(ROOT, 'hermes_memory'), (ROOT / 'packages/policy-registry', 'hermes_policy_registry')]
    with tempfile.TemporaryDirectory(prefix='hermes-distribution-check-') as tmp:
        temporary = Path(tmp)
        for source, module in packages:
            output = DIST / module
            if output.exists():
                raise RuntimeError(f'Use a clean build output: {output}')
            run([sys.executable, '-m', 'build', '--outdir', output, source], temporary, env)
            wheels, sdists = list(output.glob('*.whl')), list(output.glob('*.tar.gz'))
            if len(wheels) != 1 or len(sdists) != 1:
                raise RuntimeError('Expected one wheel and one sdist per distribution')
            direct = temporary / (module + '-wheel')
            direct.mkdir()
            direct_ids = check_install(wheels[0], source, module, direct, env)
            rebuilt = temporary / (module + '-rebuilt')
            rebuilt.mkdir()
            run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                 '--wheel-dir', rebuilt, sdists[0]], temporary, env)
            rebuilt_wheels = list(rebuilt.glob('*.whl'))
            if len(rebuilt_wheels) != 1:
                raise RuntimeError('Expected one rebuilt wheel')
            rebuilt_source = extract_sources(sdists[0], temporary / (module + '-source'))
            rebuilt_ids = check_install(rebuilt_wheels[0], rebuilt_source, module, rebuilt, env)
            if rebuilt_ids != direct_ids:
                raise RuntimeError('Source distribution changed the test inventory')
        checksums = {p.relative_to(DIST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(DIST.rglob('*')) if p.is_file()}
        (DIST / 'SHA256.json').write_text(json.dumps(checksums, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
