"""Opt-in finite French rendering of supplied structured facts."""
from ._admission_loader import load_graph as _load_graph

_graph = _load_graph()
render = _graph._c1.render
canonical = _graph._c1.canonical
__all__ = ['render', 'canonical']
del _graph, _load_graph
