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
