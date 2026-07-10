from __future__ import annotations



from support.data_cli_fixtures import *  # noqa: F401,F403
import pytest



def test_cli_has_data_root_and_no_flat_explore():
    ok = subprocess.run(
        [sys.executable, str(CLI), "data", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert "baseline" in ok.stdout and "workflow" in ok.stdout

    bad = subprocess.run(
        [sys.executable, str(CLI), "explore", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode != 0
    assert "invalid choice" in bad.stderr or "invalid choice" in bad.stdout

    task_help = subprocess.run(
        [sys.executable, str(CLI), "task", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert task_help.returncode == 0, task_help.stderr
    assert "scaled-e2e" in task_help.stdout

    env_help = subprocess.run(
        [sys.executable, str(CLI), "env", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert env_help.returncode == 0, env_help.stderr
    for name in ("doctor", "prepare", "preflight", "ready"):
        assert name in env_help.stdout

def test_python_runtime_prefers_data_venv_when_current_lacks_cursor_sdk():
    original_candidates = python_runtime.candidate_pythons
    original_has_modules = python_runtime.python_has_modules
    current = Path("/usr/bin/python3")
    data_python = python_runtime.DATA_VENV_PYTHON
    try:
        python_runtime.candidate_pythons = lambda include_current=True: [current, data_python]

        def _fake_has_modules(python, modules):
            if Path(python) == data_python:
                return True, []
            return False, ["cursor_sdk: No module named 'cursor_sdk'"]

        python_runtime.python_has_modules = _fake_has_modules
        assert python_runtime.resolve_data_agent_python(include_current=True) == data_python
    finally:
        python_runtime.candidate_pythons = original_candidates
        python_runtime.python_has_modules = original_has_modules

def test_environment_preflight_gates_key_runtime_and_network():
    original_runtime_report = python_runtime.runtime_report
    original_network = python_runtime.check_network_endpoints
    original_cloud_api = python_runtime._cursor_cloud_api_probe
    old_key = os.environ.pop("CURSOR_API_KEY", None)
    old_key_file = os.environ.pop("QWQ_CURSOR_API_KEY_FILE", None)
    try:
        python_runtime.runtime_report = lambda: {
            "schemaVersion": "quwoquan_data.python_runtime",
            "currentPython": "/usr/bin/python3",
            "resolvedPython": str(python_runtime.DATA_VENV_PYTHON),
            "ready": True,
            "candidates": [],
        }
        missing_key = python_runtime.environment_preflight(check_network=True)
        assert missing_key["ready"] is False
        assert "CURSOR_API_KEY missing" in missing_key["issues"]
        assert missing_key["network"]["skipped"] is True

        os.environ["CURSOR_API_KEY"] = "not-a-cursor-key"
        bad_key = python_runtime.environment_preflight(check_network=True)
        assert bad_key["ready"] is False
        assert "CURSOR_API_KEY format invalid" in bad_key["issues"]
        assert bad_key["network"]["skipped"] is True

        os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)
        python_runtime.check_network_endpoints = lambda **_kwargs: {
            "checked": True,
            "skipped": False,
            "ready": True,
            "endpoints": [],
            "issues": [],
        }
        python_runtime._cursor_cloud_api_probe = lambda **_kwargs: {
            "checked": True,
            "ready": True,
            "endpoint": python_runtime.CURSOR_CLOUD_API_ME_URL,
            "status": 200,
            "keyType": "user_api_key",
            "issues": [],
        }
        ready = python_runtime.environment_preflight(check_network=True)
        assert ready["ready"] is True
        assert ready["network"]["checked"] is True
        assert ready["cursorCloudApi"]["checked"] is True
    finally:
        python_runtime.runtime_report = original_runtime_report
        python_runtime.check_network_endpoints = original_network
        python_runtime._cursor_cloud_api_probe = original_cloud_api
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key
        if old_key_file is None:
            os.environ.pop("QWQ_CURSOR_API_KEY_FILE", None)
        else:
            os.environ["QWQ_CURSOR_API_KEY_FILE"] = old_key_file

def test_env_cli_preflight_local_runtime_still_checks_cloud_api(monkeypatch, capsys):
    from env import handler as env_handler

    seen = {}

    def _fake_preflight(**kwargs):
        seen.update(kwargs)
        return {
            "schemaVersion": "quwoquan_data.environment_preflight",
            "runtime": {"ready": True},
            "cursorApiKey": {"present": True, "valid": True},
            "network": {"checked": True, "ready": True, "endpoints": [], "issues": []},
            "cursorCloudApi": {
                "checked": True,
                "ready": False,
                "errorCode": "plan_required",
                "issues": [],
            },
            "cursorStartup": {"checked": False, "ready": True, "skipReason": "disabled", "issues": []},
            "ready": False,
            "issues": ["plan_required"],
        }

    monkeypatch.setattr(env_handler, "environment_preflight", _fake_preflight)
    with pytest.raises(SystemExit):
        env_handler.handle_preflight(
            argparse.Namespace(
                no_cursor_key=False,
                no_network=False,
                endpoint=None,
                timeout_seconds=1.0,
                no_cursor_startup=True,
                cursor_startup=False,
                model="composer",
                runtime="local",
                startup_timeout_seconds=1.0,
                json=True,
            )
        )
    capsys.readouterr()

    assert seen["check_cursor_cloud_api"] is True
    assert seen["cursor_startup_runtime"] == "local"

def test_env_cli_preflight_cloud_runtime_checks_cloud_api(monkeypatch, capsys):
    from env import handler as env_handler

    seen = {}

    def _fake_preflight(**kwargs):
        seen.update(kwargs)
        return {
            "schemaVersion": "quwoquan_data.environment_preflight",
            "runtime": {"ready": True},
            "cursorApiKey": {"present": True, "valid": True},
            "network": {"checked": True, "ready": True, "endpoints": [], "issues": []},
            "cursorCloudApi": {"checked": True, "ready": True, "issues": []},
            "cursorStartup": {"checked": False, "ready": True, "skipReason": "disabled", "issues": []},
            "ready": True,
            "issues": [],
        }

    monkeypatch.setattr(env_handler, "environment_preflight", _fake_preflight)
    env_handler.handle_preflight(
        argparse.Namespace(
            no_cursor_key=False,
            no_network=False,
            endpoint=None,
            timeout_seconds=1.0,
            no_cursor_startup=True,
            cursor_startup=False,
            model="composer",
            runtime="cloud",
            startup_timeout_seconds=1.0,
            json=True,
        )
    )
    capsys.readouterr()

    assert seen["check_cursor_cloud_api"] is True
    assert seen["cursor_startup_runtime"] == "cloud"

def test_environment_preflight_refreshes_key_file_before_cloud_probe(tmp_path):
    original_runtime_report = python_runtime.runtime_report
    original_network = python_runtime.check_network_endpoints
    original_cloud_api = python_runtime._cursor_cloud_api_probe
    old_key = os.environ.get("CURSOR_API_KEY")
    old_key_file = os.environ.get("QWQ_CURSOR_API_KEY_FILE")
    stale_key = "crsr_" + ("a" * 32)
    fresh_key = "crsr_" + ("b" * 32)
    key_file = tmp_path / "cursor_api_key"
    key_file.write_text(fresh_key, encoding="utf-8")
    seen = {}
    try:
        os.environ["CURSOR_API_KEY"] = stale_key
        os.environ["QWQ_CURSOR_API_KEY_FILE"] = str(key_file)
        python_runtime.runtime_report = lambda: {
            "schemaVersion": "quwoquan_data.python_runtime",
            "currentPython": "/usr/bin/python3",
            "resolvedPython": str(python_runtime.DATA_VENV_PYTHON),
            "ready": True,
            "candidates": [],
        }
        python_runtime.check_network_endpoints = lambda **_kwargs: {
            "checked": True,
            "skipped": False,
            "ready": True,
            "endpoints": [],
            "issues": [],
        }

        def _cloud_api_probe(**_kwargs):
            seen["key"] = os.environ.get("CURSOR_API_KEY")
            return {
                "checked": True,
                "ready": True,
                "endpoint": python_runtime.CURSOR_CLOUD_API_ME_URL,
                "status": 200,
                "keyType": "user_api_key",
                "issues": [],
            }

        python_runtime._cursor_cloud_api_probe = _cloud_api_probe
        report = python_runtime.environment_preflight(check_network=True)
    finally:
        python_runtime.runtime_report = original_runtime_report
        python_runtime.check_network_endpoints = original_network
        python_runtime._cursor_cloud_api_probe = original_cloud_api
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key
        if old_key_file is None:
            os.environ.pop("QWQ_CURSOR_API_KEY_FILE", None)
        else:
            os.environ["QWQ_CURSOR_API_KEY_FILE"] = old_key_file

    assert report["ready"] is True
    assert seen["key"] == fresh_key
    assert report["cursorApiKey"]["present"] is True

def test_cursor_cloud_api_probe_reports_plan_required():
    import io

    original_urlopen = python_runtime.urlrequest.urlopen
    old_key = os.environ.get("CURSOR_API_KEY")
    os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)

    def _fake_urlopen(_request, timeout):  # noqa: ARG001
        raise python_runtime.urlerror.HTTPError(
            python_runtime.CURSOR_CLOUD_API_ME_URL,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(
                json.dumps(
                    {
                        "error": {
                            "code": "plan_required",
                            "message": "Cloud Agent is not available for free users. Please upgrade to Pro.",
                        }
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            ),
        )

    try:
        python_runtime.urlrequest.urlopen = _fake_urlopen
        report = python_runtime._cursor_cloud_api_probe(timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key

    assert report["checked"] is True
    assert report["ready"] is False
    assert report["status"] == 403
    assert report["errorCode"] == "plan_required"
    assert any("plan_required" in item for item in report["issues"])

def test_cursor_cloud_api_probe_uses_user_api_key_bearer_auth():
    original_urlopen = python_runtime.urlrequest.urlopen
    old_key = os.environ.get("CURSOR_API_KEY")
    key = "crsr_" + ("x" * 32)
    os.environ["CURSOR_API_KEY"] = key
    seen_headers = {}

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "userId": "user_123",
                    "userEmail": "data@example.test",
                    "apiKeyName": "scale-key",
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def _fake_urlopen(request, timeout):  # noqa: ARG001
        seen_headers.update(dict(request.header_items()))
        return _FakeResponse()

    try:
        python_runtime.urlrequest.urlopen = _fake_urlopen
        report = python_runtime._cursor_cloud_api_probe(timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key

    assert report["ready"] is True
    assert report["keyType"] == "user_api_key"
    assert seen_headers["Authorization"] == f"Bearer {key}"

def test_cursor_cloud_api_probe_falls_back_to_curl_for_ssl_error():
    original_urlopen = python_runtime.urlrequest.urlopen
    original_which = python_runtime.shutil.which
    original_run = python_runtime.subprocess.run
    old_key = os.environ.get("CURSOR_API_KEY")
    os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)

    class _FakeProc:
        returncode = 22
        stdout = json.dumps(
            {
                "error": {
                    "code": "plan_required",
                    "message": "Cloud Agent is not available for free users. Please upgrade to Pro.",
                }
            },
            ensure_ascii=False,
        ) + "\n403"
        stderr = "curl: (22) The requested URL returned error: 403"

    try:
        python_runtime.urlrequest.urlopen = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            python_runtime.urlerror.URLError("EOF occurred in violation of protocol")
        )
        python_runtime.shutil.which = lambda name: "/usr/bin/curl" if name == "curl" else None
        python_runtime.subprocess.run = lambda *_args, **_kwargs: _FakeProc()
        report = python_runtime._cursor_cloud_api_probe(timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen
        python_runtime.shutil.which = original_which
        python_runtime.subprocess.run = original_run
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key

    assert report["checked"] is True
    assert report["ready"] is False
    assert report["status"] == 403
    assert report["errorCode"] == "plan_required"
    assert any("plan_required" in item for item in report["issues"])

def test_environment_preflight_blocks_plan_required_before_cursor_startup():
    original_runtime_report = python_runtime.runtime_report
    original_network = python_runtime.check_network_endpoints
    original_cloud_api = python_runtime._cursor_cloud_api_probe
    original_startup = python_runtime.cursor_startup_probe
    old_key = os.environ.get("CURSOR_API_KEY")
    try:
        os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)
        python_runtime.runtime_report = lambda: {
            "schemaVersion": "quwoquan_data.python_runtime",
            "currentPython": "/usr/bin/python3",
            "resolvedPython": str(python_runtime.DATA_VENV_PYTHON),
            "ready": True,
            "candidates": [],
        }
        python_runtime.check_network_endpoints = lambda **_kwargs: {
            "checked": True,
            "skipped": False,
            "ready": True,
            "endpoints": [],
            "issues": [],
        }
        python_runtime._cursor_cloud_api_probe = lambda **_kwargs: {
            "checked": True,
            "ready": False,
            "endpoint": python_runtime.CURSOR_CLOUD_API_ME_URL,
            "status": 403,
            "keyType": "user_api_key",
            "errorCode": "plan_required",
            "message": "Cloud Agent is not available for free users. Please upgrade to Pro.",
            "issues": [
                "Cursor Cloud Agent unavailable for current API key: plan_required "
                "(Cloud Agent is not available for free users. Please upgrade to Pro.)"
            ],
        }

        def _fail_startup(**_kwargs):
            raise AssertionError("cursor_startup_probe should be skipped when cloud API probe failed")

        python_runtime.cursor_startup_probe = _fail_startup
        report = python_runtime.environment_preflight(
            check_network=True,
            check_cursor_startup=True,
        )
    finally:
        python_runtime.runtime_report = original_runtime_report
        python_runtime.check_network_endpoints = original_network
        python_runtime._cursor_cloud_api_probe = original_cloud_api
        python_runtime.cursor_startup_probe = original_startup
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key

    assert report["ready"] is False
    assert report["cursorCloudApi"]["errorCode"] == "plan_required"
    assert any("plan_required" in item for item in report["issues"])
    assert report["cursorStartup"]["checked"] is False

def test_cursor_startup_probe_preserves_sdk_error_diagnostics():
    old_key = os.environ.get("CURSOR_API_KEY")
    original_run = python_runtime.subprocess.run
    original_resolve = python_runtime.resolve_data_agent_python
    try:
        os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)
        python_runtime.resolve_data_agent_python = lambda include_current=True: Path(sys.executable)

        class _Completed:
            returncode = 0
            stderr = ""
            stdout = json.dumps(
                {
                    "ready": False,
                    "started": False,
                    "probeType": "agent_prompt_smoke",
                    "status": "error",
                    "errorClass": "InternalServerError",
                    "error": "internal error crsr_" + ("x" * 32),
                    "retryable": False,
                    "errorCode": "internal",
                    "httpStatus": "500",
                    "protoErrorCode": None,
                    "requestId": None,
                    "details": [],
                    "headers": {"content-type": "application/json"},
                    "retryAfter": None,
                },
                ensure_ascii=False,
            )

        def _fake_run(*_args, **kwargs):
            assert kwargs["env"]["CURSOR_API_KEY"].startswith("crsr_")
            return _Completed()

        python_runtime.subprocess.run = _fake_run
        report = python_runtime.cursor_startup_probe(
            model="composer",
            runtime="local",
            timeout_seconds=1,
        )

        assert report["ready"] is False
        assert report["probeType"] == "agent_prompt_smoke"
        assert report["errorClass"] == "InternalServerError"
        assert report["errorCode"] == "internal"
        assert report["httpStatus"] == "500"
        assert report["headers"]["content-type"] == "application/json"
        assert "crsr_" not in report["error"]
        assert "crsr_" not in "\n".join(report["issues"])
    finally:
        python_runtime.subprocess.run = original_run
        python_runtime.resolve_data_agent_python = original_resolve
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key

def test_cursor_startup_probe_uses_resolved_data_agent_python():
    old_key = os.environ.get("CURSOR_API_KEY")
    original_run = python_runtime.subprocess.run
    original_resolve = python_runtime.resolve_data_agent_python
    resolved_python = Path("/tmp/qwq-data-agent-python")
    seen = {}
    try:
        os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)
        python_runtime.resolve_data_agent_python = lambda include_current=True: resolved_python

        class _Completed:
            returncode = 0
            stderr = ""
            stdout = json.dumps(
                {
                    "ready": True,
                    "started": True,
                    "probeType": "agent_prompt_smoke",
                    "status": "finished",
                    "agentId": "agent-test",
                    "runId": "run-test",
                },
                ensure_ascii=False,
            )

        def _fake_run(cmd, *_args, **kwargs):
            seen["cmd"] = cmd
            assert kwargs["env"]["CURSOR_API_KEY"].startswith("crsr_")
            return _Completed()

        python_runtime.subprocess.run = _fake_run
        report = python_runtime.cursor_startup_probe(
            model="composer",
            runtime="cloud",
            timeout_seconds=1,
        )
    finally:
        python_runtime.subprocess.run = original_run
        python_runtime.resolve_data_agent_python = original_resolve
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key

    assert report["ready"] is True
    assert report["probePython"] == str(resolved_python)
    assert seen["cmd"][0] == str(resolved_python)

def test_network_probe_falls_back_to_get_when_head_fails():
    original_urlopen = python_runtime.urlrequest.urlopen
    calls: list[str] = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _fake_urlopen(request, timeout):  # noqa: ARG001
        calls.append(request.get_method())
        if request.get_method() == "HEAD":
            raise OSError("EOF occurred in violation of protocol")
        return _FakeResponse()

    try:
        python_runtime.urlrequest.urlopen = _fake_urlopen
        row = python_runtime._probe_endpoint("https://api2.cursor.sh/", timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen

    assert calls == ["HEAD", "GET"]
    assert row["reachable"] is True
    assert row["method"] == "GET"

def test_network_probe_falls_back_to_curl_when_urllib_fails():
    original_urlopen = python_runtime.urlrequest.urlopen
    original_which = python_runtime.shutil.which
    original_run = python_runtime.subprocess.run

    class _FakeProc:
        returncode = 0
        stdout = "200"
        stderr = ""

    try:
        python_runtime.urlrequest.urlopen = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("EOF occurred in violation of protocol")
        )
        python_runtime.shutil.which = lambda name: "/usr/bin/curl" if name == "curl" else None
        python_runtime.subprocess.run = lambda *_args, **_kwargs: _FakeProc()
        row = python_runtime._probe_endpoint("https://api2.cursor.sh/", timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen
        python_runtime.shutil.which = original_which
        python_runtime.subprocess.run = original_run

    assert row["reachable"] is True
    assert row["method"] == "curl"
    assert row["status"] == 200
