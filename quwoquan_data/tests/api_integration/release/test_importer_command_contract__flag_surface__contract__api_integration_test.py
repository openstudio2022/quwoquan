# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""Data ship 组装的 importer 命令与 service 侧 importer 真实 flag 面的跨仓契约。

`run_tag/creator/content/homepage_importer` 组装 `go run <service cmd>` 命令，
service 侧 flag 改名或删除不会被 Data 侧 local_contract 的命令断言发现。本测试
把 Data 生产代码组装出的每条命令**真实执行**（存储端点替换为不可达、release
root 替换为空目录），断言进程通过 flag 解析进入业务阶段——flag 面漂移会在
Go flag 解析层立即失败并被捕获。附带未知 flag 负例证明探测手段本身有效。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.environment import importers  # noqa: E402
from content.release.model import ImportMode  # noqa: E402

GO_FLAG_ERROR_TOKENS = (
    "flag provided but not defined",
    "flag needs an argument",
)

#: 端点不可达但语法合法；importer 必须先通过 flag 解析才会触达这些端点。
UNREACHABLE_MONGO = (
    "mongodb://127.0.0.1:1/flag-probe?serverSelectionTimeoutMS=200&connectTimeoutMS=200"
)
UNREACHABLE_POSTGRES = "postgres://flag-probe@127.0.0.1:1/flag-probe?connect_timeout=1"


def _assembled_commands(tmp_path: Path) -> list[tuple[list[str], Path]]:
    """从 Data 生产组装逻辑收集全部 importer 命令与各自 cwd（唯一真相源）。

    ``importers.subprocess`` 即全局 subprocess 模块，收集期的 patch 必须在
    真实执行阶段前恢复，因此使用局部 MonkeyPatch 上下文。
    """
    release = tmp_path / "releases/release-a"
    run = tmp_path / "runs/apply-a"
    (release / "payload").mkdir(parents=True)
    commands: list[tuple[list[str], Path]] = []

    def record_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append((list(command), Path(str(kwargs["cwd"]))))
        return SimpleNamespace(returncode=0)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(importers.subprocess, "run", record_run)
        patch.setattr(
            importers,
            "assert_import_report_contract",
            lambda *_a, **_k: {
                "tagRefs": [],
                "nodeCount": 0,
                "issues": [],
                "skipped": [],
                "projected": 0,
                "entityRefToHomepageId": {},
            },
        )
        patch.setattr(
            importers,
            "read_json",
            lambda _path: {"desiredRefs": {"entities": [], "tags": [], "creators": []}},
        )
        patch.setattr(importers, "payload_digest", lambda _release: "sha256:" + "0" * 64)

        importers.run_tag_importer(
            release=release,
            env="alpha",
            run=run,
            mongo_uri=UNREACHABLE_MONGO,
            dry_run=True,
        )
        importers.run_creator_importer(
            release=release,
            env="alpha",
            run=run,
            mongo_uri=UNREACHABLE_MONGO,
            postgres_dsn=UNREACHABLE_POSTGRES,
            media_avatar_base_url="https://cdn.example.invalid",
            dry_run=True,
        )
        importers.run_content_importer(
            release=release,
            env="alpha",
            run=run,
            mongo_uri=UNREACHABLE_MONGO,
            media_avatar_base_url="https://cdn.example.invalid",
            media_image_base_url="https://cdn.example.invalid",
            media_video_base_url="https://cdn.example.invalid",
            dry_run=True,
            creator_receipt=run / "creator-import.json",
        )
        importers.run_homepage_importer(
            release=release,
            env="alpha",
            run=run,
            run_id="apply-a",
            mongo_uri=UNREACHABLE_MONGO,
            media_image_base_url="https://cdn.example.invalid",
            dry_run=True,
            mode=ImportMode.UPSERT,
        )
    assert len(commands) == 4
    return commands


def _execute(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return (result.stdout or "") + (result.stderr or "")


@pytest.mark.api_integration
def test_every_assembled_importer_command_passes_the_real_flag_surface(
    tmp_path: Path,
) -> None:
    for command, cwd in _assembled_commands(tmp_path):
        output = _execute(command, cwd)
        for token in GO_FLAG_ERROR_TOKENS:
            assert token not in output, (
                "importer flag surface drifted between quwoquan_data and "
                f"quwoquan_service: {' '.join(command[:3])} -> {output[-800:]}"
            )


@pytest.mark.api_integration
def test_unknown_flag_is_rejected_so_the_probe_cannot_go_stale(
    tmp_path: Path,
) -> None:
    command, cwd = _assembled_commands(tmp_path)[0]
    output = _execute([*command, "--qwq-flag-probe-unknown"], cwd)
    assert "flag provided but not defined" in output, output[-800:]
