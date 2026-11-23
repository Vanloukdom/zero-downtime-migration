"""API clients compatible avec toutes les phases d'une migration expand/contract.

SCHEMA_PHASE :
  v1       → lit/écrit full_name (ancienne version)
  expand   → écrit full_name ET first/last_name, lit full_name   (rollback vers v1 possible)
  migrate  → écrit les deux, lit first/last_name                  (rollback vers expand possible)
  contract → n'utilise plus que first/last_name (après DROP de full_name)
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.db import close_db, init_db, pool
from app.observability import setup_observability

PHASES = ("v1", "expand", "migrate", "contract")


def phase() -> str:
    p = os.getenv("SCHEMA_PHASE", "expand")
    if p not in PHASES:
        raise RuntimeError(f"SCHEMA_PHASE invalide : {p}")
    return p


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP") == "true":  # pratique en local uniquement
        from app.migrate import migrate
        migrate()
    yield
    close_db()


app = FastAPI(
    title="Zero-downtime migration",
    description="Renommer/découper une colonne critique sans interruption ni casse de l'ancienne version.",
    version=os.getenv("APP_VERSION", "2.0.0"),
    lifespan=lifespan,
)
setup_observability(app)


class CustomerIn(BaseModel):
    email: str
    first_name: str
    last_name: str | None = None


@app.get("/version")
def version():
    return {"version": app.version, "schema_phase": phase()}


@app.post("/customers", status_code=201)
def create_customer(body: CustomerIn):
    full = " ".join(x for x in (body.first_name, body.last_name) if x)
    p = phase()
    with pool.connection() as conn:
        if p == "v1":
            row = conn.execute(
                "INSERT INTO customers (email, full_name) VALUES (%s, %s) RETURNING id", (body.email, full)
            ).fetchone()
        elif p in ("expand", "migrate"):
            row = conn.execute(
                """INSERT INTO customers (email, full_name, first_name, last_name)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (body.email, full, body.first_name, body.last_name),
            ).fetchone()
        else:
            row = conn.execute(
                "INSERT INTO customers (email, first_name, last_name) VALUES (%s, %s, %s) RETURNING id",
                (body.email, body.first_name, body.last_name),
            ).fetchone()
    return get_customer(row["id"])


@app.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    p = phase()
    cols = "id, email, full_name" if p in ("v1", "expand") else "id, email, first_name, last_name"
    with pool.connection() as conn:
        row = conn.execute(f"SELECT {cols} FROM customers WHERE id = %s", (customer_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Client introuvable")
    if "full_name" in row:
        first, _, last = row.pop("full_name").partition(" ")
        row.update(first_name=first, last_name=last or None)
    return row
