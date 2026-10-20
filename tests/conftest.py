import pytest
from fastapi.testclient import TestClient

from app.cache import cache
from app.main import app


@pytest.fixture
def client():
    cache.clear()
    with TestClient(app) as c:
        yield c
    cache.clear()
