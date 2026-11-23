"""BACKFILL : remplit first/last_name par petits lots (pas de long verrou)."""


def run(conn, batch_size: int = 1000) -> int:
    total = 0
    while True:
        n = conn.execute(
            """
            UPDATE customers SET full_name = full_name     -- le trigger calcule first/last
             WHERE id IN (SELECT id FROM customers WHERE first_name IS NULL
                          ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED)
            """,
            (batch_size,),
        ).rowcount
        conn.commit()
        total += n
        if n == 0:
            return total
