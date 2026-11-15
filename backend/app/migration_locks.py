"""Acquire release locks without blocking live queries in a partial lock cycle."""

import time

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def acquire_release_locks(connection, tables, *, attempts=30, delay=1):
    # Identifiers are the fixed, source-controlled migration table list.
    names = ", ".join('"' + name.replace('"', '""') + '"' for name in tables)
    sql = text(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE NOWAIT")
    for attempt in range(attempts):
        try:
            # Rolling back a failed savepoint releases every partial lock before
            # sleeping. No active reader is killed or made to wait behind DDL.
            with connection.begin_nested():
                connection.execute(sql)
            return
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) not in {"55P03", "40P01"}:
                raise
            if attempt + 1 == attempts:
                raise RuntimeError(
                    "Archive is busy; no access changes applied. Retry release later."
                ) from exc
            time.sleep(delay)
