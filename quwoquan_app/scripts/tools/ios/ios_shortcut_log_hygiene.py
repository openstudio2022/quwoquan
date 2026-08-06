#!/usr/bin/env python3
"""Audit and filter benign iOS Shortcuts indexing noise for local Flutter runs.

This script intentionally stays outside the Flutter app process. It scans the
iOS project for real Shortcut/AppIntents/Siri/CoreSpotlight sources, and can
filter the known benign WFIsolatedShortcutRunner indexing block from local
stdout while preserving Flutter/runtime/video errors.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO


APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IOS_ROOT = APP_ROOT / "ios"


@dataclass(frozen=True)
class AuditRule:
    label: str
    needle: str
    detail: str


@dataclass(frozen=True)
class AuditFinding:
    path: Path
    line: int | None
    label: str
    detail: str
    snippet: str


SOURCE_RULES: tuple[AuditRule, ...] = (
    AuditRule(
        "app-intents-import",
        "import AppIntents",
        "AppIntents can create Shortcut indexing surfaces.",
    ),
    AuditRule(
        "intents-import",
        "import Intents",
        "Intents.framework can donate Siri/Shortcut interactions.",
    ),
    AuditRule(
        "core-spotlight-import",
        "import CoreSpotlight",
        "CoreSpotlight can create system indexing surfaces.",
    ),
    AuditRule(
        "app-intent-type",
        "AppIntent",
        "AppIntent declarations should be reviewed before enabling indexing.",
    ),
    AuditRule(
        "app-shortcuts-provider",
        "AppShortcutsProvider",
        "AppShortcutsProvider registers Shortcut actions for the app.",
    ),
    AuditRule(
        "in-interaction",
        "INInteraction",
        "INInteraction donation can trigger Siri/Shortcut indexing.",
    ),
    AuditRule(
        "in-intent",
        "INIntent",
        "INIntent usage can trigger Siri/Shortcut indexing.",
    ),
    AuditRule(
        "searchable-item",
        "CSSearchableItem",
        "CSSearchableItem participates in Spotlight indexing.",
    ),
    AuditRule(
        "searchable-index",
        "CSSearchableIndex",
        "CSSearchableIndex participates in Spotlight indexing.",
    ),
    AuditRule(
        "ns-user-activity",
        "NSUserActivity(",
        "NSUserActivity donation can feed search/prediction indexing.",
    ),
    AuditRule(
        "eligible-for-search",
        ".isEligibleForSearch",
        "Search-eligible user activities can create indexing surfaces.",
    ),
    AuditRule(
        "eligible-for-prediction",
        ".isEligibleForPrediction",
        "Prediction-eligible activities can create Shortcut suggestions.",
    ),
)

PLIST_RULES: tuple[AuditRule, ...] = (
    AuditRule(
        "siri-usage-description",
        "NSSiriUsageDescription",
        "Siri usage declarations should not be present without a Shortcut feature.",
    ),
    AuditRule(
        "user-activity-types",
        "NSUserActivityTypes",
        "NSUserActivityTypes can register system activity indexing surfaces.",
    ),
    AuditRule(
        "shortcut-items",
        "UIApplicationShortcutItems",
        "Home-screen Shortcut items should be intentional and reviewed.",
    ),
    AuditRule(
        "intents-supported",
        "IntentsSupported",
        "Intent extension declarations should not be present for this app path.",
    ),
    AuditRule(
        "intents-locked",
        "IntentsRestrictedWhileLocked",
        "Intent extension declarations should not be present for this app path.",
    ),
    AuditRule(
        "intents-extension",
        "com.apple.intents-service",
        "Intents app extensions can trigger Shortcut indexing.",
    ),
    AuditRule(
        "intents-ui-extension",
        "com.apple.intents-ui-service",
        "Intents UI extensions can trigger Shortcut indexing.",
    ),
)

ENTITLEMENT_RULES: tuple[AuditRule, ...] = (
    AuditRule(
        "siri-entitlement",
        "com.apple.developer.siri",
        "Siri entitlement should not be enabled without a Shortcut feature.",
    ),
)

PROJECT_RULES: tuple[AuditRule, ...] = (
    AuditRule(
        "app-extension-product",
        "wrapper.app-extension",
        "App extension products should be reviewed before enabling indexing.",
    ),
    AuditRule(
        "intentdefinition-reference",
        ".intentdefinition",
        "Intent definition files register Siri/Shortcut surfaces.",
    ),
)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(APP_ROOT.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_audit_files(ios_root: Path) -> Iterable[tuple[Path, tuple[AuditRule, ...]]]:
    if not ios_root.exists():
        return

    runner_info = ios_root / "Runner" / "Info.plist"
    if runner_info.is_file():
        yield runner_info, PLIST_RULES

    project_file = ios_root / "Runner.xcodeproj" / "project.pbxproj"
    if project_file.is_file():
        yield project_file, PROJECT_RULES

    for path in sorted(ios_root.glob("**/*.entitlements")):
        yield path, ENTITLEMENT_RULES

    for path in sorted(ios_root.glob("**/*.intentdefinition")):
        yield path, (
            AuditRule(
                "intentdefinition-file",
                "",
                "Intent definition files should not exist without an approved Shortcut feature.",
            ),
        )

    for path in sorted(ios_root.glob("**/*.appex")):
        yield path, (
            AuditRule(
                "appex-bundle",
                "",
                "App extension bundles should not exist in the app source tree.",
            ),
        )

    source_globs = ("Runner/**/*.swift", "Runner/**/*.m", "Runner/**/*.mm", "Runner/**/*.h")
    for pattern in source_globs:
        for path in sorted(ios_root.glob(pattern)):
            if path.is_file():
                yield path, SOURCE_RULES

    pod_support = ios_root / "Pods" / "Target Support Files"
    if pod_support.is_dir():
        for path in sorted(pod_support.glob("**/*.plist")):
            if path.is_file():
                yield path, PLIST_RULES


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def audit_ios_shortcut_sources(ios_root: Path = DEFAULT_IOS_ROOT) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for path, rules in _iter_audit_files(ios_root):
        if path.is_dir():
            for rule in rules:
                findings.append(
                    AuditFinding(
                        path=path,
                        line=None,
                        label=rule.label,
                        detail=rule.detail,
                        snippet=path.name,
                    )
                )
            continue

        text = _read_text(path)
        for rule in rules:
            if not rule.needle:
                findings.append(
                    AuditFinding(
                        path=path,
                        line=None,
                        label=rule.label,
                        detail=rule.detail,
                        snippet=path.name,
                    )
                )
                continue
            start = 0
            while True:
                offset = text.find(rule.needle, start)
                if offset == -1:
                    break
                line = _line_for_offset(text, offset)
                snippet = text.splitlines()[line - 1].strip()
                findings.append(
                    AuditFinding(
                        path=path,
                        line=line,
                        label=rule.label,
                        detail=rule.detail,
                        snippet=snippet,
                    )
                )
                start = offset + len(rule.needle)
    return findings


PRIMARY_WF_TOKENS = (
    "WFIsolatedShortcutRunner",
    "WFToolKitIndexingRequest",
)

WF_CONTINUATION_TOKENS = (
    "VoiceShortcutClient.ToolKitIndexingReason",
    "LaunchServicesSnapshot",
    "Inserted en/languageModel",
    "Resolved Preferred localizations:",
    "Indexed:",
    "Errored:",
    "Skipped:",
    "Finished in ",
)


def _is_wf_block_start(line: str) -> bool:
    return any(token in line for token in PRIMARY_WF_TOKENS)


def _is_wf_continuation(line: str) -> bool:
    return any(token in line for token in WF_CONTINUATION_TOKENS)


def _is_wf_block_end(line: str) -> bool:
    return "WFIsolatedShortcutRunner unaliveProcess" in line


def _is_benign_wf_block(lines: list[str]) -> bool:
    text = "".join(lines)
    has_indexer = "WFToolKitIndexingRequest" in text or "WFIsolatedShortcutRunner" in text
    indexed_zero = any(line.strip() == "Indexed: 0" for line in lines)
    errored_zero = any(line.strip() == "Errored: 0" for line in lines)
    has_nonzero_error = any(
        line.strip().startswith("Errored:") and line.strip() != "Errored: 0"
        for line in lines
    )
    return has_indexer and indexed_zero and errored_zero and not has_nonzero_error


class ShortcutLogNoiseFilter:
    """Line-buffered filter for benign iOS Shortcut indexing blocks."""

    def __init__(self) -> None:
        self._buffer: list[str] = []

    def feed_line(self, line: str) -> list[str]:
        if not self._buffer:
            if _is_wf_block_start(line):
                self._buffer.append(line)
                if _is_wf_block_end(line):
                    return self._flush()
                return []
            return [line]

        if _is_wf_block_start(line) or _is_wf_continuation(line):
            self._buffer.append(line)
            if _is_wf_block_end(line):
                return self._flush()
            return []

        output = self._flush()
        output.append(line)
        return output

    def finish(self) -> list[str]:
        return self._flush()

    def _flush(self) -> list[str]:
        lines = self._buffer
        self._buffer = []
        if lines and _is_benign_wf_block(lines):
            return []
        return lines


def filter_shortcut_log_noise(lines: Iterable[str]) -> list[str]:
    noise_filter = ShortcutLogNoiseFilter()
    output: list[str] = []
    for line in lines:
        output.extend(noise_filter.feed_line(line))
    output.extend(noise_filter.finish())
    return output


def _print_findings(findings: list[AuditFinding], *, stream: TextIO) -> None:
    print(
        "[ios_shortcut_log_hygiene] FAIL: app-side Shortcut/AppIntents/Siri/"
        "CoreSpotlight source found.",
        file=stream,
    )
    for finding in findings:
        location = _display_path(finding.path)
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        print(f"  - {location} [{finding.label}]", file=stream)
        print(f"    {finding.detail}", file=stream)
        if finding.snippet:
            print(f"    snippet: {finding.snippet}", file=stream)


def cmd_audit(args: argparse.Namespace) -> int:
    ios_root = Path(args.ios_root).resolve()
    findings = audit_ios_shortcut_sources(ios_root)
    if findings:
        _print_findings(findings, stream=sys.stderr)
        return 1
    print(
        "[ios_shortcut_log_hygiene] OK: no app-side Shortcut/AppIntents/Siri/"
        "CoreSpotlight sources found."
    )
    return 0


def cmd_filter_log(args: argparse.Namespace) -> int:
    if args.log_file == "-":
        input_lines = sys.stdin.readlines()
    else:
        input_lines = Path(args.log_file).read_text(encoding="utf-8").splitlines(True)
    sys.stdout.writelines(filter_shortcut_log_noise(input_lines))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if not args.skip_audit:
        findings = audit_ios_shortcut_sources(Path(args.ios_root).resolve())
        if findings:
            _print_findings(findings, stream=sys.stderr)
            return 1

    flutter_args = list(args.flutter_args)
    if flutter_args and flutter_args[0] == "--":
        flutter_args = flutter_args[1:]
    cmd = ["bash", str(APP_ROOT / "run.sh"), *flutter_args]
    print(f"[ios_shortcut_log_hygiene] running: {' '.join(cmd)}", file=sys.stderr)

    process = subprocess.Popen(
        cmd,
        cwd=APP_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    noise_filter = ShortcutLogNoiseFilter()
    try:
        for line in process.stdout:
            for output_line in noise_filter.feed_line(line):
                sys.stdout.write(output_line)
                sys.stdout.flush()
        for output_line in noise_filter.finish():
            sys.stdout.write(output_line)
            sys.stdout.flush()
    except KeyboardInterrupt:
        process.terminate()
        raise
    return process.wait()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit and filter benign iOS Shortcuts indexing logs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit", help="Fail if iOS Shortcut/AppIntents/Siri/Spotlight sources exist."
    )
    audit_parser.add_argument("--ios-root", default=str(DEFAULT_IOS_ROOT))
    audit_parser.set_defaults(handler=cmd_audit)

    filter_parser = subparsers.add_parser(
        "filter-log", help="Filter a saved flutter run log or stdin."
    )
    filter_parser.add_argument(
        "log_file", nargs="?", default="-", help="Log file to filter, or '-' for stdin."
    )
    filter_parser.set_defaults(handler=cmd_filter_log)

    run_parser = subparsers.add_parser(
        "run", help="Run the canonical App launcher with a narrow benign WF log filter."
    )
    run_parser.add_argument("--ios-root", default=str(DEFAULT_IOS_ROOT))
    run_parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip source audit before launching the canonical App launcher.",
    )
    run_parser.add_argument("flutter_args", nargs=argparse.REMAINDER)
    run_parser.set_defaults(handler=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
