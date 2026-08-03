from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

import pytest
from pymongo import MongoClient


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def mongo_client():
    configured = (os.getenv("QWQ_TEST_MONGO_URI") or os.getenv("TEST_MONGO_URI") or "").strip()
    process: subprocess.Popen[bytes] | None = None
    runtime_root: str | None = None
    if configured:
        client = MongoClient(configured, serverSelectionTimeoutMS=10_000, tz_aware=True)
        client.admin.command("ping")
    else:
        executable = shutil.which("mongod")
        if executable is None:
            pytest.fail("recommendation api_integration requires TEST_MONGO_URI or mongod")
        port = _free_port()
        runtime_root = tempfile.mkdtemp(prefix="qwq-recommendation-mongo-")
        process = subprocess.Popen(
            [
                executable,
                "--dbpath",
                runtime_root,
                "--port",
                str(port),
                "--bind_ip",
                "127.0.0.1",
                "--replSet",
                "qwqtest",
                "--oplogSize",
                "64",
                "--quiet",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        direct = MongoClient(
            f"mongodb://127.0.0.1:{port}/?directConnection=true",
            serverSelectionTimeoutMS=500,
        )
        deadline = time.monotonic() + 20
        while True:
            try:
                direct.admin.command("ping")
                break
            except Exception:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("temporary MongoDB did not start")
                time.sleep(0.1)
        direct.admin.command(
            {
                "replSetInitiate": {
                    "_id": "qwqtest",
                    "members": [{"_id": 0, "host": f"127.0.0.1:{port}"}],
                }
            }
        )
        direct.close()
        client = MongoClient(
            f"mongodb://127.0.0.1:{port}/?replicaSet=qwqtest",
            serverSelectionTimeoutMS=500,
            tz_aware=True,
        )
        deadline = time.monotonic() + 20
        while True:
            try:
                if client.admin.command("hello").get("isWritablePrimary"):
                    break
            except Exception:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("temporary MongoDB replica set did not become primary")
            time.sleep(0.1)
    try:
        yield client
    finally:
        client.close()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if runtime_root is not None:
            shutil.rmtree(Path(runtime_root), ignore_errors=True)


@pytest.fixture
def mongo_database(mongo_client):
    name = f"qwq_recommendation_test_{uuid.uuid4().hex}"
    database = mongo_client[name]
    try:
        yield database
    finally:
        mongo_client.drop_database(name)
