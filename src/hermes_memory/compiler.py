"""Provider interface; configuration is persisted, so do not put credentials in it."""
from typing import Mapping, Protocol, Sequence

class Compiler(Protocol):
    compiler_id: str
    compiler_version: str
    def compile(self, texts: Sequence[str], config: Mapping) -> str: ...

class DeterministicCompiler:
    compiler_id = 'hermes.deterministic.join'
    compiler_version = '1'
    def compile(self, texts, config):
        return '\n'.join(texts)
