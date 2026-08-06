"""Real Redis launcher shared by recommendation api_integration suites."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import pytest
from redis import Redis


@pytest.fixture()
def real_redis():
    binary = shutil.which("redis-server")
    if not binary:
        pytest.fail("redis-server is required for recommendation api_integration")
    with tempfile.TemporaryDirectory(prefix="qwq-rec-redis-", dir="/tmp") as runtime_dir:
        socket_path = Path(runtime_dir) / "redis.sock"
        process = subprocess.Popen(
            [
                binary,
                "--port",
                "0",
                "--unixsocket",
                str(socket_path),
                "--unixsocketperm",
                "700",
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        client = Redis(unix_socket_path=str(socket_path), decode_responses=False)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    pytest.fail(f"redis-server exited before becoming ready: {output}")
                try:
                    if client.ping():
                        break
                except Exception:
                    time.sleep(0.02)
            else:
                pytest.fail("redis-server did not become ready")
            yield client
        finally:
            try:
                client.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
