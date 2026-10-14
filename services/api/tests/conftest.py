from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from yield_guardian.api.app import create_app
from yield_guardian.core.settings import Settings
from yield_guardian.services.registry import ServiceRegistry


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", log_json=False)


@pytest.fixture
def registry(settings: Settings) -> ServiceRegistry:
    return ServiceRegistry(settings=settings)


@pytest.fixture
def app(settings: Settings, registry: ServiceRegistry) -> FastAPI:
    return create_app(settings, registry)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
