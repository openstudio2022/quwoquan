"""no-fake 门禁的词法判定常量：占位/skip/替身/环境命名的正则与替身库名册。"""

from __future__ import annotations

import re

PLACEHOLDER_PATTERNS = (
    re.compile(r"\bassert\s*\(\s*true\s*\)"),
    re.compile(r"\bexpect\s*\(\s*true\s*,\s*isTrue\s*\)"),
    re.compile(r"\bTODO_FAKE_TEST\b"),
)
SKIP_PATTERNS = (
    re.compile(r"\bpytest\s*\.\s*skip\s*\("),
    re.compile(r"@\s*pytest\s*\.\s*mark\s*\.\s*skip\b"),
    re.compile(r"@\s*unittest\s*\.\s*skip\b"),
    re.compile(r"\b(?:t|b)\s*\.\s*Skip(?:f)?\s*\("),
    re.compile(r"\bskip\s*:\s*true\b"),
    re.compile(r"\bos\s*\.\s*Exit\s*\(\s*0\s*\)"),
)
#: 进程内替身库：这些包的存在意义就是把真实依赖换成替身，判定对象是包名本身。
#: 刻意不含 `net/http/httptest`——api_integration 用 `httptest.NewRecorder/NewRequest`
#: 驱动**真实** handler（今日 142 个文件），它不是替身而是传输壳，列进来等于制造 142 个误报。
SUBSTITUTE_LIBRARY_IMPORTS = (
    "github.com/golang/mock",
    "go.uber.org/mock",
    "github.com/stretchr/testify/mock",
    "github.com/alicebob/miniredis",
    "github.com/DATA-DOG/go-sqlmock",
    "unittest.mock",
    "mock",
    "requests_mock",
    "responses",
    "package:mocktail",
    "package:mockito",
    "package:http/testing.dart",
    "package:quwoquan_cloud_mock",
)
#: 构建约束是编译器可见的结构事实。
FAKE_BUILD_TAG_RE = re.compile(
    r"(?m)^//\s*(?:go:build|\+build)\b.*\b(?:fake|mock|stub)\b"
)
_SUBSTITUTE_INFRA_SUFFIX = (
    r"(?:Store|Repository|Client|Writer|Reader|Executor|Transport|Gateway|"
    r"Clock|Queue|Cache|Database|Backend|Service)"
)
SUBSTITUTE_CALL_NAME_RE = re.compile(
    rf"^(?:(?:New|new)(?:InMemory|Memory)[A-Za-z0-9_]*|"
    rf"(?:InMemory|Memory)[A-Za-z0-9_]*{_SUBSTITUTE_INFRA_SUFFIX}|"
    r"(?:Noop|Mock|Stub|Fake)[A-Za-z0-9_]*)$"
)
SUBSTITUTE_COMPOSITE_NAME_RE = re.compile(
    rf"^(?:(?:InMemory|Memory)[A-Za-z0-9_]*{_SUBSTITUTE_INFRA_SUFFIX}|"
    r"(?:Noop|Mock|Stub|Fake|Recording)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]*(?:Mock|Stub|Fake|Double))$"
)
ENVIRONMENT_CLASS_NAME_RE = re.compile(
    r"^_?(?:Alpha|Beta|Gamma|Prod(?!uct(?:ion)?))[A-Za-z0-9_]*$"
)
ENVIRONMENT_DATA_NAME_RE = re.compile(
    r"(?<![a-z0-9_])(?:alpha|beta|gamma|prod)_[a-z0-9_]+",
    re.IGNORECASE,
)
ENVIRONMENT_PATH_SEGMENT_RE = re.compile(
    r"(?:^|[_-])(?:alpha|beta|gamma|prod)(?:[_-]|$)",
    re.IGNORECASE,
)
FIRST_PARTY_DOUBLE_PATH_RE = re.compile(
    r"(?:^|[_-])(?:fake|mock|stub|noop|memory|typed[_-]?double|test[_-]?double|recording)(?:[_\-.]|$)",
    re.IGNORECASE,
)
FIRST_PARTY_DOUBLE_TYPE_RE = re.compile(
    rf"^_?(?:(?:InMemory|Memory)[A-Za-z0-9_]*{_SUBSTITUTE_INFRA_SUFFIX}|"
    r"(?:Fake|Mock|Stub|Noop|Recording)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]*(?:Fake|Mock|Stub|Double))$"
)
DART_TEST_RE = re.compile(r"\b(?:test(?:Widgets)?|patrolTest)\s*\(")
PYTHON_TEST_RE = re.compile(r"\bdef\s+test_[A-Za-z0-9_]+\s*\(")
GO_TEST_ENTRYPOINT_RE = re.compile(
    r"\bfunc\s+(?:Test[A-Za-z0-9_]+|Benchmark[A-Za-z0-9_]+|TestMain)\s*\("
)
