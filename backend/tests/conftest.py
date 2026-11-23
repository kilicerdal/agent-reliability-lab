import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import pytest


@pytest.fixture(scope="session")
def database():
    if not os.environ.get("LAB_DATABASE_URL"):
        pytest.skip(
            "PostgreSQL integration requires LAB_DATABASE_URL and inventory service"
        )
    from lab.db import init_db

    init_db()
