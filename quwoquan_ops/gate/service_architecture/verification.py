"""Verification 核心：状态容器、错误收集与 verify 主序列。

注意：``VerificationCore`` 不含 ``verify_kind_aware_object_implementation``。
该方法因 object_path_map 门禁（``object_path_map_lib/claims.py``）对入口文件的
AST 镜像校验，必须以字面量形式留在 ``verify_service_architecture.py``；入口以
``class Verification(VerificationCore)`` 补齐它。请勿直接实例化本核心类执行
``verify()``——``verify_source_and_test_paths`` 会经 ``self`` 调用该方法。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .verification_contracts import ContractVerificationMixin
from .verification_operations import OperationsVerificationMixin
from .verification_sources import SourceVerificationMixin


class VerificationCore(
    ContractVerificationMixin,
    SourceVerificationMixin,
    OperationsVerificationMixin,
):
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.objects: dict[tuple[str, str, str], tuple[str, Path, dict[str, Any]]] = {}
        self.contexts: set[tuple[str, str]] = set()
        self.source_owners: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self.layer_sources: dict[
            tuple[str, str, str], dict[str, set[Path]]
        ] = defaultdict(lambda: defaultdict(set))
        self.routed_objects: set[tuple[str, str, str]] = set()
        self.runtime_entrypoint_objects: set[tuple[str, str, str]] = set()
        self.runtime_entrypoint_kinds: dict[tuple[str, str, str], str] = {}
        self.lifecycle_entrypoint_candidates: dict[
            tuple[str, str, str], list[dict[str, str]]
        ] = {}
        self.lifecycle_entrypoint_objects: set[tuple[str, str, str]] = set()
        self.application_sources: dict[tuple[str, str, str], set[Path]] = defaultdict(set)
        self.local_contract_objects: set[tuple[str, str, str]] = set()
        self.api_integration_objects: set[tuple[str, str, str]] = set()
        self.object_test_spec_refs: dict[
            tuple[str, str, str], set[str]
        ] = defaultdict(set)
        self.object_kinds: Counter[str] = Counter()
        self.aggregate_members = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def verify(self) -> None:
        self.verify_service_set_and_truth_sources()
        self.verify_contracts()
        self.verify_service_templates()
        self.verify_source_and_test_paths()
        self.verify_generated_paths()
        self.verify_dependency_boundaries()
        self.verify_resources_and_migrations()
        self.verify_compose_ownership()
        self.verify_runtime_port_contracts()
        self.verify_special_assets()
        self.verify_kustomize_entries()
        self.verify_no_source_artifacts()
        self.run_subgates()
