"""ASGI entry point: `uvicorn tsch_api.asgi:app`."""

from .main import create_app

app = create_app()
