"""Shared pytest fixtures for the plan API tests.

Mirrors the setup of tests/plans.test.ts in the TS project:
  * NODE_ENV=test is set before the app is imported.
  * Redis is replaced with an in-memory fakeredis instance (flushed before the suite).
  * Bearer-token auth is overridden so requests are treated as authenticated.
  * publish_plan_event is mocked so no RabbitMQ broker is needed.
"""

import os

os.environ["NODE_ENV"] = "test"

from unittest.mock import AsyncMock  # noqa: E402

import fakeredis  # noqa: E402
import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Modules that hold a reference to the `redis` client via
# `from app.services.redis import redis`.
REDIS_MODULES = (
    "app.services.redis",
    "app.routes.plans_routes",
    "app.services.plan_store",
)


@pytest.fixture(scope="session")
def fake_redis():
    server = fakeredis.FakeServer()
    return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture(scope="module")
def client(fake_redis):
    import importlib

    mp = pytest.MonkeyPatch()

    for mod_name in REDIS_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "redis"):
            mp.setattr(mod, "redis", fake_redis)

    from app.main import app
    from app.middleware.auth import validate_bearer_token

    publish_mock = AsyncMock(return_value=None)
    mp.setattr("app.routes.plans_routes.publish_plan_event", publish_mock)

    app.dependency_overrides[validate_bearer_token] = lambda: {"sub": "test-user"}

    with TestClient(app) as test_client:
        # beforeAll: clean redis before running
        test_client.portal.call(fake_redis.flushall)
        test_client.publish_mock = publish_mock
        yield test_client
        # afterAll: close redis
        test_client.portal.call(fake_redis.aclose)

    app.dependency_overrides.clear()
    mp.undo()
