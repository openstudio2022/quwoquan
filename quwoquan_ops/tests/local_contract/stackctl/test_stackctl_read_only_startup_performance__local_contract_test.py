"""Read-only stackctl startup stays isolated from unrelated command domains.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"


def _source() -> str:
    return STACKCTL.read_text(encoding="utf-8")


def test_read_only_bootstrap_precedes_heavy_stackctl_import_graph__local_contract() -> None:
    tree = ast.parse(_source())
    guard_line = next(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.If)
        and any(
            isinstance(item, ast.Constant)
            and item.value == "__main__"
            for item in ast.walk(node.test)
        )
        and "read_only_entry" in ast.get_source_segment(_source(), node)
    )
    first_ops_import_line = next(
        node.lineno
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("quwoquan_ops"))
            or (
                isinstance(node, ast.Import)
                and any(alias.name.startswith("quwoquan_ops") for alias in node.names)
            )
        )
    )
    assert guard_line < first_ops_import_line


def test_bootstrap_command_does_not_treat_global_option_value_as_command__local_contract() -> None:
    namespace: dict[str, object] = {"Sequence": __import__("collections.abc").abc.Sequence}
    tree = ast.parse(_source())
    definition = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_bootstrap_command"
    )
    exec(compile(ast.Module(body=[definition], type_ignores=[]), str(STACKCTL), "exec"), namespace)
    resolve = namespace["_bootstrap_command"]
    assert resolve(["--report-dir", "status", "package", "--env", "alpha"]) == "package"
    assert resolve(["--output-format=json", "health", "--target", "alpha-local"]) == "health"



def test_main_dispatch_uses_live_stackctl_monkeypatch_surface__local_contract(
    monkeypatch,
) -> None:
    from argparse import Namespace

    from quwoquan_ops.cli import stackctl

    expected = {"exitCode": 7, "summary": "patched package handler"}
    received: list[Namespace] = []

    class Parser:
        @staticmethod
        def parse_args() -> Namespace:
            return Namespace(command="package", output_format="json")

    def patched_handler(args: Namespace) -> dict[str, object]:
        received.append(args)
        return expected

    monkeypatch.setattr(stackctl, "build_parser", Parser)
    monkeypatch.setattr(stackctl, "command_package", patched_handler)

    assert stackctl.main() == 7
    assert len(received) == 1
    assert received[0].command == "package"


def test_dispatch_covers_every_registered_parser_command__local_contract() -> None:
    import argparse

    from quwoquan_ops.cli import stackctl
    from quwoquan_ops.cli.commands import stackctl_dispatch

    command_action = next(
        action
        for action in stackctl.build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    handlers = stackctl_dispatch.command_handlers(vars(stackctl))

    assert set(handlers) == set(command_action.choices)


def test_stackctl_contract_exports_defined_canonical_constants__local_contract() -> None:
    from quwoquan_ops.cli.commands import stackctl_contract

    assert set(stackctl_contract.__all__) == {
        name for name in stackctl_contract.__all__ if hasattr(stackctl_contract, name)
    }
    assert stackctl_contract.DEFAULT_TARGET_BY_ENV == {
        "alpha": "alpha-local",
        "beta": "beta-local",
        "gamma": "gamma-local",
        "prod": "prod-hosted",
    }
    assert stackctl_contract.PROVIDER_CONFORMANCE_SCRIPT == (
        "quwoquan_ops/cli/lib/provider_conformance.py"
    )


def test_mutating_and_read_only_help_bootstraps__local_contract() -> None:
    for command in ("package", "status", "health", "inspect", "doctor"):
        result = subprocess.run(
            [sys.executable, str(STACKCTL), command, "--help"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, f"{command}: {result.stderr}"


def test_read_only_facade_covers_static_command_collaborators__local_contract() -> None:
    from quwoquan_ops.cli import read_only_entry

    roots = (
        (ROOT / "quwoquan_ops/cli/commands/status.py", None),
        (ROOT / "quwoquan_ops/cli/commands/health.py", None),
        (ROOT / "quwoquan_ops/cli/commands/inspect_surface.py", None),
        (ROOT / "quwoquan_ops/cli/commands/doctor.py", None),
        (ROOT / "quwoquan_ops/cli/commands/diagnostics_shared.py", None),
        (
            ROOT / "quwoquan_ops/cli/commands/environment_probe.py",
            frozenset({"_run_environment_integration_probe"}),
        ),
        (ROOT / "quwoquan_ops/cli/lib/read_only_user_availability.py", None),
        (
            ROOT / "quwoquan_ops/cli/commands/deploy_release_state.py",
            frozenset(
                {"_load_release_state", "_load_release_state_path", "_release_state_dir"}
            ),
        ),
    )
    collaborators: set[str] = set()
    for source_path, read_only_functions in roots:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        search_roots: tuple[ast.AST, ...] = (tree,)
        if read_only_functions is not None:
            functions = {
                node.name: node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert read_only_functions <= functions.keys()
            search_roots = tuple(
                functions[name] for name in sorted(read_only_functions)
            )
        for search_root in search_roots:
            collaborators.update(
                node.attr
                for node in ast.walk(search_root)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "_stackctl"
            )
    provided = set(read_only_entry._BINDINGS) | {
        "ROOT",
        "resolve_report_dir",
        "_CanonicalLocalHTTPSConnection",
    }
    assert collaborators <= provided, sorted(collaborators - provided)


def test_environment_integration_auth_bindings_are_lazy__local_contract(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "probe.json"
    script = f"""
import json
import sys
from pathlib import Path
from quwoquan_ops.cli import read_only_entry
module_name = 'quwoquan_ops.cli.lib.local_environment_auth'
facade = read_only_entry.install_facade()
loaded_before = module_name in sys.modules
open_session = facade.open_test_data_acceptance_session
loaded_after_open = module_name in sys.modules
close_actor = facade.close_test_data_acceptance_actor
Path({str(probe)!r}).write_text(
    json.dumps(
        {{
            'closeCallable': callable(close_actor),
            'loadedAfterOpen': loaded_after_open,
            'loadedBefore': loaded_before,
            'openCallable': callable(open_session),
        }}
    ),
    encoding='utf-8',
)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(probe.read_text(encoding="utf-8")) == {
        "closeCallable": True,
        "loadedAfterOpen": True,
        "loadedBefore": False,
        "openCallable": True,
    }


def test_prod_hosted_release_state_reader_is_lazy__local_contract(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "probe.json"
    state_dir = tmp_path / "release-state"
    state_dir.mkdir()
    (state_dir / "prod-stack.state").write_text(
        "schema=prod-release-ledger\nstage=canary\n",
        encoding="utf-8",
    )
    script = f"""
import json
import os
import sys
from pathlib import Path
from quwoquan_ops.cli import read_only_entry
module_name = 'quwoquan_ops.cli.commands.deploy_release_state'
facade = read_only_entry.install_facade()
loaded_before = module_name in sys.modules
os.environ['QWQ_PROD_RELEASE_STATE_DIR'] = {str(state_dir)!r}
resolved = facade._load_release_state()
loaded_after = module_name in sys.modules
forbidden = (
    'quwoquan_ops.cli.lib.test_data',
    'quwoquan_ops.cli.lib.objective_execution',
    'quwoquan_ops.cli.commands.app_preflight',
    'quwoquan_ops.cli.commands.app_uat_evidence',
    'quwoquan_ops.cli.commands.package_',
    'quwoquan_ops.migrations.',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
Path({str(probe)!r}).write_text(
    json.dumps(
        {{
            'loadedAfter': loaded_after,
            'loadedBefore': loaded_before,
            'resolved': resolved,
            'unrelated': loaded,
        }}
    ),
    encoding='utf-8',
)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(probe.read_text(encoding="utf-8")) == {
        "loadedAfter": True,
        "loadedBefore": False,
        "resolved": {"schema": "prod-release-ledger", "stage": "canary"},
        "unrelated": [],
    }


def test_inspect_facade_resolves_socket_probe_without_unrelated_domains__local_contract() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from quwoquan_ops.cli import read_only_entry; "
                "facade=read_only_entry.install_facade(); "
                "assert callable(facade.socket_probe); "
                "forbidden=('quwoquan_ops.cli.lib.test_data',"
                "'quwoquan_ops.cli.lib.objective_execution',"
                "'quwoquan_ops.cli.commands.app_uat_evidence',"
                "'quwoquan_ops.cli.commands.deploy_',"
                "'quwoquan_ops.cli.commands.package_',"
                "'quwoquan_ops.migrations.'); "
                "assert not [n for n in sys.modules if n.startswith(forbidden)]"
            ),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr



def test_content_uat_lookup_does_not_descend_unrelated_output_tree__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from quwoquan_ops.cli.lib.read_only_user_availability import (
        _content_uat_report_candidates,
    )

    runs = tmp_path / "runs"
    expected = runs / "canonical-run" / "report.json"
    expected.parent.mkdir(parents=True)
    expected.write_text("{}\n", encoding="utf-8")
    unrelated = runs / "unrelated" / "deep" / "output"
    unrelated.mkdir(parents=True)
    for index in range(200):
        (unrelated / f"artifact-{index}.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        Path,
        "rglob",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("read-only UAT lookup must not recursively scan output trees")
        ),
    )

    assert [path for _modified, path in _content_uat_report_candidates((runs,))] == [
        expected
    ]


def test_health_facade_resolves_json_payload_without_unrelated_domains__local_contract(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "probe.json"
    script = f"""
import json
import sys
from pathlib import Path
from quwoquan_ops.cli import read_only_entry
facade = read_only_entry.install_facade()
payload_path = Path({str(tmp_path / "payload.json")!r})
payload_path.write_text('{{"status": "passed"}}\\n', encoding='utf-8')
resolved = facade._read_json_payload(payload_path)
forbidden = (
    'quwoquan_ops.cli.lib.test_data',
    'quwoquan_ops.cli.lib.objective_execution',
    'quwoquan_ops.cli.commands.app_preflight',
    'quwoquan_ops.cli.commands.app_uat_evidence',
    'quwoquan_ops.cli.commands.deploy_',
    'quwoquan_ops.cli.commands.package_',
    'quwoquan_ops.migrations.',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
Path({str(probe)!r}).write_text(
    json.dumps({{'resolved': resolved, 'loaded': loaded}}),
    encoding='utf-8',
)
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(probe.read_text(encoding="utf-8")) == {
        "resolved": {"status": "passed"},
        "loaded": [],
    }


def test_read_only_help_does_not_load_unrelated_domains__local_contract(tmp_path: Path) -> None:
    probe = tmp_path / "probe.json"
    script = f"""
import json
import runpy
import sys
sys.argv = [{str(STACKCTL)!r}, 'status', '--help']
try:
    runpy.run_path({str(STACKCTL)!r}, run_name='__main__')
except SystemExit as exc:
    if exc.code not in (0, None):
        raise
forbidden = (
    'quwoquan_ops.cli.lib.test_data',
    'quwoquan_ops.cli.lib.objective_execution',
    'quwoquan_ops.cli.commands.app_preflight',
    'quwoquan_ops.cli.commands.app_uat_evidence',
    'quwoquan_ops.cli.commands.deploy_',
    'quwoquan_ops.cli.commands.package_',
    'quwoquan_ops.migrations.',
)
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
open({str(probe)!r}, 'w', encoding='utf-8').write(json.dumps(loaded))
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(probe.read_text(encoding="utf-8")) == []
