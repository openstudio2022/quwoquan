"""Online App dependency fetches recover only typed transient network failures."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync as sync
from quwoquan_ops.cli.commands import app_dependency_sync_builder as builder
from quwoquan_ops.cli.lib.package_reuse import dependency_network_command as network
from quwoquan_ops.tests.support.app_dependency_sync_test_support import digest as _digest

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001.t9


def _run(
    tmp_path: Path,
    *,
    retry: bool,
) -> subprocess.CompletedProcess[str]:
    return builder._run_checked(
        command=["pod", "install", "--deployment"],
        cwd=tmp_path,
        environment={"CP_HOME_DIR": str(tmp_path / "home")},
        log_path=tmp_path / "pod.log",
        phase="production CocoaPods network sync",
        retry_transient_network=retry,
    )


@pytest.mark.parametrize(
    "failure_output",
    [
        "curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL",
        "javax.net.ssl.SSLHandshakeException: Remote host terminated the handshake",
        "Received status code 503 from server",
        "curl: (22) The requested URL returned error: 503",
    ],
)
def test_online_sync_retries_transient_failure_in_the_same_private_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_output: str,
) -> None:
    calls: list[tuple[Path, dict[str, str]]] = []
    sleeps: list[float] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        calls.append((Path(kwargs["cwd"]), environment))
        marker = Path(environment["CP_HOME_DIR"]) / "partial"
        marker.parent.mkdir(exist_ok=True)
        if len(calls) == 1:
            marker.write_text("retained", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1, stdout=failure_output)
        assert marker.read_text(encoding="utf-8") == "retained"
        return subprocess.CompletedProcess(command, 0, stdout="recovered")

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    completed = _run(tmp_path, retry=True)

    assert completed.stdout == "recovered"
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert sleeps == [1.0]
    log = (tmp_path / "pod.log").read_text(encoding="utf-8")
    assert "result=transient_failure" in log
    assert "result=success" in log
    assert failure_output not in log
    assert "recovered" not in log


@pytest.mark.parametrize(
    "failure_output",
    [
        "Received status code 404 from server",
        "curl: (22) The requested URL returned error: 404",
        "SSLHandshakeException: PKIX path building failed",
        "SSL_connect: certificate verify failed",
        "Unable to find a specification for `MissingPod`",
    ],
)
def test_online_sync_does_not_retry_deterministic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_output: str,
) -> None:
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 1, stdout=failure_output)

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed") as caught:
        _run(tmp_path, retry=True)
    assert failure_output in str(caught.value)
    assert calls == 1


def test_online_sync_transient_then_deterministic_returns_current_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = [
        "SSL_ERROR_SYSCALL transient-first",
        "Received status code 404 deterministic-second",
    ]
    sleeps: list[float] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout=outputs.pop(0))

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed") as caught:
        _run(tmp_path, retry=True)

    assert "deterministic-second" in str(caught.value)
    assert "transient-first" not in str(caught.value)
    assert outputs == []
    assert sleeps == [1.0]
    log = (tmp_path / "pod.log").read_text(encoding="utf-8")
    assert "result=transient_failure" in log
    assert "deterministic-second" in log
    assert "transient-first" not in log


def test_online_sync_exhaustion_preserves_first_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = [
        "SSL_ERROR_SYSCALL first",
        "Received status code 503 second",
        "SSLHandshakeException: EOF third",
    ]
    sleeps: list[float] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout=outputs.pop(0))

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    with pytest.raises(ValueError) as caught:
        _run(tmp_path, retry=True)
    assert "first" in str(caught.value)
    assert "second" not in str(caught.value)
    assert outputs == []
    assert sleeps == [1.0, 2.0]


def test_online_sync_timeout_has_process_and_total_wall_clock_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    timeouts: list[float] = []
    sleeps: list[float] = []
    monkeypatch.setattr(builder, "_SYNC_TIMEOUT_SECONDS", 4)
    monkeypatch.setattr(builder, "_SYNC_NETWORK_DEADLINE_SECONDS", 10)
    monkeypatch.setattr(builder.time, "monotonic", lambda: clock[0])
    def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(builder.time, "sleep", fake_sleep)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeouts.append(float(kwargs["timeout"]))
        clock[0] += float(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="timed out")

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_timeout"):
        _run(tmp_path, retry=True)
    assert timeouts == [4.0, 4.0]
    assert sleeps == [1.0, 1.0]
    assert clock[0] == 10.0


def test_non_network_phase_is_single_attempt_even_for_tls_shaped_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 1, stdout="SSL_ERROR_SYSCALL")

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed"):
        _run(tmp_path, retry=False)
    assert calls == 1


def test_pub_online_sync_retries_hosted_client_upstream_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = [
        "Package not available (authorization failed).",
        "recovered",
    ]
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            command,
            1 if calls == 1 else 0,
            stdout=outputs[calls - 1],
        )

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        builder, "_public_pub_origin_archive_fallback", lambda **_kwargs: False
    )
    app = tmp_path / "app"
    app.mkdir()
    builder.run_pub_get(
        flutter="/fixture/flutter",
        app_dir=app,
        pub_cache=tmp_path / "pub",
        hosted_url="https://pub.flutter-io.cn",
        offline=False,
        log_path=tmp_path / "pub-online.log",
    )

    assert calls == 2
    log = (tmp_path / "pub-online.log").read_text(encoding="utf-8")
    assert "cause=public_hosted_upstream_unavailable" in log
    assert "result=success" in log
    assert "authorization failed" not in log


def test_public_pub_origin_fallback_requires_exact_lock_sha_and_preserves_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    cache = tmp_path / "pub"
    hosted = cache / "hosted/pub.flutter-io.cn"
    metadata = hosted / ".cache/pkg-versions.json"
    metadata.parent.mkdir(parents=True)
    archive = tmp_path / "pkg.tar.gz"
    package_root = tmp_path / "archive-source"
    package_root.mkdir()
    package_root.joinpath("pubspec.yaml").write_text("name: pkg\nversion: 1.0.0\n")
    import hashlib
    import tarfile

    with tarfile.open(archive, "w:gz") as output:
        output.add(package_root, arcname="pkg-1.0.0")
    encoded = archive.read_bytes()
    digest = hashlib.sha256(encoded).hexdigest()
    lock = {
        "packages": {
            "pkg": {
                "source": "hosted",
                "version": "1.0.0",
                "description": {
                    "name": "pkg",
                    "url": "https://pub.flutter-io.cn",
                    "sha256": digest,
                },
            }
        }
    }
    app.joinpath("pubspec.lock").write_text(json.dumps(lock))
    metadata.write_text(
        json.dumps(
            {
                "versions": [
                    {
                        "version": "1.0.0",
                        "archive_url": (
                            "https://storage.flutter-io.cn/dartlang-pub-exported-api/"
                            "latest/api/archives/pkg-1.0.0.tar.gz"
                        ),
                        "archive_sha256": digest,
                    }
                ]
            }
        )
    )
    before = app.joinpath("pubspec.lock").read_bytes()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return encoded

    monkeypatch.setattr(
        builder.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    assert builder._public_pub_origin_archive_fallback(
        app_dir=app, pub_cache=cache, log_path=tmp_path / "fallback.log"
    )
    assert app.joinpath("pubspec.lock").read_bytes() == before
    assert hosted.joinpath("pkg-1.0.0/pubspec.yaml").is_file()
    assert (
        cache.joinpath(
            "hosted-hashes/pub.flutter-io.cn/pkg-1.0.0.sha256"
        ).read_text().strip()
        == digest
    )


def test_public_pub_origin_fallback_rejects_sha_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    cache = tmp_path / "pub"
    metadata = cache / "hosted/pub.flutter-io.cn/.cache/pkg-versions.json"
    metadata.parent.mkdir(parents=True)
    expected = "a" * 64
    app.joinpath("pubspec.lock").write_text(
        json.dumps(
            {
                "packages": {
                    "pkg": {
                        "source": "hosted",
                        "version": "1.0.0",
                        "description": {
                            "name": "pkg",
                            "url": "https://pub.flutter-io.cn",
                            "sha256": expected,
                        },
                    }
                }
            }
        )
    )
    metadata.write_text(
        json.dumps(
            {
                "versions": [
                    {
                        "version": "1.0.0",
                        "archive_url": (
                            "https://storage.flutter-io.cn/dartlang-pub-exported-api/"
                            "latest/api/archives/pkg-1.0.0.tar.gz"
                        ),
                        "archive_sha256": expected,
                    }
                ]
            }
        )
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return b"wrong archive"

    monkeypatch.setattr(
        builder.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    assert not builder._public_pub_origin_archive_fallback(
        app_dir=app, pub_cache=cache, log_path=tmp_path / "fallback.log"
    )
    assert not cache.joinpath("hosted/pub.flutter-io.cn/pkg-1.0.0").exists()


def test_private_pub_authorization_failure_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            command, 1, stdout="Package not available (authorization failed)."
        )

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    app = tmp_path / "app"
    app.mkdir()
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed"):
        builder.run_pub_get(
            flutter="/fixture/flutter",
            app_dir=app,
            pub_cache=tmp_path / "pub",
            hosted_url="https://private.example.invalid",
            offline=False,
            log_path=tmp_path / "private-pub.log",
        )

    assert calls == 1


def test_pub_offline_replay_never_retries_hosted_client_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            command, 1, stdout="Package not available (authorization failed)."
        )

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    app = tmp_path / "app"
    app.mkdir()
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed"):
        builder.run_pub_get(
            flutter="/fixture/flutter",
            app_dir=app,
            pub_cache=tmp_path / "pub",
            hosted_url="https://pub.flutter-io.cn",
            offline=True,
            log_path=tmp_path / "pub-offline.log",
        )

    assert calls == 1


def test_process_group_cleanup_failure_is_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise network.DependencyProcessGroupCleanupError(
            "APP.DEPENDENCY.process_group_cleanup_failed"
        )

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(
        network.DependencyProcessGroupCleanupError,
        match="APP.DEPENDENCY.process_group_cleanup_failed",
    ):
        _run(tmp_path, retry=True)
    assert calls == 1




def test_pub_online_transient_cleanup_removes_only_known_metadata(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    package = cache / "hosted/pub.flutter-io.cn/pkg-1.0.0/lib/pkg.dart"
    package.parent.mkdir(parents=True)
    package.write_text("const pkg = true;\n")
    metadata = cache / "hosted/pub.flutter-io.cn/.cache/pkg-versions.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("{}")
    (cache / "_temp").mkdir()
    (cache / "README.md").write_text("pub cache\n")

    builder._remove_pub_online_transients(cache)

    assert package.is_file()
    assert not metadata.parent.exists()
    assert not cache.joinpath("_temp").exists()
    assert not cache.joinpath("README.md").exists()


def test_pub_online_transient_cleanup_rejects_symlink(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    cache.joinpath("README.md").symlink_to(tmp_path / "foreign")

    with pytest.raises(ValueError, match="pub_online_transient_unsafe"):
        builder._remove_pub_online_transients(cache)


def test_pub_offline_replay_allows_only_host_bound_active_root_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "cache"
    dependency = cache / "hosted/pkg/file"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("dependency\n", encoding="utf-8")
    host = tmp_path / "projection/app"
    (host / ".dart_tool").mkdir(parents=True)
    (host / ".dart_tool/package_config.json").write_text("{}", encoding="utf-8")
    marker = cache / ("active_roots/ab/" + "c" * 62)
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps(
            {"package_config": (host / ".dart_tool/package_config.json").as_uri()}
        ),
        encoding="utf-8",
    )
    snapshot = SimpleNamespace(
        manifest={"treeDigest": _digest("1")},
        files=(SimpleNamespace(relative="hosted/pkg/file"),),
        directories=("hosted", "hosted/pkg"),
    )
    monkeypatch.setattr(
        sync._builder,
        "build_pub_cache_snapshot",
        lambda **_kwargs: SimpleNamespace(manifest=snapshot.manifest),
    )

    sync._builder._verify_pub_replay(
        snapshot=snapshot,
        lock_path=tmp_path / "pubspec.lock",
        cache_root=cache,
        host_root=host,
    )

    (cache / "unexpected").write_text("escape\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pub_offline_replay_extra_bytes"):
        sync._builder._verify_pub_replay(
            snapshot=snapshot,
            lock_path=tmp_path / "pubspec.lock",
            cache_root=cache,
            host_root=host,
        )


def test_pub_replay_state_is_inside_source_projection_for_ios_cas_validation(
    tmp_path: Path,
) -> None:
    projection = tmp_path / "work/source-projection"
    for name in ("productionPub", "patrolPub"):
        state = sync._builder._pub_state_root(projection, name)
        assert state.is_relative_to(projection)
        assert state == projection / ".dependency-sync/pub" / name

    with pytest.raises(ValueError, match="pub_component_invalid"):
        sync._builder._pub_state_root(projection, "../outside")
