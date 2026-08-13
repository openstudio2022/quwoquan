"""三层测试目录门禁的目录闭集、后缀映射与命名正则的唯一定义处。"""

from __future__ import annotations

import re

from test_directory_layout_lib import LAYERS, ROOT

#: 端侧测试层顶层目录里**尚未对象化**的旧形态残留。
#:
#: 这不是白名单：`verify_app_unmigrated_residue(...)` 对 missing / empty /
#: remaining 三种状态全部 BLOCK。它只让门禁能输出可执行的存量路径，
#: 不把任何存量测试解释为 canonical evidence。集合只能随对象化搬迁
#: 单调收缩，新对象目录只能位于由 service contracts 派生的 ``service/`` 容器。
APP_UNMIGRATED_LAYER_DIRS = {
    "local_contract": set(),
    "api_integration": set(),
    "user_acceptance": set(),
}
APP_CROSS_OBJECT_JOURNEY_ROOT = "journeys"
APP_PATROL_RUNNER_ROOT = "patrol"
APP_PATROL_RUNNER_FILES = frozenset({"patrol_test_main.dart", "test_bundle.dart"})
APP_PATROL_IMPORT_URI = "package:patrol/patrol.dart"
APP_TEST_ROOT_DIRS = {*LAYERS, "support"}
DATA_TEST_ROOT_DIRS = {*LAYERS, "support"}
IGNORED_TEST_CACHE_DIRS = {"__pycache__", ".pytest_cache"}


def _data_local_contract_layer_dirs() -> set[str]:
    """Data local_contract 领域目录集从 scripts 树实时派生，不再维护第二份清单。

    ``quwoquan_data/scripts/content/<subdomain>`` 与测试层目录一一对应
    （测试层沿用既有形态，省略 ``content/`` 包装层）；``core`` 与
    ``governance`` 对应 scripts 顶层同名目录。scripts 新增/退役子域时，
    测试目录白名单随之自动对齐。
    """
    content_root = ROOT / "quwoquan_data/scripts/content"
    subdomains = {
        path.name
        for path in content_root.iterdir()
        if path.is_dir() and path.name not in IGNORED_TEST_CACHE_DIRS
    } if content_root.is_dir() else set()
    return {"core", "governance", *subdomains}


DATA_LAYER_DIRS = {
    "local_contract": _data_local_contract_layer_dirs(),
    "api_integration": {"execution", "release"},
    "user_acceptance": {"journeys", "quality"},
}
OPS_TEST_ROOT_DIRS = {"local_contract", "acceptance", "support"}
OPS_ACCEPTANCE_DIRS = {"api_integration", "user_acceptance"}
SERVICE_TEST_DIRS = {"local_contract", "api_integration", "support"}

TEST_SUFFIX_BY_LAYER = {
    ".dart": {
        "local_contract": "__local_contract_test.dart",
        "api_integration": "__api_integration_test.dart",
        "user_acceptance": "__user_acceptance_test.dart",
    },
    ".go": {
        "local_contract": "__local_contract_test.go",
        "api_integration": "__api_integration_test.go",
    },
    ".py": {
        "local_contract": "__local_contract_test.py",
        "api_integration": "__api_integration_test.py",
        "user_acceptance": "__user_acceptance_test.py",
    },
}
DATA_TEST_NAME_RE = re.compile(
    r"^test_[a-z0-9]+(?:_[a-z0-9]+)*__[a-z0-9]+(?:_[a-z0-9]+)*__"
    r"(functional|contract|reliability|availability|observability|experience|security|performance|data_consistency)"
    r"__(local_contract|api_integration|user_acceptance)_test\.py$"
)
APP_JOURNEY_DIR_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DART_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_SERVICE_DOMAIN_RE = re.compile(r"(?m)^domain:\s*['\"]?([a-z][a-z0-9_]*)['\"]?\s*$")
TEST_SUPPORT_BARREL_NAME_RE = re.compile(
    r"(?:mock|fake|fixture|double|reexports?|repository)",
    re.IGNORECASE,
)
