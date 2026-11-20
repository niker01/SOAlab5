import contextvars
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_TRACEPARENT_PATTERN = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$",
    re.IGNORECASE,
)
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_traceparent_context = contextvars.ContextVar("traceparent", default=None)
_request_logger = logging.getLogger("soa.http")
_request_logger.setLevel(logging.INFO)
_request_logger.propagate = False
if not any(getattr(handler, "_soa_json_handler", False) for handler in _request_logger.handlers):
    _json_handler = logging.StreamHandler()
    _json_handler.setFormatter(logging.Formatter("%(message)s"))
    _json_handler._soa_json_handler = True
    _request_logger.addHandler(_json_handler)
_HISTOGRAM_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def current_traceparent() -> str | None:
    return _traceparent_context.get()


def _new_traceparent(incoming: str | None, incoming_trace_id: str | None) -> str:
    if incoming:
        match = _TRACEPARENT_PATTERN.fullmatch(incoming.strip())
        if match:
            trace_id = match.group(1).lower()
            flags = match.group(3).lower()
            return f"00-{trace_id}-{secrets.token_hex(8)}-{flags}"

    if incoming_trace_id and _TRACE_ID_PATTERN.fullmatch(incoming_trace_id.strip()):
        trace_id = incoming_trace_id.strip().lower()
    else:
        trace_id = secrets.token_hex(16)
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


def install_observability(app, service_name: str) -> None:
    registry = CollectorRegistry()
    requests_total = Counter(
        "http_server_requests",
        "Total HTTP requests handled by this service",
        ("service", "method", "route", "status_code"),
        registry=registry,
    )
    request_duration = Histogram(
        "http_server_request_duration_seconds",
        "HTTP request duration in seconds",
        ("service", "method", "route"),
        buckets=_HISTOGRAM_BUCKETS,
        registry=registry,
    )

    async def metrics_endpoint(request: Request) -> Response:
        return Response(
            content=generate_latest(registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    app.add_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
    )

    if not any(getattr(route, "path", None) == "/health" for route in app.routes):
        async def health_endpoint(request: Request) -> Response:
            return JSONResponse({"status": "ok", "service": service_name})

        app.add_route(
            "/health",
            health_endpoint,
            methods=["GET"],
        )

    class ObservabilityMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            headers = {
                key.lower(): value
                for key, value in scope.get("headers", [])
            }
            traceparent = _new_traceparent(
                headers.get(b"traceparent", b"").decode("latin-1"),
                headers.get(b"x-trace-id", b"").decode("latin-1"),
            )
            token = _traceparent_context.set(traceparent)
            trace_id = traceparent.split("-")[1]
            span_id = traceparent.split("-")[2]
            path = scope.get("path", "")
            observed = path not in {"/health", "/metrics"}
            started_at = time.perf_counter()
            status_code = 500
            route = "unmatched"

            async def send_with_trace_headers(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    existing = {
                        key.lower()
                        for key, _ in message.get("headers", [])
                    }
                    new_headers = list(message.get("headers", []))
                    if b"x-trace-id" not in existing:
                        new_headers.append((b"x-trace-id", trace_id.encode("ascii")))
                    if b"traceparent" not in existing:
                        new_headers.append(
                            (b"traceparent", traceparent.encode("ascii"))
                        )
                    message["headers"] = new_headers
                await send(message)

            try:
                await self.app(scope, receive, send_with_trace_headers)
            except Exception:
                status_code = 500
                raise
            finally:
                elapsed = time.perf_counter() - started_at
                route_object = scope.get("route")
                if route_object is not None:
                    route = getattr(route_object, "path", "unmatched")

                if observed:
                    method = scope.get("method", "UNKNOWN")
                    requests_total.labels(
                        service_name,
                        method,
                        route,
                        str(status_code),
                    ).inc()
                    request_duration.labels(
                        service_name,
                        method,
                        route,
                    ).observe(elapsed)
                    _request_logger.info(
                        json.dumps(
                            {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "event": "http_request",
                                "severity": "INFO",
                                "service": service_name,
                                "trace_id": trace_id,
                                "span_id": span_id,
                                "method": method,
                                "route": route,
                                "status_code": status_code,
                                "duration_ms": round(elapsed * 1000, 3),
                            },
                            separators=(",", ":"),
                        )
                    )

                _traceparent_context.reset(token)

    app.add_middleware(ObservabilityMiddleware)
