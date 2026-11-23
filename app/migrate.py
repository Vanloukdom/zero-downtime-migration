"""Exécuteur de migrations : versionné, sous verrou consultatif, avec lock_timeout.

    python -m app.migrate                # applique jusqu'à MIGRATE_TO (défaut : 003)
    MIGRATE_TO=004 python -m app.migrate # contract (à lancer en dernier)
"""
import importlib.util
import os
from pathlib import Path

import psycopg

from app.db import DATABASE_URL

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
LOCK_ID = 727_001  # pg_advisory_lock : un seul migrateur à la fois, même avec N pods


def pending(conn, target: str) -> list[Path]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
    )
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    files = sorted(p for p in MIGRATIONS.iterdir() if p.suffix in (".sql", ".py"))
    return [p for p in files if p.name[:3] <= target and p.name[:3] not in done]


def migrate(target: str | None = None, url: str = DATABASE_URL) -> list[str]:
    target = target or os.getenv("MIGRATE_TO", "003")
    applied = []
    with psycopg.connect(url) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        conn.commit()
        try:
            for path in pending(conn, target):
                # Échouer vite plutôt que bloquer le trafic derrière un verrou DDL.
                conn.execute("SET lock_timeout = '5s'")
                if path.suffix == ".sql":
                    conn.execute(path.read_text())
                else:
                    spec = importlib.util.spec_from_file_location(path.stem, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.run(conn)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name[:3],))
                conn.commit()
                applied.append(path.name)
                print(f"migration appliquée : {path.name}")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
            conn.commit()
    return applied


if __name__ == "__main__":
    migrate()
