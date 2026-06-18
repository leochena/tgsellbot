import json
import socket

import pytest

from bot.model_lab import (
    MODEL_LAB_P0_SUITE_VERSION,
    ModelLabWorker,
    ModelLabWorkerConfig,
    UnsafeWorkerTarget,
    normalize_worker_endpoint,
    resolve_public_addresses,
)


def public_resolver(host, port, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def private_resolver(host, port, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]


class FakeResponse:
    def __init__(self, status, payload, *, headers=None, url="https://relay.example.com/v1"):
        self.status = status
        self.headers = headers or {"content-type": "application/json"}
        self.url = url
        if isinstance(payload, bytes):
            self._body = payload
        elif isinstance(payload, str):
            self._body = payload.encode("utf-8")
        else:
            self._body = json.dumps(payload).encode("utf-8")

    async def read(self):
        return self._body


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    async def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, "kwargs": kwargs})
        return self.handler(method, url, kwargs.get("json"))


class TestModelLabTargetSafety:
    @pytest.mark.parametrize(
        "url",
        [
            "http://relay.example.com/v1",
            "https://localhost/v1",
            "https://127.0.0.1/v1",
            "https://10.0.0.1/v1",
            "https://169.254.169.254/latest/meta-data",
            "https://relay.example.com:8080/v1",
            "https://user:pass@relay.example.com/v1",
            "https://relay.example.com/v1?api_key=secret",
        ],
    )
    def test_normalize_worker_endpoint_blocks_unsafe_targets(self, url):
        with pytest.raises(UnsafeWorkerTarget):
            normalize_worker_endpoint(url)

    def test_resolve_public_addresses_blocks_private_dns(self):
        with pytest.raises(UnsafeWorkerTarget):
            resolve_public_addresses("relay.example.com", resolver=private_resolver)

    async def test_worker_revalidates_redirect_target(self):
        def handler(method, url, body):
            return FakeResponse(
                302,
                b"",
                headers={"location": "https://127.0.0.1/internal"},
                url=url,
            )

        worker = ModelLabWorker(
            ModelLabWorkerConfig(resolver=public_resolver, max_redirects=2),
            session=FakeSession(handler),
        )

        report = await worker.run_task({
            "endpoint": "https://relay.example.com/v1",
            "protocol": "openai-compatible",
            "requested_model": "gpt-test",
            "api_key": "sk-test-secret",
        })

        assert report["grade"] == "F"
        suite = report["evidence_json"]["suite"]
        assert any(item["name"] == "models_list" and item["status"] == "failed" for item in suite)
        assert "sk-test-secret" not in str(report)


class TestOpenAICompatibleWorker:
    async def test_openai_compatible_report_is_redacted_and_scores_p0_items(self):
        secret = "sk-test-secret-value"

        def handler(method, url, body):
            if url.endswith("/models"):
                return FakeResponse(200, {
                    "object": "list",
                    "data": [{"id": "gpt-test", "object": "model"}],
                }, url=url)
            if body and body.get("stream"):
                return FakeResponse(
                    200,
                    'data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"pong"}}]}\n\n'
                    "data: [DONE]\n\n",
                    headers={"content-type": "text/event-stream"},
                    url=url,
                )
            if body and body.get("tools"):
                return FakeResponse(200, {
                    "object": "chat.completion",
                    "model": body["model"],
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "inspect_endpoint", "arguments": "{}"},
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                }, url=url)
            content = "{\"ok\": true}" if body and body.get("response_format") else "pong"
            return FakeResponse(200, {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": body["model"],
                "choices": [{
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            }, url=url)

        session = FakeSession(handler)
        worker = ModelLabWorker(
            ModelLabWorkerConfig(resolver=public_resolver, max_tokens=16),
            session=session,
        )

        report = await worker.run_task({
            "endpoint": "https://relay.example.com/v1",
            "protocol": "openai-compatible",
            "requested_model": "gpt-test",
            "api_key": secret,
            "visibility": "private",
        })

        assert report["suite_version"] == MODEL_LAB_P0_SUITE_VERSION
        assert report["declared_model"] == "gpt-test"
        assert report["returned_model"] == "gpt-test"
        assert report["scores"]["protocol_compatibility"] == 1.0
        assert report["scores"]["declared_model_consistency"] == 1.0
        assert report["scores"]["observed_behavior"] >= 0.9
        assert "Black-box testing cannot prove the real upstream model" in report["limitation_note"]
        assert secret not in str(report)
        assert report["evidence_json"]["credential"]["fingerprint"]
        assert report["evidence_json"]["credential"]["mask"] == "sk-t...alue"
        suite_by_name = {item["name"]: item for item in report["evidence_json"]["suite"]}
        for name in [
            "models_list",
            "chat_basic",
            "multilingual_text",
            "stop_condition",
            "json_output",
            "streaming",
            "tool_call",
            "usage_accounting",
        ]:
            assert name in suite_by_name
        assert suite_by_name["streaming"]["status"] == "passed"
        assert suite_by_name["tool_call"]["status"] == "passed"
        assert all(request["kwargs"]["allow_redirects"] is False for request in session.requests)


class TestAnthropicCompatibleWorker:
    async def test_anthropic_compatible_report_uses_protocol_specific_shapes(self):
        secret = "anthropic-secret-value"

        def handler(method, url, body):
            if url.endswith("/models"):
                return FakeResponse(200, {
                    "data": [{"id": "claude-test", "type": "model"}],
                    "has_more": False,
                }, url=url)
            if body and body.get("stream"):
                return FakeResponse(
                    200,
                    'event: message_start\n'
                    'data: {"type":"message_start","message":{"model":"claude-test"}}\n\n',
                    headers={"content-type": "text/event-stream"},
                    url=url,
                )
            if body and body.get("tools"):
                return FakeResponse(200, {
                    "id": "msg_tool",
                    "type": "message",
                    "model": body["model"],
                    "content": [{"type": "tool_use", "name": "inspect_endpoint", "input": {}}],
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 4, "output_tokens": 2},
                }, url=url)
            text = "{\"ok\": true}" if "JSON" in body["messages"][0]["content"] else "pong"
            return FakeResponse(200, {
                "id": "msg_test",
                "type": "message",
                "model": body["model"],
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 4, "output_tokens": 2},
            }, url=url)

        worker = ModelLabWorker(
            ModelLabWorkerConfig(resolver=public_resolver, max_tokens=16),
            session=FakeSession(handler),
        )

        report = await worker.run_task({
            "endpoint": "https://anthropic-relay.example.com/v1",
            "protocol": "anthropic-compatible",
            "requested_model": "claude-test",
            "api_key": secret,
        })

        assert report["returned_model"] == "claude-test"
        assert report["scores"]["protocol_compatibility"] == 1.0
        assert secret not in str(report)
        suite_by_name = {item["name"]: item for item in report["evidence_json"]["suite"]}
        assert suite_by_name["message_basic"]["status"] == "passed"
        assert suite_by_name["streaming"]["status"] == "passed"
        assert suite_by_name["tool_call"]["status"] == "passed"
