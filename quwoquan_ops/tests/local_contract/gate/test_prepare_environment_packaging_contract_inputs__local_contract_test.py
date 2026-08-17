from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from quwoquan_ops.cli.lib.graphql_read_registry_signing import (
    SIGNING_KEY_ID_ENV,
    SIGNING_PRIVATE_KEY_FILE_ENV,
    TRUSTED_PUBLIC_KEYS_FILE_ENV,
    resolve_signing_material,
)


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/prepare_environment_packaging_contract_inputs.py"
SPEC = importlib.util.spec_from_file_location(
    "prepare_environment_packaging_contract_inputs", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SCRIPT.parent))
try:
    SPEC.loader.exec_module(MODULE)
finally:
    sys.path.pop(0)


def test_prepared_inputs_are_external_valid_and_commercial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "validated_deployment_test_workspace", Path)
    workspace = tmp_path / "quwoquan-deploy.abc123"
    workspace.mkdir()

    MODULE.prepare_environment_packaging_contract_inputs(str(workspace))

    private_key = workspace / MODULE.PRIVATE_KEY_NAME
    keyring = workspace / MODULE.KEYRING_NAME
    assert private_key.stat().st_mode & 0o777 == 0o600
    assert keyring.stat().st_mode & 0o777 == 0o600
    signing = resolve_signing_material(
        ROOT,
        {
            SIGNING_KEY_ID_ENV: MODULE.KEY_ID,
            SIGNING_PRIVATE_KEY_FILE_ENV: str(private_key),
            TRUSTED_PUBLIC_KEYS_FILE_ENV: str(keyring),
        }.get,
    )
    assert signing.key_id == MODULE.KEY_ID

    for filename in ("candidate-release.json", "rollback-release.json"):
        payload = json.loads((workspace / filename).read_text(encoding="utf-8"))
        assert payload["releaseClass"] == "commercial"
        assert payload["productLifecycleState"] == "commercial"


def test_preparation_refuses_to_overwrite_existing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "validated_deployment_test_workspace", Path)
    workspace = tmp_path / "quwoquan-deploy.abc123"
    workspace.mkdir()
    (workspace / MODULE.PRIVATE_KEY_NAME).write_text("occupied", encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        MODULE.prepare_environment_packaging_contract_inputs(str(workspace))
