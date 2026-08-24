# database.py
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.engine import Engine


def _load_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.is_file():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key not in os.environ:
                os.environ[key] = val


_load_dotenv()


def is_pr_preview() -> bool:
    """True when running as a Render pull request preview instance.

    Render sets IS_PULL_REQUEST on preview instances only; it is "false" (or
    absent) on the production service and on local runs. See PREVIEWS.md.
    """
    return os.getenv("IS_PULL_REQUEST", "").strip().lower() == "true"


def _preview_database_url() -> str:
    """Resolve the database a PR preview is allowed to touch.

    Render preview instances inherit every env var from their base service,
    production DATABASE_URL included. Without this, un-reviewed code on a PR
    branch would read and write real data. So on a preview we ignore
    DATABASE_URL entirely and require PREVIEW_DATABASE_URL — set once on the
    base service, inherited by every preview, ignored in production.

    Fails closed: a preview with no preview database refuses to start rather
    than quietly falling back to production.
    """
    url = os.getenv("PREVIEW_DATABASE_URL", "").strip()
    if url:
        return url

    if os.getenv("PREVIEW_ALLOW_PROD_DB", "").strip().lower() == "true":
        return ""  # caller falls through to the normal resolution

    raise RuntimeError(
        "This is a Render PR preview (IS_PULL_REQUEST=true) but "
        "PREVIEW_DATABASE_URL is not set. Refusing to start against the "
        "production database. Set PREVIEW_DATABASE_URL on the base service so "
        "every preview inherits it, or set PREVIEW_ALLOW_PROD_DB=true to "
        "deliberately run this preview against production. See PREVIEWS.md."
    )


def _build_database_url() -> str:
    if is_pr_preview():
        preview_url = _preview_database_url()
        if preview_url:
            return preview_url

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
    echo = os.getenv("SQL_ECHO", "false").lower() == "true"

    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


engine: Engine = _create_engine()



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
