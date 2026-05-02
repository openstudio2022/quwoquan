#!/usr/bin/env python3
"""Run 21 assistant skills on alpha and beta simulators and score parity."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "quwoquan_app"
ASSISTANT_SERVICE_DIR = (
    REPO_ROOT / "quwoquan_service" / "services" / "assistant-service"
)
FIXTURE_PATH = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "assistant"
    / "test_fixtures"
    / "scenarios"
    / "assistant_skill_eval_scenarios.json"
)
TEST_PATH = "test/gamma/assistant_skill_comparison_test.dart"
RESULT_PREFIX = "ASSISTANT_SKILL_EVAL_RESULT_JSON:"
DEFAULT_REPORT = REPO_ROOT / "tmp" / "assistant_skill_comparison_report.json"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    include_output: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    timed_out = False
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        output, _ = process.communicate(timeout=timeout_seconds)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        output = ""
        exit_code = 124
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                output, _ = process.communicate(timeout=10)
            except Exception:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    pass
    output = output or ""
    result: dict[str, Any] = {
        "command": command,
        "cwd": str(cwd),
        "exitCode": exit_code,
        "durationMs": int((time.monotonic() - started) * 1000),
        "timedOut": timed_out,
        "outputSummary": summarize_output(output),
    }
    if include_output:
        result["output"] = output
    return result


def summarize_output(output: str, max_lines: int = 120) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join([f"... omitted {len(lines) - max_lines} earlier lines ...", *lines[-max_lines:]])


def discover_devices() -> list[dict[str, Any]]:
    result = run_command(
        ["flutter", "devices", "--machine"],
        cwd=APP_DIR,
        timeout_seconds=60,
        include_output=True,
    )
    if result["exitCode"] != 0:
        raise RuntimeError("flutter devices failed:\n" + result["outputSummary"])
    raw = extract_json_array(result["output"])
    devices = json.loads(raw)
    out: list[dict[str, Any]] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        if target not in {"ios", "android"}:
            continue
        out.append(
            {
                "id": str(device.get("id", "")),
                "name": str(device.get("name", "")),
                "targetPlatform": str(device.get("targetPlatform", "")),
                "screenClass": infer_screen_class(device),
            }
        )
    return [device for device in out if device["id"]]


def extract_json_array(output: str) -> str:
    start = output.find("[")
    end = output.rfind("]")
    if start < 0 or end < start:
        raise ValueError("flutter devices output missing JSON array")
    return output[start : end + 1]


def infer_screen_class(device: dict[str, Any]) -> str:
    text = f"{device.get('name', '')} {device.get('targetPlatform', '')}".lower()
    if "ipad" in text or "tablet" in text:
        return "tablet"
    return "phone"


def choose_device(devices: list[dict[str, Any]], explicit: str, preferred_name: str) -> dict[str, Any]:
    if explicit:
        for device in devices:
            if device["id"] == explicit:
                return device
        raise RuntimeError(f"GATE_BLOCK: device id not found: {explicit}")
    preferred_lower = preferred_name.lower()
    for device in devices:
        if preferred_lower in device["name"].lower():
            return device
    raise RuntimeError(f"GATE_BLOCK: required simulator not found: {preferred_name}")


def fixture_b64() -> str:
    return base64.b64encode(FIXTURE_PATH.read_bytes()).decode("ascii")


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def clean_ports(ports: list[int]) -> None:
    for port in ports:
        subprocess.run(
            ["bash", "-lc", f"lsof -tiTCP:{port} -sTCP:LISTEN | xargs -r kill"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    log_path: Path,
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            pass


def wait_for_gateway(base_url: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    url = base_url.rstrip("/") + "/v1/assistant/skills"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    return False


def start_beta_stack(args: argparse.Namespace, report_dir: Path) -> tuple[subprocess.Popen[str], subprocess.Popen[str], dict[str, Any]]:
    clean_ports([args.assistant_port, args.gateway_port])
    logs_dir = report_dir / "assistant_skill_comparison_logs"
    assistant_log = logs_dir / "assistant-service-beta.log"
    gateway_log = logs_dir / "assistant-beta-gateway.log"
    assistant_env = os.environ.copy()
    assistant_env["APP_ENV"] = "beta"
    assistant_env["ASSISTANT_MODEL_PROVIDER"] = os.environ.get(
        "ASSISTANT_MODEL_PROVIDER", "deterministic"
    )
    assistant_env["ALLOW_DETERMINISTIC_BETA"] = "1"
    assistant_env.pop("ASSISTANT_SCENARIO_SEED_REFS", None)
    assistant = start_process(
        ["go", "run", "./cmd/api"],
        cwd=ASSISTANT_SERVICE_DIR,
        env=assistant_env,
        log_path=assistant_log,
    )
    gateway = start_process(
        [
            "python3",
            "scripts/dev_assistant_beta_gateway.py",
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(args.gateway_port),
            "--upstream-host",
            "127.0.0.1",
            "--upstream-port",
            str(args.assistant_port),
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        log_path=gateway_log,
    )
    reachable = wait_for_gateway(args.gateway_base_url, args.service_start_timeout_seconds)
    return assistant, gateway, {
        "gatewayReachable": reachable,
        "assistantLog": str(assistant_log.relative_to(REPO_ROOT)),
        "gatewayLog": str(gateway_log.relative_to(REPO_ROOT)),
        "assistantPort": args.assistant_port,
        "gatewayPort": args.gateway_port,
    }


def run_eval(env_name: str, device: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    command = [
        "flutter",
        "test",
        TEST_PATH,
        "-d",
        device["id"],
        f"--dart-define=APP_RUNTIME_ENV={env_name}",
        f"--dart-define=VALIDATION_SCREEN_CLASS={device['screenClass']}",
        "--dart-define=ASSISTANT_SCENARIO_FIXTURE_JSON_B64=" + fixture_b64(),
    ]
    if env_name == "alpha":
        command.append("--dart-define=APP_DATA_SOURCE=mock")
    else:
        command.extend(
            [
                "--dart-define=APP_DATA_SOURCE=remote",
                f"--dart-define=CLOUD_GATEWAY_BASE_URL={args.gateway_base_url}",
            ]
        )
    print(
        f"[assistant-skill-comparison] {env_name} -> {device['name']} ({device['id']})",
        flush=True,
    )
    result = run_command(
        command,
        cwd=APP_DIR,
        timeout_seconds=args.test_timeout_seconds,
        include_output=True,
    )
    evidence = parse_eval_output(result.get("output", ""))
    result.update(
        {
            "env": env_name,
            "device": device,
            "status": "passed" if result["exitCode"] == 0 else "failed",
            "evidence": evidence,
        }
    )
    result.pop("output", None)
    return result


def parse_eval_output(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        index = line.find(RESULT_PREFIX)
        if index < 0:
            continue
        raw = line[index + len(RESULT_PREFIX) :].strip()
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            rows.append({"parseError": raw})
    return rows


def normalize_event(event: str) -> str:
    mapping = {
        "turn_started": "assistant.turn.started",
        "understanding_updated": "assistant.skill.selected",
        "tool_use_requested": "assistant.tool.requested",
        "tool_result_received": "assistant.tool.completed",
        "final_answer": "assistant.answer.final",
    }
    return mapping.get(event, event)


def score_evidence(row: dict[str, Any], scenario: dict[str, Any], env_name: str) -> dict[str, Any]:
    answer = str(row.get("answer", ""))
    error = str(row.get("errorMessage", ""))
    events = [str(item) for item in row.get("eventTypes", [])]
    normalized_events = {normalize_event(item) for item in events}
    transcript = row.get("transcript", [])
    tool_names = {str(item) for item in row.get("toolNames", []) if str(item)}
    selected_skills = {str(item) for item in row.get("selectedSkillIds", []) if str(item)}

    fragments = scenario_fragments(scenario, env_name)
    matched_fragments = [fragment for fragment in fragments if fragment in answer]
    expected_events = scenario_events(scenario, env_name)
    matched_events = [
        event for event in expected_events if normalize_event(event) in normalized_events
    ]
    expected_tools = {str(item) for item in scenario.get("expectedToolNames", [])}
    matched_tools = sorted(expected_tools & tool_names)

    stream_score = 0.0
    if events:
        stream_score += 1.0
    if expected_events:
        stream_score += 1.0 * len(matched_events) / len(expected_events)
    if isinstance(transcript, list) and len(transcript) >= 2:
        stream_score += 1.0

    answer_score = 0.0
    if fragments:
        answer_score = 3.0 * len(matched_fragments) / len(fragments)
    elif answer:
        answer_score = 3.0

    semantic_score = 0.0
    if env_name == "alpha" or str(scenario.get("skillId")) in selected_skills:
        semantic_score += 1.0
    if expected_tools and matched_tools:
        semantic_score += 1.0

    stability_score = 1.0 if not error and not row.get("running") and answer else 0.0
    experience_score = 1.0 if answer and stream_score >= 2.0 else 0.0
    total = stream_score + answer_score + semantic_score + stability_score + experience_score
    return {
        "total": round(total, 2),
        "streamNarrative": round(stream_score, 2),
        "answerQuality": round(answer_score, 2),
        "skillToolSemantic": round(semantic_score, 2),
        "stability": round(stability_score, 2),
        "experienceParity": round(experience_score, 2),
        "matchedFragments": matched_fragments,
        "missingFragments": [item for item in fragments if item not in matched_fragments],
        "matchedEvents": matched_events,
        "missingEvents": [item for item in expected_events if item not in matched_events],
        "matchedTools": matched_tools,
        "missingTools": sorted(expected_tools - tool_names),
    }


def scenario_fragments(scenario: dict[str, Any], env_name: str) -> list[str]:
    if env_name != "alpha":
        remote = scenario.get("remoteExpectations", {})
        values = remote.get("answerFragments", [])
        if values:
            return [str(item) for item in values]
    return [str(item) for item in scenario.get("expectedAnswerFragments", [])]


def scenario_events(scenario: dict[str, Any], env_name: str) -> list[str]:
    if env_name != "alpha":
        remote = scenario.get("remoteExpectations", {})
        values = remote.get("eventTypes", [])
        if values:
            return [str(item) for item in values]
    return [str(item) for item in scenario.get("expectedEvents", [])]


def build_comparison_report(
    fixture: dict[str, Any],
    alpha_run: dict[str, Any],
    beta_run: dict[str, Any],
    beta_services: dict[str, Any],
) -> dict[str, Any]:
    scenarios = [
        item
        for item in fixture.get("scenarios", [])
        if item.get("type") == "assistant_turn"
    ]
    by_id = {str(item.get("id")): item for item in scenarios}
    alpha = {str(item.get("scenarioId")): item for item in alpha_run.get("evidence", [])}
    beta = {str(item.get("scenarioId")): item for item in beta_run.get("evidence", [])}
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = str(scenario.get("id"))
        alpha_row = alpha.get(scenario_id, {"errorMessage": "missing alpha evidence"})
        beta_row = beta.get(scenario_id, {"errorMessage": "missing beta evidence"})
        alpha_score = score_evidence(alpha_row, scenario, "alpha")
        beta_score = score_evidence(beta_row, scenario, "beta")
        gap = round(beta_score["total"] - alpha_score["total"], 2)
        rows.append(
            {
                "scenarioId": scenario_id,
                "skillId": scenario.get("skillId"),
                "domainId": scenario.get("domainId"),
                "title": scenario.get("title"),
                "alphaScore": alpha_score,
                "betaScore": beta_score,
                "scoreGap": gap,
                "status": "passed" if beta_score["total"] >= 8 and gap >= -1 else "needs_fix",
                "gapReason": gap_reason(beta_score, alpha_score, beta_row),
                "alphaEvidence": summarize_evidence(alpha_row),
                "betaEvidence": summarize_evidence(beta_row),
            }
        )
    needs_fix = [row for row in rows if row["status"] != "passed"]
    return {
        "schemaVersion": "assistant.skill-comparison-report.v1",
        "startedAt": alpha_run.get("startedAt"),
        "endedAt": utc_now(),
        "status": "passed" if not needs_fix and beta_run.get("exitCode") == 0 else "needs_fix",
        "skillCount": len(rows),
        "alphaDevice": alpha_run.get("device"),
        "betaDevice": beta_run.get("device"),
        "betaServices": beta_services,
        "runs": {
            "alpha": strip_run(alpha_run),
            "beta": strip_run(beta_run),
        },
        "summary": {
            "passed": len(rows) - len(needs_fix),
            "needsFix": len(needs_fix),
            "averageAlphaScore": average([row["alphaScore"]["total"] for row in rows]),
            "averageBetaScore": average([row["betaScore"]["total"] for row in rows]),
        },
        "rows": rows,
        "missingScenarioIds": sorted(set(by_id) - set(alpha) | set(by_id) - set(beta)),
    }


def summarize_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": str(row.get("answer", ""))[:500],
        "answerLength": row.get("answerLength", 0),
        "errorMessage": row.get("errorMessage", ""),
        "eventTypes": row.get("eventTypes", []),
        "toolNames": row.get("toolNames", []),
        "selectedSkillIds": row.get("selectedSkillIds", []),
        "durationMs": row.get("durationMs", 0),
        "turnId": row.get("turnId", ""),
    }


def strip_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "env": run.get("env"),
        "exitCode": run.get("exitCode"),
        "status": run.get("status"),
        "durationMs": run.get("durationMs"),
        "outputSummary": run.get("outputSummary", ""),
    }


def gap_reason(beta_score: dict[str, Any], alpha_score: dict[str, Any], beta_row: dict[str, Any]) -> str:
    if beta_row.get("errorMessage"):
        return "beta_error:" + str(beta_row.get("errorMessage"))
    if beta_score["total"] < 8:
        missing = []
        for key in ("missingFragments", "missingEvents", "missingTools"):
            values = beta_score.get(key, [])
            if values:
                missing.append(f"{key}={values}")
        return "; ".join(missing) or "beta_score_below_threshold"
    if beta_score["total"] < alpha_score["total"] - 1:
        return "beta_quality_gap"
    return ""


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha-device-id", default="")
    parser.add_argument("--beta-device-id", default="")
    parser.add_argument("--alpha-device-name", default="iPhone 17")
    parser.add_argument("--beta-device-name", default="iPhone 15")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--gateway-base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--assistant-port", type=int, default=18087)
    parser.add_argument("--gateway-port", type=int, default=18080)
    parser.add_argument("--service-start-timeout-seconds", type=int, default=45)
    parser.add_argument("--test-timeout-seconds", type=int, default=900)
    parser.add_argument("--skip-beta-services", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report_dir = report_path.parent
    fixture = load_fixture()
    beta_assistant: subprocess.Popen[str] | None = None
    beta_gateway: subprocess.Popen[str] | None = None
    beta_services: dict[str, Any] = {"started": False}
    try:
        devices = discover_devices()
        alpha_device = choose_device(devices, args.alpha_device_id, args.alpha_device_name)
        beta_device = choose_device(devices, args.beta_device_id, args.beta_device_name)
        beta_services["startedAt"] = utc_now()
        if not args.skip_beta_services:
            beta_assistant, beta_gateway, beta_services = start_beta_stack(args, report_dir)
            beta_services["started"] = True
            if not beta_services.get("gatewayReachable"):
                raise RuntimeError("GATE_BLOCK: beta gateway health check failed")
        alpha_run = run_eval("alpha", alpha_device, args)
        alpha_run["startedAt"] = utc_now()
        beta_run = run_eval("beta", beta_device, args)
        report = build_comparison_report(fixture, alpha_run, beta_run, beta_services)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[assistant-skill-comparison] report: {report_path}", flush=True)
        print(f"[assistant-skill-comparison] status: {report['status']}", flush=True)
        return 0 if report["status"] == "passed" else 1
    except Exception as exc:
        failure = {
            "schemaVersion": "assistant.skill-comparison-report.v1",
            "startedAt": utc_now(),
            "endedAt": utc_now(),
            "status": "gate_block",
            "failureReason": str(exc),
            "betaServices": beta_services,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[assistant-skill-comparison] report: {report_path}", flush=True)
        print(f"[assistant-skill-comparison] status: gate_block ({exc})", flush=True)
        return 2
    finally:
        stop_process(beta_gateway)
        stop_process(beta_assistant)
        if not args.skip_beta_services:
            clean_ports([args.assistant_port, args.gateway_port])


if __name__ == "__main__":
    raise SystemExit(main())
