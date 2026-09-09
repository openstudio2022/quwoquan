from __future__ import annotations

import argparse
import ast
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]


def _canonical_ssh_host() -> str:
    """SSH 管理端点的唯一真相源是 access-isolation.yaml，测试不复制其值。"""
    from quwoquan_ops.cli.lib.common import load_json_yaml

    policy = load_json_yaml(
        ROOT / "quwoquan_ops" / "environments" / "prod" / "access-isolation.yaml"
    )
    return str((policy.get("management") or {})["sshHost"])


class ProdPlaneSshSetupTest(unittest.TestCase):
    """部署模块：本地 prod 平面 SSH key 生成与映射产物输出。"""

    # spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003
    def test_native_runtime_requires_explicit_install_confirmation(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import command_runtime_bootstrap

        result = command_runtime_bootstrap(argparse.Namespace(confirm_runtime_install=False))
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("explicit confirmation", result["summary"])

    def test_native_runtime_unknown_placement_is_blocked_before_ssh(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import command_runtime_bootstrap

        result = command_runtime_bootstrap(argparse.Namespace(
            confirm_runtime_install=True, host_id="not-in-inventory",
        ))
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("invalid bootstrap placement", result["summary"])

    def test_native_runtime_is_same_version_bounded_and_no_manual_probe(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import (
            _native_runtime_script, PODMAN_SOURCE_COMMIT, PODMAN_VERSION,
        )

        script = _native_runtime_script("/home/admin/build", "a" * 64)
        self.assertIn(PODMAN_SOURCE_COMMIT, script)
        self.assertIn("podman version " + PODMAN_VERSION, script)
        self.assertIn("systemd containers_image_openpgp", script)
        self.assertIn("MemoryMax=2G", script)
        self.assertIn("RuntimeMaxSec=1800", script)
        self.assertNotIn("healthcheck run", script)
        self.assertNotIn("systemctl restart docker", script)
        self.assertNotIn("dnf upgrade", script.replace("# 不执行 dnf upgrade", ""))
        checked = subprocess.run(["bash", "-n"], input=script, text=True,
                                 capture_output=True, check=False)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_runtime_scripts_compile_embedded_python_and_fail_closed(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import (
            _native_lock_migration_script, _native_scheduler_script,
        )

        migration = _native_lock_migration_script("quwoquan-service-prevalidate-r0")
        scheduler = _native_scheduler_script("redis@sha256:" + "a" * 64, "quwoquan-runtime-probe-test")
        for script in (migration, scheduler):
            checked = subprocess.run(["bash", "-n"], input=script, text=True,
                                     capture_output=True, check=False)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            source = script.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
            compile(source, "remote-runtime-probe", "exec")
            self.assertNotIn("system reset", source)
            self.assertNotIn("image prune", source)
        self.assertIn("RUNTIME_MIGRATION_ACTIVE_WRITER", migration)
        self.assertIn("RUNTIME_MIGRATION_FOREIGN_CONTAINER", migration)
        self.assertIn("RUNTIME_MIGRATION_BACKUP_ALREADY_EXISTS", migration)
        self.assertIn("os.link(lock, lock_backup, follow_symlinks=False)", migration)
        self.assertNotIn("lock.rename", migration)
        self.assertLess(migration.index("RUNTIME_MIGRATION_FOREIGN_CONTAINER"), migration.index("'stop', 'podman.socket'"))
        self.assertIn("len(successful) >= 2", scheduler)
        self.assertIn("timeout -k 2 85 python3", scheduler)
        self.assertIn("timeout -k 5 20 podman create", scheduler)
        self.assertNotIn("healthcheck run", scheduler)

    def test_runtime_parser_rejects_multiple_mutation_actions(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import register_runtime_parser

        parser = argparse.ArgumentParser()
        register_runtime_parser(parser.add_subparsers(dest="command", required=True))
        with self.assertRaises(SystemExit):
            parser.parse_args(["prod-hosted-bootstrap", "--host-id", "prod-host-01",
                               "--confirm-runtime-install", "--confirm-lock-migration"])

    def test_secret_directories_are_private_empty_and_idempotent(self) -> None:
        from quwoquan_ops.cli.prod import setup_prod_plane_ssh_access as bootstrap

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "secrets"
            with mock.patch.object(bootstrap, "SECRET_INPUT_ROOT", root):
                result = bootstrap._prepare_secret_directories()
                self.assertEqual(result, bootstrap._prepare_secret_directories())
            self.assertEqual(result["consumerBinding"], "not-configured")
            for path in root.rglob("*"):
                self.assertTrue(path.is_dir())
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertTrue((root / "prod/prevalidate/mtls/user-to-integration").is_dir())
            self.assertTrue((root / "prod/formal/app-signing/android").is_dir())

    def test_secret_directories_reject_symlink_or_unsafe_existing_scope(self) -> None:
        from quwoquan_ops.cli.prod import setup_prod_plane_ssh_access as bootstrap

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "secrets"
            root.mkdir(mode=0o700)
            (root / "alpha").symlink_to(base, target_is_directory=True)
            with mock.patch.object(bootstrap, "SECRET_INPUT_ROOT", root):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    bootstrap._prepare_secret_directories()
            self.assertFalse((root / "prod").exists())
            (root / "alpha").unlink()
            (root / "alpha").mkdir(mode=0o755)
            (root / "alpha").chmod(0o755)
            with mock.patch.object(bootstrap, "SECRET_INPUT_ROOT", root):
                with self.assertRaisesRegex(ValueError, "0700"):
                    bootstrap._prepare_secret_directories()
            self.assertFalse((root / "prod").exists())

    def test_remote_bootstrap_requires_host_even_with_authorized_action(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import command_runtime_bootstrap

        result = command_runtime_bootstrap(argparse.Namespace(confirm_lock_migration=True))
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("host-id", result["summary"])

    def _migration_source(self) -> str:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import _native_lock_migration_script

        return _native_lock_migration_script("rehearsal").split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]

    def _run_native_migration(self, home: Path, rows: list[dict], *, socket_failure: bool = False) -> None:
        def run(command, **kwargs):
            if command[0] == "timeout":
                return subprocess.CompletedProcess(command, 0, stdout=b"systemd v2\n")
            if socket_failure:
                raise subprocess.CalledProcessError(19, command)
            return subprocess.CompletedProcess(command, 0)

        with mock.patch.object(Path, "home", return_value=home), mock.patch.dict(os.environ, EXPECTED_PROJECT="rehearsal"), \
                mock.patch.object(subprocess, "run", side_effect=run), \
                mock.patch.object(subprocess, "check_output", return_value=json.dumps(rows).encode()):
            exec(compile(self._migration_source(), "migration", "exec"), {})

    def test_native_info_success_does_not_bypass_foreign_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            for names, labels in ((["foreign-app"], {}), (["rehearsal-api"], {})):
                with self.subTest(names=names):
                    with self.assertRaisesRegex(SystemExit, "FOREIGN_CONTAINER"):
                        self._run_native_migration(home, [{"Names": names, "Labels": labels}])
                    self.assertFalse((home / ".config").exists())
                    self.assertFalse((home / ".cache").exists())

    def test_migration_rejects_unsafe_ancestors_before_runtime_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            other = home / "elsewhere"
            other.mkdir(mode=0o700)
            for name in (".cache", ".config"):
                path = home / name
                path.symlink_to(other, target_is_directory=True)
                with self.assertRaisesRegex(SystemExit, "UNSAFE_PATH"):
                    self._run_native_migration(home, [])
                self.assertEqual(list(other.iterdir()), [])
                path.unlink()
            (home / ".cache").mkdir(mode=0o777)
            (home / ".cache").chmod(0o777)
            with self.assertRaisesRegex(SystemExit, "UNSAFE_ANCESTOR"):
                self._run_native_migration(home, [])

    def test_migration_failure_does_not_write_completion_and_retry_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            marker = home / ".cache/quwoquan-runtime-migration/native-locks-completed"
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                self._run_native_migration(home, [], socket_failure=True)
            self.assertEqual(failure.exception.returncode, 19)
            self.assertFalse(marker.exists())
            self._run_native_migration(home, [])
            inode = marker.stat().st_ino
            self._run_native_migration(home, [])
            self.assertEqual(marker.stat().st_ino, inode)
            marker.write_text("invalid previous marker")
            with self.assertRaisesRegex(SystemExit, "CONFIGURATION_DRIFT"):
                self._run_native_migration(home, [])
            self.assertEqual(marker.read_text(), "invalid previous marker")

    def test_migration_owned_running_inventory_is_not_reported_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows = [{"Names": ["rehearsal-api"], "Labels": {"io.podman.compose.project": "rehearsal"},
                     "Id": "a" * 64, "State": "running"}]
            with self.assertRaisesRegex(SystemExit, "CONTAINERS_STILL_RUNNING"):
                self._run_native_migration(Path(temporary).resolve(), rows)

    def test_migration_path_helper_rejects_owner_hardlink_and_symlink(self) -> None:
        tree = ast.parse(self._migration_source())
        functions = ast.Module(body=[node for node in tree.body if isinstance(node, (ast.Import, ast.FunctionDef))], type_ignores=[])
        namespace = {"uid": os.getuid()}
        exec(compile(functions, "migration-helpers", "exec"), namespace)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "backup"
            path.write_text("preserve")
            path.chmod(0o600)
            namespace["safe_path"](path)
            with mock.patch.object(Path, "lstat", return_value=os.stat_result((0o100600, 1, 1, 1, os.getuid() + 1, 1, 0, 0, 0, 0))):
                with self.assertRaises(SystemExit):
                    namespace["safe_path"](path)
            sibling = path.with_name("hardlink")
            os.link(path, sibling)
            with self.assertRaisesRegex(SystemExit, "UNSAFE_PATH"):
                namespace["safe_path"](path)
            sibling.unlink()
            sibling.symlink_to(path)
            with self.assertRaisesRegex(SystemExit, "UNSAFE_PATH"):
                namespace["safe_path"](sibling)
            self.assertEqual(path.read_text(), "preserve")

    def _run_legacy_lock_migration(self, home: Path, *, renumber_failure: bool = False) -> None:
        source = self._migration_source()
        for system_path in ("/proc", "/run/user", "/dev/shm"):
            source = source.replace(repr(system_path), repr(str(home / system_path.lstrip("/"))))
        infos = iter((124, 0))
        def run(command, **kwargs):
            if command[0] == "timeout":
                return subprocess.CompletedProcess(command, next(infos), stdout=b"systemd v2\n")
            if command[:3] == ["podman", "system", "renumber"] and renumber_failure:
                raise subprocess.CalledProcessError(23, command)
            return subprocess.CompletedProcess(command, 0)
        def output(command, **kwargs):
            return b"podman version 6.1.1" if command[-1] == "--version" else b"[]"
        opened = []
        original_open = os.open
        def open_file(*args, **kwargs):
            fd = original_open(*args, **kwargs)
            opened.append(fd)
            return fd
        with mock.patch.object(Path, "home", return_value=home), mock.patch.dict(os.environ, EXPECTED_PROJECT="rehearsal"), \
                mock.patch.object(subprocess, "run", side_effect=run), mock.patch.object(subprocess, "check_output", side_effect=output), \
                mock.patch.object(os, "open", side_effect=open_file):
            try:
                exec(compile(source, "legacy-migration", "exec"), {})
            finally:
                for fd in set(opened):
                    try:
                        os.close(fd)
                    except OSError:
                        pass  # fdopen 已关闭的文件不再持有迁移锁。

    def _legacy_migration_files(self, home: Path) -> tuple[Path, Path]:
        pause = home / f"run/user/{os.getuid()}/libpod/tmp/pause.pid"
        pause.parent.mkdir(parents=True)
        pause.write_text("1234")
        pause.chmod(0o644)
        process = home / "proc/1234"
        process.mkdir(parents=True)
        binary = home / "podman-static"
        binary.write_bytes(b"old-musl-binary")
        binary.chmod(0o700)
        (process / "exe").symlink_to(binary)
        lock = home / f"dev/shm/libpod_rootless_lock_{os.getuid()}"
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"original-musl-lock")
        lock.chmod(0o600)
        return lock, lock.with_name(lock.name + ".musl-backup")

    def test_legacy_lock_backup_collision_never_overwrites_existing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            lock, backup = self._legacy_migration_files(home)
            backup.write_bytes(b"previous-recovery-object")
            with self.assertRaisesRegex(SystemExit, "BACKUP_ALREADY_EXISTS"):
                self._run_legacy_lock_migration(home)
            self.assertEqual(backup.read_bytes(), b"previous-recovery-object")
            self.assertEqual(lock.read_bytes(), b"original-musl-lock")
            self.assertFalse((home / ".cache").exists())

    def test_legacy_renumber_failure_preserves_recovery_and_first_cause(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            lock, backup = self._legacy_migration_files(home)
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                self._run_legacy_lock_migration(home, renumber_failure=True)
            self.assertEqual(failure.exception.returncode, 23)
            self.assertFalse(lock.exists())
            self.assertEqual(backup.read_bytes(), b"original-musl-lock")
            self.assertEqual((home / ".cache/quwoquan-runtime-migration/podman-static-6.1.1").read_bytes(), b"old-musl-binary")
            self.assertFalse((home / ".cache/quwoquan-runtime-migration/native-locks-completed").exists())
            self.assertFalse((home / ".config").exists())

    def test_runtime_key_validation_and_errors_do_not_expose_private_material(self) -> None:
        from quwoquan_ops.cli.prod import setup_prod_plane_ssh_access as bootstrap

        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / "sensitive-key-location"
            key.write_text("private-material-must-not-leak")
            key.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "KEY_UNSAFE"):
                bootstrap._runtime_ssh("account", "host", key)
            key.chmod(0o600)
            argv = bootstrap._runtime_ssh("account", "host", key)
            self.assertIn("IdentitiesOnly=yes", argv)
            for error in (subprocess.TimeoutExpired(argv, 1), subprocess.CalledProcessError(7, argv),
                          FileNotFoundError(2, "unavailable", str(key))):
                result = json.dumps(bootstrap._runtime_failure(error))
                self.assertNotIn(str(key), result)
                self.assertNotIn(key.read_text(), result)

    def test_secret_root_rejects_overlap_and_unsafe_ancestors_before_mkdir(self) -> None:
        from quwoquan_ops.cli.prod import setup_prod_plane_ssh_access as bootstrap
        from quwoquan_ops.cli.lib import output_paths

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "secrets"
            for protected in (base, root, root / "nested"):
                with mock.patch.object(bootstrap, "SECRET_INPUT_ROOT", root), \
                        mock.patch.object(output_paths, "output_root", return_value=protected):
                    with self.assertRaisesRegex(ValueError, "overlap"):
                        bootstrap._prepare_secret_directories()
                    self.assertFalse(root.exists())
            base.chmod(0o777)
            with mock.patch.object(bootstrap, "SECRET_INPUT_ROOT", root):
                with self.assertRaisesRegex(ValueError, "ancestor"):
                    bootstrap._prepare_secret_directories()
            base.chmod(0o700)
            alias = base / "alias"
            alias.symlink_to(base, target_is_directory=True)
            with mock.patch.object(bootstrap, "SECRET_INPUT_ROOT", alias / "secrets"):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    bootstrap._prepare_secret_directories()
            self.assertFalse(root.exists())

    def test_scheduler_requires_structured_evidence_not_ssh_exit_zero(self) -> None:
        from quwoquan_ops.cli.prod import setup_prod_plane_ssh_access as bootstrap

        placement = argparse.Namespace(account="plane", ssh_host="host")
        good = {"status": "passed", "automaticProbeCount": 2, "nativeTimer": True, "oomKilled": False}
        with mock.patch("quwoquan_ops.cli.prod.prod_hosted_topology.resolve_plan", return_value=[placement]):
            for stdout, code, expected in (("", 0, 2), ("{}", 0, 2), (json.dumps(good), 0, 0),
                                            (json.dumps(good), 19, 2)):
                with mock.patch.object(bootstrap, "_run_plane_script", return_value=subprocess.CompletedProcess([], code, stdout, "")):
                    self.assertEqual(bootstrap._verify_native_scheduler("host")["exitCode"], expected)

    def test_scheduler_embedded_probe_rejects_duplicate_or_failed_logs(self) -> None:
        from quwoquan_ops.cli.prod import setup_prod_plane_ssh_access as bootstrap

        script = bootstrap._native_scheduler_script("image", "name")
        source = script.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        cid = "a" * 64
        for logs, passed in (([{"Start": "one", "ExitCode": 0}] * 2, False),
                             ([{"Start": "one", "ExitCode": 0}, {"Start": "two", "ExitCode": 1}], False),
                             ([{"Start": "one", "ExitCode": 0}, {"Start": "two", "ExitCode": 0}], True)):
            container = [{"Id": cid, "State": {"Status": "running", "OOMKilled": False,
                          "Health": {"Status": "healthy", "Log": logs}}}]
            def output(command, **kwargs):
                return json.dumps(container).encode() if command[0] == "podman" else (cid + "-af123.timer").encode()
            with mock.patch.dict(os.environ, PROBE_CONTAINER_ID=cid), mock.patch.object(subprocess, "check_output", side_effect=output), \
                    mock.patch("time.sleep"), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                if passed:
                    exec(compile(source, "scheduler", "exec"), {})
                    self.assertEqual(json.loads(stdout.getvalue())["automaticProbeCount"], 2)
                else:
                    with self.assertRaisesRegex(SystemExit, "SCHEDULER_UNAVAILABLE"):
                        exec(compile(source, "scheduler", "exec"), {})

    def test_native_install_seals_once_without_overwriting_running_inode(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import _native_install_script

        source = _native_install_script().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        tree = ast.parse(source)
        definitions = ast.Module(body=[node for node in tree.body if isinstance(node, (ast.Import, ast.FunctionDef))], type_ignores=[])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = root / "candidate"
            binary = root / "podman"
            candidate.write_bytes(b"native binary")
            namespace = {"runtime": root}
            exec(compile(definitions, "install-helpers", "exec"), namespace)
            # seal 的文件写入执行真实 OS；root owner 校验在独立测试中覆盖。
            namespace["trusted"] = lambda path: self.assertTrue(path.is_file())
            namespace["seal"](candidate, binary)
            inode = binary.stat().st_ino
            with binary.open("rb") as running:
                namespace["seal"](candidate, binary)
                self.assertEqual(binary.stat().st_ino, inode)
                candidate.write_bytes(b"unexpected replacement")
                with self.assertRaisesRegex(SystemExit, "BINARY_DRIFT"):
                    namespace["seal"](candidate, binary)
                self.assertEqual(running.read(), b"native binary")
            other = root / "other"
            other.write_bytes(b"preserve foreign file")
            link = root / "link"
            link.symlink_to(other)
            with self.assertRaisesRegex(SystemExit, "BINARY_DRIFT"):
                namespace["seal"](candidate, link)
            self.assertEqual(other.read_bytes(), b"preserve foreign file")
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["candidate", "link", "other", "podman"])

    def test_install_trusted_helper_rejects_symlink_owner_and_writable_binary(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import _native_install_script

        source = _native_install_script().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        tree = ast.parse(source)
        namespace = {}
        definitions = ast.Module(body=[node for node in tree.body if isinstance(node, (ast.Import, ast.FunctionDef))], type_ignores=[])
        exec(compile(definitions, "install-helpers", "exec"), namespace)
        path = Path("/not-accessed")
        for mode, uid, links in ((0o120755, 0, 1), (0o100755, 501, 1), (0o100777, 0, 1), (0o100755, 0, 2)):
            info = os.stat_result((mode, 1, 1, links, uid, 0, 1, 0, 0, 0))
            with mock.patch.object(Path, "lstat", return_value=info):
                with self.assertRaisesRegex(SystemExit, "RUNTIME_INSTALL_UNSAFE"):
                    namespace["trusted"](path)

    def test_probe_cleanup_preserves_first_failure_and_reports_cleanup_failure(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import _native_scheduler_script

        script = _native_scheduler_script("image", "probe")
        cleanup = script.split("cleanup() {", 1)[1].split("trap cleanup EXIT", 1)[0]
        for first, expected in ((17, 17), (0, 9)):
            with tempfile.TemporaryDirectory() as temporary:
                isolated = "\n".join([
                    "set -euo pipefail", "timeout() { return 9; }", "rm() { return 0; }",
                    "container_id=" + "a" * 64, "probe_dir=" + temporary,
                    "cleanup() {" + cleanup, "trap cleanup EXIT", f"exit {first}",
                ])
                result = subprocess.run(["bash", "-s"], input=isolated, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, expected)
                self.assertIn("RUNTIME_PROBE_CLEANUP_FAILED", result.stderr)

    def test_probe_cleanup_can_recover_created_id_after_create_timeout(self) -> None:
        from quwoquan_ops.cli.prod.setup_prod_plane_ssh_access import _native_scheduler_script

        script = _native_scheduler_script("image", "probe")
        cleanup = script.split("cleanup() {", 1)[1].split("trap cleanup EXIT", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            cid = "b" * 64
            (Path(temporary) / "cid").write_text(cid)
            isolated = "\n".join([
                "set -euo pipefail", 'timeout() { printf "%s\\n" "$*" >&2; }', "rm() { return 0; }",
                "container_id=''", "probe_dir=" + temporary, "cleanup() {" + cleanup,
                "trap cleanup EXIT", "exit 124",
            ])
            result = subprocess.run(["bash", "-s"], input=isolated, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 124)
            self.assertIn("podman rm -f " + cid, result.stderr)
            self.assertNotIn("probe\n", result.stderr)

    def test_generate_mode_writes_mapping_and_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            mapping = json.loads(mapping_out.read_text(encoding="utf-8"))
            self.assertEqual(mapping["host"], _canonical_ssh_host())
            self.assertEqual(
                [account["account"] for account in mapping["accounts"]],
                ["prod-edge-svc", "prod-media-svc", "prod-service-svc"],
            )
            for account in mapping["accounts"]:
                self.assertTrue(Path(account["privateKeyPath"]).is_file())
                self.assertTrue(Path(account["publicKeyPath"]).is_file())
            instructions = instructions_out.read_text(encoding="utf-8")
            self.assertIn("prod 私钥不再进入 GitHub Actions secrets", instructions)
            self.assertIn("PROD_SERVICE_SSH_KEY", instructions)
            self.assertIn("--github-prune-obsolete-secrets", instructions)

    def test_generate_mode_can_include_relay_and_readonly_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--all-accounts",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            mapping = json.loads(mapping_out.read_text(encoding="utf-8"))
            self.assertEqual(
                [account["account"] for account in mapping["accounts"]],
                [
                    "prod-edge-svc",
                    "prod-media-svc",
                    "prod-service-svc",
                    "prod-ops",
                    "prod-data-svc",
                ],
            )

    def test_generate_mode_can_prune_obsolete_github_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            log_file = tmp_path / "gh_secret_calls.log"
            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import pathlib, sys",
                        f"log = pathlib.Path({str(log_file)!r})",
                        "args = sys.argv[1:]",
                        "if args[:2] == ['secret', 'list']:",
                        "    print('PROD_KUBECONFIG\\t2026-01-01T00:00:00Z')",
                        "    print('PROD_EDGE_SSH_KEY\\t2026-01-01T00:00:00Z')",
                        "    print('PROD_SERVICE_SSH_KEY\\t2026-01-01T00:00:00Z')",
                        "    print('GAMMA_BASE_URL\\t2026-01-01T00:00:01Z')",
                        "    raise SystemExit(0)",
                        "with log.open('a', encoding='utf-8') as fh:",
                        "    fh.write('ARGS=' + ' '.join(args) + '\\n')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                    "--github-prune-obsolete-secrets",
                    "--github-repo",
                    "openstudio2022/quwoquan",
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            log = log_file.read_text(encoding="utf-8")
            self.assertNotIn("secret set", log)
            self.assertIn("ARGS=secret delete PROD_EDGE_SSH_KEY --repo openstudio2022/quwoquan --app actions", log)
            self.assertIn("ARGS=secret delete PROD_SERVICE_SSH_KEY --repo openstudio2022/quwoquan --app actions", log)
            self.assertIn("ARGS=secret delete PROD_KUBECONFIG --repo openstudio2022/quwoquan --app actions", log)
            self.assertIn("ARGS=secret delete GAMMA_BASE_URL --repo openstudio2022/quwoquan --app actions", log)

    def test_generate_mode_can_export_encrypted_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            bundle_out = tmp_path / "prod_ssh_keys.tar.enc"
            env = os.environ.copy()
            env["PROD_SSH_BUNDLE_PASSPHRASE"] = "test-passphrase"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--all-accounts",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                    "--export-encrypted-bundle",
                    "--bundle-out",
                    str(bundle_out),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            decrypted_tar = tmp_path / "prod_ssh_keys.tar"
            decrypt = subprocess.run(
                [
                    "openssl",
                    "enc",
                    "-d",
                    "-aes-256-cbc",
                    "-pbkdf2",
                    "-in",
                    str(bundle_out),
                    "-out",
                    str(decrypted_tar),
                    "-pass",
                    "env:PROD_SSH_BUNDLE_PASSPHRASE",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(decrypt.returncode, 0, decrypt.stdout + decrypt.stderr)
            extract_dir = tmp_path / "bundle"
            extract_dir.mkdir()
            with tarfile.open(decrypted_tar, "r") as tar:
                tar.extractall(extract_dir, filter="data")
            manifest = json.loads(
                (extract_dir / "prod-ssh-bundle" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["host"], _canonical_ssh_host())
            self.assertEqual(len(manifest["accounts"]), 5)
            self.assertTrue((extract_dir / "prod-ssh-bundle" / "prod-service-svc").is_file())


if __name__ == "__main__":
    unittest.main()
