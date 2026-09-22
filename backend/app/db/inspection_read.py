"""Short read-only snapshots for inspection detail and its stock compatibility endpoint."""
from sqlalchemy import text

from app.db.session import SessionLocal


def get_inspection_read_db():
    # Use a fresh session: authentication and writes keep their normal transactions.
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield db
    # Session.close rolls back the read transaction, returning the connection to the pool.
