import os

import psycopg
import pytest

TEST_DB = os.getenv("TEST_DB_NAME", "migration_test")
ADMIN_URL = os.getenv("ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
os.environ.setdefault("DATABASE_URL", ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB)


def _reset_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')


_reset_database()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
