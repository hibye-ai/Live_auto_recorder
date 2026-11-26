"""Registration for legacy status and system telemetry handlers."""
from typing import Any


def install_monitoring_route(app: Any, endpoint: Any, *, path: str) -> None:
    """Register an existing core handler without changing its order or identity."""
    app.add_api_route(path, endpoint, methods=['GET'])


def install_metrics_websocket(app: Any, endpoint: Any) -> None:
    """Register the original telemetry websocket handler."""
    app.add_api_websocket_route('/ws/sys_metrics', endpoint)
