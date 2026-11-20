import asyncio
import re
import unittest

from fastapi import FastAPI
from starlette.applications import Starlette

from observability import install_observability


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        install_observability(self.app, "test-service")

        @self.app.get("/probe/{item_id}")
        async def probe(item_id: str):
            return {"item_id": item_id}

    def _request(self, path: str, headers=None, app=None):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": headers or [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {},
        }
        messages = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        asyncio.run((app or self.app)(scope, receive, send))
        return messages

    def test_trace_context_is_preserved_and_http_metrics_are_exported(self):
        trace_id = "0123456789abcdef0123456789abcdef"
        messages = self._request(
            "/probe/123",
            [
                (
                    b"traceparent",
                    f"00-{trace_id}-0123456789abcdef-01".encode("ascii"),
                )
            ],
        )
        response_start = next(
            message for message in messages
            if message["type"] == "http.response.start"
        )
        response_headers = dict(response_start["headers"])
        self.assertEqual(response_headers[b"x-trace-id"].decode(), trace_id)
        self.assertTrue(
            response_headers[b"traceparent"].decode().startswith(f"00-{trace_id}-")
        )

        metrics_messages = self._request("/metrics")
        metrics_body = b"".join(
            message.get("body", b"")
            for message in metrics_messages
            if message["type"] == "http.response.body"
        ).decode()
        self.assertIn(
            'http_server_requests_total{method="GET",route="/probe/{item_id}",'
            'service="test-service",status_code="200"} 1.0',
            metrics_body,
        )

    def test_invalid_trace_context_is_replaced_with_valid_context(self):
        messages = self._request(
            "/probe/456",
            [(b"traceparent", b"not-a-valid-traceparent")],
        )
        response_start = next(
            message for message in messages
            if message["type"] == "http.response.start"
        )
        response_headers = dict(response_start["headers"])
        traceparent = response_headers[b"traceparent"].decode()
        self.assertRegex(
            traceparent,
            re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-01$"),
        )

    def test_starlette_app_gets_health_and_metrics_routes(self):
        app = Starlette()
        install_observability(app, "starlette-service")

        health_messages = self._request("/health", app=app)
        health_start = next(
            message for message in health_messages
            if message["type"] == "http.response.start"
        )
        health_body = b"".join(
            message.get("body", b"")
            for message in health_messages
            if message["type"] == "http.response.body"
        )
        self.assertEqual(health_start["status"], 200)
        self.assertEqual(
            health_body,
            b'{"status":"ok","service":"starlette-service"}',
        )

        metrics_messages = self._request("/metrics", app=app)
        metrics_start = next(
            message for message in metrics_messages
            if message["type"] == "http.response.start"
        )
        self.assertEqual(metrics_start["status"], 200)


if __name__ == "__main__":
    unittest.main()
