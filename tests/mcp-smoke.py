"""Test only Terraform MCP initialization and discovery; never call a tool.

Protocol: https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
Run on Linux: python3 tests/mcp-smoke.py /path/to/generated/.mcp.json
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


def smoke(config, timeout=15):
    server = json.loads(Path(config).read_text())["mcpServers"]["terraform"]

    def expired(signum, frame):
        raise TimeoutError("Terraform MCP handshake exceeded its deadline")

    with tempfile.TemporaryDirectory(prefix="mcp-smoke-") as scratch:
        # No inherited credentials or user config; discovery needs neither.
        with subprocess.Popen(
            [server["command"], *server["args"]],
            env={"PATH": os.environ["PATH"], "HOME": scratch, "TMPDIR": scratch, "TFE_TOKEN": ""},
            cwd=scratch,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        ) as child:
            def send(message):
                child.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
                child.stdin.flush()

            def result(request_id):
                while True:
                    line = child.stdout.readline()
                    assert line, "MCP server exited before responding"
                    response = json.loads(line)
                    assert response.get("jsonrpc") == "2.0", "invalid JSON-RPC version"
                    assert "error" not in response, "MCP server returned a protocol error"
                    if "id" not in response:  # Notifications can precede the response.
                        assert "method" in response, "invalid MCP notification"
                        continue
                    assert response["id"] == request_id, "unexpected response ID"
                    return response["result"]

            previous = signal.signal(signal.SIGALRM, expired)
            try:
                signal.alarm(timeout)
                send({"id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "cloud-templates-smoke", "version": "1"},
                }})
                initialized = result(1)
                assert initialized["protocolVersion"] == "2025-06-18", "unsupported protocol version"
                assert "tools" in initialized["capabilities"], "server lacks tool discovery"
                send({"method": "notifications/initialized"})
                send({"id": 2, "method": "tools/list", "params": {}})
                tools = result(2)["tools"]
                assert isinstance(tools, list) and tools, "server returned no tools"
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous)
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    print("Terraform MCP handshake passed (no tools invoked)")


if __name__ == "__main__":
    smoke(sys.argv[1])
