"""Launcher-owned platform transport for DEC-008 external UAT relay.

传输只搬运内存帧。terminal ref、secret、query、snapshot 都不写 argv/env/file/log。
"""
from __future__ import annotations

import json
import os
import re
import socket
import struct
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[Any]]
_SOCKET_NAME = re.compile(r"[A-Za-z0-9._-]{1,96}")


def _command(command: Sequence[str], *, runner: Runner) -> subprocess.CompletedProcess[Any]:
    try:
        return runner(list(command), capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise ConnectionError("APP.UAT.relay_process_died: platform command failed") from error


def _exchange(path: str, frame: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
    encoded = json.dumps(frame, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(encoded) > 64 * 1024:
        raise ValueError("APP.UAT.relay_contract_drift: relay frame exceeds bound")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout_seconds)
        client.connect("\0" + path.removeprefix("localabstract:") if path.startswith("localabstract:") else path)
        if sys.platform == 'darwin' and not path.startswith('localabstract:'):
            name = Path(path).name
            matched = re.fullmatch(r'gwt008-([1-9][0-9]*)-[a-z0-9-]+\.sock', name)
            if matched:
                peer_pid = struct.unpack('i', client.getsockopt(0, 2, 4))[0]  # SOL_LOCAL / LOCAL_PEERPID
                peer_token = struct.unpack('8I', client.getsockopt(0, 6, 32))  # LOCAL_PEERTOKEN
                if peer_pid != int(matched[1]) or peer_token[5] != peer_pid or peer_token[1] != os.geteuid():
                    raise ConnectionError('APP.UAT.relay_peer_rejected: server process identity mismatch')
        client.sendall(encoded)
        chunks, length = [], 0
        while True:
            chunk = client.recv(8192)
            if not chunk:
                raise EOFError("relay disconnected before terminal frame")
            chunks.append(chunk); length += len(chunk)
            if length > 256 * 1024:
                raise ValueError("APP.UAT.relay_contract_drift: broker result exceeds bound")
            if b"\n" in chunk:
                break
    raw = b"".join(chunks)
    line, remainder = raw.split(b"\n", 1)
    if remainder:
        raise ValueError("APP.UAT.relay_contract_drift: broker emitted multiple frames")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("APP.UAT.relay_contract_drift: broker result is not an object")
    return value


@dataclass
class AndroidAdbForwardRelayTransport:
    adb: str
    device_id: str
    local_socket: str
    package_socket: str
    runner: Runner = subprocess.run
    exchange: Callable[[str, Mapping[str, Any], float], Mapping[str, Any]] = _exchange
    runtime_verified: bool = True
    _owned: bool = False
    disconnected: bool = False

    def __post_init__(self) -> None:
        if not _SOCKET_NAME.fullmatch(self.package_socket) or not self.local_socket.startswith("localabstract:"):
            raise ValueError("APP.UAT.relay_scope_mismatch: invalid Android attempt socket")

    def arm(self, admission: Mapping[str, Any], verifier: bytes) -> None:
        if self._owned:
            raise ValueError("APP.UAT.relay_stale: Android forward already owned")
        result = _command([self.adb, "-s", self.device_id, "forward", self.local_socket,
                           "localabstract:" + self.package_socket], runner=self.runner)
        if result.returncode != 0:
            raise ConnectionError("APP.UAT.relay_process_died: adb forward failed")
        self._owned = True
        self._arm = {"operation": "armRelay", "admission": dict(admission), "verifier": verifier.hex()}

    def query(self, frame: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]:
        if not self._owned:
            raise ConnectionError("APP.UAT.relay_peer_rejected: Android forward is not owned")
        self.exchange(self.local_socket, self._arm, timeout_seconds)
        return self.exchange(self.local_socket, frame, timeout_seconds)

    def close(self) -> None:
        self._arm = {}
        if self._owned:
            result = _command([self.adb, "-s", self.device_id, "forward", "--remove", self.local_socket], runner=self.runner)
            self._owned = False
            if result.returncode != 0:
                raise OSError("APP.UAT.relay_revoked: adb forward cleanup failed")
        self.disconnected = True

    def peer_absent(self) -> bool:
        result = _command(
            [self.adb, "-s", self.device_id, "shell", "cat", "/proc/net/unix"],
            runner=self.runner,
        )
        if result.returncode != 0:
            raise ConnectionError("APP.UAT.teardown_pid_alive: Android unix table unreadable")
        return self.package_socket not in str(result.stdout or "")


@dataclass
class IosSimulatorAppGroupRelayTransport:
    device_id: str
    app_group_id: str
    socket_name: str
    runner: Runner = subprocess.run
    exchange: Callable[[str, Mapping[str, Any], float], Mapping[str, Any]] = _exchange
    runtime_verified: bool = True
    _socket_path: str = ""
    _arm_started: bool = False
    _queried: bool = False
    disconnected: bool = False

    def __post_init__(self) -> None:
        if not self.app_group_id.startswith("group.") or not _SOCKET_NAME.fullmatch(self.socket_name):
            raise ValueError("APP.UAT.relay_scope_mismatch: invalid iOS App Group socket identity")

    def arm(self, admission: Mapping[str, Any], verifier: bytes) -> None:
        if self._arm_started or self.disconnected:
            raise ValueError("APP.UAT.relay_stale: iOS admission is create-once")
        self._arm_started = True
        result = _command(["xcrun", "simctl", "get_app_container", self.device_id,
                           self.app_group_id, "group"], runner=self.runner)
        root = Path(str(result.stdout or "").strip())
        if result.returncode != 0 or not root.is_absolute() or root.is_symlink():
            raise ConnectionError("APP.UAT.relay_peer_rejected: App Group container unavailable")
        path = root / self.socket_name
        if path.parent != root or not path.exists() or not path.is_socket():
            raise ConnectionError("APP.UAT.relay_peer_rejected: exact App Group socket unavailable")
        if path.is_symlink() or path.resolve() != path:
            raise ConnectionError("APP.UAT.relay_peer_rejected: linked App Group socket")
        acknowledgement = self.exchange(os.fspath(path),
            {"operation": "armRelay", "admission": dict(admission), "verifier": verifier.hex()}, 10)
        if acknowledgement != {}:
            raise ValueError("APP.UAT.relay_admission_mismatch: native arm acknowledgement rejected")
        self._socket_path = os.fspath(path)

    def query(self, frame: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]:
        if self._queried:
            raise ValueError("APP.UAT.relay_consumed: iOS query is single-use")
        if not self._socket_path:
            raise ConnectionError("APP.UAT.relay_peer_rejected: iOS relay is not armed")
        self._queried = True
        return self.exchange(self._socket_path, frame, timeout_seconds)

    def close(self) -> None:
        self._socket_path = ""; self.disconnected = True

    def peer_absent(self) -> bool:
        result = _command(["xcrun", "simctl", "get_app_container", self.device_id,
                           self.app_group_id, "group"], runner=self.runner)
        root = Path(str(result.stdout or "").strip())
        if result.returncode != 0 or not root.is_absolute():
            raise ConnectionError("APP.UAT.teardown_pid_alive: App Group container unreadable")
        path = root / self.socket_name
        if path.parent != root:
            raise ConnectionError("APP.UAT.relay_peer_rejected: socket escaped container")
        if not path.exists() or not path.is_socket():
            return True
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect(os.fspath(path))
        except OSError:
            return True
        return False
