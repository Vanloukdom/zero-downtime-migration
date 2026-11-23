import os
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/app")

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=int(os.getenv("DB_POOL_MAX", "10")),
    kwargs={"row_factory": dict_row, "autocommit": False},
    open=False,
)


def init_db() -> None:
    """Ouvre le pool et applique le schéma (idempotent : CREATE ... IF NOT EXISTS)."""
    pool.open(wait=True)
    schema = (Path(__file__).parent / "schema.sql").read_text()
    with pool.connection() as conn:
        conn.execute(schema)


def close_db() -> None:
    pool.close()
