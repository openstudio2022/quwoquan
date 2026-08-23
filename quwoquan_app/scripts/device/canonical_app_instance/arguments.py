"""Canonical executor 的 CLI 参数契约。

叶子模块：launcher 在首个工具调用前的 fail-closed 参数预检直接导入本模块，
因此这里只允许标准库依赖，不得引入 metadata/契约等仓库依赖链。
"""

from __future__ import annotations


class CanonicalExecutorError(RuntimeError):
    """Canonical launch executor 的 typed 失败。"""


def sanitize_attach_arguments(arguments: tuple[str, ...]) -> list[str]:
    """只放行不改变设备、身份、VM URI/端口或编译输入的诊断参数。"""
    sanitized: list[str] = []
    for argument in arguments:
        if argument != "--verbose":
            raise CanonicalExecutorError(
                f"canonical executor owns Flutter attach argument {argument}"
            )
        sanitized.append(argument)
    return sanitized
