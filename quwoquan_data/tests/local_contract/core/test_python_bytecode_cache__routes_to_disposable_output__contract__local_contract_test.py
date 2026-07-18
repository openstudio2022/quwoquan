from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_python_bytecode_cache_routes_to_disposable_output(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    cache_root = tmp_path / "output" / "python-cache"
    source_root.mkdir()
    (source_root / "sample_module.py").write_text("VALUE = 42\n", encoding="utf-8")

    child_env = os.environ.copy()
    child_env.pop("PYTHONDONTWRITEBYTECODE", None)
    child_env["PYTHONPYCACHEPREFIX"] = str(cache_root)
    subprocess.run(
        [sys.executable, "-c", "import sample_module; assert sample_module.VALUE == 42"],
        cwd=source_root,
        env=child_env,
        check=True,
    )

    assert not (source_root / "__pycache__").exists()
    assert any(cache_root.rglob("sample_module*.pyc"))
