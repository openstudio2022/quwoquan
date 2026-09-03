from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree.py"
SPEC = importlib.util.spec_from_file_location("feature_tree_manifest_writer", MODULE_PATH)
assert SPEC and SPEC.loader
feature_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feature_tree
SPEC.loader.exec_module(feature_tree)

from quwoquan_ops.cli.lib.feature_tree import commands as ft_commands  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import context as ft_context  # noqa: E402
from quwoquan_ops.cli.lib.feature_context_fingerprint import (  # noqa: E402
    validate_content_addressed_ref,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    tree = root / "specs" / "feature-tree"
    write(tree / "spec.md", "# AppRoot Spec：演示\n")
    write(tree / "design.md", "# AppRoot Design：演示\n")
    write(tree / "domain" / "spec.md", "# L1 Domain Service：领域 (`domain`)\n")
    write(tree / "domain" / "design.md", "# L1 Design：领域 (`domain`)\n")
    write(
        tree / "domain" / "capability" / "spec.md",
        "# L2 Business Capability：能力 (`capability`)\n",
    )
    write(
        tree / "domain" / "capability" / "story" / "spec.md",
        "# L3 Story：故事 (`story`)\n",
    )
    return root


def test_two_targets_write_distinct_immutable_refs_without_cross_consumption(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    target_a = "specs/feature-tree/domain/spec.md"
    target_b = "specs/feature-tree/domain/capability/spec.md"
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(
        ft_context, "OUTPUT_ROOT",
        root / ".qwq_output/env/repo/runs/feature-tree",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    write(root / "quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture generator\n")
    write(root / "quwoquan_ops/policies/agent_governance_contract.yaml", "schema_version: 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=root, check=True,
    )

    barrier = __import__("threading").Barrier(2)

    def produce(target: str) -> tuple[str, dict[str, object]]:
        nodes = feature_tree.discover_nodes()
        resolution = feature_tree.resolve_target_details(target, nodes)
        manifest = ft_commands._context_manifest(target, resolution, nodes)
        content = ft_commands.canonical_json_bytes(manifest)
        barrier.wait()
        ref = ft_commands._write_content_addressed_bytes(content)
        relative = ref.relative_to(root).as_posix()
        return relative, json.loads(ref.read_bytes())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(produce, (target_a, target_b)))
    refs = [item[0] for item in results]
    assert refs[0] != refs[1]
    for (ref, manifest), expected_target in zip(results, (target_a, target_b)):
        raw = (root / ref).read_bytes()
        assert Path(ref).name == hashlib.sha256(raw).hexdigest() + ".json"
        validate_content_addressed_ref(ref, raw_bytes=raw, repo_root=root)
        assert manifest["target"] == expected_target
        assert json.loads(raw)["target"] == expected_target
        assert "profiles" not in manifest


@pytest.mark.skipif(
    not hasattr(ft_commands.fcntl, "F_GETPATH"),
    reason="仅 macOS F_GETPATH 可用时验证",
)
def test_fd_path_reads_current_macos_directory_with_bytes_buffer() -> None:
    descriptor = ft_commands.os.open(
        ROOT, ft_commands.os.O_RDONLY | ft_commands.os.O_DIRECTORY
    )
    try:
        assert ft_commands._fd_path(descriptor).resolve(strict=True) == ROOT.resolve(
            strict=True
        )
    finally:
        ft_commands.os.close(descriptor)


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (bytearray(1024), "返回类型无效"),
        (b"", "返回空结果"),
        (b"/tmp/no-terminator", "缺少 NUL 终止符"),
        (bytes(1024), "返回空路径"),
        (b"/tmp/\xff\0" + bytes(1017), "不是有效 UTF-8"),
    ],
)
def test_fd_path_blocks_invalid_f_getpath_results(
    monkeypatch,
    raw: object,
    error: str,
) -> None:
    monkeypatch.setattr(ft_commands.fcntl, "F_GETPATH", 50, raising=False)

    def fake_fcntl(descriptor: int, operation: int, buffer: bytes) -> object:
        assert descriptor == 123
        assert operation == 50
        assert type(buffer) is bytes
        assert len(buffer) == 1024
        return raw

    monkeypatch.setattr(ft_commands.fcntl, "fcntl", fake_fcntl)

    with pytest.raises(OSError, match=error):
        ft_commands._fd_path(123)


@pytest.mark.parametrize("error", [OSError("boom"), TypeError("boom")])
def test_fd_path_propagates_f_getpath_call_failure(
    monkeypatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(ft_commands.fcntl, "F_GETPATH", 50, raising=False)

    def fail_fcntl(descriptor: int, operation: int, buffer: bytes) -> bytes:
        assert descriptor == 123
        assert operation == 50
        assert type(buffer) is bytes
        assert len(buffer) == 1024
        raise error

    monkeypatch.setattr(ft_commands.fcntl, "fcntl", fail_fcntl)

    with pytest.raises(type(error), match="boom"):
        ft_commands._fd_path(123)


@pytest.mark.parametrize("symlink_location", ["output-root", "by-fingerprint"])
def test_content_addressed_writer_blocks_outside_directory_symlink_without_writes(
    tmp_path: Path,
    monkeypatch,
    symlink_location: str,
) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    output_root = root / ".qwq_output/env/repo/runs/feature-tree"
    output_root.parent.mkdir(parents=True)
    if symlink_location == "output-root":
        output_root.symlink_to(outside, target_is_directory=True)
    else:
        output_root.mkdir()
        (output_root / "by-fingerprint").symlink_to(
            outside, target_is_directory=True
        )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "OUTPUT_ROOT", output_root)

    with pytest.raises(ValueError, match="GATE_BLOCK:"):
        ft_commands._write_content_addressed_bytes(b"outside must stay empty")

    assert list(outside.iterdir()) == []


def test_content_addressed_writer_blocks_receipts_symlink_without_outside_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    output_root = root / ".qwq_output/env/repo/runs/feature-tree"
    by_fingerprint = output_root / "by-fingerprint"
    by_fingerprint.mkdir(parents=True)
    (by_fingerprint / "receipts").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "OUTPUT_ROOT", output_root)

    with pytest.raises(ValueError, match="GATE_BLOCK:"):
        ft_commands._write_content_addressed_bytes(
            b"receipt outside must stay empty", subdirectory="receipts"
        )

    assert list(outside.iterdir()) == []


def test_same_content_concurrent_create_once_keeps_exact_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "repo"
    output_root = root / ".qwq_output/env/repo/runs/feature-tree"
    output_root.parent.mkdir(parents=True)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "OUTPUT_ROOT", output_root)
    content = b'{"same":"immutable bytes"}'
    barrier = __import__("threading").Barrier(8)

    def create_once(_: int) -> Path:
        barrier.wait()
        return ft_commands._write_content_addressed_bytes(content)

    with ThreadPoolExecutor(max_workers=8) as pool:
        refs = list(pool.map(create_once, range(8)))

    assert len(set(refs)) == 1
    assert refs[0].read_bytes() == content
    assert list(refs[0].parent.glob("*.json")) == [refs[0]]
    assert not list(refs[0].parent.glob("*.tmp"))


def test_content_addressed_filename_uses_manifest_bytes_not_evidence_digest(
    tmp_path: Path, monkeypatch,
) -> None:
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(
        ft_context, "OUTPUT_ROOT",
        root / ".qwq_output/env/repo/runs/feature-tree",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    write(root / "quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture generator\n")
    write(root / "quwoquan_ops/policies/agent_governance_contract.yaml", "schema_version: 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=root, check=True,
    )
    nodes = feature_tree.discover_nodes()
    target = "specs/feature-tree/domain/spec.md"
    manifest = ft_commands._context_manifest(
        target, feature_tree.resolve_target_details(target, nodes), nodes
    )
    raw = ft_commands.canonical_json_bytes(manifest)
    ref = ft_commands._write_content_addressed_bytes(raw).relative_to(root).as_posix()
    manifest_digest = hashlib.sha256(raw).hexdigest()
    evidence_digest = str(manifest["evidence_fingerprint"]["digest"]).removeprefix("sha256:")
    assert Path(ref).stem == manifest_digest
    assert Path(ref).stem != evidence_digest


def _configure_writer_root(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    output_root = root / ".qwq_output/env/repo/runs/feature-tree"
    output_root.parent.mkdir(parents=True)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "OUTPUT_ROOT", output_root)
    return root, output_root


def test_content_addressed_writer_rejects_existing_final_symlink_fifo_and_hardlink(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    content = b'{"immutable":"existing"}'
    for kind in ("symlink", "fifo", "hardlink"):
        case_root = tmp_path / kind
        _, output_root = _configure_writer_root(case_root, monkeypatch)
        final = ft_commands._content_addressed_path(content)
        final.parent.mkdir(parents=True)
        if kind == "symlink":
            outside = case_root / "outside.json"
            outside.write_bytes(content)
            final.symlink_to(outside)
        elif kind == "fifo":
            os.mkfifo(final)
        else:
            source = case_root / "source.json"
            source.write_bytes(content)
            os.link(source, final)
        with pytest.raises(ValueError, match="GATE_BLOCK:"):
            ft_commands._write_content_addressed_bytes(content)
        assert output_root.exists()


def test_content_addressed_writer_rejects_hardlink_inserted_before_final_reopen(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t4
    _, output_root = _configure_writer_root(tmp_path, monkeypatch)
    content = b'{"immutable":"race"}'
    real_link = ft_commands.os.link
    linked_alias: Path | None = None

    def link_and_alias(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        nonlocal linked_alias
        real_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )
        real_link(
            destination,
            "attacker-hardlink.json",
            src_dir_fd=dst_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=False,
        )
        linked_alias = output_root / "by-fingerprint/attacker-hardlink.json"

    monkeypatch.setattr(ft_commands.os, "link", link_and_alias)
    with pytest.raises(ValueError, match="exact bytes 校验失败"):
        ft_commands._write_content_addressed_bytes(content)
    assert linked_alias is not None and linked_alias.exists()


def test_content_addressed_writer_rejects_final_path_replacement_before_reopen(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    _, output_root = _configure_writer_root(tmp_path, monkeypatch)
    content = b'{"immutable":"expected"}'
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b'{"immutable":"replacement"}')
    real_link = ft_commands.os.link
    replaced = False

    def link_then_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        nonlocal replaced
        real_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )
        replacement.replace(output_root / "by-fingerprint" / destination)
        replaced = True

    monkeypatch.setattr(ft_commands.os, "link", link_then_replace)
    with pytest.raises(ValueError, match="内容冲突"):
        ft_commands._write_content_addressed_bytes(content)
    assert replaced


def test_content_addressed_writer_rejects_path_replacement_during_final_read(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t4
    _, _ = _configure_writer_root(tmp_path, monkeypatch)
    content = b'{"immutable":"single-link"}'
    ref = ft_commands._write_content_addressed_bytes(content)
    assert ref.read_bytes() == content
    assert ref.stat().st_nlink == 1

    replacement = ref.parent / "replacement.json"
    replacement.write_bytes(b"replacement")
    real_read = os.read
    replaced = False

    def replace_path_then_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        if not replaced:
            replaced = True
            replacement.replace(ref)
        return real_read(descriptor, size)

    monkeypatch.setattr(os, "read", replace_path_then_read)
    directory_fd = os.open(ref.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(ValueError, match="目录项身份漂移"):
            ft_commands._read_exact_bytes_at(directory_fd, ref.name)
    finally:
        os.close(directory_fd)
    assert replaced
    assert ref.read_bytes() == b"replacement"
