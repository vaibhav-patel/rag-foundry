"""rag-foundry SDK for plugin development."""

from rag_foundry_sdk.client import ControlPlaneClient
from rag_foundry_sdk.types import (
    DenseSearchHit,
    DenseSearchResponse,
    RagCitation,
    RagQueryResponse,
    ResponseShapeError,
)

__all__ = [
    "ControlPlaneClient",
    "DenseSearchHit",
    "DenseSearchResponse",
    "RagCitation",
    "RagQueryResponse",
    "ResponseShapeError",
    "__version__",
]

__version__ = "0.2.0"
