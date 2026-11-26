"""Minimal MCP stdio client used by the end-to-end tests.

Speaks newline-delimited JSON-RPC 2.0 directly instead of importing the SDK
client, so the test proves protocol compliance rather than re-using the same
abstractions the server is built on.
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT = 45.0


class StdioServer:
    """A running ``python -m <module>`` server, driven over stdin/stdout."""

    def __init__(self, module: str = "mcp_steam_price", env: dict[str, str] | None = None):
        environment = os.environ.copy()
        src = str(ROOT / "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            [src, environment.get("PYTHONPATH", "")].copy()
        ).strip(os.pathsep)
        environment["MCP_TRANSPORT"] = "stdio"
        environment.pop("MCP_LOCALE", None)
        environment.update(env or {})

        self.module = module
        self._proc = subprocess.Popen(
            [sys.executable, "-m", module],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
        )
        self._messages: queue.Queue[str] = queue.Queue()
        self._stderr: list[str] = []
        self._ids = itertools.count(1)
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    # ------------------------------------------------------------- plumbing
    def _pump_stdout(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if line:
                self._messages.put(line)

    def _pump_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr.append(line)

    def _write(self, payload: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

    def _await(self, want_id: int, timeout: float) -> dict:
        while True:
            try:
                raw = self._messages.get(timeout=timeout)
            except queue.Empty:
                raise AssertionError(
                    f"no reply to request {want_id} within {timeout}s; "
                    f"stderr tail: {''.join(self._stderr)[-1500:]}"
                )
            message = json.loads(raw)
            if message.get("id") == want_id:
                return message

    # ------------------------------------------------------------------ API
    def request(self, method: str, params: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        request_id = next(self._ids)
        payload: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)
        return self._await(request_id, timeout)

    def notify(self, method: str, params: dict | None = None) -> None:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)

    def initialize(self) -> dict:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0.0"},
            },
        )
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        return self.request("tools/list", {})["result"]["tools"]

    def call_tool(self, name: str, arguments: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        response = self.request(
            "tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout
        )
        assert "result" in response, f"tools/call failed: {response}"
        return response["result"]

    def payload(self, name: str, arguments: dict | None = None) -> dict:
        """Call a tool and decode the JSON body the model would receive."""
        result = self.call_tool(name, arguments)
        if result.get("structuredContent"):
            return result["structuredContent"]
        return json.loads(result["content"][0]["text"])

    # --------------------------------------------------------------- teardown
    def close(self) -> None:
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self._proc.kill()

    def __enter__(self) -> "StdioServer":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
