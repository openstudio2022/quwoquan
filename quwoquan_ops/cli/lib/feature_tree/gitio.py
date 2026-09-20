"""git 增量与 HEAD 文本读取。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import context


def _using_private_index() -> bool:
    return bool(str(os.environ.get("GIT_INDEX_FILE") or "").strip())


def git_staged_paths() -> list[str]:
    """当前 index 相对 HEAD 的 staged 路径；私有 index 下即本次 commit/candidate 闭集。"""
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=off",
            "diff",
            "--name-only",
            "-z",
            "--cached",
            "--find-renames",
        ],
        cwd=context.REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(path for path in result.stdout.decode("utf-8", errors="replace").split("\0") if path)


def git_changed_paths() -> list[str]:
    if _using_private_index():
        return git_staged_paths()
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=context.REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    parts = result.stdout.decode("utf-8", errors="replace").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(parts):
        item = parts[index]
        if not item:
            break
        status, path = item[:2], item[3:]
        if status[0] in "RC" or status[1] in "RC":
            index += 1
            path = parts[index] if index < len(parts) else path
        paths.append(path)
        index += 1
    return sorted(set(paths))


def git_range_paths(base: str, head: str) -> list[str]:
    """与 ImpactPlan / lane_gate impact-boundary 同一 candidate range（两 SHA 闭包）。"""
    start = str(base or "").strip()
    end = str(head or "").strip()
    if not start or not end:
        raise ValueError("git range requires base and head")
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=off",
            "diff",
            "--name-only",
            "-z",
            "--find-renames",
            start,
            end,
        ],
        cwd=context.REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(path for path in result.stdout.decode("utf-8", errors="replace").split("\0") if path)


def git_head_text(rel: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=context.REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def git_index_text(rel: str) -> str | None:
    """当前 index 中的文件文本；路径不在 index 时返回 None。"""
    return _load_index_texts("specs/feature-tree").get(rel)


def _load_index_texts(prefix: str) -> dict[str, str]:
    cache = getattr(_load_index_texts, "_cache", None)
    if isinstance(cache, dict) and prefix in cache:
        return cache[prefix]
    listed = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-s", "-z", "--", prefix],
        cwd=context.REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    entries: list[tuple[str, str]] = []
    for record in listed.stdout.split(b"\0"):
        if not record:
            continue
        meta, raw_path = record.split(b"\t", 1)
        sha = meta.split()[1].decode("ascii")
        entries.append((sha, raw_path.decode("utf-8", errors="replace")))
    documents: dict[str, str] = {}
    if entries:
        payload = b"".join(f"{sha}\n".encode("ascii") for sha, _ in entries)
        batched = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=context.REPO_ROOT,
            input=payload,
            check=True,
            stdout=subprocess.PIPE,
        )
        data = batched.stdout
        offset = 0
        for _, path in entries:
            newline = data.find(b"\n", offset)
            header = data[offset:newline].decode("ascii")
            parts = header.split()
            offset = newline + 1
            if len(parts) < 3 or parts[1] == "missing":
                continue
            size = int(parts[2])
            documents[path] = data[offset : offset + size].decode("utf-8", errors="replace")
            offset += size + 1
    store = cache if isinstance(cache, dict) else {}
    store[prefix] = documents
    _load_index_texts._cache = store  # type: ignore[attr-defined]
    return documents


def _is_verify_document(rel: str) -> bool:
    if rel.startswith(
        (
            "specs/feature-tree/",
            "quwoquan_app/test/",
            "quwoquan_app/scripts/",
            "quwoquan_data/tests/",
            "quwoquan_ops/gate/",
            "quwoquan_ops/tests/",
        )
    ):
        return True
    name = Path(rel).name.lower()
    return rel.startswith("quwoquan_service/") and ("/tests/" in rel or "test" in name)


def _load_verify_documents() -> dict[str, str]:
    documents: dict[str, str] = {}
    for prefix in (
        "specs/feature-tree",
        "quwoquan_app/test",
        "quwoquan_app/scripts",
        "quwoquan_data/tests",
        "quwoquan_ops/gate",
        "quwoquan_ops/tests",
    ):
        documents.update(_load_index_texts(prefix))
    listed = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-s", "-z", "--", "quwoquan_service"],
        cwd=context.REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    service_entries: list[tuple[str, str]] = []
    for record in listed.stdout.split(b"\0"):
        if not record:
            continue
        meta, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8", errors="replace")
        if not _is_verify_document(path):
            continue
        service_entries.append((meta.split()[1].decode("ascii"), path))
    if service_entries:
        payload = b"".join(f"{sha}\n".encode("ascii") for sha, _ in service_entries)
        batched = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=context.REPO_ROOT,
            input=payload,
            check=True,
            stdout=subprocess.PIPE,
        )
        data = batched.stdout
        offset = 0
        for _, path in service_entries:
            newline = data.find(b"\n", offset)
            header = data[offset:newline].decode("ascii")
            parts = header.split()
            offset = newline + 1
            if len(parts) < 3 or parts[1] == "missing":
                continue
            size = int(parts[2])
            documents[path] = data[offset : offset + size].decode("utf-8", errors="replace")
            offset += size + 1
    return documents


def use_private_index_documents() -> None:
    """L0 私有 index 下，规格与证据测试读 index，不读他人工作区脏字节。"""
    if not _using_private_index() or getattr(Path.read_text, "_qwq_private_index", False):
        return
    documents = _load_verify_documents()
    original = Path.read_text
    root = context.REPO_ROOT.resolve()

    def read_text(self: Path, *args: object, **kwargs: object) -> str:
        try:
            rel = self.resolve().relative_to(root).as_posix()
        except ValueError:
            return original(self, *args, **kwargs)
        if rel in documents:
            return documents[rel]
        if _is_verify_document(rel):
            return ""
        return original(self, *args, **kwargs)

    read_text._qwq_private_index = True  # type: ignore[attr-defined]
    Path.read_text = read_text  # type: ignore[method-assign]
