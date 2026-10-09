"""Load one verified, opt-in graph from fixed installed source resources."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType

_PINS = (
    ('admission.py', 15828, '6fb7fd9a6eaecd0da2a50acd05ba253841da3ec41d904b324c8184720db43600'),
    ('structured_memory.py', 16801, '4febba12532671486bdb82e1eb39009cd7bb10206e33c10d46807e718da99697'),
    ('quality_contract.py', 8795, '0d16ebbf0042f03a5d6b36b1ed3b32b58e00945b73af1582f4bf2760492123b4'),
)
_NAMES = ('hermes_memory._verified_admission_graph',
          '_hermes_a1_pinned_c1', '_hermes_c1_pinned_mechanical')
_LOCK = threading.RLock()
_CACHE = None
_OWNED = ()
_ERROR = 'verified_admission_graph_unavailable'


def _sources():
    root = Path(__file__).resolve().with_name('_admission_sources')
    captured = []
    for name, length, digest in _PINS:
        path = root / name
        with path.open('rb') as handle:
            raw = handle.read(length + 1)
        if len(raw) != length or hashlib.sha256(raw).hexdigest() != digest:
            raise ImportError(_ERROR)
        captured.append((path, raw))
    return captured


def _objects(admission):
    """Known module dictionaries only; partial construction is valid for cleanup."""
    c1 = admission.__dict__.get('_c1') if type(admission) is ModuleType else None
    counter = c1.__dict__.get('_counter') if type(c1) is ModuleType else None
    return admission, c1, counter


def load_graph():
    """Verify at each loading boundary; return the canonical admission module.

    Normal Python import caching does not revalidate each later function call.
    This is not a sandbox against Python introspection or concurrent external
    mutation of the installed files or sys.modules.
    """
    global _CACHE, _OWNED
    with _LOCK:
        created = None
        try:
            captured = _sources()
            if _CACHE is not None:
                objects = _objects(_CACHE)
                if len(_OWNED) != 3 or any(a is not b for a, b in zip(objects, _OWNED)):
                    raise ImportError(_ERROR)
                if any(sys.modules.get(name) is not obj for name, obj in zip(_NAMES, _OWNED)):
                    raise ImportError(_ERROR)
                return _CACHE
            if _OWNED or any(name in sys.modules for name in _NAMES):
                raise ImportError(_ERROR)
            path, raw = captured[0]
            spec = importlib.util.spec_from_file_location(_NAMES[0], path)
            created = importlib.util.module_from_spec(spec)
            sys.modules[_NAMES[0]] = created
            # Execute captured bytes, never loader bytecode or an ambient homonym.
            # The unchanged bootstrap verifies and executes its fixed siblings.
            exec(compile(raw, str(path), 'exec'), created.__dict__)
            objects = _objects(created)
            if any(type(obj) is not ModuleType for obj in objects):
                raise ImportError(_ERROR)
            if any(sys.modules.get(name) is not obj for name, obj in zip(_NAMES, objects)):
                raise ImportError(_ERROR)
            if created.__dict__.get('_counter') is not objects[2]:
                raise ImportError(_ERROR)
            _OWNED, _CACHE = objects, created
            return created
        except BaseException:
            if created is not None:
                for name, obj in zip(_NAMES, _objects(created)):
                    if obj is not None and sys.modules.get(name) is obj:
                        del sys.modules[name]
            raise ImportError(_ERROR) from None
