"""The Data symbol gate blocks latent runtime NameError defects."""
from __future__ import annotations

from verify.verify_python_symbols import source_undefined_name_issues


def test_python_symbols_reject_an_unowned_runtime_name() -> None:
    source = """
def execute():
    return load_execution_state("execution-id")
"""

    issues = source_undefined_name_issues(source, label="sample.py")

    assert issues == ["sample.py:2: undefined global name 'load_execution_state'"]


def test_python_symbols_accept_imported_and_builtin_names() -> None:
    source = """
from somewhere import load_execution_state

def execute():
    return len(load_execution_state("execution-id"))
"""

    assert source_undefined_name_issues(source, label="sample.py") == []
