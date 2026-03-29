from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from memstate.api.deps import (
    get_executor,
    get_reasoner,
    get_settings,
    verify_api_key,
)
from memstate.api.ui_api import router as ui_router
from memstate.llm.chat_api import router as llm_router
from memstate.config import Settings
from memstate.core.executor import Executor
from memstate.core.models import IngestRequest, IngestResponse, QueryRequest, QueryResponse
from memstate.reasoner.engine import Reasoner


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="MemState API",
    description="Topic graph memory (Kuzu embedded + UEM) — ingest and query",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _ui_static_no_cache(request: Request, call_next):
    """Dev UI: avoid stale app.js / styles.css after updates (browser disk cache)."""
    response = await call_next(request)
    path = request.url.path
    if path == "/ui" or path.startswith("/ui/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


def _auth_dep(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    verify_api_key(settings, x_api_key=x_api_key, authorization=authorization)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


_DB_HINT = (
    "Check MEMSTATE_KUZU_PATH (default memstate.kuzu) is writable, "
    "or point it to a directory where the process can create the database file."
)

_DB_LOCK_HINT = (
    "Kuzu allows one open database handle per file. This app now shares a single connection; "
    "if this persists, stop duplicate API processes. Cloud-sync folders (e.g. OneDrive) can "
    "also lock files — set MEMSTATE_KUZU_PATH to a non-synced path such as "
    "%LOCALAPPDATA%\\MemState\\memstate.kuzu on Windows."
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/graph")
def health_graph():
    """Whether the embedded Kuzu store opens (no auth — for UI / ops checks)."""
    from memstate.store.graph_store import get_graph

    s = get_settings()
    try:
        g = get_graph(s)
        g.ro_query("RETURN 1 AS ok")
        return {"status": "ok", "backend": "kuzu", "path": g.db_path}
    except Exception as e:
        err = str(e)
        hint = _DB_HINT
        if "lock" in err.lower():
            hint = _DB_LOCK_HINT
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error": err,
                "path": s.kuzu_path,
                "hint": hint,
            },
        )


@app.get("/health/falkordb")
def health_falkordb():
    """Backward-compatible alias for `/health/graph`."""
    return health_graph()


@app.get("/")
def root():
    return RedirectResponse(url="/ui/")


_static_ui = Path(__file__).resolve().parent / "static" / "ui"
if _static_ui.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(_static_ui), html=True),
        name="ui",
    )

app.include_router(ui_router, dependencies=[Depends(_auth_dep)])
app.include_router(llm_router, dependencies=[Depends(_auth_dep)])


@app.post("/v1/ingest", response_model=IngestResponse, dependencies=[Depends(_auth_dep)])
def ingest(
    body: IngestRequest,
    background: BackgroundTasks,
    executor: Executor = Depends(get_executor),
    reasoner: Reasoner = Depends(get_reasoner),
):
    result = executor.ingest(body)

    def _after():
        reasoner.run("ingest_complete")

    background.add_task(_after)
    return result


@app.post("/v1/query", response_model=QueryResponse, dependencies=[Depends(_auth_dep)])
def query_op(
    body: QueryRequest,
    background: BackgroundTasks,
    executor: Executor = Depends(get_executor),
    reasoner: Reasoner = Depends(get_reasoner),
):
    result = executor.query(body)

    def _after():
        reasoner.run("query_complete")

    background.add_task(_after)
    return result
