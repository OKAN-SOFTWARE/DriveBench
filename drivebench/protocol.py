"""Correlated JSON-line requests over a bounded TCP session."""
from __future__ import annotations
import json
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Callable


class ClientError(Exception):
    pass


class TransportTimeout(ClientError):
    pass


class ConnectionLost(ClientError):
    pass


class ProtocolError(ClientError):
    pass


class RemoteError(ClientError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def strict_json(text: str):
    def reject(value):
        raise ValueError(f"Nonstandard JSON constant: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject, object_pairs_hook=unique)


class DiagnosticClient:
    def __init__(self, host: str, port: int, timeout: float = 0.8, trace: Callable | None = None):
        self.host, self.port, self.timeout, self.trace = host, port, timeout, trace
        self._socket = None
        self._buffer = bytearray()

    def connect(self):
        if self._socket is not None:
            return
        try:
            self._socket = socket.create_connection((self.host, self.port), self.timeout)
            self._socket.settimeout(self.timeout)
        except TimeoutError as exc:
            self.close()
            raise TransportTimeout("TCP connection timed out") from exc
        except OSError as exc:
            self.close()
            raise ConnectionLost("Cannot connect to simulator") from exc

    def close(self):
        if self._socket:
            self._socket.close()
        self._socket = None
        self._buffer.clear()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def _event(self, direction, request_id, payload, elapsed=None):
        if self.trace:
            self.trace({"at": utc_now(), "direction": direction, "request_id": request_id,
                        "payload": payload, "duration_ms": elapsed})

    def request(self, command: str, **fields) -> dict:
        if "id" in fields or "command" in fields:
            raise ProtocolError("Reserved envelope fields cannot be overridden")
        request_id = uuid.uuid4().hex
        request = {"id": request_id, "command": command, **fields}
        encoded = (json.dumps(request, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > 8192:
            raise ProtocolError("Request exceeds 8192-byte frame limit")
        started = time.perf_counter()
        self._event("TX", request_id, request)
        try:
            self.connect()
            self._socket.sendall(encoded)
            deadline = time.monotonic() + self.timeout
            while b"\n" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                self._socket.settimeout(remaining)
                chunk = self._socket.recv(4096)
                if not chunk:
                    raise ConnectionLost("Simulator closed the TCP connection")
                self._buffer.extend(chunk)
                if len(self._buffer) > 65536:
                    raise ProtocolError("Response exceeds 64 KiB")
            frame, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            response = strict_json(frame.decode("utf-8"))
            if not isinstance(response, dict) or response.get("id") != request_id or type(response.get("ok")) is not bool:
                raise ProtocolError("Response correlation ID or envelope is invalid")
            self._event("RX", request_id, response, round((time.perf_counter() - started) * 1000, 3))
            if not response["ok"]:
                error = response.get("error")
                if not isinstance(error, dict) or not isinstance(error.get("code"), str):
                    raise ProtocolError("Malformed remote error")
                raise RemoteError(error["code"], str(error.get("message", "Remote command failed")))
            if not isinstance(response.get("data"), dict):
                raise ProtocolError("Response data must be an object")
            self._socket.settimeout(self.timeout)
            return response["data"]
        except (TimeoutError, socket.timeout, TransportTimeout) as exc:
            self.close()
            self._event("ERROR", request_id, {"type": "TransportTimeout", "message": "Request timed out"})
            raise TransportTimeout("Simulator response timed out; session closed") from exc
        except RemoteError:
            raise  # A well-framed remote rejection leaves the connection usable.
        except (OSError, ConnectionLost) as exc:
            self.close()
            self._event("ERROR", request_id, {"type": "ConnectionLost", "message": str(exc)})
            if isinstance(exc, ConnectionLost):
                raise
            raise ConnectionLost("TCP connection failed; session closed") from exc
        except (ValueError, UnicodeError, ProtocolError) as exc:
            self.close()
            self._event("ERROR", request_id, {"type": "ProtocolError", "message": str(exc)})
            raise ProtocolError(str(exc)) from exc
