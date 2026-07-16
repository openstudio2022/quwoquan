"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
from content.execution.support import Any, Callable, DEFAULT_CURSOR_AGENT_MODEL, ExecutionContext, Mapping, Path, REFERENCE_ONLY_NO_IMAGE_RELEASE, Sequence, _CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, _normalize_managed_agent_provider, _resolve_managed_model, argparse, contextmanager, cursor_api_key_file, execution_baseline_freeze_packet_path, execution_branch_issues, execution_branch_payload, execution_root, hashlib, image_asset_strategy, image_asset_strategy_scale_issues, os, resolve_cursor_startup_timeout_seconds, store, subprocess, tempfile, time, validate_image_asset_strategy, write_json

_LOCAL_PROCESS_PROBE_TIMEOUT_SECONDS = active_runtime_policy().local_process_probe_timeout_seconds

def _managed_preflight(execution_id: str, spec: dict, args: argparse.Namespace) -> list[str]:
    """托管任务启动前失败快返；不创建 batch/runtime。"""
    from content.execution.agent.agent_conflicts import _cleanup_managed_local_workspace_conflicts, _cross_task_managed_data_cli_conflicts, _managed_local_workspace_conflicts, _managed_workspace_conflicts_for_provider
    from content.execution.agent.agent_runner import _redact_managed_secret
    issues: list[str] = []
    agent_provider = _normalize_managed_agent_provider(getattr(args, "agent_provider", None))
    if str(spec.get("status") or "") != "active":
        issues.append(f"task status must be active for --managed, got {spec.get('status')!r}")
    issues.extend(execution_branch_issues(spec, cwd=Path.cwd()))
    from content.post.content_plan import validate_content_plan
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    if not targets:
        issues.append("scope.coverageTargets must not be empty")
    article_quota = int(quotas.get("entityArticlesPerTarget") or 0)
    homepage_quota = int(quotas.get("entityHomepagesPerTarget") or 0)
    image_quota = int(quotas.get("imageWorksPerTarget") or 0)
    if article_quota + homepage_quota + image_quota < 1:
        issues.append(
            "at least one content quota must be >= 1 "
            "(entityArticlesPerTarget/entityHomepagesPerTarget/imageWorksPerTarget)"
        )
    active_content_types: set[str] = set()
    if article_quota > 0 or int(quotas.get("routeArticles") or 0) > 0:
        active_content_types.add("article")
    if homepage_quota > 0:
        active_content_types.add("homepage")
    if image_quota > 0:
        active_content_types.add("image")
    if len(active_content_types) > 1:
        issues.append(
            "one execution may declare exactly one content type; split quotas into "
            "recipe/release fanout executions: " + ",".join(sorted(active_content_types))
        )
    else:
        from content.execution.workspace import load_execution_manifest
        try:
            manifest_content_type = str(
                load_execution_manifest(execution_id).get("contentType") or ""
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            issues.append(f"canonical execution manifest unavailable: {exc}")
        else:
            active_content_type = next(iter(active_content_types), "")
            if active_content_type and active_content_type != manifest_content_type:
                issues.append(
                    f"execution contentType {manifest_content_type!r} does not match "
                    f"active quota type {active_content_type!r}"
                )
    content = spec.get("content") or {}
    if str(content.get("modalityContract") or "") != "separated_research":
        issues.append("content.modalityContract must be separated_research for --managed")
    research = content.get("research") or {}
    lanes = {str(lane) for lane in (research.get("lanes") or [])}
    route_quota = int(quotas.get("routeArticles") or quotas.get("routeArticlesPerTarget") or 0)
    required_lanes: set[str] = set()
    if homepage_quota > 0:
        required_lanes.add("homepage")
    if article_quota > 0 or route_quota > 0:
        required_lanes.add("article")
    if image_quota > 0:
        required_lanes.add("image")
    if required_lanes and not required_lanes.issubset(lanes):
        issues.append(
            "content.research.lanes must contain active quota lanes: "
            + ",".join(sorted(required_lanes))
        )
    issues.extend(validate_image_asset_strategy(spec))
    issues.extend(image_asset_strategy_scale_issues(spec))
    if image_asset_strategy(spec) == REFERENCE_ONLY_NO_IMAGE_RELEASE:
        until = str(getattr(args, "until", "") or "").strip()
        if until not in {"download_plan", "download_fetch"}:
            issues.append(
                "content.research.imageAssetStrategy=reference_only_no_image_release "
                "may only run through --until download_plan or --until download_fetch"
            )
    if str(getattr(args, "runtime", "local")) == "local" and not getattr(args, "agent_runner", None):
        from core import ops_governance as og
        lease_issue = og.active_controller_issue(execution_id)
        if lease_issue:
            issues.append(lease_issue)
            conflicts = []
        else:
            conflicts = _managed_workspace_conflicts_for_provider(
                _managed_local_workspace_conflicts(Path.cwd()),
                agent_provider,
            )
        # 孤儿 bridge 自动回收：父进程已死（ppid=1）的 cursor-sdk-bridge 无归属，
        # 历史上会让 resume 循环反复 BLOCK 直至崩溃；确认孤儿后直接回收，
        # 不要求 --force-clean-workspace-agent-state。
        orphan_bridges = [
            item for item in conflicts
            if str(item.get("kind") or "") == "cursor_sdk_bridge"
            and int(item.get("ppid") or 0) == 1
        ]
        if orphan_bridges:
            orphan_report = _cleanup_managed_local_workspace_conflicts(orphan_bridges)
            orphan_report["mode"] = "auto_reclaimed_orphan_cursor_bridges"
            setattr(args, "_managed_orphan_bridge_cleanup_report", orphan_report)
            orphan_pids = {int(item.get("pid") or 0) for item in orphan_bridges}
            conflicts = [
                item for item in conflicts
                if int(item.get("pid") or 0) not in orphan_pids
            ]
        cleanup_report: dict[str, Any] | None = None
        if conflicts and bool(getattr(args, "force_clean_workspace_agent_state", False)):
            cross_task_conflicts = _cross_task_managed_data_cli_conflicts(
                conflicts,
                execution_id=execution_id,
            )
            observed_cross_task: dict[str, Any] | None = None
            if cross_task_conflicts:
                cross_task_pids = {
                    int(item.get("pid") or 0) for item in cross_task_conflicts
                }
                conflicts = [
                    item for item in conflicts
                    if int(item.get("pid") or 0) not in cross_task_pids
                ]
                observed_cross_task = {
                    "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
                    "mode": "force_clean_workspace_agent_state_observed_cross_task",
                    "requestedConflictCount": len(conflicts) + len(cross_task_conflicts),
                    "crossTaskConflictCount": len(cross_task_conflicts),
                    "conflicts": cross_task_conflicts[:20],
                }
            if conflicts:
                cleanup_report = _cleanup_managed_local_workspace_conflicts(conflicts)
                conflicts = _managed_workspace_conflicts_for_provider(
                    _managed_local_workspace_conflicts(Path.cwd()),
                    agent_provider,
                )
                if cross_task_conflicts:
                    cross_task_pids = {
                        int(item.get("pid") or 0) for item in cross_task_conflicts
                    }
                    conflicts = [
                        item for item in conflicts
                        if int(item.get("pid") or 0) not in cross_task_pids
                    ]
            elif observed_cross_task is not None:
                cleanup_report = {
                    "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
                    **observed_cross_task,
                }
            if cleanup_report is not None:
                setattr(args, "_managed_workspace_cleanup_report", cleanup_report)
        elif conflicts:
            setattr(
                args,
                "_managed_workspace_cleanup_report",
                {
                    "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
                    "mode": "not_requested",
                    "conflictCount": len(conflicts),
                    "conflicts": conflicts[:20],
                },
            )
        if conflicts:
            rendered = "; ".join(
                f"{item.get('kind')} pid={item.get('pid')} pgid={item.get('pgid')} "
                f"cmd={_redact_managed_secret(str(item.get('command') or ''))[:220]}"
                for item in conflicts[:8]
            )
            issues.append(
                "managed local workspace has active data workflow/cursor bridge conflicts; "
                "stop them or rerun with --force-clean-workspace-agent-state: "
                + rendered
            )
        elif cleanup_report is not None:
            setattr(args, "_managed_workspace_cleanup_report", cleanup_report)
    try:
        from core.python_runtime import environment_preflight
        managed_runtime = str(getattr(args, "runtime", "local") or "local")
        managed_model = _resolve_managed_model(
            agent_provider,
            getattr(args, "model", None),
        )
        requires_cursor_startup = (
            agent_provider == "cursor_sdk"
            and bool(managed_model)
        )
        def _run_env_preflight() -> dict:
            return environment_preflight(
                require_cursor_key=agent_provider == "cursor_sdk",
                check_network=True,
                # local/cloud 都要先证明账号资格；否则本地 bridge 里的 auth/plan 错误
                # 会被折叠成 startup 500，掩盖真实根因。
                check_cursor_cloud_api=agent_provider == "cursor_sdk",
                check_cursor_startup=requires_cursor_startup,
                cursor_startup_model=managed_model or DEFAULT_CURSOR_AGENT_MODEL,
                cursor_startup_runtime=managed_runtime,
                cursor_startup_timeout_seconds=resolve_cursor_startup_timeout_seconds(
                    getattr(args, "startup_timeout_seconds", None)
                ),
            )
        runtime_policy = active_runtime_policy()
        max_attempts = runtime_policy.preflight_startup_attempts if requires_cursor_startup else 1
        delay_seconds = runtime_policy.preflight_retry_delay_seconds
        env_attempts: list[dict[str, Any]] = []
        env_report = _run_env_preflight()
        env_attempts.append(_managed_env_preflight_attempt_summary(env_report))
        for attempt in range(1, max_attempts):
            if env_report.get("ready") or not _managed_preflight_startup_retryable(env_report):
                break
            if delay_seconds:
                time.sleep(delay_seconds)
            env_report = _run_env_preflight()
            env_attempts.append(_managed_env_preflight_attempt_summary(env_report))
        if len(env_attempts) > 1 and isinstance(env_report, dict):
            env_report = {
                **env_report,
                "managedPreflightAttempts": env_attempts,
            }
    except Exception as exc:  # noqa: BLE001
        env_report = {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": False,
            "issues": [f"environment preflight unavailable: {exc}"],
        }
        setattr(args, "_env_preflight_report", env_report)
        issues.append(f"environment preflight unavailable: {exc}")
    else:
        setattr(args, "_env_preflight_report", env_report)
        issues.extend([str(item) for item in (env_report.get("issues") or [])])
    if not execution_baseline_freeze_packet_path(execution_id).is_file() and not getattr(args, "baseline_packet", None):
        issues.append("baseline freeze packet missing")
    return issues

def _managed_env_preflight_attempt_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    startup = report.get("cursorStartup") if isinstance(report, Mapping) else {}
    startup = startup if isinstance(startup, Mapping) else {}
    return {
        "ready": bool(report.get("ready")) if isinstance(report, Mapping) else False,
        "cursorStartupReady": bool(startup.get("ready")),
        "cursorStartupStatus": startup.get("status"),
        "cursorStartupErrorClass": startup.get("errorClass"),
        "cursorStartupErrorCode": startup.get("errorCode"),
        "cursorStartupHttpStatus": startup.get("httpStatus"),
    }

def _managed_preflight_startup_retryable(report: Mapping[str, Any]) -> bool:
    startup = report.get("cursorStartup") if isinstance(report, Mapping) else {}
    if not isinstance(startup, Mapping) or startup.get("ready"):
        return False
    parts = [
        startup.get("error"),
        startup.get("status"),
        startup.get("errorClass"),
        startup.get("errorCode"),
        *(startup.get("issues") or []),
    ]
    text = " ".join(str(part or "") for part in parts).casefold()
    hard_blockers = (
        "unauthorized",
        "invalid api key",
        "authentication",
        "permission",
        "forbidden",
        "plan_required",
        "free",
        "subscription",
    )
    if any(marker in text for marker in hard_blockers):
        return False
    try:
        http_status = int(startup.get("httpStatus") or 0)
    except (TypeError, ValueError):
        http_status = 0
    return (
        _cursor_bridge_error_is_retryable(
            text,
            code=str(startup.get("errorCode") or ""),
            explicit_retryable=bool(startup.get("retryable")),
        )
        or 500 <= http_status < 600
    )

def _write_managed_env_ready_report(ctx: ExecutionContext, args: argparse.Namespace) -> Path:
    report = getattr(args, "_env_preflight_report", None)
    if not isinstance(report, Mapping):
        report = {"ready": False, "issues": ["managed preflight report missing"]}
    startup_timeout_seconds = resolve_cursor_startup_timeout_seconds(
        getattr(args, "startup_timeout_seconds", None)
    )
    cursor_startup = (
        dict(report.get("cursorStartup") or {})
        if isinstance(report.get("cursorStartup"), Mapping)
        else {}
    )
    if cursor_startup and "timeoutSeconds" not in cursor_startup:
        cursor_startup["timeoutSeconds"] = startup_timeout_seconds
    preflight_report = dict(report)
    if cursor_startup:
        preflight_report["cursorStartup"] = cursor_startup
    payload = {
        "schemaVersion": "quwoquan_data.env_ready_report",
        "executionId": ctx.execution_id,
        "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
        "model": ctx.model,
        "recordedAt": store.now_iso(),
        "ready": bool(report.get("ready")),
        "preflight": preflight_report,
        "cursorStartup": cursor_startup,
        "startupTimeoutSeconds": startup_timeout_seconds,
        "executionBranch": execution_branch_payload(ctx.spec, cwd=Path.cwd()),
        "credentialIngress": {
            "source": "key_file" if cursor_api_key_file() is not None else "missing",
        },
        "runtimeRoots": {
            "workspace": str(Path.cwd()),
            "dataRoot": str(os.environ.get("QWQ_DATA_ROOT") or ""),
            "outputRoot": str(os.environ.get("QWQ_OUTPUT_ROOT") or ""),
            "publishRoot": str(os.environ.get("QWQ_PUBLISH_ROOT") or ""),
        },
    }
    cleanup_report = getattr(args, "_managed_workspace_cleanup_report", None)
    if isinstance(cleanup_report, Mapping):
        payload["workspaceCleanup"] = dict(cleanup_report)
    path = execution_root(ctx.execution_id) / "_shared" / "env_ready_report.json"
    write_json(path, payload)
    return path

def _cursor_bridge_error_is_retryable(
    message: str,
    *,
    code: str | None = None,
    explicit_retryable: bool = False,
) -> bool:
    """Classify Cursor bridge startup/discovery failures as infra retryable."""
    lowered = str(message or "").casefold()
    code_lower = str(code or "").casefold()
    retry_markers = (
        "connection refused",
        "connecterror",
        "connection reset",
        "bridge request failed",
        "exited before discovery",
        "failed before discovery",
        "cursor-sdk-bridge failed",
        "tool-callback-auth-token",
        "internal error",
    )
    return (
        bool(explicit_retryable)
        or code_lower == "internal"
        or any(marker in lowered for marker in retry_markers)
    )

def _cursor_safe_auth_token_factory(original: Callable[[], str]) -> Callable[[], str]:
    """Wrap Cursor SDK callback token generation for argv parsers.
    The bundled Cursor bridge accepts `--tool-callback-auth-token <value>`.
    `secrets.token_urlsafe(...)` may legally return a value beginning with `-`;
    the bridge parser can then treat the token as another flag and fail with
    "Missing value for --tool-callback-auth-token". Keep the token random, but
    prefix the rare leading-dash case before it reaches argv.
    """
    def _factory() -> str:
        token = str(original() or "")
        if token.startswith("-"):
            return "qwq_" + token.lstrip("-")
        return token
    setattr(_factory, "_qwq_safe_token_factory", True)
    return _factory

def _patch_cursor_sdk_tool_callback_token() -> None:
    try:
        import cursor_sdk._tool_callback as tool_callback  # type: ignore
    except Exception:  # noqa: BLE001
        return
    original = getattr(tool_callback, "_new_auth_token", None)
    if not callable(original) or getattr(original, "_qwq_safe_token_factory", False):
        return
    setattr(tool_callback, "_new_auth_token", _cursor_safe_auth_token_factory(original))

def _cursor_bridge_launch_lock_path(workspace: str | Path) -> Path:
    """Resolve the Cursor bridge launch serialization lock (per-workspace by default).
    Bridge discovery races are *workspace-coupled* (the SDK binds a callback
    endpoint/port per workspace), not machine-global. Serializing every launch on
    the host through a single global lock needlessly throttles horizontal scaling
    across independent workspace clones (the documented 本机多 agent / 多 VM 路径):
    clone A's launch + cooldown blocks clone B even though their bridges never
    race. Keying the lock by workspace serializes launches only *within* the same
    workspace (where discovery genuinely races) while letting separate clones
    launch bridges in parallel. An explicit ``QWQ_CURSOR_BRIDGE_LAUNCH_LOCK``
    still forces a shared lock when an operator wants host-global serialization.
    """
    override = str(os.environ.get("QWQ_CURSOR_BRIDGE_LAUNCH_LOCK") or "").strip()
    if override:
        return Path(override)
    digest = hashlib.sha256(str(workspace).encode("utf-8")).hexdigest()[:16]
    root = Path(os.environ.get("QWQ_MANAGED_LOCAL_LOCK_DIR", tempfile.gettempdir()))
    return root / f"qwq-cursor-bridge-launch-{digest}.lock"

@contextmanager
def _cursor_bridge_launch_guard():
    """Serialize Cursor bridge discovery within a workspace (parallel across clones)."""
    lock_path = _cursor_bridge_launch_lock_path(Path.cwd())
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        yield
        return
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
            if _CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS:
                time.sleep(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

def _process_rows() -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "pgid=", "-o", "command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return []
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(maxsplit=3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            pgid = int(parts[2])
        except ValueError:
            continue
        rows.append({"pid": pid, "ppid": ppid, "pgid": pgid, "command": parts[3]})
    return rows

def _process_cwd(pid: int) -> str:
    if pid <= 0:
        return ""
    try:
        proc = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_LOCAL_PROCESS_PROBE_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001
        return ""
    for line in proc.stdout.splitlines():
        if line.startswith("n"):
            return line[1:].strip()
    return ""

def _current_process_family_pids(rows: Sequence[Mapping[str, Any]] | None = None) -> set[int]:
    rows = list(rows or _process_rows())
    parent_by_pid = {
        int(row.get("pid") or 0): int(row.get("ppid") or 0)
        for row in rows
        if int(row.get("pid") or 0) > 0
    }
    family = {os.getpid()}
    cursor = os.getpid()
    for _ in range(32):
        parent = parent_by_pid.get(cursor)
        if not parent or parent in family:
            break
        family.add(parent)
        cursor = parent
    return family
