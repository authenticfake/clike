# DeepSeek cloud exposes an OpenAI-compatible API surface.
# We reuse the OpenAI-compatible adapter.
# app/providers/deepseek.py
# DeepSeek cloud exposes an OpenAI-compatible API surface.
# We reuse the OpenAI-compatible adapter with unified envelope.
from .openai_compat import openai_complete_unified as deepseek_complete_unified  # re-export
from .openai_compat import embeddings as deepseek_embeddings  # re-export
from .openai_compat import chat as chat  # re-export
