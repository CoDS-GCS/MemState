from functools import lru_cache

from memstate.config import Settings, get_settings as _get_settings
from memstate.core.executor import Executor
from memstate.reasoner.engine import Reasoner
from memstate.store.kuzu_adapter import clear_kuzu_graph_cache
from memstate.store.graph_store import GraphStore, get_store


def get_settings() -> Settings:
    return _get_settings()


@lru_cache
def _executor_singleton() -> Executor:
    store = get_store()
    return Executor(store)


@lru_cache
def _reasoner_singleton() -> Reasoner:
    return Reasoner(_executor_singleton())


def get_executor() -> Executor:
    return _executor_singleton()


def get_graph_store() -> GraphStore:
    """Same `GraphStore` instance as the executor (single graph connection)."""
    return _executor_singleton().store


def get_reasoner() -> Reasoner:
    return _reasoner_singleton()


def reset_singletons() -> None:
    _executor_singleton.cache_clear()
    _reasoner_singleton.cache_clear()
    clear_kuzu_graph_cache()


def verify_api_key(
    settings: Settings,
    x_api_key: str | None = None,
    authorization: str | None = None,
) -> None:
    expected = settings.api_key
    if not expected:
        return
    if x_api_key and x_api_key == expected:
        return
    if authorization and authorization.startswith("Bearer "):
        if authorization.removeprefix("Bearer ").strip() == expected:
            return
    from fastapi import HTTPException

    raise HTTPException(status_code=401, detail="Unauthorized")
