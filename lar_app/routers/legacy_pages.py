"""Registration of the original console pages."""
from typing import Any
from fastapi.responses import HTMLResponse


def install_legacy_page(app: Any, endpoint: Any, *, path: str) -> None:
    """Keep the original endpoint, HTML response class and route position."""
    app.add_api_route(path, endpoint, methods=['GET'], response_class=HTMLResponse)
