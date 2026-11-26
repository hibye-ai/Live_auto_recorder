"""Registration of legacy local-account endpoints."""
from typing import Any


def install_account_route(app: Any, endpoint: Any, *, path: str, method: str) -> None:
    """Retain each original route position and core callable."""
    app.add_api_route(path, endpoint, methods=[method])
