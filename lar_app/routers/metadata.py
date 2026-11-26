"""Registration of legacy cached metadata endpoints."""
from typing import Any


def install_metadata_route(app: Any, endpoint: Any, *, path: str) -> None:
    """Register the core callable at its original route position."""
    app.add_api_route(path, endpoint, methods=['GET'])
