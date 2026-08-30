"""stackctl matrix：固定候选上的 Alpha → Beta → Gamma 串行门禁。

本包由原单文件 ``local_env_gate_matrix.py`` 拆分而来，按职责切分为：

- ``identity``：常量、运行标识、执行租约与证据路径原语。
- ``preflight``：L0 commit gate、Docker 就绪与设备/发布绑定前置校验。
- ``data_phases``：Data CLI 阶段执行、阶段记录与 runner 调用封装。
- ``evidence``：Provider 本地功能面与 live 矩阵证据身份校验。
- ``reporting``：矩阵结果 CaseResult / Markdown 落盘与 claim 计算。
- ``orchestrator``：单个 matrix run 的串行状态机主体。
- ``entry``：进程级执行租约下的公开入口 ``run_local_env_gate_matrix``。

对外导入路径保持不变：``from quwoquan_ops.cli.lib.local_env_gate_matrix import ...``。
测试会 monkeypatch 本包属性（``subprocess.run`` / ``output_root`` /
``write_timing_bundle`` / ``probe_migration_drift`` / ``_run_commit_gate``），
包内消费方对这些名字保持包属性延迟访问，禁止改回子模块 from-import 直连。
"""

from __future__ import annotations

# 测试通过 "quwoquan_ops.cli.lib.local_env_gate_matrix.subprocess.run"
# monkeypatch 子进程调用，包属性必须保留 subprocess 模块引用。
import subprocess  # noqa: F401

from quwoquan_ops.cli.lib import (  # noqa: F401
    external_provider_governance,
    provider_conformance,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: F401
    validate_packaged_provider_runtime,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import (  # noqa: F401
    _acceptance_lease_event,
    _data_cli_runner,
    _data_readiness_path,
    _data_run_ids,
    _homepage_release_evidence,
    _invoke_env,
    _lifecycle_exit_path,
    _record_phase,
    _run_data_phase,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.entry import (  # noqa: F401
    run_local_env_gate_matrix,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.evidence import (  # noqa: F401
    _contains_non_unknown_attempt,
    _down_target,
    _freeze_matrix_package_identity,
    _integration_verify_has_required_test_data_case,
    _live_matrix_evidence_errors,
    _package_candidate_release_identity,
    _provider_local_functional_errors,
    _uat_matches_package_identity,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (  # noqa: F401
    _ATTEMPT_ID,
    _PROVIDER_CAPABILITY_ID,
    _PROVIDER_LAYERS,
    _SHA256,
    CANONICAL_TARGETS,
    DEVICE_PROFILE_EMULATOR_ONLY,
    DEVICE_PROFILE_FULL,
    DEVICE_PROFILES,
    EMULATOR_ONLY_CLAIM,
    PROFILE_LOCAL_ENV_GATE,
    ROOT,
    SPEC_REFS,
    TARGET_ENVIRONMENTS,
    DataRunner,
    EnvRunner,
    MatrixExecutionLeaseBusy,
    _evidence_path,
    _matrix_execution_lease,
    _matrix_lease_path,
    _namespace,
    _new_matrix_run_id,
    _repo_matrix_dir,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.orchestrator import (  # noqa: F401
    _run_local_env_gate_matrix,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.preflight import (  # noqa: F401
    _device_binding_errors,
    _device_uat_bindings,
    _docker_daemon_ready,
    _release_binding,
    _run_commit_gate,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.reporting import (  # noqa: F401
    _write_matrix_result,
)
from quwoquan_ops.cli.lib.local_env_gate_timing import (  # noqa: F401
    PhaseTimer,
    load_local_env_matrix_budgets,
    utc_now,
    write_timing_bundle,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (  # noqa: F401
    format_drift_gate_block,
    probe_migration_drift,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: F401
    active_deployment_candidate_snapshot,
    output_root,  # noqa: F401
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (
    load_startup_attempt,  # noqa: F401
)
