"""非页面 runtime execution 消费证据的生产文件与 symbol 校验。"""
from __future__ import annotations

import re
from collections import defaultdict

from .constants import DART_NON_CODE_RE, ROOT


def without_dart_non_code(source: str) -> str:
    """剥离注释与字符串，避免用注释/常量伪造 production evidence。"""

    def replace(match: re.Match[str]) -> str:
        newline_count = match.group(0).count("\n")
        return "\n" * newline_count if newline_count else " "

    return DART_NON_CODE_RE.sub(replace, source)


def runtime_execution_consumers(
    raw_entries: object,
    *,
    operations: dict[str, dict],
    known_objects: set[str],
    claimed: set[str],
) -> dict[str, set[str]]:
    """Validate explicit non-page App execution chains and return object owners."""
    if raw_entries is None:
        return {}
    if not isinstance(raw_entries, list):
        raise SystemExit("GATE_BLOCK runtime_execution 必须是列表")

    result: dict[str, set[str]] = defaultdict(set)
    seen_objects: set[str] = set()
    app_root = ROOT / "quwoquan_app"
    for index, raw_entry in enumerate(raw_entries):
        location = f"runtime_execution[{index}]"
        if not isinstance(raw_entry, dict):
            raise SystemExit(f"GATE_BLOCK {location} 必须是 mapping")
        if set(raw_entry) != {"object_id", "operation_ids", "production_evidence"}:
            raise SystemExit(
                f"GATE_BLOCK {location} 字段必须精确为 object_id / operation_ids / "
                "production_evidence"
            )
        object_id = str(raw_entry.get("object_id") or "").strip()
        if not object_id or object_id in seen_objects:
            raise SystemExit(f"GATE_BLOCK {location} object_id 为空或重复: {object_id!r}")
        seen_objects.add(object_id)
        if object_id not in known_objects:
            continue
        if object_id in claimed:
            raise SystemExit(
                f"GATE_BLOCK {location} {object_id} 已是 page participant，"
                "不得再以 runtime_execution 双轨关闭"
            )

        operation_ids = raw_entry.get("operation_ids")
        if (
            not isinstance(operation_ids, list)
            or not operation_ids
            or any(not isinstance(value, str) or not value.strip() for value in operation_ids)
            or len(operation_ids) != len(set(operation_ids))
        ):
            raise SystemExit(
                f"GATE_BLOCK {location}.operation_ids 必须是非空不重复字符串列表"
            )
        bound_operations: list[dict] = []
        for operation_id in operation_ids:
            operation_id = operation_id.strip()
            operation = operations.get(operation_id)
            if (
                operation is None
                or not operation.get("clientContract")
                or operation.get("objectId") != object_id
            ):
                raise SystemExit(
                    f"GATE_BLOCK {location} operation 不存在、非 App clientContract "
                    f"或对象不匹配: {operation_id}"
                )
            bound_operations.append(operation)

        evidence = raw_entry.get("production_evidence")
        if not isinstance(evidence, list) or len(evidence) < 2:
            raise SystemExit(
                f"GATE_BLOCK {location}.production_evidence 至少需要 adapter/binding "
                "与真实 execution owner 两个生产文件"
            )
        source_chunks: list[str] = []
        execution_owner_found = False
        seen_paths: set[str] = set()
        for evidence_index, raw_evidence in enumerate(evidence):
            evidence_location = f"{location}.production_evidence[{evidence_index}]"
            if not isinstance(raw_evidence, dict) or set(raw_evidence) != {"path", "symbols"}:
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location} 字段必须精确为 path / symbols"
                )
            relative = str(raw_evidence.get("path") or "").strip()
            symbols = raw_evidence.get("symbols")
            if (
                not relative.startswith("lib/")
                or not relative.endswith(".dart")
                or "/generated/" in relative
                or relative in seen_paths
            ):
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.path 必须是唯一非 generated App "
                    f"production Dart: {relative!r}"
                )
            seen_paths.add(relative)
            absolute = (app_root / relative).resolve()
            try:
                absolute.relative_to((app_root / "lib").resolve())
            except ValueError as error:
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.path 越出 App lib: {relative}"
                ) from error
            if not absolute.is_file():
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.path 不存在: {relative}"
                )
            if (
                not isinstance(symbols, list)
                or not symbols
                or any(not isinstance(symbol, str) or not symbol.strip() for symbol in symbols)
                or len(symbols) != len(set(symbols))
            ):
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.symbols 必须是非空不重复字符串列表"
                )
            source = without_dart_non_code(
                absolute.read_text(encoding="utf-8", errors="ignore")
            )
            for symbol in symbols:
                if not re.search(rf"\b{re.escape(symbol.strip())}\b", source):
                    raise SystemExit(
                        f"GATE_BLOCK {evidence_location} 未消费声明 symbol "
                        f"{symbol!r}: {relative}"
                    )
            source_chunks.append(source)
            if "/adapters/" not in relative and not relative.startswith("lib/runtime/di/"):
                execution_owner_found = True
        if not execution_owner_found:
            raise SystemExit(
                f"GATE_BLOCK {location} 只有 adapter/DI，没有可验证 production "
                "runtime/background execution owner"
            )

        combined_source = "\n".join(source_chunks)
        for operation in bound_operations:
            tokens = {
                str(operation.get(field) or "").strip()
                for field in ("localId", "requestEntity", "facadeMethod")
                if str(operation.get(field) or "").strip()
            }
            # localId may be embedded in a canonical generated identifier, e.g.
            # `realtimeConnectionWebSocketUpgrade`; operation binding therefore
            # uses an exact case-sensitive substring while evidence symbols above
            # still require identifier boundaries.
            if not tokens or not any(token in combined_source for token in tokens):
                raise SystemExit(
                    f"GATE_BLOCK {location} production evidence 未绑定 operation "
                    f"{operation.get('id')} 的 localId/requestEntity/facadeMethod"
                )
        result[object_id].update(str(value).strip() for value in operation_ids)
    return result
