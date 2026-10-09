"""Opt-in mechanical output counter shared with structured rendering/admission."""
from ._admission_loader import load_graph as _load_graph

_graph = _load_graph()
_counter = _graph._c1._counter
OutputContract = _counter.OutputContract
ContractError = _counter.ContractError
validate_output = _counter.validate_output
make_initial_prompt = _counter.make_initial_prompt
make_repair_prompt = _counter.make_repair_prompt
VERSION = _counter.VERSION
WORD_COUNT_RULE = _counter.WORD_COUNT_RULE
MAX_TEXT_BYTES = _counter.MAX_TEXT_BYTES
MAX_PROMPT_BYTES = _counter.MAX_PROMPT_BYTES
__all__ = ['OutputContract', 'ContractError', 'validate_output',
           'make_initial_prompt', 'make_repair_prompt', 'VERSION', 'WORD_COUNT_RULE',
           'MAX_TEXT_BYTES', 'MAX_PROMPT_BYTES']
del _graph, _counter, _load_graph
