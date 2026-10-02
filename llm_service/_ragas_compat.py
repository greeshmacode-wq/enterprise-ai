"""
Purpose: it's a workaround for a bug in the `ragas` library so `import ragas` doesn't crash.

Simple explanation:
- `ragas` tries to import `ChatVertexAI` from `langchain_community`, but that piece was removed from the library — so the import fails with an error, even though this project never uses VertexAI at all.
- Instead of installing a whole extra Google Cloud package just to fix one dead import, this file **fakes** that missing piece:
  - It creates a fake empty module and registers it in Python's module cache (`sys.modules`), pretending `langchain_community.chat_models.vertexai` exists.
  - Inside it, `ChatVertexAI` is a dummy class that immediately raises an error if anyone ever tries to actually use it (which never happens — it's only there to satisfy the import).
- The `if ... not in sys.modules` check just avoids doing this twice.

So it tricks Python into thinking the missing module is there, letting `import ragas` succeed — that's why line 26 in evaluation.py says this must run **before** `import ragas`.
"""

import sys
import types

if "langchain_community.chat_models.vertexai" not in sys.modules:
    _stub = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # pragma: no cover - import-only stub, never instantiated
        def __init__(self, *args, **kwargs):
            raise NotImplementedError(
                "ChatVertexAI is a ragas-import compat stub, not a real "
                "implementation - this project uses Ollama, not VertexAI."
            )

    _stub.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _stub
