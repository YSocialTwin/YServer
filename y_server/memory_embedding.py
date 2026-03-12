import math
import re
import threading


class MemoryEmbeddingService:
    """
    Ollama-backed embedding wrapper for memory embeddings.

    The service degrades gracefully: if the model cannot be loaded,
    callers receive None embeddings and can use lexical fallback retrieval.
    """

    def __init__(self, model_name: str = "embeddinggemma", ollama_host: str = "http://127.0.0.1:11434"):
        self.model_name = model_name
        self.ollama_host = ollama_host
        self._client = None
        self._available = None
        self._lock = threading.Lock()
        self._last_error = None

    def _ensure_client(self):
        if self._available is False:
            return None
        if self._client is not None:
            return self._client

        with self._lock:
            if self._client is not None:
                return self._client
            if self._available is False:
                return None
            try:
                from ollama import Client as OllamaClient
            except Exception as exc:
                self._available = False
                self._last_error = f"ollama import failed: {exc}"
                return None

            try:
                client = OllamaClient(host=self.ollama_host)
                client.embed(model=self.model_name, input="test")
                self._client = client
                self._available = True
            except Exception as exc:
                self._available = False
                self._last_error = f"ollama connect/embed failed ({self.model_name}): {exc}"
                self._client = None
            return self._client

    def embed_text(self, text: str):
        if not isinstance(text, str) or not text.strip():
            return None
        client = self._ensure_client()
        if client is None:
            return None
        try:
            response = client.embed(model=self.model_name, input=text.strip())
            return [float(x) for x in response.embeddings[0]]
        except Exception:
            return None

    @property
    def available(self):
        if self._available is None:
            self._ensure_client()
        return bool(self._available)

    @property
    def last_error(self):
        return self._last_error


def cosine_similarity(vec_a, vec_b) -> float:
    if not isinstance(vec_a, list) or not isinstance(vec_b, list):
        return 0.0
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for a, b in zip(vec_a, vec_b):
        try:
            fa = float(a)
            fb = float(b)
        except Exception:
            continue
        dot += fa * fb
        na += fa * fa
        nb += fb * fb
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(dot / (math.sqrt(na) * math.sqrt(nb)))


def lexical_relevance(query_text: str, memory_text: str) -> float:
    if not isinstance(query_text, str) or not isinstance(memory_text, str):
        return 0.0
    q_tokens = set(re.findall(r"[a-z0-9]+", query_text.lower()))
    m_tokens = set(re.findall(r"[a-z0-9]+", memory_text.lower()))
    if not q_tokens or not m_tokens:
        return 0.0
    inter = len(q_tokens & m_tokens)
    if inter <= 0:
        return 0.0
    return float(inter / math.sqrt(len(q_tokens) * len(m_tokens)))
