"""Author tests for the public package boundary; all examples are newly synthetic."""
import importlib
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

import hermes_memory


class AdmissionPackageAuthor(unittest.TestCase):
    def child(self, source, package_copy=False):
        with tempfile.TemporaryDirectory(prefix='admission-package-') as directory:
            root = Path(directory)
            preamble = ''
            if package_copy:
                shutil.copytree(Path(hermes_memory.__file__).parent, root/'hermes_memory',
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                preamble = 'import sys; sys.path.insert(0, '+repr(str(root))+')\n'
            result = subprocess.run([sys.executable, '-I', '-B', '-c', preamble+textwrap.dedent(source)],
                                    cwd=root, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_default_package_remains_opt_in(self):
        self.child('''
            import sys, hermes_memory
            assert 'hermes_memory.admission' not in sys.modules
            assert 'hermes_memory._admission_loader' not in sys.modules
            assert '_hermes_a1_pinned_c1' not in sys.modules
        ''')

    def test_all_import_orders_share_counter_and_functions(self):
        for order in itertools.permutations(('admission', 'structured_memory', 'quality_contract')):
            with self.subTest(order=order):
                self.child('''
import importlib
for name in %r:
    importlib.import_module('hermes_memory.'+name)
from hermes_memory import admission as a, structured_memory as s, quality_contract as q
from hermes_memory._admission_loader import load_graph
assert a.admit is load_graph().admit
assert a.admit.__globals__['_c1'].render is s.render
assert s.render.__globals__['_counter'].OutputContract is q.OutputContract
assert s.render.__globals__['_counter'].validate_output is q.validate_output
assert q.validate_output('Texte synthétique.', q.OutputContract(1, 10))['mechanical_pass']
''' % (order,))

    def test_ambient_homonyms_are_not_executed(self):
        self.child('''
            from pathlib import Path
            import sys
            for name in ('admission', 'structured_memory', 'quality_contract'):
                Path(name+'.py').write_text("raise RuntimeError('foreign module executed')")
            sys.path.insert(0, str(Path.cwd()))
            from hermes_memory.admission import admit
            assert callable(admit)
            assert all(name not in sys.modules for name in ('admission', 'structured_memory', 'quality_contract'))
        ''')

    def test_reserved_names_are_refused_without_replacement(self):
        for name in ('hermes_memory._verified_admission_graph', '_hermes_a1_pinned_c1',
                     '_hermes_c1_pinned_mechanical'):
            with self.subTest(name=name):
                self.child('''
import sys, types
name = %r
foreign = types.ModuleType(name)
sys.modules[name] = foreign
try:
    from hermes_memory.admission import admit
except ImportError as error:
    assert str(error) == 'verified_admission_graph_unavailable'
else:
    raise AssertionError('reserved collision admitted')
assert sys.modules[name] is foreign
''' % name)

    def test_missing_changed_and_oversized_resources_are_refused(self):
        for name in ('admission.py', 'structured_memory.py', 'quality_contract.py'):
            for action in ('missing', 'changed', 'oversized'):
                with self.subTest(name=name, action=action):
                    self.child('''
from pathlib import Path
import sys
root = Path.cwd()/'hermes_memory'/'_admission_sources'
path = root/%r
original = path.read_bytes()
action = %r
if action == 'missing':
    path.unlink()
elif action == 'changed':
    path.write_bytes(bytes([original[0] ^ 1])+original[1:])
else:
    path.write_bytes(original+b'!')
try:
    from hermes_memory.admission import admit
except ImportError as error:
    assert str(error) == 'verified_admission_graph_unavailable'
else:
    raise AssertionError('bad resource admitted')
assert all(name not in sys.modules for name in ('hermes_memory._verified_admission_graph',
    '_hermes_a1_pinned_c1', '_hermes_c1_pinned_mechanical'))
path.write_bytes(original)
from hermes_memory.admission import admit
assert callable(admit)
''' % (name, action), package_copy=True)

    def test_partial_construction_rolls_back_and_can_retry(self):
        self.child('''
            import builtins, sys
            from hermes_memory._admission_loader import load_graph
            original = builtins.compile
            def fail_counter(source, filename, *args, **kwargs):
                if str(filename).endswith('quality_contract.py'):
                    raise RuntimeError('private failure details')
                return original(source, filename, *args, **kwargs)
            builtins.compile = fail_counter
            try:
                try:
                    load_graph()
                except ImportError as error:
                    assert str(error) == 'verified_admission_graph_unavailable'
                else:
                    raise AssertionError('construction failure ignored')
            finally:
                builtins.compile = original
            assert all(name not in sys.modules for name in ('hermes_memory._verified_admission_graph',
                '_hermes_a1_pinned_c1', '_hermes_c1_pinned_mechanical'))
            assert callable(load_graph().admit)
        ''')

    def test_cached_loading_rechecks_resources_and_module_identity(self):
        self.child('''
            import sys, types
            from pathlib import Path
            from hermes_memory._admission_loader import load_graph
            graph = load_graph()
            path = Path.cwd()/'hermes_memory'/'_admission_sources'/'quality_contract.py'
            original = path.read_bytes()
            path.write_bytes(original+b'!')
            try:
                load_graph()
            except ImportError:
                pass
            else:
                raise AssertionError('cached load skipped source check')
            path.write_bytes(original)
            assert load_graph() is graph
            foreign = types.ModuleType('_hermes_c1_pinned_mechanical')
            sys.modules[foreign.__name__] = foreign
            try:
                load_graph()
            except ImportError:
                pass
            else:
                raise AssertionError('cached ownership mismatch ignored')
            assert sys.modules[foreign.__name__] is foreign
        ''', package_copy=True)

    def test_concurrent_loads_return_one_graph(self):
        self.child('''
            from concurrent.futures import ThreadPoolExecutor
            from hermes_memory._admission_loader import load_graph
            with ThreadPoolExecutor(max_workers=6) as pool:
                graphs = list(pool.map(lambda _: load_graph(), range(24)))
            assert all(graph is graphs[0] for graph in graphs)
        ''')

    def test_synthetic_demo_has_distinct_useful_outcomes(self):
        from hermes_memory.admission_demo import run_demo
        result = run_demo()
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['examples']), 8)
        self.assertFalse(result['publication_atomic'])
        self.assertFalse(result['acknowledgment_proves_consumption'])

    def test_source_loss_overrides_transform_failure_and_scrubs_receipt(self):
        from hermes_memory.admission import admit, LabOrchestratorSink
        from hermes_memory.admission_demo import example_request, demo_authority
        stages = []
        def authority(snapshot, stage):
            stages.append(stage)
            if stage == 'before_handoff':
                return dict(status='denied', revision='v2', disclose_withdrawal=False)
            return demo_authority(snapshot, stage)
        def transform(body):
            raise RuntimeError('do not export this synthetic error')
        result = admit(example_request(), authority, LabOrchestratorSink(), transform)
        self.assertEqual(stages, ['before', 'before_handoff'])
        self.assertEqual(result['envelope']['decision'], 'access_unavailable')
        self.assertEqual(result['receipt']['provenance'], [])
        self.assertEqual(result['receipt']['evidence_review'], 'not_disclosed')
        self.assertNotIn('demo-note', json.dumps(result))
        self.assertNotIn('synthetic error', json.dumps(result))

    def test_request_bound_rejects_before_callbacks(self):
        from hermes_memory.admission import admit
        from hermes_memory.admission_demo import example_request
        calls = []
        request = example_request()
        request['brief'] = 'x'*8193
        result = admit(request, lambda *args: calls.append('authority'),
                       lambda *args: calls.append('sink'))
        self.assertEqual(result['envelope']['decision'], 'invalid_request')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
