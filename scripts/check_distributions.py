"""Build and check installed wheels and rebuilt sdists outside the checkout."""
from pathlib import Path
import argparse
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


def save_report(report, path):
    if path is not None:
        temporary = path.with_name(path.name + '.partial')
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
        os.replace(temporary, path)


def fresh_absolute(value):
    """Require a new absolute target and existing, non-symlink parent chain."""
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected a fresh absolute path')
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError('Target exists or parent is unavailable')
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Symlink parent is not accepted')
    return path


def check_install(wheel, source, module, variant, destination, env, report, report_path):
    record = dict(module=module, variant=variant, status='preparing', test_ids=[],
                  tests_run=0, failures=0, errors=0, skipped=0, returncode=None,
                  stdout_log=str(destination / 'tests.stdout.log'),
                  stderr_log=str(destination / 'tests.stderr.log'), installed_origin=None)
    report['suites'].append(record)
    save_report(report, report_path)
    venv.EnvBuilder(with_pip=True).create(destination / 'venv')
    python = destination / 'venv/bin/python'
    run([python, '-m', 'pip', 'install', '--no-index', '--no-deps', wheel], destination, env)
    origin = subprocess.run([str(python), '-c',
        'import importlib,pathlib,sys; m=importlib.import_module(sys.argv[1]); '
        'p=pathlib.Path(m.__file__).resolve(); '
        'assert p.is_relative_to(pathlib.Path(sys.prefix).resolve()), p; print(p)', module],
        cwd=destination, env=env, text=True, capture_output=True, check=True)
    record['installed_origin'] = origin.stdout.strip()
    inventory = subprocess.run([str(python), '-c',
        'import json,sys,unittest; '
        'flatten=lambda s: sum((flatten(x) if isinstance(x,unittest.TestSuite) else [x.id()] for x in s),[]); '
        'print(json.dumps(sorted(flatten(unittest.defaultTestLoader.discover(sys.argv[1])))))',
        str(source / 'tests')], cwd=destination, env=env, text=True, capture_output=True, check=True)
    test_ids = json.loads(inventory.stdout)
    record['test_ids'] = test_ids
    if not test_ids or len(test_ids) != len(set(test_ids)):
        raise RuntimeError('Empty or duplicated discovered tests')
    record['status'] = 'running'
    save_report(report, report_path)
    result_path = destination / 'tests.result.json'
    runner = (
        'import json,pathlib,sys,unittest; '
        'suite=unittest.defaultTestLoader.discover(sys.argv[1]); '
        'result=unittest.TextTestRunner(verbosity=2).run(suite); '
        'value=dict(tests_run=result.testsRun,failures=len(result.failures),'
        'errors=len(result.errors),skipped=len(result.skipped)); '
        'pathlib.Path(sys.argv[2]).write_text(json.dumps(value)+"\\n",encoding="utf-8"); '
        'sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)'
    )
    with Path(record['stdout_log']).open('x', encoding='utf-8') as stdout, \
            Path(record['stderr_log']).open('x', encoding='utf-8') as stderr:
        completed = subprocess.run([str(python), '-c', runner, str(source / 'tests'), str(result_path)],
                                   cwd=destination, env=env, stdout=stdout, stderr=stderr)
    record['returncode'] = completed.returncode
    if result_path.is_file():
        record.update(json.loads(result_path.read_text(encoding='utf-8')))
    passed = (completed.returncode == 0 and record['tests_run'] == len(test_ids)
              and record['tests_run'] > 0 and not any(record[key] for key in ('failures', 'errors', 'skipped')))
    record['status'] = 'tests_passed' if passed else 'failed'
    save_report(report, report_path)
    if not passed:
        raise RuntimeError('Installed test suite failed or inventory changed')
    if module == 'hermes_memory':
        run([destination / 'venv/bin/hermes-memory-demo', '--directory', destination / 'demo'], destination, env)
        run([python, '-m', 'hermes_memory.admission_demo'], destination, env)
        run([python, source / 'benchmarks/run_benchmark.py'], destination, env)
    else:
        run([destination / 'venv/bin/hermes-policy', '--help'], destination, env)
        run([destination / 'venv/bin/hermes-policy-demo', '--directory', destination / 'demo'], destination, env)
    record['status'] = 'passed'
    save_report(report, report_path)
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


def check_all(temporary, options, report, report_path):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    packages = [(ROOT, 'hermes_memory'), (ROOT / 'packages/policy-registry', 'hermes_policy_registry')]
    for source, module in packages:
        output = DIST / module
        if output.exists():
            raise RuntimeError('Use a clean build output')
        build_flags = ['--no-isolation'] if options.no_build_isolation else []
        run([sys.executable, '-m', 'build', *build_flags, '--outdir', output, source], temporary, env)
        wheels, sdists = list(output.glob('*.whl')), list(output.glob('*.tar.gz'))
        if len(wheels) != 1 or len(sdists) != 1:
            raise RuntimeError('Expected one wheel and one sdist per distribution')
        rebuilt_source = extract_sources(sdists[0], temporary / (module + '-source'))
        def test_files(root):
            return {p.relative_to(root / 'tests').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((root / 'tests').rglob('*'))
                    if p.is_file() and p.suffix in ('.py', '.json')}
        original_tests, extracted_tests = test_files(source), test_files(rebuilt_source)
        report['test_source_parity'].append(dict(module=module, source=original_tests,
                                                extracted=extracted_tests,
                                                passed=bool(original_tests) and original_tests == extracted_tests))
        save_report(report, report_path)
        if not original_tests or original_tests != extracted_tests:
            raise RuntimeError('Source distribution changed test files or bytes')
        direct = temporary / (module + '-wheel')
        direct.mkdir()
        direct_ids = check_install(wheels[0], rebuilt_source, module, 'wheel', direct, env, report, report_path)
        rebuilt = temporary / (module + '-rebuilt')
        rebuilt.mkdir()
        run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
             '--wheel-dir', rebuilt, sdists[0]], temporary, env)
        rebuilt_wheels = list(rebuilt.glob('*.whl'))
        if len(rebuilt_wheels) != 1:
            raise RuntimeError('Expected one rebuilt wheel')
        rebuilt_ids = check_install(rebuilt_wheels[0], rebuilt_source, module, 'sdist', rebuilt, env, report, report_path)
        if rebuilt_ids != direct_ids:
            raise RuntimeError('Source distribution changed the test inventory')
    checksums = {p.relative_to(DIST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(DIST.rglob('*')) if p.is_file()}
    (DIST / 'SHA256.json').write_text(json.dumps(checksums, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-build-isolation', action='store_true',
                        help='Use an explicitly prepared build environment; default remains isolated.')
    parser.add_argument('--work-dir', help='Fresh absolute work directory to retain installations and logs.')
    parser.add_argument('--report-json', help='Fresh absolute JSON report path; failed partial runs are retained.')
    options = parser.parse_args()
    if sys.platform != 'linux':
        raise SystemExit('This verification recipe requires Linux.')
    report_path = fresh_absolute(options.report_json) if options.report_json else None
    report = dict(schema='persistent-memory.distribution-check.v1', overall_status='running', exit_code=None,
                  work_dir=None, work_dir_retained=bool(options.work_dir), suites=[], test_source_parity=[], error=None)
    temporary_context = None
    try:
        if options.work_dir:
            temporary = fresh_absolute(options.work_dir)
            if temporary.is_relative_to(ROOT):
                raise ValueError('Work directory must be outside the source checkout')
            temporary.mkdir()
        else:
            temporary_context = tempfile.TemporaryDirectory(prefix='hermes-distribution-check-')
            temporary = Path(temporary_context.name)
        report['work_dir'] = str(temporary)
        save_report(report, report_path)
        check_all(temporary, options, report, report_path)
        if len(report['suites']) != 4 or any(item['status'] != 'passed' for item in report['suites']):
            raise RuntimeError('Incomplete installed qualification')
        report['overall_status'] = 'passed'
        report['exit_code'] = 0
    except BaseException as error:
        report['overall_status'] = 'failed'
        report['exit_code'] = 1
        report['error'] = type(error).__name__
        raise
    finally:
        save_report(report, report_path)
        if temporary_context is not None:
            temporary_context.cleanup()


if __name__ == '__main__':
    main()
