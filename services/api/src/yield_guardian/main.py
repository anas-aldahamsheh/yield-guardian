"""ASGI entry point: `uvicorn yield_guardian.main:app`."""

from yield_guardian.api.app import create_app

app = create_app()
