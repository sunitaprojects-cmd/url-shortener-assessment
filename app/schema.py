from pathlib import Path

from sqlalchemy import Engine

from app.config import database_url_from_environment
from app.database import Database
from app.models import Base

MIGRATIONS = (
    Path(__file__).with_name("migrations") / "002_add_redirect_analytics.sql",
)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    apply_schema_migrations(engine)


def apply_schema_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        for migration in MIGRATIONS:
            connection.exec_driver_sql(migration.read_text(encoding="utf-8"))


def main() -> None:
    database = Database(database_url_from_environment())
    try:
        create_schema(database.engine)
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
