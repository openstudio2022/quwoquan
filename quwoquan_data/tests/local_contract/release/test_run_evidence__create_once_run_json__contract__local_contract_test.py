"""create_run 的 create-once 判据绑定 run.json，而非 run 目录本身。

research 编排允许环境 owner 先把 create-once runtime proof 写进同一
verify run 目录；ship verify 随后创建 run.json 仍必须成功，而重复的
run.json 必须保持 append-only 拒绝。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment.run_evidence import create_run  # noqa: E402

_VALID = frozenset({"gamma"})


def _create(tmp_path: Path) -> Path:
    return create_run(
        output_root=tmp_path,
        environment="gamma",
        release_id="release-a",
        run_id="research-api-001",
        kind="verify",
        valid_environments=_VALID,
    )


def test_create_run_accepts_predeposited_runtime_proof_directory(
    tmp_path: Path,
) -> None:
    run_dir = (
        tmp_path
        / "env/gamma/runs/data-release/release-a/research-api-001"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "research-isolation-runtime-proof.json").write_text(
        "{}",
        encoding="utf-8",
    )

    created = _create(tmp_path)

    assert created == run_dir
    assert (created / "run.json").is_file()
    assert (created / "research-isolation-runtime-proof.json").is_file()


def test_create_run_rejects_existing_run_json(tmp_path: Path) -> None:
    _create(tmp_path)

    with pytest.raises(SystemExit, match="append-only run 已存在"):
        _create(tmp_path)
