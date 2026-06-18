from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import aiohttp


MODEL_LAB_P0_SUITE_VERSION = "model-lab-p0-2026-06-17"
MODEL_REPORT_LIMITATION = (
    "This report evaluates protocol compatibility, declared-model consistency, observed behavior, "
    "and degradation risk. Black-box testing cannot prove the real upstream model with certainty."
)

ALLOWED_WORKER_PORTS = frozenset({443})
SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "bearer",
    "key",
    "password",
    "secret",
    "token",
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
OPENAI_PROTOCOLS = {"openai", "openai-compatible"}
ANTHROPIC_PROTOCOLS = {"anthropic", "anthropic-compatible"}


class UnsafeWorkerTarget(ValueError):
    """Raised when a Worker target fails runtime network safety rules."""


class WorkerRequestError(RuntimeError):
    """Raised for bounded network/request failures inside a suite item."""


@dataclass(frozen=True)
class WorkerEndpoint:
    normalized: str
    public: str
    url_hash: str
    hostname: str
    port: int


@dataclass(frozen=True)
class WorkerHTTPResult:
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int
    final_url: str
    public_url: str
    resolved_address_count: int
    redirects: int = 0

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class ModelLabWorkerConfig:
    timeout_seconds: float = 20.0
    max_response_bytes: int = 256 * 1024
    max_redirects: int = 2
    max_concurrency: int = 2
    max_tokens: int = 64
    allowed_ports: frozenset[int] = ALLOWED_WORKER_PORTS
    resolver: Callable[..., Iterable[Any]] = socket.getaddrinfo
    user_agent: str = "TGSellBot-ModelLab/0.1"
    anthropic_version: str = "2023-06-01"


def stable_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def fingerprint_secret(value: str | None) -> str:
    text = (value or "").strip()
    return stable_hash(text) if text else ""


def mask_secret(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return f"{text[:2]}...{text[-2:]}"
    return f"{text[:4]}...{text[-4:]}"


def normalize_worker_endpoint(raw_url: str, *, allowed_ports: frozenset[int] = ALLOWED_WORKER_PORTS) -> WorkerEndpoint:
    text = (raw_url or "").strip()
    if not text:
        raise UnsafeWorkerTarget("Target URL is required.")
    if "://" not in text:
        text = f"https://{text}"

    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeWorkerTarget("Target port is not valid.") from exc

    if parsed.scheme.lower() != "https":
        raise UnsafeWorkerTarget("Only HTTPS targets are allowed.")
    if parsed.username or parsed.password:
        raise UnsafeWorkerTarget("Credentials are not allowed in target URLs.")
    if not parsed.hostname:
        raise UnsafeWorkerTarget("Target host is required.")

    hostname = parsed.hostname.lower().strip(".")
    if _is_blocked_hostname(hostname) or _is_blocked_ip(hostname):
        raise UnsafeWorkerTarget("Target host is not allowed.")

    effective_port = int(port or 443)
    if effective_port not in allowed_ports:
        raise UnsafeWorkerTarget("Target port is not allowed.")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    for key, _ in query_pairs:
        if key.strip().lower() in SENSITIVE_QUERY_KEYS:
            raise UnsafeWorkerTarget("Sensitive credentials are not allowed in target query parameters.")

    path = parsed.path or ""
    if path and not path.startswith("/"):
        path = f"/{path}"
    normalized_query = urlencode(sorted(query_pairs))
    netloc = hostname if effective_port == 443 else f"{hostname}:{effective_port}"
    normalized = urlunsplit(("https", netloc, path, normalized_query, ""))
    public = urlunsplit(("https", netloc, path, "", ""))
    return WorkerEndpoint(
        normalized=normalized,
        public=public,
        url_hash=stable_hash(normalized),
        hostname=hostname,
        port=effective_port,
    )


def resolve_public_addresses(
        hostname: str,
        *,
        port: int = 443,
        resolver: Callable[..., Iterable[Any]] = socket.getaddrinfo,
) -> list[str]:
    host = (hostname or "").strip().strip("[]").lower().strip(".")
    if not host:
        raise UnsafeWorkerTarget("Target host is required.")
    if _is_blocked_hostname(host):
        raise UnsafeWorkerTarget("Target host is not allowed.")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        _ensure_public_ip(ip)
        return [ip.compressed]

    try:
        records = resolver(host, port, type=socket.SOCK_STREAM)
    except TypeError:
        records = resolver(host, port)
    except socket.gaierror as exc:
        raise UnsafeWorkerTarget("Target DNS resolution failed.") from exc

    addresses: set[str] = set()
    for record in records or []:
        try:
            raw_address = record[-1][0]
            resolved = ipaddress.ip_address(str(raw_address).strip("[]"))
        except (IndexError, TypeError, ValueError) as exc:
            raise UnsafeWorkerTarget("Target DNS returned an invalid address.") from exc
        _ensure_public_ip(resolved)
        addresses.add(resolved.compressed)

    if not addresses:
        raise UnsafeWorkerTarget("Target DNS returned no addresses.")
    return sorted(addresses)


class ModelLabWorker:
    def __init__(self, config: ModelLabWorkerConfig | None = None, session: Any | None = None):
        self.config = config or ModelLabWorkerConfig()
        self._session = session
        self._owns_session = False
        self._semaphore = asyncio.Semaphore(max(1, int(self.config.max_concurrency or 1)))

    async def run_task(self, task: dict[str, Any]) -> dict[str, Any]:
        protocol = str(task.get("protocol") or "openai-compatible").strip().lower()
        endpoint_raw = str(task.get("endpoint") or task.get("base_url") or "").strip()
        requested_model = str(task.get("requested_model") or task.get("model") or "").strip()
        api_key = str(task.get("api_key") or "")
        visibility = str(task.get("visibility") or "private").strip() or "private"

        try:
            endpoint = normalize_worker_endpoint(endpoint_raw, allowed_ports=self.config.allowed_ports)
            initial_addresses = resolve_public_addresses(
                endpoint.hostname,
                port=endpoint.port,
                resolver=self.config.resolver,
            )
        except UnsafeWorkerTarget as exc:
            return self._build_report(
                protocol=protocol,
                endpoint=None,
                api_key=api_key,
                requested_model=requested_model,
                returned_model="",
                visibility=visibility,
                items=[
                    _suite_item(
                        "target_safety",
                        "failed",
                        _safe_error(exc, api_key),
                        {"category": "ssrf_guard"},
                    )
                ],
                dns_address_count=0,
            )

        await self._ensure_session()
        try:
            if protocol in OPENAI_PROTOCOLS:
                items, returned_model = await self._run_openai_suite(endpoint, requested_model, api_key)
            elif protocol in ANTHROPIC_PROTOCOLS:
                items, returned_model = await self._run_anthropic_suite(endpoint, requested_model, api_key)
            else:
                items, returned_model = [
                    _suite_item("protocol", "failed", "Unsupported protocol.", {"protocol": protocol})
                ], ""
        finally:
            await self._close_owned_session()

        return self._build_report(
            protocol=protocol,
            endpoint=endpoint,
            api_key=api_key,
            requested_model=requested_model,
            returned_model=returned_model,
            visibility=visibility,
            items=items,
            dns_address_count=len(initial_addresses),
        )

    async def _run_openai_suite(
            self,
            endpoint: WorkerEndpoint,
            requested_model: str,
            api_key: str,
    ) -> tuple[list[dict[str, Any]], str]:
        items: list[dict[str, Any]] = []
        returned_model = ""
        selected_model = requested_model
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        models_result = await self._run_json_item(
            "models_list",
            "GET",
            self._join(endpoint, "/models"),
            headers,
            api_key,
            required=True,
        )
        models_payload = models_result.get("json") if models_result.get("ok") else {}
        if models_result.get("ok") and models_payload.get("object") == "list" and isinstance(models_payload.get("data"), list):
            first_model = _first_model_id(models_payload.get("data"))
            selected_model = selected_model or first_model
            items.append(_suite_item(
                "models_list",
                "passed",
                "Model list response is OpenAI-compatible.",
                {
                    "status_code": models_result["status_code"],
                    "model_count": len(models_payload.get("data") or []),
                    "selected_model_present": bool(selected_model),
                    "latency_ms": models_result["latency_ms"],
                },
            ))
        else:
            items.append(_suite_item(
                "models_list",
                "failed",
                models_result.get("summary") or "Model list response is not OpenAI-compatible.",
                models_result.get("metadata", {}),
            ))

        chat_url = self._join(endpoint, "/chat/completions")
        basic_payload = self._openai_chat_payload(
            selected_model,
            [{"role": "user", "content": "Reply with exactly: pong"}],
        )
        basic = await self._run_json_item("chat_basic", "POST", chat_url, headers, api_key, json_body=basic_payload, required=True)
        basic_json = basic.get("json") if basic.get("ok") else {}
        basic_message = _openai_message(basic_json)
        if basic.get("ok") and basic_json.get("object") == "chat.completion" and basic_message:
            returned_model = str(basic_json.get("model") or returned_model or "")
            items.append(_suite_item(
                "chat_basic",
                "passed",
                "Basic text completion returned an assistant message.",
                _openai_response_metadata(basic, basic_json),
            ))
        else:
            items.append(_suite_item(
                "chat_basic",
                "failed",
                basic.get("summary") or "Basic text completion did not match OpenAI-compatible shape.",
                basic.get("metadata", {}),
            ))

        multilingual_payload = self._openai_chat_payload(
            selected_model,
            [{"role": "user", "content": "用中文简短回答：测试通过"}],
        )
        multilingual = await self._run_json_item(
            "multilingual_text",
            "POST",
            chat_url,
            headers,
            api_key,
            json_body=multilingual_payload,
            required=False,
        )
        items.append(self._openai_optional_message_item("multilingual_text", multilingual, "Multilingual prompt returned a message."))

        stop_payload = self._openai_chat_payload(
            selected_model,
            [{"role": "user", "content": "Return exactly: alpha beta gamma"}],
            stop=[" beta"],
        )
        stop_result = await self._run_json_item("stop_condition", "POST", chat_url, headers, api_key, json_body=stop_payload)
        stop_json = stop_result.get("json") if stop_result.get("ok") else {}
        finish_reason = _openai_finish_reason(stop_json)
        status = "passed" if stop_result.get("ok") and finish_reason in {"stop", "length"} else "warning"
        items.append(_suite_item(
            "stop_condition",
            status,
            "Stop condition response was accepted." if stop_result.get("ok") else stop_result.get("summary", "Stop condition was not accepted."),
            _openai_response_metadata(stop_result, stop_json),
        ))

        json_payload = self._openai_chat_payload(
            selected_model,
            [{"role": "user", "content": "Return only JSON: {\"ok\": true}"}],
            response_format={"type": "json_object"},
        )
        json_result = await self._run_json_item("json_output", "POST", chat_url, headers, api_key, json_body=json_payload)
        json_payload_response = json_result.get("json") if json_result.get("ok") else {}
        content = _openai_message(json_payload_response).get("content") if json_result.get("ok") else ""
        parsed_json = _is_json_object(str(content or ""))
        items.append(_suite_item(
            "json_output",
            "passed" if parsed_json else "warning",
            "JSON output parsed as an object." if parsed_json else json_result.get("summary", "JSON output is unsupported or did not parse."),
            _openai_response_metadata(json_result, json_payload_response) | {"json_parse_ok": parsed_json},
        ))

        stream_payload = self._openai_chat_payload(
            selected_model,
            [{"role": "user", "content": "Reply with one short word."}],
            stream=True,
        )
        stream_result = await self._run_text_item("streaming", "POST", chat_url, headers, api_key, json_body=stream_payload)
        stream_ok = stream_result.get("ok") and _has_openai_stream_chunk(stream_result.get("text", ""))
        items.append(_suite_item(
            "streaming",
            "passed" if stream_ok else "warning",
            "Streaming chunks matched OpenAI SSE shape." if stream_ok else stream_result.get("summary", "Streaming was not available or did not match OpenAI SSE shape."),
            stream_result.get("metadata", {}),
        ))

        tool_payload = self._openai_chat_payload(
            selected_model,
            [{"role": "user", "content": "Call the inspect_endpoint tool for target ping."}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "inspect_endpoint",
                        "description": "Return a synthetic endpoint inspection status.",
                        "parameters": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                            "required": ["target"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "inspect_endpoint"}},
        )
        tool_result = await self._run_json_item("tool_call", "POST", chat_url, headers, api_key, json_body=tool_payload)
        tool_json = tool_result.get("json") if tool_result.get("ok") else {}
        tool_ok = bool(_openai_message(tool_json).get("tool_calls"))
        items.append(_suite_item(
            "tool_call",
            "passed" if tool_ok else "warning",
            "Tool call response included tool_calls." if tool_ok else tool_result.get("summary", "Tool calling is unsupported or absent."),
            _openai_response_metadata(tool_result, tool_json) | {"tool_calls_present": tool_ok},
        ))

        usage_ok, usage_metadata = _usage_metadata(basic_json.get("usage") if isinstance(basic_json, dict) else None)
        items.append(_suite_item(
            "usage_accounting",
            "passed" if usage_ok else "warning",
            "Usage fields are present and non-negative." if usage_ok else "Usage fields are missing or not numeric.",
            usage_metadata,
        ))

        return items, returned_model

    async def _run_anthropic_suite(
            self,
            endpoint: WorkerEndpoint,
            requested_model: str,
            api_key: str,
    ) -> tuple[list[dict[str, Any]], str]:
        items: list[dict[str, Any]] = []
        returned_model = ""
        selected_model = requested_model
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.config.anthropic_version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        models_result = await self._run_json_item(
            "models_list",
            "GET",
            self._join(endpoint, "/models"),
            headers,
            api_key,
            required=True,
        )
        models_payload = models_result.get("json") if models_result.get("ok") else {}
        if models_result.get("ok") and isinstance(models_payload.get("data"), list):
            first_model = _first_model_id(models_payload.get("data"))
            selected_model = selected_model or first_model
            items.append(_suite_item(
                "models_list",
                "passed",
                "Model list response is Anthropic-compatible.",
                {
                    "status_code": models_result["status_code"],
                    "model_count": len(models_payload.get("data") or []),
                    "selected_model_present": bool(selected_model),
                    "latency_ms": models_result["latency_ms"],
                },
            ))
        else:
            items.append(_suite_item(
                "models_list",
                "failed",
                models_result.get("summary") or "Model list response is not Anthropic-compatible.",
                models_result.get("metadata", {}),
            ))

        messages_url = self._join(endpoint, "/messages")
        basic_payload = self._anthropic_message_payload(
            selected_model,
            [{"role": "user", "content": "Reply with exactly: pong"}],
        )
        basic = await self._run_json_item("message_basic", "POST", messages_url, headers, api_key, json_body=basic_payload, required=True)
        basic_json = basic.get("json") if basic.get("ok") else {}
        if basic.get("ok") and basic_json.get("type") == "message" and _anthropic_text_content(basic_json):
            returned_model = str(basic_json.get("model") or returned_model or "")
            items.append(_suite_item(
                "message_basic",
                "passed",
                "Basic message returned assistant text content.",
                _anthropic_response_metadata(basic, basic_json),
            ))
        else:
            items.append(_suite_item(
                "message_basic",
                "failed",
                basic.get("summary") or "Basic message did not match Anthropic-compatible shape.",
                basic.get("metadata", {}),
            ))

        multilingual_payload = self._anthropic_message_payload(
            selected_model,
            [{"role": "user", "content": "用中文简短回答：测试通过"}],
        )
        multilingual = await self._run_json_item("multilingual_text", "POST", messages_url, headers, api_key, json_body=multilingual_payload)
        multilingual_json = multilingual.get("json") if multilingual.get("ok") else {}
        items.append(_suite_item(
            "multilingual_text",
            "passed" if multilingual.get("ok") and _anthropic_text_content(multilingual_json) else "warning",
            "Multilingual prompt returned text content." if multilingual.get("ok") else multilingual.get("summary", "Multilingual prompt was not accepted."),
            _anthropic_response_metadata(multilingual, multilingual_json),
        ))

        stop_payload = self._anthropic_message_payload(
            selected_model,
            [{"role": "user", "content": "Return exactly: alpha beta gamma"}],
            stop_sequences=[" beta"],
        )
        stop_result = await self._run_json_item("stop_condition", "POST", messages_url, headers, api_key, json_body=stop_payload)
        stop_json = stop_result.get("json") if stop_result.get("ok") else {}
        stop_reason = str(stop_json.get("stop_reason") or "")
        items.append(_suite_item(
            "stop_condition",
            "passed" if stop_result.get("ok") and stop_reason else "warning",
            "Stop condition response was accepted." if stop_result.get("ok") else stop_result.get("summary", "Stop condition was not accepted."),
            _anthropic_response_metadata(stop_result, stop_json),
        ))

        json_payload = self._anthropic_message_payload(
            selected_model,
            [{"role": "user", "content": "Return only JSON: {\"ok\": true}"}],
        )
        json_result = await self._run_json_item("json_output", "POST", messages_url, headers, api_key, json_body=json_payload)
        json_response = json_result.get("json") if json_result.get("ok") else {}
        parsed_json = _is_json_object(_anthropic_text_content(json_response))
        items.append(_suite_item(
            "json_output",
            "passed" if parsed_json else "warning",
            "JSON output parsed as an object." if parsed_json else json_result.get("summary", "JSON output did not parse."),
            _anthropic_response_metadata(json_result, json_response) | {"json_parse_ok": parsed_json},
        ))

        stream_payload = self._anthropic_message_payload(
            selected_model,
            [{"role": "user", "content": "Reply with one short word."}],
            stream=True,
        )
        stream_result = await self._run_text_item("streaming", "POST", messages_url, headers, api_key, json_body=stream_payload)
        stream_ok = stream_result.get("ok") and _has_anthropic_stream_chunk(stream_result.get("text", ""))
        items.append(_suite_item(
            "streaming",
            "passed" if stream_ok else "warning",
            "Streaming chunks matched Anthropic SSE shape." if stream_ok else stream_result.get("summary", "Streaming was not available or did not match Anthropic SSE shape."),
            stream_result.get("metadata", {}),
        ))

        tool_payload = self._anthropic_message_payload(
            selected_model,
            [{"role": "user", "content": "Call the inspect_endpoint tool for target ping."}],
            tools=[
                {
                    "name": "inspect_endpoint",
                    "description": "Return a synthetic endpoint inspection status.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"target": {"type": "string"}},
                        "required": ["target"],
                        "additionalProperties": False,
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "inspect_endpoint"},
        )
        tool_result = await self._run_json_item("tool_call", "POST", messages_url, headers, api_key, json_body=tool_payload)
        tool_json = tool_result.get("json") if tool_result.get("ok") else {}
        tool_ok = _anthropic_has_tool_use(tool_json)
        items.append(_suite_item(
            "tool_call",
            "passed" if tool_ok else "warning",
            "Tool response included tool_use content." if tool_ok else tool_result.get("summary", "Tool calling is unsupported or absent."),
            _anthropic_response_metadata(tool_result, tool_json) | {"tool_use_present": tool_ok},
        ))

        usage_ok, usage_metadata = _usage_metadata(basic_json.get("usage") if isinstance(basic_json, dict) else None)
        items.append(_suite_item(
            "usage_accounting",
            "passed" if usage_ok else "warning",
            "Usage fields are present and non-negative." if usage_ok else "Usage fields are missing or not numeric.",
            usage_metadata,
        ))

        return items, returned_model

    async def _run_json_item(
            self,
            name: str,
            method: str,
            url: str,
            headers: dict[str, str],
            api_key: str,
            *,
            json_body: dict[str, Any] | None = None,
            required: bool = False,
    ) -> dict[str, Any]:
        try:
            result = await self._request(method, url, headers=headers, json_body=json_body)
            metadata = _http_metadata(result)
            if result.status >= 400:
                return {
                    "ok": False,
                    "status_code": result.status,
                    "latency_ms": result.elapsed_ms,
                    "summary": f"{name} returned HTTP {result.status}.",
                    "metadata": metadata,
                }
            try:
                payload = json.loads(result.text or "{}")
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "status_code": result.status,
                    "latency_ms": result.elapsed_ms,
                    "summary": f"{name} did not return JSON.",
                    "metadata": metadata,
                }
            return {
                "ok": True,
                "status_code": result.status,
                "latency_ms": result.elapsed_ms,
                "json": _redact_structure(payload, api_key),
                "metadata": metadata,
            }
        except Exception as exc:
            if required:
                status = "failed"
            else:
                status = "warning"
            return {
                "ok": False,
                "summary": _safe_error(exc, api_key),
                "metadata": {"status": status, "error_type": exc.__class__.__name__},
            }

    async def _run_text_item(
            self,
            name: str,
            method: str,
            url: str,
            headers: dict[str, str],
            api_key: str,
            *,
            json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = await self._request(method, url, headers=headers, json_body=json_body)
            metadata = _http_metadata(result)
            if result.status >= 400:
                return {
                    "ok": False,
                    "summary": f"{name} returned HTTP {result.status}.",
                    "metadata": metadata,
                }
            return {
                "ok": True,
                "text": _redact_text(result.text, api_key),
                "metadata": metadata,
            }
        except Exception as exc:
            return {
                "ok": False,
                "summary": _safe_error(exc, api_key),
                "metadata": {"status": "warning", "error_type": exc.__class__.__name__},
            }

    async def _request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json_body: dict[str, Any] | None = None,
    ) -> WorkerHTTPResult:
        current_url = url
        redirects = 0
        while True:
            target = normalize_worker_endpoint(current_url, allowed_ports=self.config.allowed_ports)
            addresses = resolve_public_addresses(
                target.hostname,
                port=target.port,
                resolver=self.config.resolver,
            )
            result = await self._single_request(
                method,
                target.normalized,
                headers=headers,
                json_body=json_body,
                public_url=target.public,
                resolved_address_count=len(addresses),
            )
            if result.status not in REDIRECT_STATUSES:
                return result
            if redirects >= self.config.max_redirects:
                raise WorkerRequestError("Target exceeded the redirect limit.")
            location = result.headers.get("location")
            if not location:
                raise WorkerRequestError("Target returned a redirect without a Location header.")
            current_url = urljoin(target.normalized, location)
            redirected = normalize_worker_endpoint(current_url, allowed_ports=self.config.allowed_ports)
            resolve_public_addresses(
                redirected.hostname,
                port=redirected.port,
                resolver=self.config.resolver,
            )
            redirects += 1

    async def _single_request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json_body: dict[str, Any] | None,
            public_url: str,
            resolved_address_count: int,
    ) -> WorkerHTTPResult:
        await self._ensure_session()
        request_headers = dict(headers or {})
        request_headers.setdefault("User-Agent", self.config.user_agent)
        started = time.monotonic()
        async with self._semaphore:
            response = self._session.request(
                method.upper(),
                url,
                headers=request_headers,
                json=json_body,
                allow_redirects=False,
                timeout=self.config.timeout_seconds,
            )
            response = await _maybe_await(response)
            if hasattr(response, "__aenter__"):
                async with response as entered:
                    return await self._read_result(
                        entered,
                        started=started,
                        public_url=public_url,
                        resolved_address_count=resolved_address_count,
                    )
            return await self._read_result(
                response,
                started=started,
                public_url=public_url,
                resolved_address_count=resolved_address_count,
            )

    async def _read_result(
            self,
            response: Any,
            *,
            started: float,
            public_url: str,
            resolved_address_count: int,
    ) -> WorkerHTTPResult:
        body = await _read_limited(response, max_bytes=self.config.max_response_bytes)
        status = int(getattr(response, "status", 0) or getattr(response, "status_code", 0) or 0)
        headers = _normalize_headers(getattr(response, "headers", {}) or {})
        final_url = str(getattr(response, "url", public_url) or public_url)
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        return WorkerHTTPResult(
            status=status,
            headers=headers,
            body=body,
            elapsed_ms=elapsed_ms,
            final_url=final_url,
            public_url=public_url,
            resolved_address_count=resolved_address_count,
        )

    async def _ensure_session(self) -> None:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True

    async def _close_owned_session(self) -> None:
        if self._owns_session and self._session is not None:
            close = getattr(self._session, "close", None)
            if close is not None:
                await _maybe_await(close())
            self._session = None
            self._owns_session = False

    def _openai_chat_payload(
            self,
            model: str,
            messages: list[dict[str, Any]],
            *,
            stop: list[str] | None = None,
            response_format: dict[str, Any] | None = None,
            stream: bool = False,
            tools: list[dict[str, Any]] | None = None,
            tool_choice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": min(max(int(self.config.max_tokens or 64), 1), 256),
        }
        if stop:
            payload["stop"] = stop
        if response_format:
            payload["response_format"] = response_format
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        return payload

    def _anthropic_message_payload(
            self,
            model: str,
            messages: list[dict[str, Any]],
            *,
            stop_sequences: list[str] | None = None,
            stream: bool = False,
            tools: list[dict[str, Any]] | None = None,
            tool_choice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": min(max(int(self.config.max_tokens or 64), 1), 256),
        }
        if stop_sequences:
            payload["stop_sequences"] = stop_sequences
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        return payload

    def _openai_optional_message_item(self, name: str, result: dict[str, Any], passed_summary: str) -> dict[str, Any]:
        payload = result.get("json") if result.get("ok") else {}
        ok = bool(result.get("ok") and _openai_message(payload))
        return _suite_item(
            name,
            "passed" if ok else "warning",
            passed_summary if ok else result.get("summary", f"{name} is unsupported or absent."),
            _openai_response_metadata(result, payload),
        )

    def _join(self, endpoint: WorkerEndpoint, suffix: str) -> str:
        base = endpoint.public.rstrip("/") + "/"
        return urljoin(base, suffix.lstrip("/"))

    def _build_report(
            self,
            *,
            protocol: str,
            endpoint: WorkerEndpoint | None,
            api_key: str,
            requested_model: str,
            returned_model: str,
            visibility: str,
            items: list[dict[str, Any]],
            dns_address_count: int,
    ) -> dict[str, Any]:
        scores = _score_items(items, requested_model=requested_model, returned_model=returned_model)
        evidence = {
            "protocol": protocol,
            "endpoint_public": endpoint.public if endpoint else "",
            "endpoint_hash": endpoint.url_hash if endpoint else "",
            "dns": {
                "checked": bool(endpoint),
                "public_address_count": dns_address_count,
            },
            "credential": {
                "fingerprint": fingerprint_secret(api_key),
                "mask": mask_secret(api_key),
            },
            "suite": items,
            "limitation": MODEL_REPORT_LIMITATION,
        }
        report = {
            "declared_model": requested_model,
            "returned_model": returned_model,
            "suite_version": MODEL_LAB_P0_SUITE_VERSION,
            "scores": scores,
            "grade": _grade(scores),
            "evidence_json": evidence,
            "visibility": visibility if visibility in {"private", "unlisted", "public"} else "private",
            "limitation_note": MODEL_REPORT_LIMITATION,
        }
        return _redact_structure(report, api_key)


def _suite_item(name: str, status: str, summary: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "metadata": metadata or {},
    }


def _score_items(items: list[dict[str, Any]], *, requested_model: str, returned_model: str) -> dict[str, Any]:
    counted = [item for item in items if item.get("status") != "skipped"]
    if not counted:
        observed = 0.0
    else:
        points = 0.0
        for item in counted:
            if item.get("status") == "passed":
                points += 1.0
            elif item.get("status") == "warning":
                points += 0.5
        observed = round(points / len(counted), 3)

    required_names = {"models_list", "chat_basic", "message_basic"}
    required = [item for item in items if item.get("name") in required_names]
    if required:
        protocol = round(sum(1 for item in required if item.get("status") == "passed") / len(required), 3)
    else:
        protocol = 0.0

    if requested_model and returned_model and requested_model == returned_model:
        consistency = 1.0
    elif requested_model and returned_model:
        consistency = 0.5
    elif not requested_model and returned_model:
        consistency = 0.75
    else:
        consistency = 0.0

    failures = sum(1 for item in counted if item.get("status") == "failed")
    degradation_risk = round(failures / len(counted), 3) if counted else 1.0
    return {
        "protocol_compatibility": protocol,
        "declared_model_consistency": consistency,
        "observed_behavior": observed,
        "degradation_risk": degradation_risk,
    }


def _grade(scores: dict[str, Any]) -> str:
    observed = float(scores.get("observed_behavior") or 0)
    protocol = float(scores.get("protocol_compatibility") or 0)
    consistency = float(scores.get("declared_model_consistency") or 0)
    risk = float(scores.get("degradation_risk") or 1)
    combined = (observed * 0.45) + (protocol * 0.35) + (consistency * 0.20) - (risk * 0.10)
    if combined >= 0.9:
        return "A"
    if combined >= 0.75:
        return "B"
    if combined >= 0.55:
        return "C"
    if combined >= 0.35:
        return "D"
    return "F"


def _http_metadata(result: WorkerHTTPResult) -> dict[str, Any]:
    content_type = result.headers.get("content-type", "")
    return {
        "status_code": result.status,
        "latency_ms": result.elapsed_ms,
        "content_type": content_type.split(";", 1)[0],
        "public_url": result.public_url,
        "resolved_address_count": result.resolved_address_count,
    }


def _openai_response_metadata(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(result.get("metadata") or {})
    if isinstance(payload, dict):
        usage = _numeric_usage(payload.get("usage"))
        metadata.update({
            "object": payload.get("object"),
            "model": payload.get("model"),
            "finish_reason": _openai_finish_reason(payload),
            "usage_present": bool(usage),
            "usage": usage,
        })
    return metadata


def _anthropic_response_metadata(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(result.get("metadata") or {})
    if isinstance(payload, dict):
        usage = _numeric_usage(payload.get("usage"))
        metadata.update({
            "type": payload.get("type"),
            "model": payload.get("model"),
            "stop_reason": payload.get("stop_reason"),
            "usage_present": bool(usage),
            "usage": usage,
        })
    return metadata


def _openai_message(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {}
    return message if isinstance(message, dict) else {}


def _openai_finish_reason(payload: dict[str, Any]) -> str:
    try:
        return str(payload["choices"][0].get("finish_reason") or "")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _anthropic_text_content(payload: dict[str, Any]) -> str:
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts).strip()


def _anthropic_has_tool_use(payload: dict[str, Any]) -> bool:
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        return False
    return any(isinstance(block, dict) and block.get("type") == "tool_use" for block in content)


def _usage_metadata(usage: Any) -> tuple[bool, dict[str, Any]]:
    if not isinstance(usage, dict):
        return False, {"usage_present": False}
    numeric_values = {
        key: value
        for key, value in usage.items()
        if isinstance(value, int | float)
    }
    non_negative = bool(numeric_values) and all(value >= 0 for value in numeric_values.values())
    return non_negative, {
        "usage_present": True,
        "usage_keys": sorted(usage.keys()),
        "non_negative_numeric_fields": non_negative,
    }


def _numeric_usage(usage: Any) -> dict[str, int | float]:
    if not isinstance(usage, dict):
        return {}
    return {
        str(key): value
        for key, value in usage.items()
        if isinstance(value, int | float) and value >= 0
    }


def _first_model_id(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return ""


def _is_json_object(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(parsed, dict)


def _has_openai_stream_chunk(text: str) -> bool:
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if payload.get("object") == "chat.completion.chunk" and isinstance(payload.get("choices"), list):
            return True
    return False


def _has_anthropic_stream_chunk(text: str) -> bool:
    event_seen = False
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("event:"):
            event_seen = True
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if payload.get("type") in {"message_start", "content_block_start", "content_block_delta", "message_delta", "message_stop"}:
            return True
    return event_seen


def _is_blocked_hostname(hostname: str) -> bool:
    lower = hostname.lower().strip(".")
    return lower in {"localhost", "localhost.localdomain"} or lower.endswith(".localhost")


def _is_blocked_ip(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    try:
        _ensure_public_ip(ip)
    except UnsafeWorkerTarget:
        return True
    return False


def _ensure_public_ip(ip: ipaddress._BaseAddress) -> None:
    if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
    ):
        raise UnsafeWorkerTarget("Target resolved to a non-public address.")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _read_limited(response: Any, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    content = getattr(response, "content", None)
    if content is not None and hasattr(content, "iter_chunked"):
        async for chunk in content.iter_chunked(8192):
            data = _to_bytes(chunk)
            total += len(data)
            if total > max_bytes:
                raise WorkerRequestError("Target response exceeded the size limit.")
            chunks.append(data)
        return b"".join(chunks)

    read = getattr(response, "read", None)
    if read is None:
        return b""
    data = _to_bytes(await _maybe_await(read()))
    if len(data) > max_bytes:
        raise WorkerRequestError("Target response exceeded the size limit.")
    return data


def _to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value or b"")


def _normalize_headers(headers: Any) -> dict[str, str]:
    if hasattr(headers, "items"):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    return {}


def _safe_error(exc: Exception, secret: str = "") -> str:
    text = f"{exc.__class__.__name__}: {exc}"
    return _redact_text(text, secret)[:240]


def _redact_structure(value: Any, secret: str = "") -> Any:
    if isinstance(value, dict):
        return {key: _redact_structure(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_structure(item, secret) for item in value]
    if isinstance(value, str):
        return _redact_text(value, secret)
    return value


def _redact_text(value: str, secret: str = "") -> str:
    text = str(value or "")
    if secret:
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    if "..." not in text:
        text = re.sub(r"sk-[A-Za-z0-9._~+/=-]{6,}", "sk-[redacted]", text)
    text = re.sub(r"(?i)(api[_-]?key|access_token|token|secret|password)=([^&\s]+)", r"\1=[redacted]", text)
    return text
