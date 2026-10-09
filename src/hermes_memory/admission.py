"""Opt-in admission boundary for explicitly reviewed structured evidence."""
from ._admission_loader import load_graph as _load_graph

_graph = _load_graph()
admit = _graph.admit
LabOrchestratorSink = _graph.LabOrchestratorSink
__all__ = ['admit', 'LabOrchestratorSink']
del _graph, _load_graph
