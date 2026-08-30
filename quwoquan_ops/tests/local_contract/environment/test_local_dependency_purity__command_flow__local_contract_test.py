from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
import ast
import tempfile
from pathlib import Path

import pytest

from quwoquan_ops.gate.local_dependency_purity.python_command_flow import (
    reachable_subprocess_command_tokens,
)
from quwoquan_ops.gate.local_dependency_purity.shell_commands import (
    ShellCommandParseError,
    reachable_shell_array_tokens,
)
from quwoquan_ops.gate.verify_local_dependency_purity import (
    _verify_launcher_dependency_helper,
    _verify_locked_offline_flutter_pub_get,
    _verify_uat_static_analysis_coverage,
)

ROOT = Path(__file__).resolve().parents[4]

_ARRAY_CONSUMER = ("python3", "canonical_consumer.py")


def _array_script(before_consumer: str) -> str:
    return f'ARGS=(--base value)\n{before_consumer}\npython3 canonical_consumer.py "${{ARGS[@]}}"\n'


@pytest.mark.parametrize(
    "mutation",
    (
        "unset ARGS",
        "read -r ARGS < /dev/null",
        "declare -n alias=ARGS\nalias+=(--forged value)",
        "eval 'ARGS+=(--forged value)'",
        "ARGS[0]=--forged",
    ),
)
def test_array_projection_rejects_unknown_or_indirect_mutation(
    mutation: str,
) -> None:
    with pytest.raises(ShellCommandParseError):
        reachable_shell_array_tokens(
            _array_script(mutation),
            array_name="ARGS",
            consumer_prefix=_ARRAY_CONSUMER,
        )


@pytest.mark.parametrize(
    "helper_body",
    (
        "unset ARGS",
        "ARGS=(--forged value)",
        "declare -n alias=ARGS; alias+=(--forged value)",
    ),
)
def test_array_projection_rejects_reachable_helper_mutation(
    helper_body: str,
) -> None:
    helper = f"mutate_args() {{ {helper_body}; }}\nmutate_args"
    with pytest.raises(ShellCommandParseError):
        reachable_shell_array_tokens(
            _array_script(helper),
            array_name="ARGS",
            consumer_prefix=_ARRAY_CONSUMER,
        )


def test_array_projection_rejects_dynamic_helper_call() -> None:
    with pytest.raises(ShellCommandParseError):
        reachable_shell_array_tokens(
            _array_script('"$ARRAY_MUTATOR"'),
            array_name="ARGS",
            consumer_prefix=_ARRAY_CONSUMER,
        )


def _launcher_and_helper_sources() -> tuple[str, str]:
    return (
        (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8"),
        (
            ROOT / "quwoquan_app/scripts/device/prepare_flutter_dependencies.py"
        ).read_text(encoding="utf-8"),
    )


def _helper_failures(helper_source: str) -> list[str]:
    launcher_source, _ = _launcher_and_helper_sources()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        launcher = root / "run.sh"
        helper = root / "prepare_flutter_dependencies.py"
        launcher.write_text(launcher_source, encoding="utf-8")
        helper.write_text(helper_source, encoding="utf-8")
        failures: list[str] = []
        _verify_launcher_dependency_helper(
            failures,
            launcher=launcher,
            helper=helper,
        )
        return failures


@pytest.mark.parametrize(
    "decoy",
    (
        (
            "    if False:\n"
            "        subprocess.run([flutter, 'pub', 'get', '--offline', "
            "'--enforce-lockfile'])\n"
        ),
        (
            "    def decoy():\n"
            "        return subprocess.run([flutter, 'pub', 'get', '--offline', "
            "'--enforce-lockfile'])\n"
        ),
        (
            "    decoy = lambda: subprocess.run([flutter, 'pub', 'get', "
            "'--offline', '--enforce-lockfile'])\n"
        ),
    ),
)
def test_helper_ignores_unreachable_subprocess_decoys(decoy: str) -> None:
    _, helper_source = _launcher_and_helper_sources()
    helper_source = helper_source.replace('        "--offline",\n', "", 1)
    helper_source = helper_source.replace(
        "    command = [\n", decoy + "    command = [\n", 1
    )

    failures = _helper_failures(helper_source)

    assert any("locked offline pub replay missing" in failure for failure in failures)


def test_helper_rejects_a_second_reachable_subprocess_call() -> None:
    _, helper_source = _launcher_and_helper_sources()
    reachable_decoy = (
        "    subprocess.run([flutter, 'pub', 'get', '--offline', "
        "'--enforce-lockfile'])\n"
    )
    helper_source = helper_source.replace(
        "    command = [\n", reachable_decoy + "    command = [\n", 1
    )

    failures = _helper_failures(helper_source)

    assert any("locked offline pub replay missing" in failure for failure in failures)


@pytest.mark.parametrize(
    "reachable_decoy",
    (
        (
            "    execute = subprocess.run\n"
            "    execute([flutter, 'pub', 'get', '--offline', "
            "'--enforce-lockfile'])\n"
        ),
        (
            "    def delegated(command):\n"
            "        subprocess.run(command)\n"
            "    delegated([flutter, 'pub', 'get'])\n"
        ),
        (
            "    execute = getattr(subprocess, resolve_executor())\n"
            "    execute([flutter, 'pub', 'get'])\n"
        ),
    ),
)
def test_helper_rejects_reachable_aliased_or_dynamic_executor(
    reachable_decoy: str,
) -> None:
    _, helper_source = _launcher_and_helper_sources()
    helper_source = helper_source.replace(
        "    command = [\n", reachable_decoy + "    command = [\n", 1
    )

    failures = _helper_failures(helper_source)

    assert any("locked offline pub replay missing" in failure for failure in failures)


def test_subprocess_flow_propagates_each_try_path_into_finally() -> None:
    module = ast.parse(
        """
import subprocess

def replay(flutter):
    command = [flutter, "pub", "get", "--offline", "--enforce-lockfile"]
    try:
        command = [flutter, "pub", "get"]
    finally:
        subprocess.run(command)
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get"),)


def test_subprocess_flow_propagates_terminating_try_path_into_finally() -> None:
    module = ast.parse(
        """
import subprocess

def replay(flutter):
    command = [flutter, "pub", "get", "--offline", "--enforce-lockfile"]
    try:
        command = [flutter, "pub", "get"]
        return
    finally:
        subprocess.run(command)
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get"),)


@pytest.mark.parametrize("terminal", ("return", "raise RuntimeError()"))
def test_subprocess_flow_keeps_terminal_finally_paths_out_of_post_try(
    terminal: str,
) -> None:
    module = ast.parse(
        f"""
import subprocess

def replay(flutter, stop):
    command = [flutter, "pub", "get", "--offline", "--enforce-lockfile"]
    try:
        if stop:
            command = [flutter, "pub", "get"]
            {terminal}
    finally:
        subprocess.run(command)
    subprocess.run([flutter, "pub", "get", "--offline", "--enforce-lockfile"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (
        ("<flutter>", "pub", "get"),
        ("<flutter>", "pub", "get", "--offline", "--enforce-lockfile"),
        ("<flutter>", "pub", "get", "--offline", "--enforce-lockfile"),
    )


def test_subprocess_flow_sends_break_path_through_finally() -> None:
    module = ast.parse(
        """
import subprocess

def replay(flutter, values):
    for _ in values:
        command = [flutter, "pub", "get"]
        try:
            break
        finally:
            subprocess.run(command)
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get"),)


def test_subprocess_flow_follows_module_helper_and_import_aliases() -> None:
    module = ast.parse(
        """
import subprocess as process
from subprocess import run as execute

def delegated(command):
    execute(command)

def replay(flutter):
    process.run([flutter, "pub", "get", "--offline", "--enforce-lockfile"])
    delegated([flutter, "pub", "get"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (
        ("<flutter>", "pub", "get", "--offline", "--enforce-lockfile"),
        ("<flutter>", "pub", "get"),
    )


def test_subprocess_flow_keeps_dynamic_helper_commands_fail_closed() -> None:
    module = ast.parse(
        """
from subprocess import run

def delegated(command):
    run(command)

def replay(flutter, resolve_option):
    delegated([flutter, "pub", "get", resolve_option()])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get", "<dynamic>"),)


def test_subprocess_flow_follows_nested_helper_and_executor_aliases() -> None:
    module = ast.parse(
        """
import subprocess

module_execute = subprocess.run

def replay(flutter):
    def delegated(command):
        local_execute = module_execute
        local_execute(command)
    delegated([flutter, "pub", "get"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get"),)


def test_subprocess_flow_projects_dynamic_getattr_executor_fail_closed() -> None:
    module = ast.parse(
        """
import subprocess

def replay(flutter, executor_name):
    execute = getattr(subprocess, executor_name)
    execute([flutter, "pub", "get", "--offline", "--enforce-lockfile"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<dynamic>",),)


def test_subprocess_flow_tracks_local_imports_and_getattr_builtin_alias() -> None:
    module = ast.parse(
        """
def replay(flutter):
    import subprocess as process
    from subprocess import check_call as imported_execute
    builtin_getattr = getattr
    execute = builtin_getattr(process, "run")
    execute([flutter, "pub", "get"])
    imported_execute([flutter, "pub", "get", "--offline"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (
        ("<flutter>", "pub", "get"),
        ("<flutter>", "pub", "get", "--offline"),
    )


def test_subprocess_flow_projects_path_unknown_local_import_fail_closed() -> None:
    module = ast.parse(
        """
def replay(flutter, enabled):
    if enabled:
        import subprocess as process
    process.run([flutter, "pub", "get", "--offline", "--enforce-lockfile"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (
        ("<flutter>", "pub", "get", "--offline", "--enforce-lockfile"),
        ("<dynamic>",),
    )


def test_subprocess_executor_alias_snapshots_resolved_identity() -> None:
    module = ast.parse(
        """
import subprocess as process

def replay(flutter):
    source = process
    execute = source.run
    source = object()
    execute([flutter, "pub", "get", "--offline", "--enforce-lockfile"])
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get", "--offline", "--enforce-lockfile"),)


def test_subprocess_flow_traverses_an_invoked_lambda_body() -> None:
    module = ast.parse(
        """
import subprocess

def replay(flutter):
    (lambda executable: subprocess.run(
        [executable, "pub", "get", "--offline", "--enforce-lockfile"]
    ))(flutter)
"""
    )

    commands = reachable_subprocess_command_tokens(
        module,
        function_name="replay",
        executable_parameter="flutter",
    )

    assert commands == (("<flutter>", "pub", "get", "--offline", "--enforce-lockfile"),)


def test_launcher_helper_rejects_a_second_command_hidden_in_invoked_lambda() -> None:
    _, helper_source = _launcher_and_helper_sources()
    invoked_lambda = "    (lambda: subprocess.run([flutter, 'pub', 'get']))()\n"
    helper_source = helper_source.replace(
        "    command = [\n", invoked_lambda + "    command = [\n", 1
    )

    failures = _helper_failures(helper_source)

    assert any("locked offline pub replay missing" in failure for failure in failures)


@pytest.mark.parametrize(
    "decoy",
    (
        (
            "cat <<'PUB_GET_DECOY'\n"
            "flutter pub get --offline --enforce-lockfile\n"
            "PUB_GET_DECOY\n"
        ),
        "printf '%s' 'flutter pub\nget --offline --enforce-lockfile'\n",
    ),
)
def test_pub_get_scanner_ignores_non_executable_multiline_decoys(decoy: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(decoy + "flutter pub get --offline\n", encoding="utf-8")
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 1
    assert len(failures) == 1
    assert "missing --enforce-lockfile" in failures[0]


def test_pub_get_scanner_does_not_accept_an_indented_heredoc_terminator() -> None:
    decoy = (
        "cat <<'PUB_GET_DECOY'\n"
        "  PUB_GET_DECOY\n"
        "flutter pub get --offline --enforce-lockfile\n"
        "PUB_GET_DECOY\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(decoy + "flutter pub get --offline\n", encoding="utf-8")
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 1
    assert len(failures) == 1
    assert "missing --enforce-lockfile" in failures[0]


@pytest.mark.parametrize(
    "decoy",
    (
        "unused() { flutter pub get --offline --enforce-lockfile; }\n",
        "exit 0\nflutter pub get --offline --enforce-lockfile\n",
        "false && flutter pub get --offline --enforce-lockfile\n",
        "true || flutter pub get --offline --enforce-lockfile\n",
    ),
)
def test_pub_get_scanner_rejects_unreachable_command_decoys(decoy: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(decoy, encoding="utf-8")
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 0
    assert any("must execute Flutter pub get" in failure for failure in failures)


def test_pub_get_scanner_accepts_statically_reached_false_or_command() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(
            "false || flutter pub get --offline --enforce-lockfile\n",
            encoding="utf-8",
        )
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 1
    assert failures == []


@pytest.mark.parametrize(
    "body",
    (
        "if false; then flutter pub get --offline --enforce-lockfile; fi",
        "return 0; flutter pub get --offline --enforce-lockfile",
        "true || flutter pub get --offline --enforce-lockfile",
        "case false in\ntrue) flutter pub get --offline --enforce-lockfile ;;\nesac",
    ),
)
def test_pub_get_scanner_rejects_dead_commands_inside_dispatched_function(
    body: str,
) -> None:
    source = f"replay() {{ {body}; }}\nreplay\n"
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(source, encoding="utf-8")
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 0
    assert any("must execute Flutter pub get" in failure for failure in failures)


def _write_uat_fixture(root: Path) -> tuple[Path, Path]:
    app = root / "quwoquan_app"
    (app / "test/user_acceptance/journeys/startup").mkdir(parents=True)
    (app / "test/support/runtime/patrol").mkdir(parents=True)
    (app / "test_host/patrol/test").mkdir(parents=True)
    (app / "test/user_acceptance/journeys/startup/startup_test.dart").write_text(
        "void main() {}\n", encoding="utf-8"
    )
    (app / "test/support/runtime/patrol/patrol_test_support.dart").write_text(
        "void support() {}\n", encoding="utf-8"
    )
    (app / "analysis_options.yaml").write_text(
        "analyzer:\n"
        "  exclude:\n"
        "    - test/user_acceptance/**\n"
        "    - test/support/runtime/patrol/**\n",
        encoding="utf-8",
    )
    (app / "test_host/patrol/test/canonical").symlink_to(
        Path("../../../test"), target_is_directory=True
    )
    return app, root / "gate_repo.sh"


def _run_app_gate(command: str, *, dispatch: bool = True) -> str:
    script = "run_app() {\n" + command + "\n}\n"
    if dispatch:
        script += (
            'case "$scope" in\n'
            "  all)\n    run_app\n    ;;\n"
            "  app)\n    run_app\n    ;;\n"
            "esac\n"
        )
    return script


@pytest.mark.parametrize(
    "decoy",
    (
        (
            "cat <<'ANALYZE_DECOY'\n"
            "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
            "test/canonical/user_acceptance "
            "test/canonical/support/runtime/patrol)\n"
            "ANALYZE_DECOY\n"
        ),
        (
            "printf '%s' '(cd quwoquan_app/test_host/patrol && flutter analyze\n"
            "test/canonical/user_acceptance "
            "test/canonical/support/runtime/patrol)'\n"
        ),
    ),
)
def test_uat_scanner_ignores_non_executable_multiline_decoys(decoy: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(
            decoy
            + _run_app_gate(
                "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)"
            ),
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any(
        failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
        and "test/canonical/user_acceptance" in failure
        for failure in failures
    )


def test_uat_scanner_rejects_complete_analysis_in_an_uninvoked_function() -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(
            "unused() {\n"
            + complete
            + "\n}\n"
            + _run_app_gate(
                "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)"
            ),
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


def test_uat_scanner_requires_run_app_to_be_dispatched() -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(_run_app_gate(complete, dispatch=False), encoding="utf-8")
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


@pytest.mark.parametrize("redefinition_position", ("before", "after", "control"))
def test_uat_scanner_rejects_run_app_redefinition(
    redefinition_position: str,
) -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    decoy = "run_app() { echo decoy; }\n"
    canonical = _run_app_gate(complete)
    if redefinition_position == "before":
        gate_source = decoy + canonical
    elif redefinition_position == "after":
        gate_source = canonical + decoy
    else:
        gate_source = canonical + "if true; then " + decoy.rstrip() + "; fi\n"
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(gate_source, encoding="utf-8")
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


@pytest.mark.parametrize(
    "dispatch",
    (
        'case "$other" in\n  all) run_app ;;\n  app) run_app ;;\nesac\n',
        'case "$scope" in\n  all) run_app ;;\nesac\n',
        (
            'case "$scope" in\n'
            "  all) if false; then run_app; fi ;;\n"
            "  app) run_app ;;\n"
            "esac\n"
        ),
        (
            "if false; then\n"
            '  case "$scope" in\n'
            "    all) run_app ;;\n"
            "    app) run_app ;;\n"
            "  esac\n"
            "fi\n"
        ),
        ('case "$scope" in\n  all) exit 0; run_app ;;\n  app) run_app ;;\nesac\n'),
        ('case "$scope" in\n  all) run_app ;;\n  app) return 0; run_app ;;\nesac\n'),
        ('exit 0\ncase "$scope" in\n  all) run_app ;;\n  app) run_app ;;\nesac\n'),
        (
            "if true; then exit 0; fi\n"
            'case "$scope" in\n  all) run_app ;;\n  app) run_app ;;\nesac\n'
        ),
        (
            'case "$scope" in\n'
            "  all) run_app | true ;;\n"
            "  app) run_app | true ;;\n"
            "esac\n"
        ),
        (
            'case "$scope" in\n'
            "  all) run_app & wait ;;\n"
            "  app) run_app & wait ;;\n"
            "esac\n"
        ),
        ('case "$scope" in\n  all) false && run_app ;;\n  app) run_app ;;\nesac\n'),
        ('case "$scope" in\n  all) run_app ;;\n  app) true || run_app ;;\nesac\n'),
        (
            'case "$scope" in\n'
            "  all) true && exit 0; run_app ;;\n"
            "  app) run_app ;;\n"
            "esac\n"
        ),
        (
            'case "$scope" in\n'
            "  all) run_app ;;\n"
            "  app) false || return 0; run_app ;;\n"
            "esac\n"
        ),
    ),
)
def test_uat_scanner_rejects_noncanonical_or_dead_scope_dispatch(
    dispatch: str,
) -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(
            "run_app() {\n" + complete + "\n}\n" + dispatch,
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


def test_uat_scanner_rejects_analysis_after_guaranteed_function_return() -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(
            _run_app_gate("if true; then return 0; fi\n" + complete),
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


@pytest.mark.parametrize("suffix", (" | true", " & wait"))
def test_uat_scanner_rejects_pipelined_or_background_analysis(
    suffix: str,
) -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(_run_app_gate(complete + suffix), encoding="utf-8")
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


@pytest.mark.parametrize(
    "body",
    (
        "if false; then {complete}; fi",
        "return 0; {complete}",
        "true || {complete}",
        "case false in\ntrue) {complete} ;;\nesac",
    ),
)
def test_uat_scanner_rejects_dead_analysis_inside_dispatched_run_app(
    body: str,
) -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(_run_app_gate(body.format(complete=complete)), encoding="utf-8")
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)


def test_uat_scanner_does_not_accept_an_indented_heredoc_terminator() -> None:
    complete = (
        "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
        "test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)"
    )
    decoy = "cat <<'ANALYZE_DECOY'\n  ANALYZE_DECOY\n" + complete + "\nANALYZE_DECOY\n"
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(
            decoy
            + _run_app_gate(
                "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)"
            ),
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any("test/canonical/user_acceptance" in failure for failure in failures)
