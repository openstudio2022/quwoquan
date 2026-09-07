"""Real Redis launcher shared by recommendation api_integration suites."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

import os

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

_REDIS_IMAGE = "redis:7.2-alpine"


def _docker(*arguments: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_for_redis(client_factory, *, label: str, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = None
        try:
            client = client_factory()
            if client.ping():
                return client
        except Exception as error:
            last_error = error
            if client is not None:
                client.close()
            time.sleep(0.05)
    raise RuntimeError(f"{label} did not become ready: {last_error}")


def _docker_host_port(container_name: str) -> int:
    output = _docker("port", container_name, "6379/tcp").stdout.strip()
    return int(output.rsplit(":", 1)[1])


class _RealRedisCluster:
    def __init__(
        self,
        *,
        client,
        direct,
        startup_port: int,
        close_runtime,
    ) -> None:
        self.client = client
        self.direct = direct
        self._startup_port = startup_port
        self._close_runtime = close_runtime
        self._closed = False

    def raw_eval_error(self, script: str, keys: tuple[str, ...]) -> bytes:
        arguments = [b"EVAL", script.encode("utf-8"), str(len(keys)).encode("ascii")]
        arguments.extend(key.encode("utf-8") for key in keys)
        request = f"*{len(arguments)}\r\n".encode("ascii") + b"".join(
            f"${len(argument)}\r\n".encode("ascii") + argument + b"\r\n"
            for argument in arguments
        )
        with socket.create_connection(
            ("127.0.0.1", self._startup_port),
            timeout=5,
        ) as connection:
            connection.sendall(request)
            return connection.makefile("rb").readline().rstrip(b"\r\n")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            try:
                self.client.close()
            finally:
                self.direct.close()
        finally:
            self._close_runtime()


class _RedisClusterFixtureDependencyError(RuntimeError):
    pass


def _cleanup_docker_cluster(
    *,
    containers: tuple[str, ...],
    volumes: tuple[str, ...],
    network: str,
) -> None:
    for container in containers:
        subprocess.run(
            ["docker", "rm", "-f", container],
            check=False,
            capture_output=True,
            text=True,
        )
    for volume in volumes:
        subprocess.run(
            ["docker", "volume", "rm", "-f", volume],
            check=False,
            capture_output=True,
            text=True,
        )
    subprocess.run(
        ["docker", "network", "rm", network],
        check=False,
        capture_output=True,
        text=True,
    )


def _start_docker_redis_cluster():
    from redis.cluster import RedisCluster

    identity = uuid.uuid4().hex[:12]
    network = f"qwq-rec-cluster-{identity}"
    containers = tuple(f"{network}-node-{index}" for index in range(1, 4))
    volumes = tuple(f"{container}-data" for container in containers)
    directs = []
    client = None
    try:
        _docker("network", "create", network)
        for container, volume in zip(containers, volumes, strict=True):
            _docker("volume", "create", volume)
            _docker(
                "run",
                "-d",
                "--name",
                container,
                "--network",
                network,
                "-p",
                "127.0.0.1::6379",
                "-v",
                f"{volume}:/data",
                _REDIS_IMAGE,
                "redis-server",
                "--cluster-enabled",
                "yes",
                "--cluster-config-file",
                "nodes.conf",
                "--cluster-node-timeout",
                "5000",
                "--appendonly",
                "no",
                "--save",
                "",
                "--protected-mode",
                "no",
            )
        ports = tuple(_docker_host_port(container) for container in containers)
        node_ips = tuple(
            json.loads(_docker("inspect", container).stdout)[0]["NetworkSettings"][
                "Networks"
            ][network]["IPAddress"]
            for container in containers
        )
        for container, port in zip(containers, ports, strict=True):
            directs.append(
                _wait_for_redis(
                    lambda port=port: Redis(
                        host="127.0.0.1",
                        port=port,
                        decode_responses=False,
                    ),
                    label=f"Redis Cluster node {container}",
                )
            )
        for peer_ip in node_ips[1:]:
            directs[0].execute_command("CLUSTER", "MEET", peer_ip, 6379)
        topology_deadline = time.monotonic() + 30
        while time.monotonic() < topology_deadline:
            if all(
                int(
                    direct.execute_command("CLUSTER", "INFO")
                    .split(b"cluster_known_nodes:", 1)[1]
                    .splitlines()[0]
                )
                == 3
                for direct in directs
            ):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError(
                "Redis Cluster nodes did not discover the three-node topology"
            )
        slot_ranges = ((0, 5460), (5461, 10922), (10923, 16383))
        for slot_owner, (slot_start, slot_end) in enumerate(slot_ranges):
            directs[slot_owner].execute_command(
                "CLUSTER",
                "ADDSLOTSRANGE",
                slot_start,
                slot_end,
            )
        deadline = time.monotonic() + 30
        info = b""
        while time.monotonic() < deadline:
            info = directs[0].execute_command("CLUSTER", "INFO")
            if b"cluster_state:ok" in info:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError(f"Redis Cluster did not become healthy: {info!r}")
        for direct in directs[1:]:
            direct.close()
        host_ports = dict(zip(node_ips, ports, strict=True))
        client = RedisCluster(
            host="127.0.0.1",
            port=ports[0],
            decode_responses=False,
            require_full_coverage=True,
            address_remap=lambda address: (
                "127.0.0.1",
                host_ports[address[0]],
            ),
        )
        if not client.ping():
            raise RuntimeError("Docker Redis Cluster did not answer PING")
        return _RealRedisCluster(
            client=client,
            direct=directs[0],
            startup_port=ports[0],
            close_runtime=lambda: _cleanup_docker_cluster(
                containers=containers,
                volumes=volumes,
                network=network,
            ),
        )
    except BaseException:
        if client is not None:
            client.close()
        for direct in directs:
            direct.close()
        _cleanup_docker_cluster(
            containers=containers,
            volumes=volumes,
            network=network,
        )
        raise


def _reserve_native_cluster_ports(
    node_count: int,
) -> tuple[tuple[int, socket.socket, socket.socket], ...]:
    reservations: list[tuple[int, socket.socket, socket.socket]] = []
    try:
        while len(reservations) < node_count:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                server_socket.bind(("127.0.0.1", 0))
                server_socket.listen()
                server_port = int(server_socket.getsockname()[1])
                if server_port > 55535:
                    continue
                cluster_bus_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    cluster_bus_socket.bind(("127.0.0.1", server_port + 10000))
                    cluster_bus_socket.listen()
                except OSError:
                    cluster_bus_socket.close()
                    continue
                reservations.append((server_port, server_socket, cluster_bus_socket))
                server_socket = None
            finally:
                if server_socket is not None:
                    server_socket.close()
        return tuple(reservations)
    except BaseException:
        for _, server_socket, cluster_bus_socket in reservations:
            server_socket.close()
            cluster_bus_socket.close()
        raise


def _native_redis_log(log_path: Path) -> str:
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return f"unable to read log: {error}"
    return output[-4000:]


def _wait_for_native_redis(
    *,
    process: subprocess.Popen[bytes],
    port: int,
    log_path: Path,
    timeout: float = 30.0,
):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"native Redis node on port {port} exited before becoming ready: "
                f"{_native_redis_log(log_path)}"
            )
        client = Redis(host="127.0.0.1", port=port, decode_responses=False)
        try:
            if client.ping():
                return client
        except Exception as error:
            last_error = error
        client.close()
        time.sleep(0.05)
    raise RuntimeError(
        f"native Redis node on port {port} did not become ready: {last_error}; "
        f"log={_native_redis_log(log_path)}"
    )


def _stop_native_redis_processes(
    processes: tuple[subprocess.Popen[bytes], ...],
) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
    for process in processes:
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)


def _cleanup_native_redis_cluster(
    *,
    processes: tuple[subprocess.Popen[bytes], ...],
    runtime_root: Path,
) -> None:
    try:
        _stop_native_redis_processes(processes)
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def _start_native_redis_cluster():
    from redis.cluster import RedisCluster

    redis_server = shutil.which("redis-server")
    redis_cli = shutil.which("redis-cli")
    missing = tuple(
        binary
        for binary, location in (
            ("redis-server", redis_server),
            ("redis-cli", redis_cli),
        )
        if location is None
    )
    if missing:
        raise _RedisClusterFixtureDependencyError(
            f"native Redis Cluster requires binaries: missing={','.join(missing)}"
        )
    assert redis_server is not None
    assert redis_cli is not None

    runtime_root = Path(tempfile.mkdtemp(prefix="qwq-rec-redis-cluster-", dir="/tmp"))
    reservations: tuple[tuple[int, socket.socket, socket.socket], ...] = ()
    processes: list[subprocess.Popen[bytes]] = []
    directs = []
    client = None
    try:
        reservations = _reserve_native_cluster_ports(3)
        ports = tuple(port for port, _, _ in reservations)
        for index, (port, server_socket, cluster_bus_socket) in enumerate(
            reservations,
            start=1,
        ):
            node_root = runtime_root / f"node-{index}"
            node_root.mkdir()
            log_path = node_root / "redis.log"
            server_socket.close()
            cluster_bus_socket.close()
            with log_path.open("wb") as log_file:
                process = subprocess.Popen(
                    [
                        redis_server,
                        "--bind",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--dir",
                        str(node_root),
                        "--dbfilename",
                        "dump.rdb",
                        "--cluster-enabled",
                        "yes",
                        "--cluster-config-file",
                        "nodes.conf",
                        "--cluster-node-timeout",
                        "5000",
                        "--cluster-announce-ip",
                        "127.0.0.1",
                        "--cluster-announce-port",
                        str(port),
                        "--cluster-announce-bus-port",
                        str(port + 10000),
                        "--appendonly",
                        "no",
                        "--save",
                        "",
                        "--protected-mode",
                        "no",
                    ],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
            processes.append(process)
            directs.append(
                _wait_for_native_redis(
                    process=process,
                    port=port,
                    log_path=log_path,
                )
            )

        cluster_create = subprocess.run(
            [
                redis_cli,
                "--cluster",
                "create",
                *(f"127.0.0.1:{port}" for port in ports),
                "--cluster-replicas",
                "0",
                "--cluster-yes",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if cluster_create.returncode != 0:
            raise RuntimeError(
                "redis-cli cluster creation failed: "
                f"stdout={cluster_create.stdout!r} stderr={cluster_create.stderr!r}"
            )

        deadline = time.monotonic() + 30
        info = b""
        while time.monotonic() < deadline:
            info = directs[0].execute_command("CLUSTER", "INFO")
            if b"cluster_state:ok" in info:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError(
                f"native Redis Cluster did not become healthy: {info!r}"
            )
        for direct in directs[1:]:
            direct.close()
        client = RedisCluster(
            host="127.0.0.1",
            port=ports[0],
            decode_responses=False,
            require_full_coverage=True,
        )
        if not client.ping():
            raise RuntimeError("native Redis Cluster did not answer PING")
        owned_processes = tuple(processes)
        return _RealRedisCluster(
            client=client,
            direct=directs[0],
            startup_port=ports[0],
            close_runtime=lambda: _cleanup_native_redis_cluster(
                processes=owned_processes,
                runtime_root=runtime_root,
            ),
        )
    except BaseException:
        if client is not None:
            client.close()
        for direct in directs:
            direct.close()
        _cleanup_native_redis_cluster(
            processes=tuple(processes),
            runtime_root=runtime_root,
        )
        raise
    finally:
        for _, server_socket, cluster_bus_socket in reservations:
            server_socket.close()
            cluster_bus_socket.close()


def _describe_fixture_error(error: BaseException) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        detail = error.stderr or error.stdout or str(error)
    else:
        detail = str(error)
    return f"{type(error).__name__}: {detail.strip()}"


@pytest.fixture()
def real_redis_cluster():
    docker_error: BaseException
    if os.getenv("TESTINFRA_DISABLE_CONTAINERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        docker_error = RuntimeError("containers disabled by TESTINFRA_DISABLE_CONTAINERS")
    elif shutil.which("docker") is None:
        docker_error = FileNotFoundError("docker binary was not found")
    else:
        try:
            runtime = _start_docker_redis_cluster()
        except Exception as error:
            docker_error = error
        else:
            try:
                yield runtime
            finally:
                runtime.close()
            return

    try:
        runtime = _start_native_redis_cluster()
    except _RedisClusterFixtureDependencyError as error:
        pytest.fail(
            "FIXTURE_DEPENDENCY_MISSING[real_redis_cluster]: "
            f"docker setup failed ({_describe_fixture_error(docker_error)}); "
            f"native fallback unavailable ({error})",
            pytrace=False,
        )
    except Exception as error:
        pytest.fail(
            "FIXTURE_SETUP_FAILED[real_redis_cluster]: "
            f"docker setup failed ({_describe_fixture_error(docker_error)}); "
            f"native fallback failed ({_describe_fixture_error(error)})",
            pytrace=False,
        )

    try:
        yield runtime
    finally:
        runtime.close()

class _DockerDurableRedis:
    def __init__(self, *, container: str, volume: str, port: int, client: Redis) -> None:
        self._container = container
        self._volume = volume
        self._port = port
        self._closed = False
        self.client = client

    def restart_after_sigkill(self) -> tuple[str, str]:
        container_id_before = _docker(
            "inspect", "--format", "{{.Id}}", self._container
        ).stdout.strip()
        self.client.close()
        _docker("kill", "--signal", "KILL", self._container)
        _docker("rm", self._container)
        _docker(
            "run",
            "-d",
            "--name",
            self._container,
            "-p",
            f"127.0.0.1:{self._port}:6379",
            "-v",
            f"{self._volume}:/data",
            _REDIS_IMAGE,
            "redis-server",
            "--appendonly",
            "yes",
            "--appendfsync",
            "always",
            "--save",
            "",
            "--protected-mode",
            "no",
        )
        self.client = _wait_for_redis(
            lambda: Redis(host="127.0.0.1", port=self._port, decode_responses=False),
            label="durable Redis after SIGKILL",
        )
        container_id_after = _docker(
            "inspect", "--format", "{{.Id}}", self._container
        ).stdout.strip()
        return container_id_before, container_id_after

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.client.close()
        subprocess.run(
            ["docker", "rm", "-f", self._container],
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["docker", "volume", "rm", "-f", self._volume],
            check=False,
            capture_output=True,
            text=True,
        )


class _NativeDurableRedis:
    def __init__(self, *, binary: str, runtime_root: Path, port: int) -> None:
        self._binary = binary
        self._runtime_root = runtime_root
        self._port = port
        self._log_path = runtime_root / "redis.log"
        self._closed = False
        self._process, self.client = self._start()

    def _start(self) -> tuple[subprocess.Popen[bytes], Redis]:
        with self._log_path.open("ab") as log_file:
            process = subprocess.Popen(
                [
                    self._binary,
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(self._port),
                    "--dir",
                    str(self._runtime_root),
                    "--dbfilename",
                    "dump.rdb",
                    "--appendonly",
                    "yes",
                    "--appendfsync",
                    "always",
                    "--save",
                    "",
                    "--protected-mode",
                    "no",
                ],
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        client = _wait_for_native_redis(
            process=process,
            port=self._port,
            log_path=self._log_path,
        )
        return process, client

    def restart_after_sigkill(self) -> tuple[str, str]:
        process_id_before = f"native-pid:{self._process.pid}"
        self.client.close()
        self._process.kill()
        self._process.wait(timeout=5)
        self._process, self.client = self._start()
        return process_id_before, f"native-pid:{self._process.pid}"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.client.close()
        finally:
            try:
                _stop_native_redis_processes((self._process,))
            finally:
                shutil.rmtree(self._runtime_root, ignore_errors=True)


def _start_docker_durable_redis() -> _DockerDurableRedis:
    identity = uuid.uuid4().hex[:12]
    container = f"qwq-rec-durable-{identity}"
    volume = f"{container}-data"
    try:
        _docker("volume", "create", volume)
        _docker(
            "run",
            "-d",
            "--name",
            container,
            "-p",
            "127.0.0.1::6379",
            "-v",
            f"{volume}:/data",
            _REDIS_IMAGE,
            "redis-server",
            "--appendonly",
            "yes",
            "--appendfsync",
            "always",
            "--save",
            "",
            "--protected-mode",
            "no",
        )
        port = _docker_host_port(container)
        client = _wait_for_redis(
            lambda: Redis(host="127.0.0.1", port=port, decode_responses=False),
            label="durable Redis",
        )
        return _DockerDurableRedis(
            container=container,
            volume=volume,
            port=port,
            client=client,
        )
    except BaseException:
        subprocess.run(
            ["docker", "rm", "-f", container],
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["docker", "volume", "rm", "-f", volume],
            check=False,
            capture_output=True,
            text=True,
        )
        raise


def _start_native_durable_redis() -> _NativeDurableRedis:
    binary = shutil.which("redis-server")
    if binary is None:
        raise _RedisClusterFixtureDependencyError(
            "native durable Redis requires redis-server"
        )
    runtime_root = Path(tempfile.mkdtemp(prefix="qwq-rec-durable-redis-", dir="/tmp"))
    reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reservation.bind(("127.0.0.1", 0))
        port = int(reservation.getsockname()[1])
    finally:
        reservation.close()
    try:
        return _NativeDurableRedis(
            binary=binary,
            runtime_root=runtime_root,
            port=port,
        )
    except BaseException:
        shutil.rmtree(runtime_root, ignore_errors=True)
        raise


@pytest.fixture()
def durable_redis():
    docker_error: BaseException
    if os.getenv("TESTINFRA_DISABLE_CONTAINERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        docker_error = RuntimeError("containers disabled by TESTINFRA_DISABLE_CONTAINERS")
    elif shutil.which("docker") is None:
        docker_error = FileNotFoundError("docker binary was not found")
    else:
        try:
            runtime = _start_docker_durable_redis()
        except Exception as error:
            docker_error = error
        else:
            try:
                yield runtime
            finally:
                runtime.close()
            return

    try:
        runtime = _start_native_durable_redis()
    except _RedisClusterFixtureDependencyError as error:
        pytest.fail(
            "FIXTURE_DEPENDENCY_MISSING[durable_redis]: "
            f"docker setup failed ({_describe_fixture_error(docker_error)}); "
            f"native fallback unavailable ({error})",
            pytrace=False,
        )
    except Exception as error:
        pytest.fail(
            "FIXTURE_SETUP_FAILED[durable_redis]: "
            f"docker setup failed ({_describe_fixture_error(docker_error)}); "
            f"native fallback failed ({_describe_fixture_error(error)})",
            pytrace=False,
        )

    try:
        yield runtime
    finally:
        runtime.close()
