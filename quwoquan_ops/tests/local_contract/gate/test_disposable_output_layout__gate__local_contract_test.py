from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_output_path_source_contract as source_contract
from quwoquan_ops.gate.verify_output_layout import output_layout_issues
from quwoquan_ops.gate.verify_root_layout import (
    ALLOWED_TOP_LEVEL,
    source_cache_issues,
    top_level_issues,
)


def _mkdirs(root: Path, paths: tuple[str, ...]) -> None:
    for relative in paths:
        (root / relative).mkdir(parents=True)


def test_layout_gate_accepts_canonical_fixture(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/alpha/runs/run-1",
            "env/alpha/observability/run-1",
            "env/alpha/local/alpha-local/process",
            "env/alpha/local/alpha-local/cache",
            "env/repo/runs/tests",
            "env/repo/observability/run-1",
            "env/repo/local/ci/process",
            "env/repo/local/ci/cache",
            "data/tasks/execution-1",
            "data/releases/release-1",
            "data/local/workspace",
        ),
    )

    assert output_layout_issues(root) == []


def test_layout_gate_rejects_retired_categories_and_misplaced_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "packages",
            "env/staging/runs",
            "env/gamma/packages",
            "env/alpha/release",
            "env/gamma/local/gamma-local/pki",
            "env/repo/release",
            "data/runs",
            "data/observability/run-1",
        ),
    )

    issues = output_layout_issues(root)

    assert any("only permits env/ and data/" in issue for issue in issues)
    assert any("env only permits alpha/beta/gamma/prod/repo" in issue for issue in issues)
    assert sum("invalid" in issue and "output category" in issue for issue in issues) >= 2
    assert any("only permits process/ and cache/" in issue for issue in issues)
    assert any("invalid repo output category" in issue for issue in issues)
    assert sum("data only permits tasks/releases/local" in issue for issue in issues) == 2


def test_layout_gate_rejects_reusable_truth_inside_valid_output_categories(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/repo/local/tool/process/templates",
            "data/local/workspace/schema",
            "env/gamma/runs/run-1/policies",
        ),
    )

    issues = output_layout_issues(root)

    assert sum("reusable source truth is forbidden" in issue for issue in issues) == 3


def test_layout_gate_rejects_deployment_files_and_secret_values(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    run = root / "env/gamma/runs/run-1"
    run.mkdir(parents=True)
    (run / "runtime.env").write_text("PROVIDER_TOKEN=plain-text-secret\n", encoding="utf-8")
    (run / "evidence.log").write_text("api_key=plain-text-secret\n", encoding="utf-8")

    issues = output_layout_issues(root)

    assert any("deployment configuration, TLS or secret material" in issue for issue in issues)
    assert any("unredacted secret assignment is forbidden" in issue for issue in issues)


def test_layout_gate_accepts_pycache_prefix_mirror_as_opaque_cache(
    tmp_path: Path,
) -> None:
    """env/repo/local/pycache 是 PYTHONPYCACHEPREFIX 的绝对路径镜像缓存。

    镜像子目录形如 Users/、opt/,不满足 <target>/{process,cache} 结构;
    reconciliation 的 LOCAL_CACHE_HINTS 已把 pycache 归为缓存,布局门禁
    与其同语义放行,避免任何写字节码的并行进程让门禁间歇性 FAIL。
    """
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/repo/local/pycache/Users/someone/project",
            "env/repo/local/pycache/opt/homebrew/lib",
        ),
    )

    issues = output_layout_issues(root)

    assert not any("pycache" in issue for issue in issues)


def test_layout_gate_accepts_redirected_tmpdir_with_test_fixture_material(
    tmp_path: Path,
) -> None:
    """env/repo/local/tmp 是重定向进输出根的 TMPDIR,内容 opaque disposable。

    pytest tmp_path 工厂会在其中物化测试自签证书等 fixture 材料;
    按部署残留一刀切会让门禁在并行测试会话运行期间间歇性 FAIL。
    """
    root = tmp_path / ".qwq_output"
    fixture = root / "env/repo/local/tmp/pytest-of-someone/pytest-0/test_case0"
    fixture.mkdir(parents=True)
    (fixture / "root.crt").write_text("---fixture---\n", encoding="utf-8")

    issues = output_layout_issues(root)

    assert not any("local/tmp" in issue for issue in issues)


def test_layout_gate_exempts_runtime_mount_projection_facts_tree(
    tmp_path: Path,
) -> None:
    """platform-ops-facts 是容器 /app 的只读挂载投影,整棵豁免配置/秘密扫描。

    runtime_artifact_identity_mount 在每次 up 时把服务 config 与环境定义复制进
    run 目录供容器挂载;secretRefs 的值是环境变量名而非秘密。若按残留配置
    一刀切,任何环境启动后门禁都永久 FAIL。
    """
    root = tmp_path / ".qwq_output"
    facts = (
        root
        / "env/gamma/runs/run-1/platform-ops-facts"
        / "quwoquan_service/services/content-service/environments/gamma"
    )
    facts.mkdir(parents=True)
    (facts / "config.yaml").write_text(
        "secretRefs:\n"
        "  sys.content-service.oss.access_key_secret: CONTENT_OSS_ACCESS_KEY_SECRET\n",
        encoding="utf-8",
    )
    # 同一 run 目录之外的秘密赋值仍然违规,豁免不能外溢。
    leak = root / "env/gamma/runs/run-1"
    (leak / "evidence.log").write_text(
        "api_key=plain-text-secret\n", encoding="utf-8"
    )

    issues = output_layout_issues(root)

    assert not any("platform-ops-facts" in issue for issue in issues)
    assert any("unredacted secret assignment is forbidden" in issue for issue in issues)


def test_layout_gate_forbidden_name_heuristic_uses_content_as_the_real_verdict(
    tmp_path: Path,
) -> None:
    """词表类文件名命中只是启发式;真判据是内容里有没有密钥材料。

    stackctl 每次 dev-session 都会把 Caddyfile 物化进 runs/<run>/mutable-runtime,
    data 采集会写「缺凭据」的 credential-blocker 收据——按文件名一刀切会把这类
    合法运行产物永久判违禁,门禁永远追不上环境启动。
    """
    root = tmp_path / ".qwq_output"
    run = root / "env/alpha/runs/run-1/alpha-local/mutable-runtime/runtime-shared"
    run.mkdir(parents=True)
    # 物化 Caddyfile:引用路径与端口,不含 secret 值 → 放行。
    (run / "Caddyfile").write_text(
        "example.local {\n  reverse_proxy 127.0.0.1:18080\n}\n", encoding="utf-8"
    )
    blocker = root / "data/local/workspace/source-acquisition/video"
    blocker.mkdir(parents=True)
    # 「缺凭据」收据:记录 blocker 状态,不含 secret 值 → 放行。
    (blocker / "stock-provider-credential-blocker-1.json").write_text(
        '{"status": "blocked", "reason": "provider credential is not provisioned"}\n',
        encoding="utf-8",
    )

    assert output_layout_issues(root) == []

    # 同名文件一旦真的落了 secret 值,照拦。
    (run / "Caddyfile").write_text(
        "example.local {\n  basicauth {\n    admin password=hunter2\n  }\n}\n",
        encoding="utf-8",
    )
    assert any(
        "deployment configuration, TLS or secret material" in issue
        for issue in output_layout_issues(root)
    )


def test_layout_gate_treats_top_level_cache_and_process_as_shared_roots(
    tmp_path: Path,
) -> None:
    """local/ 一级的 cache/ 与 process/ 是共享缓存/进程根,不套 target 结构。

    AGENTS 把 bytecode/pytest 缓存统一重定向到 env/repo/local/cache/**;把
    「cache」解析成 target 名会让这一半约定永久红门。
    """
    root = tmp_path / ".qwq_output"
    shared = root / "env/repo/local/cache/python-pyc/some/module"
    shared.mkdir(parents=True)
    (root / "env/repo/local/process").mkdir(parents=True)

    assert output_layout_issues(root) == []

    # 普通 target 目录仍必须只含 process/ 与 cache/。
    stray = root / "env/repo/local/my-target/notes"
    stray.mkdir(parents=True)
    assert any(
        "only permits process/ and cache/" in issue
        for issue in output_layout_issues(root)
    )


def test_layout_gate_certificate_suffixes_are_never_content_exempt(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    run = root / "env/alpha/runs/run-1"
    run.mkdir(parents=True)
    # 即使内容无 secret 赋值,.pem 后缀名字即证据,不做内容豁免。
    (run / "ca.pem").write_text("just text\n", encoding="utf-8")

    assert any(
        "deployment configuration, TLS or secret material" in issue
        for issue in output_layout_issues(root)
    )


def test_layout_gate_allows_only_fixed_schema_runtime_process_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    process_record = (
        root / "env/beta/local/beta-local/process/processes/gateway.env"
    )
    process_record.parent.mkdir(parents=True)
    process_record.write_text(
        "\n".join(
            (
                "name=gateway",
                "pid=123",
                "pgid=123",
                "wrapper_pid=122",
                "owner_id=beta-local-123",
                "log=/tmp/gateway.log",
                "cwd=/tmp/repo",
                "started_at=123456",
                "",
            )
        ),
        encoding="utf-8",
    )

    assert output_layout_issues(root) == []

    process_record.write_text(
        f"{process_record.read_text(encoding='utf-8')}CONFIG_ROOT=/tmp/config\n",
        encoding="utf-8",
    )
    assert any(
        "deployment configuration, TLS or secret material" in issue
        for issue in output_layout_issues(root)
    )


def test_layout_gate_rejects_interpreter_cache_under_disposable_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/repo/local/python-envs/cache/quwoquan-data/site-packages/schema",
        ),
    )

    issues = output_layout_issues(root)

    assert any("interpreter caches belong in the external tool cache" in issue for issue in issues)


def test_layout_gate_does_not_misclassify_evidence_or_scan_dependency_payloads(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    report = root / "data/tasks/execution-1/env_ready_report.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"status":"ready"}\n', encoding="utf-8")
    dependency = root / "env/repo/local/python-test-deps/example.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("api_key = generated_example_value\n", encoding="utf-8")

    issues = output_layout_issues(root)

    assert not any("env_ready_report.json" in issue for issue in issues)
    assert not any("example.py" in issue for issue in issues)
    assert any("interpreter caches belong in the external tool cache" in issue for issue in issues)


def test_source_gate_rejects_retired_cache_and_output_owned_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_config = tmp_path / "pytest.ini"
    root_config.write_text(
        "cache_dir=.qwq_output/env/repo/local/test-cache/pytest\n"
        "schema=.qwq_output/env/repo/local/tool/process/schema\n"
        "caddy=.qwq_output/env/gamma/local/gamma-local/process/caddy-data\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(source_contract, "SOURCE_ROOTS", ())
    monkeypatch.setattr(source_contract, "ROOT_CONFIG_FILES", (root_config,))

    issues = source_contract.source_path_issues()

    assert len(issues) == 3
    assert all("retired output/state path" in issue for issue in issues)


def test_root_layout_rejects_source_interpreter_and_pytest_caches(tmp_path: Path) -> None:
    bytecode_dir = tmp_path / "quwoquan_data" / "scripts" / "core" / "__pycache__"
    bytecode_dir.mkdir(parents=True)
    (bytecode_dir / "paths.cpython-313.pyc").write_bytes(b"bytecode")
    pytest_cache = tmp_path / "quwoquan_ops" / ".pytest_cache"
    pytest_cache.mkdir(parents=True)
    stray_bytecode = tmp_path / "quwoquan_app" / "scripts" / "app.pyo"
    stray_bytecode.parent.mkdir(parents=True)
    stray_bytecode.write_bytes(b"bytecode")

    issues = source_cache_issues(tmp_path)

    assert sum("source cache is forbidden" in issue for issue in issues) == 2
    assert sum("Python bytecode is forbidden" in issue for issue in issues) == 1


def test_root_layout_rejects_top_level_entries_no_blocklist_ever_predicted(
    tmp_path: Path,
) -> None:
    """未被预见的一级条目必须被拦下。

    `v/`、`v0/`、`v360p/` 是被截断的 ffmpeg 参数在根目录误建的空目录，具名黑名单
    永远不会包含它们。这条测试锁住「根目录默认封闭」这个性质本身。
    """
    for name in ("v", "v0", "v360p", "some_future_junk"):
        (tmp_path / name).mkdir()
    (tmp_path / "stray_report.json").write_text("{}", encoding="utf-8")

    issues = top_level_issues(tmp_path)

    assert len(issues) == 5
    assert all("unregistered top-level entry" in issue for issue in issues)
    for name in ("v", "v0", "v360p", "some_future_junk", "stray_report.json"):
        assert any(issue.startswith(f"{name}:") for issue in issues)


def test_root_layout_names_the_disposition_for_retired_entries(tmp_path: Path) -> None:
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "node_modules").mkdir()

    issues = top_level_issues(tmp_path)

    assert len(issues) == 2
    assert any(
        issue == ".pytest_cache: retired top-level entry; "
        "redirect to .qwq_output/env/repo/local/**"
        for issue in issues
    )
    assert any(
        issue == "node_modules: retired top-level entry; no root-level npm project"
        for issue in issues
    )


def test_root_layout_accepts_every_registered_top_level_entry(tmp_path: Path) -> None:
    for name in sorted(ALLOWED_TOP_LEVEL):
        target = tmp_path / name
        if Path(name).suffix and name not in {".git", ".github", ".cursor", ".vscode"}:
            target.write_text("", encoding="utf-8")
        else:
            target.mkdir()

    assert top_level_issues(tmp_path) == []


def test_root_layout_registry_covers_the_real_repository_root() -> None:
    """白名单必须覆盖真实根目录的受版本控制条目。

    否则收紧这道门会立刻把仓库自身判成违规，开发者只会去放宽门而不是清理根目录。
    """
    tracked_top_level = {
        path.name
        for path in ROOT.iterdir()
        if not path.name.startswith(".") or path.name in ALLOWED_TOP_LEVEL
    }

    assert tracked_top_level <= ALLOWED_TOP_LEVEL
