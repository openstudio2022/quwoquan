from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "quwoquan_ops/ci/run_recommendation_test_mongodb.sh"


def _write_fake_docker(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$QWQ_TEST_DOCKER_LOG"
case "$*" in
  "inspect qwq-rec-mongo")
    if [[ "${QWQ_TEST_MONGO_EXISTING:-false}" == true ]]; then exit 0; else exit 1; fi
    ;;
  "run -d --name qwq-rec-mongo -p 127.0.0.1:27017:27017 mongo:7-jammy --replSet rs0 --bind_ip_all")
    if [[ "${QWQ_TEST_MONGO_FAIL_START:-false}" == true ]]; then exit 1; else echo container-id; fi
    ;;
  *"db.runCommand({ping:1}).ok"*)
    if [[ "${QWQ_TEST_MONGO_FAIL_PING:-false}" == true ]]; then echo 0; else echo 1; fi
    ;;
  *"rs.initiate"*)
    if [[ "${QWQ_TEST_MONGO_FAIL_INIT:-false}" == true ]]; then exit 1; else echo '{ ok: 1 }'; fi
    ;;
  *"db.hello().isWritablePrimary"*)
    if [[ "${QWQ_TEST_MONGO_FAIL_PRIMARY:-false}" == true ]]; then echo false; else echo true; fi
    ;;
  "logs qwq-rec-mongo") echo diagnostic-log ;;
  "rm -f qwq-rec-mongo") ;;
  *) exit 99 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run(
    tmp_path: Path,
    *,
    fail_ping: bool = False,
    fail_primary: bool = False,
    fail_start: bool = False,
    fail_init: bool = False,
    existing: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_docker(bin_dir / "docker")
    log = tmp_path / "docker.log"
    github_env = tmp_path / "github.env"
    completed = subprocess.run(
        ["bash", str(RUNNER)],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "QWQ_TEST_DOCKER_LOG": str(log),
            "QWQ_TEST_MONGO_FAIL_PING": "true" if fail_ping else "false",
            "QWQ_TEST_MONGO_FAIL_PRIMARY": "true" if fail_primary else "false",
            "QWQ_TEST_MONGO_FAIL_START": "true" if fail_start else "false",
            "QWQ_TEST_MONGO_FAIL_INIT": "true" if fail_init else "false",
            "QWQ_TEST_MONGO_EXISTING": "true" if existing else "false",
            "QWQ_CI_MONGO_READY_ATTEMPTS": "2",
            "QWQ_CI_MONGO_READY_DELAY_SECONDS": "0",
            "GITHUB_ENV": str(github_env),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    exported = github_env.read_text(encoding="utf-8") if github_env.exists() else ""
    return completed, log.read_text(encoding="utf-8").splitlines(), exported


def test_bootstrap_waits_for_ping_initializes_replica_set_and_waits_for_primary(
    tmp_path: Path,
) -> None:
    completed, commands, exported = _run(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert commands[0] == "inspect qwq-rec-mongo"
    assert commands[1].startswith(
        "run -d --name qwq-rec-mongo -p 127.0.0.1:27017:27017"
    )
    assert any("db.runCommand({ping:1}).ok" in command for command in commands)
    assert any("rs.initiate" in command for command in commands)
    assert any("db.hello().isWritablePrimary" in command for command in commands)
    assert "rm -f qwq-rec-mongo" not in commands
    assert exported == (
        "QWQ_TEST_MONGO_URI="
        "mongodb://127.0.0.1:27017/?directConnection=true\n"
    )


def test_ping_timeout_removes_failed_container_and_emits_typed_blocker(
    tmp_path: Path,
) -> None:
    completed, commands, exported = _run(tmp_path, fail_ping=True)

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.MONGO_PING_TIMEOUT" in completed.stderr
    assert commands[-1] == "rm -f qwq-rec-mongo"
    assert commands[-2] == "logs qwq-rec-mongo"
    assert exported == ""


def test_existing_container_blocks_without_deleting_foreign_state(tmp_path: Path) -> None:
    completed, commands, exported = _run(tmp_path, existing=True)

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.MONGO_CONTAINER_ALREADY_EXISTS" in completed.stderr
    assert commands == ["inspect qwq-rec-mongo"]
    assert exported == ""


def test_primary_timeout_preserves_logs_then_removes_owned_container(
    tmp_path: Path,
) -> None:
    completed, commands, exported = _run(tmp_path, fail_primary=True)

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.MONGO_PRIMARY_TIMEOUT" in completed.stderr
    assert commands[-2:] == ["logs qwq-rec-mongo", "rm -f qwq-rec-mongo"]
    assert exported == ""


def test_start_failure_does_not_delete_a_container_it_did_not_own(
    tmp_path: Path,
) -> None:
    completed, commands, exported = _run(tmp_path, fail_start=True)

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.MONGO_START_FAILED" in completed.stderr
    assert commands[-1].startswith("run -d --name qwq-rec-mongo")
    assert not any(command.startswith(("logs ", "rm ")) for command in commands)
    assert exported == ""


def test_replica_init_failure_logs_then_removes_owned_container(
    tmp_path: Path,
) -> None:
    completed, commands, exported = _run(tmp_path, fail_init=True)

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.MONGO_REPLICA_INIT_FAILED" in completed.stderr
    assert commands[-2:] == ["logs qwq-rec-mongo", "rm -f qwq-rec-mongo"]
    assert exported == ""


def test_bounds_fail_before_docker_is_invoked(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "docker-called"
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/usr/bin/env bash\ntouch "$QWQ_TEST_DOCKER_MARKER"\nexit 99\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)

    completed = subprocess.run(
        ["bash", str(RUNNER)],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "QWQ_TEST_DOCKER_MARKER": str(marker),
            "QWQ_CI_MONGO_READY_ATTEMPTS": "61",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.MONGO_BOUND_INVALID" in completed.stderr
    assert not marker.exists()
