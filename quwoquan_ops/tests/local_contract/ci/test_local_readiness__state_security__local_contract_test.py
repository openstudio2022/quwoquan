"""Local readiness state-storage security contracts."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.local_readiness.core import (  # noqa: E402
    LocalReadinessError,
    _atomic_json,
    _state_root,
    enqueue_paths,
    plan_readiness,
    resource_lock,
    run_readiness,
    verify_receipt,
)


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002
@pytest.mark.parametrize("blob", [
    b"AccessKeySecret: ossBinding.AccessKeySecret,",
    b"APIKey: cfg.Telemetry.ProviderAPIKey,",
    b"AppSecret: cfg.Telemetry.ProviderAPIKey,",
    b"clientSecret: cfg.Telemetry.ProviderAPIKey,",
    b"redisPassword: cfg.Telemetry.ProviderAPIKey,",
])
def test_secret_scan_allows_unquoted_field_references(blob: bytes) -> None:
    from quwoquan_ops.cli import local_readiness as cli

    assert not cli._has_secret_material(blob)


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002
def test_secret_scan_does_not_treat_operation_identifier_suffix_as_credential_label() -> None:
    from quwoquan_ops.cli import local_readiness as cli

    page_ids = ROOT / "quwoquan_app/lib/runtime/transport/generated/user/user_request_page_ids.g.dart"
    assert not cli._has_secret_material(page_ids.read_bytes())
    for label in (b"AccessKeySecret", b"ACCESS_KEY_SECRET", b"API_KEY", b"SECRET", b"PASSWORD", b"ACCESS_TOKEN"):
        assert cli._has_secret_material(label + b" = '" + b"aB9_" * 8 + b"'")


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("label", [b"AppSecret", b"clientSecret", b"redisPassword", b"providerAPIKey", b"sessionAccessToken"])
@pytest.mark.parametrize("quote", [b"", b"'", b'"', b"`"])
def test_secret_scan_rejects_camelcase_sensitive_suffixes(label: bytes, quote: bytes) -> None:
    from quwoquan_ops.cli import local_readiness as cli

    assert cli._has_secret_material(label + b": " + quote + b"aB9_" * 8 + quote)
    assert cli._has_secret_material(b"static const String " + label + b" = " + quote + b"A" * 32 + quote + b";")


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
def test_secret_scan_operation_identifier_exemption_requires_complete_declaration() -> None:
    from quwoquan_ops.cli import local_readiness as cli

    operation = b"ResolvePushEndpointSecret"
    page_id = b"user.resolve.push.endpoint.secret"
    declaration = b"  static const String resolvePushEndpointSecret = '" + page_id + b"';\n"
    mapping = b"  static const Map<String, String> operationToPageId = <String, String>{\n    '" + operation + b"': '" + page_id + b"',\n  };\n"
    source = b"class UserRequestPageIds {\n  const UserRequestPageIds._();\n\n" + mapping + declaration + b"}\n"
    assert not cli._has_secret_material(source)
    assert cli._has_secret_material(declaration)
    assert cli._has_secret_material(source.replace(mapping, b""))
    assert cli._has_secret_material(source.replace(operation, b"DifferentOperation"))
    assert cli._has_secret_material(source.replace(page_id, b"aB9_" * 8))
    assert cli._has_secret_material(source + b"clientSecret: '" + page_id + b"'\n")
    assert cli._has_secret_material(source.replace(b";\n}", b" + 'extra';\n}"))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002
@pytest.mark.parametrize("quote", [b"'", b'"', b"`"])
@pytest.mark.parametrize("value", [b"A" * 32, b"aB9_" * 8, b"cfg.Telemetry.ProviderAPIKey"])
def test_secret_scan_rejects_quoted_material_even_if_identifier_shaped(quote: bytes, value: bytes) -> None:
    from quwoquan_ops.cli import local_readiness as cli

    assert cli._has_secret_material(b"password: " + quote + value + quote)


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002
@pytest.mark.parametrize("blob", [
    b"password: " + b"A" * 32,
    b"password: " + b"aB9_" * 8,
    b"AKIA" + b"A" * 16,
    b"-----BEGIN " + b"PRIVATE KEY-----",
])
def test_secret_scan_preserves_unquoted_material_and_key_detection(blob: bytes) -> None:
    from quwoquan_ops.cli import local_readiness as cli

    assert cli._has_secret_material(blob)


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("path", [
    "quwoquan_ops/cli/local_readiness.py",
    "quwoquan_ops/ci/verify_ci_changed_boundary.py",
    "quwoquan_ops/tests/local_contract/ci/test_local_readiness__state_security__local_contract_test.py",
    "quwoquan_ops/tests/local_contract/ci/test_local_readiness__core__local_contract_test.py",
])
def test_secret_scan_regression_sources_do_not_embed_credential_samples(path: str) -> None:
    from quwoquan_ops.cli import local_readiness as cli

    assert not cli._has_secret_material((ROOT / path).read_bytes())


SECRET_CONFIG_PATH = "quwoquan_service/services/scanner-service/environments/alpha/config.yaml"
SECRET_SCHEMA_PATH = "quwoquan_service/services/scanner-service/config/schema.yaml"
SECRET_CONFIG_KEY = "sys.scanner-service.redis.password"
SECRET_ENV_NAME = "SCANNER_REDIS_GENERAL_PASSWORD"
SECRET_SCHEMA = (
    f"configs:\n- key: {SECRET_CONFIG_KEY}\n  type: string\n  sensitive: true\n"
).encode()


def _secret_config(value: str = SECRET_ENV_NAME) -> bytes:
    return f"secretRefs:\n  {SECRET_CONFIG_KEY}: {value}\n".encode()


def _scan_config(blob: bytes, schema: bytes | None = SECRET_SCHEMA) -> bool:
    from quwoquan_ops.cli import local_readiness as cli

    return cli._has_secret_material(
        blob, path=SECRET_CONFIG_PATH,
        read_blob=lambda path: schema if path == SECRET_SCHEMA_PATH else None,
    )


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("environment", ["alpha", "beta", "gamma", "prod"])
def test_secret_scan_allows_real_schema_declared_environment_refs(environment: str) -> None:
    from quwoquan_ops.cli import local_readiness as cli

    path = f"quwoquan_service/services/content-service/environments/{environment}/config.yaml"
    assert not cli._has_secret_material(
        (ROOT / path).read_bytes(), path=path,
        read_blob=lambda relative: (ROOT / relative).read_bytes(),
    )
    assert not _scan_config(_secret_config())


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("value", [
    "aB9_" * 8,
    "short-literal",
    "A" * 24 + "/suffix",
    "'" + "aB9_" * 8 + "'",
    '"' + "aB9_" * 8 + '"',
    "'" + SECRET_ENV_NAME + "'",
    '"' + SECRET_ENV_NAME + '"',
    "|\n    " + "aB9_" * 8,
    ">-\n    " + SECRET_ENV_NAME,
    "[" + SECRET_ENV_NAME + "]",
    "{password: " + SECRET_ENV_NAME + "}",
    "null",
    "true",
    "123456789012345678901234567890",
    "!!str " + SECRET_ENV_NAME,
    "&credential " + SECRET_ENV_NAME,
])
def test_secret_scan_rejects_noncanonical_secret_ref_values(value: str) -> None:
    assert _scan_config(_secret_config(value))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("schema", [
    None,
    b"configs: []\n",
    SECRET_SCHEMA.replace(b"sensitive: true", b"sensitive: false"),
    SECRET_SCHEMA.replace(b"sensitive: true", b"sensitive: 'true'"),
    SECRET_SCHEMA.replace(b"type: string", b"type: map"),
    SECRET_SCHEMA + SECRET_SCHEMA.removeprefix(b"configs:\n"),
    SECRET_SCHEMA + b"  sensitive: false\n",
])
def test_secret_scan_rejects_undeclared_or_ambiguous_schema_refs(schema: bytes | None) -> None:
    assert _scan_config(_secret_config(), schema)


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("extra", [
    "  sys.scanner-service.unknown.password: " + SECRET_ENV_NAME + "\n",
    "  nested:\n    password: " + SECRET_ENV_NAME + "\n",
    "  " + SECRET_CONFIG_KEY + ": " + SECRET_ENV_NAME + "\n",
    "secretRefs: {}\n",
    "unknown:\n  secretRefs:\n    password: " + SECRET_ENV_NAME + "\n",
    "overrides:\n  " + SECRET_CONFIG_KEY + ": " + SECRET_ENV_NAME + "\n",
    "externalBindings:\n  unknown:\n    password: " + "A" * 32 + "\n",
    "# password: " + "A" * 32 + "\n",
    "---\nsecretRefs: {}\n",
])
def test_secret_scan_does_not_swallow_mixed_unknown_or_nested_values(extra: str) -> None:
    assert _scan_config(_secret_config() + extra.encode())


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("blob", [
    b"password: " + b"A" * 32,
    b"password: '" + b"aB9_" * 8 + b"'",
    b"AKIA" + b"A" * 16,
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN RSA " + b"PRIVATE KEY-----",
])
def test_secret_scan_keeps_all_three_patterns_outside_valid_refs(blob: bytes) -> None:
    assert _scan_config(_secret_config() + b"externalBindings:\n  " + blob + b"\n")


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
def test_secret_scan_requires_structure_and_exact_snapshot_schema() -> None:
    from quwoquan_ops.cli import local_readiness as cli

    blob = _secret_config()
    assert cli._has_secret_material(blob)
    assert cli._has_secret_material(blob, path="unrelated.yaml", read_blob=lambda _: SECRET_SCHEMA)
    assert _scan_config(blob.replace(b"secretRefs:", b"overrides:"))
    assert _scan_config(blob.replace(b"secretRefs:", b"unknown:\n  secretRefs:"))
    assert _scan_config(blob, None)
    # UTF-8 注释改变字符与字节偏移；豁免必须精确落在 env-name，而非注释或相邻值。
    assert not _scan_config("# 配置引用\n".encode() + blob)
    assert _scan_config(_secret_config("AKIA" + "A" * 16))
    assert _scan_config(b"!!set\nsecretRefs: null\n")
    assert _scan_config(b"secretRefs: {" + SECRET_CONFIG_KEY.encode() + b": '" + b"aB9_" * 8 + b"'}\n")
    assert _scan_config(b"secretRefs:\n  <<: {" + SECRET_CONFIG_KEY.encode() + b": " + SECRET_ENV_NAME.encode() + b"}\n")
    assert _scan_config(blob + b"externalBindings:\n  unknown:\n    password: *missing\n")


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003
@pytest.mark.parametrize("boundary", ["staged", "ci"])
@pytest.mark.parametrize("case", [
    "valid", "literal", "unknown", "missing_schema", "nonsensitive_schema", "field_reference",
    "camel_AppSecret", "camel_clientSecret", "camel_redisPassword",
])
def test_secret_scan_boundaries_consume_their_exact_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, boundary: str, case: str,
) -> None:
    from quwoquan_ops.ci import verify_ci_changed_boundary as ci
    from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan
    from quwoquan_ops.cli import local_readiness as cli

    config = _secret_config("aB9_" * 8) if case == "literal" else _secret_config()
    if case == "unknown":
        config = config.replace(SECRET_CONFIG_KEY.encode(), b"sys.scanner-service.unknown.password")
    schema = SECRET_SCHEMA.replace(b"sensitive: true", b"sensitive: false") if case == "nonsensitive_schema" else SECRET_SCHEMA
    blobs = {SECRET_CONFIG_PATH: config, SECRET_SCHEMA_PATH: schema}
    if case == "missing_schema":
        del blobs[SECRET_SCHEMA_PATH]
    changed_path = SECRET_CONFIG_PATH
    if case.startswith("camel_") or case == "field_reference":
        changed_path = "quwoquan_service/services/scanner-service/cmd/api/config.go"
        label = case.removeprefix("camel_").encode()
        blobs[changed_path] = label + b': "' + b"aB9_" * 8 + b'",\n'
        if case == "field_reference":
            blobs[changed_path] = b"AppSecret: ossBinding.AccessKeySecret,\n"
    # 工作树始终有合法声明；两个入口都不能用它覆盖快照的缺失/非敏感声明。
    worktree_schema = tmp_path / SECRET_SCHEMA_PATH
    worktree_schema.parent.mkdir(parents=True)
    worktree_schema.write_bytes(SECRET_SCHEMA)
    observed: list[str] = []
    if boundary == "staged":
        monkeypatch.setattr(cli, "ROOT", tmp_path)
        monkeypatch.setattr(cli, "staged_paths", lambda _: [changed_path])
        monkeypatch.setattr(cli, "_assert_no_staged_unstaged_overlap", lambda _: None)

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            assert kwargs["cwd"] == tmp_path
            if "--local-commit" in command:
                return subprocess.CompletedProcess(command, 0, b"", b"")
            assert command[:2] == ["git", "show"]
            assert command[2].startswith(":")
            path = command[2][1:]
            observed.append(path)
            return subprocess.CompletedProcess(command, 0 if path in blobs else 1, blobs.get(path, b""), b"")

        monkeypatch.setattr(cli.subprocess, "run", run)
        invoke = lambda: cli.command_staged_boundary(None)
    else:
        source = "b" * 40
        tree = "sha1:" + "c" * 40
        plan = build_delivery_impact_plan(
            [changed_path], source_sha=source, base_sha="a" * 40,
            source_tree_digest=tree,
        )
        plan_path = tmp_path / "impact-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        monkeypatch.setattr(ci, "ROOT", tmp_path)

        def candidate_blob(sha: str, path: str) -> bytes | None:
            assert sha == source
            observed.append(path)
            return blobs.get(path)

        monkeypatch.setattr(ci, "_candidate_blob", candidate_blob)
        invoke = lambda: ci.verify(
            plan_path, expected_source_sha=source, expected_tree_digest=tree,
            expected_plan_digest=plan["plan_digest"],
        )
    if case in {"valid", "field_reference"}:
        invoke()
    else:
        with pytest.raises(cli.LocalReadinessError, match="secret material detected"):
            invoke()
    expected_reads = [changed_path, SECRET_SCHEMA_PATH] if changed_path == SECRET_CONFIG_PATH else [changed_path]
    assert observed == expected_reads


@pytest.mark.parametrize("case", ["binary_digits", "text_digits", "binary_secret"])
def test_ci_binary_pii_boundary_keeps_secret_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    from quwoquan_ops.ci import verify_ci_changed_boundary as ci
    from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan
    from quwoquan_ops.cli import local_readiness as cli

    source, tree = "b" * 40, "sha1:" + "c" * 40
    path = "quwoquan_app/assets/content/alpha/media/test.mp4"
    digits = b"138" + b"12345678"
    blob = b"\x00\x00\x00\x18ftypmp42 " + digits
    if case == "text_digits":
        blob = digits
    elif case == "binary_secret":
        blob += b"\n-----BEGIN " + b"PRIVATE KEY-----\n"
    plan = build_delivery_impact_plan([path], source_sha=source, base_sha="a" * 40, source_tree_digest=tree)
    plan_path = tmp_path / "impact-plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(ci, "_candidate_blob", lambda sha, ref: blob if sha == source and ref == path else None)
    if case == "binary_digits":
        ci.verify(plan_path, expected_source_sha=source, expected_tree_digest=tree, expected_plan_digest=plan["plan_digest"])
    else:
        expected = "secret material" if case == "binary_secret" else "direct PII"
        with pytest.raises(cli.LocalReadinessError, match=expected):
            ci.verify(plan_path, expected_source_sha=source, expected_tree_digest=tree, expected_plan_digest=plan["plan_digest"])


def _repo() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory()


def _init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "checkout", "-qb", "dev1.0"], cwd=path, check=True)
    (path / "docs").mkdir()
    (path / "docs/source.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/source.txt"], cwd=path, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "base",
        ],
        cwd=path,
        check=True,
    )


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t1
def test_state_root_rejects_symlink_components_and_secures_temp_repo_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = repo / "state"
    assert _state_root(state) == state.absolute()
    assert state.is_dir()
    assert state.stat().st_mode & 0o077 == 0

    target = repo / "target"
    target.mkdir()
    linked = repo / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(LocalReadinessError, match="symlink component"):
        _state_root(linked / "state")
    monkeypatch.setenv("QWQ_LOCAL_READINESS_ROOT", str(linked / "override"))
    with pytest.raises(LocalReadinessError, match="symlink component"):
        _state_root()


def test_empty_legacy_queue_is_safely_projected_to_current_schema(tmp_path: Path) -> None:
    from lib.local_readiness.queue import read_queue

    queue = tmp_path / "queue.json"
    queue.write_text('{"schema":"local-readiness-queue-v1","items":[]}\n', encoding="utf-8")
    assert read_queue(queue) == {"schema": "local-readiness-queue-v2", "items": []}
    queue.write_text('{"schema":"local-readiness-queue-v1","items":[{}]}\n', encoding="utf-8")
    with pytest.raises(LocalReadinessError, match="queue schema"):
        read_queue(queue)


def test_queue_corruption_symlink_and_extra_fields_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
    state = repo / "state"
    queue = state / "process/deferred-queue.json"
    enqueue_paths(["docs/source.txt"], state_root=state)

    corruptions = [
        {"schema": "local-readiness-queue-v2", "items": [], "extra": True},
        {"schema": "local-readiness-queue-v2", "items": [{**json.loads(queue.read_text())["items"][0], "extra": True}]},
        {"schema": "wrong", "items": []},
    ]
    for value in corruptions:
        queue.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(LocalReadinessError, match="queue"):
            enqueue_paths(["docs/source.txt"], state_root=state)

    external = repo / "external-queue.json"
    external.write_text('{"schema":"local-readiness-queue-v2","items":[]}', encoding="utf-8")
    queue.unlink()
    queue.symlink_to(external)
    with pytest.raises(LocalReadinessError, match="regular file|symlink"):
        enqueue_paths(["docs/source.txt"], state_root=state)
    queue.unlink()
    queue.mkdir()
    with pytest.raises(LocalReadinessError, match="regular file"):
        enqueue_paths(["docs/source.txt"], state_root=state)


def test_atomic_write_and_resource_lock_reject_destination_symlinks(tmp_path: Path) -> None:
    state = tmp_path / "state"
    external = tmp_path / "external.json"
    external.write_text("unchanged\n", encoding="utf-8")
    destination = state / "process/value.json"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(external)
    with pytest.raises(LocalReadinessError, match="destination"):
        _atomic_json(destination, {"status": "PASS"})
    assert external.read_text(encoding="utf-8") == "unchanged\n"

    locks = state / "process/locks"
    locks.mkdir()
    locks.rmdir()
    lock_target = tmp_path / "external-locks"
    lock_target.mkdir()
    locks.symlink_to(lock_target, target_is_directory=True)
    with pytest.raises(LocalReadinessError, match="symlink"):
        with resource_lock("runner", state_root=state):
            pass

    locks.unlink()
    locks.mkdir()
    external_lock = tmp_path / "external.lock"
    external_lock.touch()
    (locks / "runner.lock").symlink_to(external_lock)
    with pytest.raises(LocalReadinessError, match="lock|regular file"):
        with resource_lock("runner", state_root=state):
            pass


def test_cache_read_rejects_symlink_before_reuse(tmp_path: Path) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        cache = state / "cache/exact-input" / f"{receipt['fingerprint']['digest'].removeprefix('sha256:')}.json"
        external = Path(tempfile.mkdtemp()) / "external-cache.json"
        external.write_bytes(cache.read_bytes())
        cache.unlink()
        cache.symlink_to(external)
        with pytest.raises(LocalReadinessError, match="cache.*regular file|cache.*symlink"):
            run_readiness(plan, repo_root=repo, state_root=state)
        cache.unlink()
        cache.mkdir()
        with pytest.raises(LocalReadinessError, match="cache.*regular file"):
            run_readiness(plan, repo_root=repo, state_root=state)


def test_pointer_receipt_path_is_confined_and_reads_reject_symlinks(tmp_path: Path) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        pointer = next((state / "process/receipts/current").glob("*.json"))
        immutable = state / "process/receipts/by-fingerprint" / f"{receipt['fingerprint']['digest'].removeprefix('sha256:')}.json"
        external = repo / "external-receipt.json"
        external.write_text(immutable.read_text(encoding="utf-8"), encoding="utf-8")

        for raw in (str(external), "../../../../external-receipt.json"):
            value = json.loads(pointer.read_text(encoding="utf-8"))
            value["receipt"] = raw
            pointer.write_text(json.dumps(value), encoding="utf-8")
            with pytest.raises(LocalReadinessError, match="canonical|receipt"):
                verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)

        value = {"schema": "local-readiness-current-pointer-v1", "receipt": str(immutable), "fingerprint": receipt["fingerprint"]["ref"]}
        pointer.write_text(json.dumps(value), encoding="utf-8")
        pointer_target = repo / "pointer-target.json"
        pointer.replace(pointer_target)
        pointer.symlink_to(pointer_target)
        with pytest.raises(LocalReadinessError, match="pointer.*regular file|pointer.*symlink"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)

        pointer.unlink()
        pointer.mkdir()
        with pytest.raises(LocalReadinessError, match="pointer.*regular file"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        pointer.rmdir()
        pointer_target.replace(pointer)
        receipt_target = repo / "receipt-target.json"
        immutable.replace(receipt_target)
        immutable.symlink_to(receipt_target)
        with pytest.raises(LocalReadinessError, match="receipt.*regular file|receipt.*symlink"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        immutable.unlink()
        immutable.mkdir()
        with pytest.raises(LocalReadinessError, match="receipt.*regular file"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
