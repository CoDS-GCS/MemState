from memstate.embeddings.base import EmbeddingProvider, HashEmbeddingProvider
from memstate.embeddings.fastembed_provider import try_fastembed

__all__ = ["EmbeddingProvider", "FastEmbedProvider", "HashEmbeddingProvider", "default_text_embedder", "try_fastembed"]


def default_text_embedder(policies_dimension: int = 384) -> EmbeddingProvider:
    fe = try_fastembed()
    if fe is not None:
        return fe
    return HashEmbeddingProvider(dimension=policies_dimension)


def __getattr__(name: str):
    if name == "FastEmbedProvider":
        from memstate.embeddings.fastembed_provider import FastEmbedProvider

        return FastEmbedProvider
    raise AttributeError(name)
