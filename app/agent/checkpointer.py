import atexit
from functools import lru_cache
from threading import Lock

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url

from app.core.config import get_settings

_lock = Lock()
_pool: ConnectionPool | None = None


@lru_cache(maxsize=1)
def get_checkpointer() -> PostgresSaver:
    """Create one bounded PostgreSQL checkpoint pool per API process."""
    global _pool
    with _lock:
        if _pool is None:
            connection_url = make_url(get_settings().database_url).set(drivername="postgresql")
            pool = ConnectionPool(
                conninfo=connection_url.render_as_string(hide_password=False),
                min_size=1,
                max_size=5,
                timeout=5,
                kwargs={"autocommit": True, "row_factory": dict_row},
                open=False,
            )
            pool.open(wait=True, timeout=5)
            checkpointer = PostgresSaver(
                pool,
                serde=JsonPlusSerializer(allowed_msgpack_modules=None),
            )
            checkpointer.setup()
            _pool = pool
            atexit.register(pool.close)
            return checkpointer
        return PostgresSaver(
            _pool,
            serde=JsonPlusSerializer(allowed_msgpack_modules=None),
        )
