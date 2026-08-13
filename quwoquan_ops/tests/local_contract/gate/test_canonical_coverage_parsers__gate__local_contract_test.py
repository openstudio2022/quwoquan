# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` 覆盖率产物解析口径的本地契约。

由 test_canonical_coverage__gate__local_contract_test.py（Python 1000 行硬顶
治理）按场景拆出：lcov 分支只认 BRDA 明细、Go coverprofile 按语句去重计量、
Python trace 保留零命中文件分母，畸形输入一律阻断。测试逐字搬移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_canonical_coverage as vcr


# ---------------------------------------------------------------------------
# 解析口径
# ---------------------------------------------------------------------------

_LCOV_TWO_FILES = "\n".join(
    [
        "SF:lib/a.dart",
        "DA:1,1",
        "DA:2,0",
        "BRDA:1,0,0,1",
        "BRDA:1,0,1,0",
        "BRDA:2,0,0,-",
        "BRDA:2,0,1,4",
        "LF:10",
        "LH:7",
        "end_of_record",
        "SF:lib/b.dart",
        "LF:10",
        "LH:3",
        # 无分支的文件不会写任何 BRDA。
        "end_of_record",
        "",
    ]
)


def test_lcov_parser_keeps_per_file_records_so_buckets_can_be_attributed() -> None:
    parsed = vcr.parse_lcov(_LCOV_TWO_FILES)

    assert sorted(parsed) == ["lib/a.dart", "lib/b.dart"]
    assert parsed["lib/a.dart"]["line"] == (7, 10)
    assert parsed["lib/b.dart"]["line"] == (3, 10)
    # 分支没有汇总行，只能数 BRDA：4 条，其中 taken 既不是 `-` 也不是 `0` 的有 2 条。
    assert parsed["lib/a.dart"]["branch"] == (2, 4)
    assert parsed["lib/b.dart"]["branch"] == (0, 0)


def test_branch_coverage_comes_from_brda_because_flutter_writes_no_summary() -> None:
    """回归守卫：Flutter 3.44 只写 BRDA。

    照 `BRF`/`BRH` 解析会让每个文件的分支分母恒为 0，把「测不出分支」伪装成
    「这个文件没有分支」，分支阈值随之失效——这正是本门禁要防的那类假绿。
    """
    assert "BRF:" not in _LCOV_TWO_FILES
    assert "BRH:" not in _LCOV_TWO_FILES

    total = sum(
        values["branch"][1] for values in vcr.parse_lcov(_LCOV_TWO_FILES).values()
    )

    assert total == 4, "没有汇总行时分支分母必须来自 BRDA 明细"


def test_lcov_branch_summary_disagreeing_with_brda_blocks() -> None:
    """若某天产出里出现 BRF/BRH，必须与 BRDA 一致，不允许两套口径并存。"""
    consistent = "SF:lib/a.dart\nBRDA:1,0,0,1\nBRDA:1,0,1,0\nBRF:2\nBRH:1\nLF:1\nLH:1\nend_of_record\n"

    assert vcr.parse_lcov(consistent)["lib/a.dart"]["branch"] == (1, 2)

    for drifted in (
        "SF:lib/a.dart\nBRDA:1,0,0,1\nBRF:9\nLF:1\nLH:1\nend_of_record\n",
        "SF:lib/a.dart\nBRDA:1,0,0,1\nBRH:9\nLF:1\nLH:1\nend_of_record\n",
    ):
        with pytest.raises(vcr.CoverageError):
            vcr.parse_lcov(drifted)


def test_lcov_parser_rejects_a_file_without_any_record() -> None:
    with pytest.raises(vcr.CoverageError):
        vcr.parse_lcov("TN:\n")


def test_go_coverprofile_parser_counts_statements_not_blocks() -> None:
    text = "\n".join(
        [
            "mode: atomic",
            "pkg/a.go:1.1,3.2 5 1",
            "pkg/a.go:5.1,6.2 2 0",
            "pkg/b.go:1.1,2.2 3 7",
            "",
        ]
    )

    parsed = vcr.parse_go_coverprofile(text)
    files = vcr.parse_go_coverprofile_files(text)

    # 分母是语句数（5+2+3），不是块数；未执行的块（count=0）不计入分子。
    assert parsed["statement"] == (8, 10)
    assert files == {"pkg/a.go": (5, 7), "pkg/b.go": (3, 3)}
    assert vcr.percent(*parsed["statement"]) == 80.0


def test_go_coverprofile_parser_merges_repeated_blocks_from_multiple_binaries() -> None:
    """同一个块会被多个测试二进制各写一份，必须按块去重后再累加计数。"""
    text = "\n".join(
        [
            "mode: atomic",
            "pkg/a.go:1.1,3.2 5 0",
            "pkg/a.go:1.1,3.2 5 4",
            "pkg/a.go:5.1,6.2 2 0",
            "pkg/a.go:5.1,6.2 2 0",
            "",
        ]
    )

    assert vcr.parse_go_coverprofile(text)["statement"] == (5, 7)


def test_go_coverprofile_parser_rejects_malformed_input() -> None:
    with pytest.raises(vcr.CoverageError):
        vcr.parse_go_coverprofile("pkg/a.go:1.1,3.2 5 1\n")
    with pytest.raises(vcr.CoverageError):
        vcr.parse_go_coverprofile("mode: atomic\nnot a block record\n")
    with pytest.raises(vcr.CoverageError):
        vcr.parse_go_coverprofile("mode: atomic\n")


def test_python_trace_parser_keeps_zero_hit_files_in_the_denominator() -> None:
    target = "quwoquan_service/services/recommendation-service"
    parsed = vcr.parse_python_trace_files(
        json.dumps(
            {
                "schema": vcr.PYTHON_TRACE_ARTIFACT_SCHEMA,
                "files": {
                    "internal/recommendation/recommendation_exposure_fact/"
                    "application/appender.py": {
                        "coveredStatements": 7,
                        "totalStatements": 9,
                    },
                    "internal/recommendation/recommendation_exposure_fact/"
                    "infrastructure/mongo_store.py": {
                        "coveredStatements": 0,
                        "totalStatements": 5,
                    },
                },
            }
        ),
        target,
    )

    prefix = "services/recommendation-service/"
    assert parsed == {
        prefix
        + "internal/recommendation/recommendation_exposure_fact/"
        + "application/appender.py": (7, 9),
        prefix
        + "internal/recommendation/recommendation_exposure_fact/"
        + "infrastructure/mongo_store.py": (0, 5),
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema": "stale", "files": {}},
        {
            "schema": vcr.PYTHON_TRACE_ARTIFACT_SCHEMA,
            "files": {"../escape.py": {"coveredStatements": 1, "totalStatements": 1}},
        },
        {
            "schema": vcr.PYTHON_TRACE_ARTIFACT_SCHEMA,
            "files": {
                "internal/probe.py": {
                    "coveredStatements": 2,
                    "totalStatements": 1,
                }
            },
        },
    ],
)
def test_python_trace_parser_rejects_unknown_or_malformed_input(payload: dict) -> None:
    with pytest.raises(vcr.CoverageError):
        vcr.parse_python_trace_files(
            json.dumps(payload),
            "quwoquan_service/services/recommendation-service",
        )
