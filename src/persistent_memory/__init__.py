"""persistent-memory, under its public import name.

The implementation lives in the `hermes_memory` package, the project's historical name.
Both names give the same objects: `persistent_memory.PersistentMemory is
hermes_memory.persistent.PersistentMemory`.
"""
from hermes_memory import __version__
from hermes_memory.core import MemoryError, Ref
from hermes_memory.persistent import OPERATIONS, PersistentMemory
from hermes_memory.qdrant_projection import OpenAIEmbeddings, QdrantProjection

__all__ = [
    "MemoryError",
    "OPERATIONS",
    "OpenAIEmbeddings",
    "PersistentMemory",
    "QdrantProjection",
    "Ref",
    "__version__",
]
