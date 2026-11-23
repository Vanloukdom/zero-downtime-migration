import os

import pytest

os.environ["RUN_MIGRATIONS_ON_STARTUP"] = "false"

from app.db import pool  # noqa: E402
from app.migrate import migrate  # noqa: E402


@pytest.fixture
def at_phase(monkeypatch):
    def set_phase(p):
        monkeypatch.setenv("SCHEMA_PHASE", p)
    return set_phase


def test_full_expand_contract_cycle_without_breaking_old_version(client, at_phase):
    # --- Production actuelle : v1 ---
    assert migrate("001") == ["001_initial.sql"]
    at_phase("v1")
    old = client.post("/customers", json={"email": "ada@ex.com", "first_name": "Ada", "last_name": "Lovelace"}).json()
    with pool.connection() as conn:
        conn.execute("INSERT INTO customers (email, full_name) SELECT 'u' || g || '@ex.com', 'User ' || g "
                     "FROM generate_series(1, 2500) g")

    # --- EXPAND : nouvelles colonnes, v1 et v2 tournent en même temps ---
    assert migrate("002") == ["002_expand_split_name.sql"]
    at_phase("v1")  # un pod v1 encore en vie écrit l'ancien format
    v1_write = client.post("/customers", json={"email": "alan@ex.com", "first_name": "Alan", "last_name": "Turing"}).json()
    at_phase("expand")  # un pod v2 écrit les deux formats
    v2_write = client.post("/customers", json={"email": "grace@ex.com", "first_name": "Grace", "last_name": "Hopper"}).json()
    at_phase("v1")  # rollback possible : v1 lit correctement ce que v2 a écrit
    assert client.get(f"/customers/{v2_write['id']}").json()["last_name"] == "Hopper"

    # --- BACKFILL par lots ---
    assert migrate("003") == ["003_backfill.py"]
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM customers WHERE first_name IS NULL").fetchone()["n"] == 0

    # --- MIGRATE : lecture sur les nouvelles colonnes ---
    at_phase("migrate")
    assert client.get(f"/customers/{old['id']}").json() == {
        "id": old["id"], "email": "ada@ex.com", "first_name": "Ada", "last_name": "Lovelace"}
    assert client.get(f"/customers/{v1_write['id']}").json()["first_name"] == "Alan"

    # --- CONTRACT : suppression de l'ancienne colonne (plus aucun pod v1) ---
    assert migrate("004") == ["004_contract_drop_full_name.sql"]
    at_phase("contract")
    new = client.post("/customers", json={"email": "linus@ex.com", "first_name": "Linus", "last_name": "Torvalds"}).json()
    assert new["last_name"] == "Torvalds"
    assert client.get(f"/customers/{old['id']}").json()["first_name"] == "Ada"


def test_migrations_are_idempotent():
    assert migrate("004") == []
