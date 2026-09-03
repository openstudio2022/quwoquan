#!/usr/bin/env bash
# L0 local commit gate: parallel static checks + impacted high-concurrency tests.
# Never runs make gate / gate_repo --scope all / full Flutter local_contract.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -o cache_dir=$QWQ_OUTPUT_ROOT/env/repo/local/tests/cache/pytest"

BUDGETS_JSON="$ROOT/quwoquan_ops/environments/pr_gate_timing_budgets.json"
REPORT_DIR="$QWQ_OUTPUT_ROOT/env/repo/runs/commit-gate"
mkdir -p "$REPORT_DIR"

SOFT_BUDGET="${COMMIT_GATE_SOFT_BUDGET_SECONDS:-}"
HARD_BUDGET="${COMMIT_GATE_HARD_BUDGET_SECONDS:-}"
if [[ -z "$SOFT_BUDGET" ]]; then
  SOFT_BUDGET="$(python3 -c 'import json,sys; from pathlib import Path; g=json.loads(Path(sys.argv[1]).read_text()).get("gates",{}).get("00.local_commit_gate",{}); print(int(g.get("budgetSeconds",180)))' "$BUDGETS_JSON")"
fi
if [[ -z "$HARD_BUDGET" ]]; then
  HARD_BUDGET="$(python3 -c 'import json,sys; from pathlib import Path; g=json.loads(Path(sys.argv[1]).read_text()).get("gates",{}).get("00.local_commit_gate",{}); print(int(g.get("hardFailSeconds",300)))' "$BUDGETS_JSON")"
fi
if ! [[ "$SOFT_BUDGET" =~ ^[0-9]+$ && "$HARD_BUDGET" =~ ^[1-9][0-9]*$ ]]; then
  echo "[commit-gate] FAIL: budgets must be non-negative soft and positive hard integers" >&2
  exit 2
fi

STARTED_AT=$(date +%s)
HARD_DEADLINE=$((STARTED_AT + HARD_BUDGET))
PROCESS_GROUP_GRACE_SECONDS="${COMMIT_GATE_PROCESS_GROUP_GRACE_SECONDS:-2}"
DEADLINE_RUNNER="$ROOT/quwoquan_ops/gate/lib/process_group_deadline.py"
FINGERPRINT_START="$(python3 -B quwoquan_ops/cli/local_readiness.py plan --level fast --staged | python3 -c 'import json,sys; print(json.load(sys.stdin)["fingerprint"]["digest"])')"
PLAN_JSON="$REPORT_DIR/plan.json"
PHASE_LOG="$REPORT_DIR/phases.jsonl"
: >"$PHASE_LOG"

log() { echo "[commit-gate] $*"; }

phase_record() {
  local name="$1" status="$2" started="$3"
  local ended elapsed
  ended=$(date +%s)
  elapsed=$((ended - started))
  python3 -c 'import json,sys; print(json.dumps({"phase":sys.argv[1],"status":sys.argv[2],"seconds":int(sys.argv[3]),"startedAt":int(sys.argv[4]),"endedAt":int(sys.argv[5])},ensure_ascii=False))' \
    "$name" "$status" "$elapsed" "$started" "$ended" >>"$PHASE_LOG"
}

elapsed_now() { echo $(( $(date +%s) - STARTED_AT )); }

write_summary() {
  local result="$1"
  local elapsed fingerprint_end
  elapsed="$(elapsed_now)"
  fingerprint_end="$(python3 -B quwoquan_ops/cli/local_readiness.py plan --level fast --staged | python3 -c 'import json,sys; print(json.load(sys.stdin)["fingerprint"]["digest"])')"
  REPORT_DIR="$REPORT_DIR" PLAN_JSON="$PLAN_JSON" PHASE_LOG="$PHASE_LOG" \
  RESULT="$result" ELAPSED="$elapsed" SOFT_BUDGET="$SOFT_BUDGET" HARD_BUDGET="$HARD_BUDGET" \
  FINGERPRINT_START="$FINGERPRINT_START" FINGERPRINT_END="$fingerprint_end" \
  python3 - <<'PY'
import json, os
from pathlib import Path
phases = []
phase_path = Path(os.environ["PHASE_LOG"])
if phase_path.exists():
    for line in phase_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            phases.append(json.loads(line))
plan = {}
plan_path = Path(os.environ["PLAN_JSON"])
if plan_path.exists():
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
jobs = []
for phase, directory in (("static", "static"), ("tests", "tests")):
    root = Path(os.environ["REPORT_DIR"]) / directory
    if not root.is_dir():
        continue
    for result_path in sorted(root.glob("*.result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["phase"] = phase
        result["name"] = result_path.name.removesuffix(".result.json")
        jobs.append(result)
elapsed = int(os.environ["ELAPSED"])
soft = int(os.environ["SOFT_BUDGET"])
summary = {
    "result": os.environ["RESULT"],
    "elapsedSeconds": elapsed,
    "softBudgetSeconds": soft,
    "hardBudgetSeconds": int(os.environ["HARD_BUDGET"]),
    "overSoftBudget": elapsed > soft,
    "hardBudgetExceeded": os.environ["RESULT"] == "fail_budget" or elapsed > int(os.environ["HARD_BUDGET"]),
    "terminal": {
        "status": "GATE_BLOCK" if os.environ["RESULT"].startswith("fail") else "PASS",
        "code": "COMMIT_GATE.HARD_TIMEOUT" if os.environ["RESULT"] == "fail_budget" else (
            "COMMIT_GATE.FAILED" if os.environ["RESULT"].startswith("fail") else "COMMIT_GATE.PASSED"
        ),
    },
    "fingerprintStart": os.environ["FINGERPRINT_START"],
    "fingerprintEnd": os.environ["FINGERPRINT_END"],
    "fingerprintChanged": os.environ["FINGERPRINT_START"] != os.environ["FINGERPRINT_END"],
    "phases": phases,
    "jobs": jobs,
    "deferredToCi": plan.get("deferred_to_ci", []),
    "flutterTests": plan.get("flutter_tests", []),
    "staticChecks": plan.get("static_checks", []),
}
out = Path(os.environ["REPORT_DIR"]) / "summary.json"
out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"[commit-gate] summary -> {out}")
PY
}

enforce_hard_budget() {
  local elapsed
  elapsed="$(elapsed_now)"
  if [[ "$elapsed" -gt "$HARD_BUDGET" ]]; then
    log "FAIL: hard budget exceeded (${elapsed}s > ${HARD_BUDGET}s)"
    write_summary "fail_budget"
    exit 1
  fi
}

python3 "$ROOT/quwoquan_ops/gate/verify_git_branch_policy.py" --local-commit
python3 "$ROOT/quwoquan_ops/gate/commit_gate_select.py" --use-staged >"$PLAN_JSON"
log "plan written to $PLAN_JSON"

STATIC_CHECKS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && STATIC_CHECKS+=("$line")
done < <(python3 -c 'import json,sys; from pathlib import Path; print("\n".join(json.loads(Path(sys.argv[1]).read_text()).get("static_checks",[])))' "$PLAN_JSON")

run_static_check() {
  local check="$1"
  case "$check" in
    branch_policy) return 0 ;;
    feature_tree) make verify-feature-tree ;;
    python_script_governance_app|python_script_governance_service|python_script_governance_ops|python_script_governance_data)
      local governance_scope="${check#python_script_governance_}"
      python3 -B quwoquan_ops/gate/verify_python_script_governance.py \
        --scope "$governance_scope" --mode check
      ;;
    entrypoint_script_paths)
      python3 -B quwoquan_ops/gate/verify_entrypoint_script_paths.py
      ;;
    local_worktree_lifecycle)
      log "FAIL: local_worktree_lifecycle is forbidden in commit-gate static checks"
      return 2
      ;;
    service_architecture) make verify-service-architecture ;;
    service_probe_homology) make verify-service-probe-homology ;;
    app_generated_manifest) make verify-app-generated-manifest ;;
    app_contract_handoff) make verify-app-contract-handoff ;;
    verify-app-mock-isolation) make verify-app-mock-isolation ;;
    verify-app-cloud-package-boundaries) make verify-app-cloud-package-boundaries ;;
    verify-app-login-entry-loop) make verify-app-login-entry-loop-contract ;;
    verify-app-enum-typed-binding) make verify-app-enum-typed-binding ;;
    verify-app-assistant-search-weak-typing-ratchet)
      make verify-app-assistant-search-weak-typing-ratchet
      ;;
    metadata_contract) bash quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh ;;
    commercial_contract) make verify-commercial-contract-generation ;;
    pageflip_backward_mainline) make verify-app-pageflip-back-mainline ;;
    app_uat_widget_key_references) make verify-app-uat-widget-key-references ;;
    data_verify) python3 quwoquan_data/scripts/cli.py verify all ;;
    *)
      log "FAIL: unknown static check: $check"
      return 2
      ;;
  esac
}

export -f run_static_check log
export ROOT HARD_DEADLINE PROCESS_GROUP_GRACE_SECONDS DEADLINE_RUNNER

STATIC_PIDS=()
STATIC_NAMES=()
STATIC_DIR="$REPORT_DIR/static"
mkdir -p "$STATIC_DIR"
if [[ "${#STATIC_CHECKS[@]}" -gt 0 ]]; then
  for check in "${STATIC_CHECKS[@]}"; do
    [[ "$check" == "branch_policy" ]] && continue
    (
      result_json="$STATIC_DIR/$check.result.json"
      if python3 -B "$DEADLINE_RUNNER" \
        --deadline-epoch-seconds "$HARD_DEADLINE" \
        --grace-seconds "$PROCESS_GROUP_GRACE_SECONDS" \
        --result-json "$result_json" \
        -- bash -c 'run_static_check "$1"' _ "$check" \
        >"$STATIC_DIR/$check.log" 2>&1; then
        echo ok >"$STATIC_DIR/$check.status"
      elif python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); raise SystemExit(0 if p.is_file() and json.loads(p.read_text()).get("timedOut") else 1)' "$result_json"; then
        echo timeout >"$STATIC_DIR/$check.status"
      else
        echo fail >"$STATIC_DIR/$check.status"
      fi
    ) &
    STATIC_PIDS+=("$!")
    STATIC_NAMES+=("$check")
  done
fi

STATIC_STARTED=$(date +%s)
STATIC_FAIL=0
if [[ "${#STATIC_PIDS[@]}" -gt 0 ]]; then
  for i in "${!STATIC_PIDS[@]}"; do
    pid="${STATIC_PIDS[$i]}"
    name="${STATIC_NAMES[$i]}"
    set +e
    wait "$pid"
    set -e
    status="$(cat "$STATIC_DIR/$name.status" 2>/dev/null || echo fail)"
    if [[ "$status" == "timeout" ]]; then
      STATIC_FAIL=2
      log "static TIMEOUT: $name (see $STATIC_DIR/$name.log)"
    elif [[ "$status" != "ok" ]]; then
      [[ "$STATIC_FAIL" -eq 2 ]] || STATIC_FAIL=1
      log "static FAIL: $name (see $STATIC_DIR/$name.log)"
      tail -n 40 "$STATIC_DIR/$name.log" || true
    else
      log "static OK: $name"
    fi
  done
fi
STATIC_PHASE_STATUS="$([[ "$STATIC_FAIL" -eq 0 ]] && echo ok || ([[ "$STATIC_FAIL" -eq 2 ]] && echo timeout || echo fail))"
phase_record "L0_static_parallel" "$STATIC_PHASE_STATUS" "$STATIC_STARTED"
if [[ "$STATIC_FAIL" -ne 0 ]]; then
  if [[ "$STATIC_FAIL" -eq 2 ]]; then
    write_summary "fail_budget"
  else
    write_summary "fail_static"
  fi
  exit 1
fi
enforce_hard_budget

TEST_DIR="$REPORT_DIR/tests"
mkdir -p "$TEST_DIR"
TEST_PIDS=()
TEST_NAMES=()

start_test_job() {
  local name="$1"
  shift
  (
    result_json="$TEST_DIR/$name.result.json"
    if python3 -B "$DEADLINE_RUNNER" \
      --deadline-epoch-seconds "$HARD_DEADLINE" \
      --grace-seconds "$PROCESS_GROUP_GRACE_SECONDS" \
      --result-json "$result_json" \
      -- "$@" >"$TEST_DIR/$name.log" 2>&1; then
      echo ok >"$TEST_DIR/$name.status"
    elif python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); raise SystemExit(0 if p.is_file() and json.loads(p.read_text()).get("timedOut") else 1)' "$result_json"; then
      echo timeout >"$TEST_DIR/$name.status"
    else
      echo fail >"$TEST_DIR/$name.status"
    fi
  ) &
  TEST_PIDS+=("$!")
  TEST_NAMES+=("$name")
}

resolve_pytest_runtime() {
  if python3 -c 'import pytest' >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  local cached_python="${QWQ_PYTHON_CACHE_ROOT:-$HOME/.cache/quwoquan/python-envs}/quwoquan-data/bin/python3"
  if [[ -x "$cached_python" ]] && "$cached_python" -c 'import pytest' >/dev/null 2>&1; then
    printf '%s\n' "$cached_python"
    return 0
  fi

  return 1
}

CORES="$(python3 -c 'import os; print(max(2, min(8, (os.cpu_count() or 2) - 1)))')"
FLUTTER_CONCURRENCY="${FLUTTER_TEST_CONCURRENCY:-$CORES}"
if [[ -z "${FLUTTER_TEST_CONCURRENCY:-}" && "$FLUTTER_CONCURRENCY" -gt 6 ]]; then
  FLUTTER_CONCURRENCY=6
fi

FLUTTER_TESTS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && FLUTTER_TESTS+=("$line")
done < <(python3 -c 'import json,sys; from pathlib import Path; print("\n".join(json.loads(Path(sys.argv[1]).read_text()).get("flutter_tests",[])))' "$PLAN_JSON")
if [[ "${#FLUTTER_TESTS[@]}" -gt 0 ]]; then
  start_test_job "flutter_impacted" env \
    FLUTTER_TEST_GUARD_TIMEOUT_SECONDS="${FLUTTER_TEST_GUARD_TIMEOUT_SECONDS:-480}" \
    FLUTTER_TEST_CONCURRENCY="$FLUTTER_CONCURRENCY" \
    python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py \
      --concurrency="$FLUTTER_CONCURRENCY" \
      "${FLUTTER_TESTS[@]}"
fi

GO_SERVICES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && GO_SERVICES+=("$line")
done < <(python3 -c 'import json,sys; from pathlib import Path; print("\n".join(json.loads(Path(sys.argv[1]).read_text()).get("go_services",[])))' "$PLAN_JSON")
if [[ "${#GO_SERVICES[@]}" -gt 0 ]]; then
  start_test_job "go_impacted" bash -c '
    set -euo pipefail
    cd quwoquan_service
    for svc in "$@"; do
      if [[ -f "services/$svc/Makefile" ]]; then
        make -C "services/$svc" gate
      else
        go test "./services/$svc/..." -count=1 -p=8
      fi
    done
  ' _ "${GO_SERVICES[@]}"
fi

PYTEST_PATHS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && PYTEST_PATHS+=("$line")
done < <(python3 -c 'import json,sys; from pathlib import Path; print("\n".join(json.loads(Path(sys.argv[1]).read_text()).get("pytest_paths",[])))' "$PLAN_JSON")
if [[ "${#PYTEST_PATHS[@]}" -gt 0 ]]; then
  PYTEST_PYTHON="$(resolve_pytest_runtime)" || {
    log "FAIL: no Python runtime with pytest; install the repository test environment or set QWQ_PYTHON_CACHE_ROOT"
    write_summary "fail_pytest_runtime"
    exit 1
  }
  log "pytest runtime=$PYTEST_PYTHON"
  start_test_job "pytest_impacted" bash -c '
    set -euo pipefail
    pytest_python="$1"
    shift
    # Git exports repository-local variables to hooks.  Test fixtures that
    # create a temporary repository must not inherit the real worktree index
    # or refs; cwd still points at ROOT, so tests that intentionally inspect
    # the current repository continue to discover it normally.
    while IFS= read -r git_local_var; do
      [[ -n "$git_local_var" ]] && unset "$git_local_var"
    done < <(git rev-parse --local-env-vars)
    if "$pytest_python" -c "import xdist" >/dev/null 2>&1; then
      "$pytest_python" -m pytest -n 4 -q "$@"
    else
      "$pytest_python" -m pytest -q "$@"
    fi
  ' _ "$PYTEST_PYTHON" "${PYTEST_PATHS[@]}"
fi

start_test_job "smoke_marker" bash -c 'echo smoke-ok'

TEST_STARTED=$(date +%s)
TEST_FAIL=0
if [[ "${#TEST_PIDS[@]}" -eq 0 ]]; then
  log "no impacted tests selected"
else
  for i in "${!TEST_PIDS[@]}"; do
    pid="${TEST_PIDS[$i]}"
    name="${TEST_NAMES[$i]}"
    set +e
    wait "$pid"
    set -e
    status="$(cat "$TEST_DIR/$name.status" 2>/dev/null || echo fail)"
    if [[ "$status" == "timeout" ]]; then
      TEST_FAIL=2
      log "test TIMEOUT: $name (see $TEST_DIR/$name.log)"
    elif [[ "$status" != "ok" ]]; then
      [[ "$TEST_FAIL" -eq 2 ]] || TEST_FAIL=1
      log "test FAIL: $name (see $TEST_DIR/$name.log)"
      tail -n 60 "$TEST_DIR/$name.log" || true
    else
      log "test OK: $name"
    fi
    enforce_hard_budget
  done
fi
TEST_PHASE_STATUS="$([[ "$TEST_FAIL" -eq 0 ]] && echo ok || ([[ "$TEST_FAIL" -eq 2 ]] && echo timeout || echo fail))"
phase_record "L0_impacted_tests_parallel" "$TEST_PHASE_STATUS" "$TEST_STARTED"

DEFERRED_COUNT="$(python3 -c 'import json,sys; from pathlib import Path; print(len(json.loads(Path(sys.argv[1]).read_text()).get("deferred_to_ci",[])))' "$PLAN_JSON")"
if [[ "$DEFERRED_COUNT" -gt 0 ]]; then
  log "deferred_to_ci=$DEFERRED_COUNT targets (see plan.json)"
fi

FINGERPRINT_END="$(python3 -B quwoquan_ops/cli/local_readiness.py plan --level fast --staged | python3 -c 'import json,sys; print(json.load(sys.stdin)["fingerprint"]["digest"])')"
if [[ "$FINGERPRINT_START" != "$FINGERPRINT_END" ]]; then
  log "FAIL: working tree changed during commit gate (concurrent writers?). Re-run after stabilizing the tree."
  write_summary "fail_fingerprint"
  exit 1
fi

ELAPSED="$(elapsed_now)"
if [[ "$TEST_FAIL" -ne 0 ]]; then
  if [[ "$TEST_FAIL" -eq 2 ]]; then
    write_summary "fail_budget"
  else
    write_summary "fail_tests"
  fi
  exit 1
fi
if [[ "$ELAPSED" -gt "$HARD_BUDGET" ]]; then
  write_summary "fail_budget"
  exit 1
fi
if [[ "$ELAPSED" -gt "$SOFT_BUDGET" ]]; then
  log "WARN: soft budget exceeded (${ELAPSED}s > ${SOFT_BUDGET}s); continuing as pass with over_budget flag"
fi

write_summary "ok"
log "OK in ${ELAPSED}s (soft=${SOFT_BUDGET}s hard=${HARD_BUDGET}s)"
exit 0
