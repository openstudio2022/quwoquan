from __future__ import annotations

import inspect

from quwoquan_ops.gate import verify_runtime_config_release_layout as gate


def test_runtime_config_release_layout_accepts_current_single_track() -> None:
    assert gate.main() == 0


def test_runtime_config_release_layout_retains_required_and_forbidden_checks() -> None:
    source = inspect.getsource(gate.main)
    assert 'filepath.Join(root, serviceName+".yaml")' in source
    assert '"configs"' in source
    assert '"releases"' in source
    assert "prod renderer retains retired release snapshot path" in source
