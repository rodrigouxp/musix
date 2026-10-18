import pytest
from sqlalchemy import create_engine

from musix.db import create_all_tables
from musix.db.engine import DbEngine


@pytest.fixture
def database(tmp_path, monkeypatch):
    """
    An empty sqlite database with every table, in a temporary folder.
    """
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setattr(DbEngine, "_engine", engine)
    create_all_tables()
    yield engine
    engine.dispose()
