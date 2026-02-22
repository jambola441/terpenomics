# database.py
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.engine import Engine


def _build_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url and url.strip():
        return url.strip()

    host = os.getenv("SUPABASE_DB_HOST")
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    name = os.getenv("SUPABASE_DB_NAME", "postgres")
    user = os.getenv("SUPABASE_DB_USER")
    password = os.getenv("SUPABASE_DB_PASSWORD")

    missing = [k for k, v in {
        "SUPABASE_DB_HOST": host,
        "SUPABASE_DB_USER": user,
        "SUPABASE_DB_PASSWORD": password,
    }.items() if not v]

    if missing:
        raise RuntimeError(
            "Missing database configuration. Provide DATABASE_URL or set: "
            + ", ".join(missing)
        )

    return (
        f"postgresql://{user}:{password}@{host}:{port}/{name}"
        f""
    )


def _create_engine() -> Engine:
    database_url = _build_database_url()
    print(database_url)
    echo = os.getenv("SQL_ECHO", "false").lower() == "true"

    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


engine: Engine = _create_engine()
print("DB USER IN ENGINE:", engine.url.username)
print("DB HOST IN ENGINE:", engine.url.host)
print("DB NAME IN ENGINE:", engine.url.database)



def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session: Optional[Session] = None
    try:
        session = Session(engine)
        yield session
        session.commit()
    except Exception:
        if session is not None:
            session.rollback()
        raise
    finally:
        if session is not None:
            session.close()
