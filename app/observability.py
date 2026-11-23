from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.db import pool


def setup_observability(app: FastAPI) -> None:
    @app.get("/healthz", tags=["ops"])
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz():
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
