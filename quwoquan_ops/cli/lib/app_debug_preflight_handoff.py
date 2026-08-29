"""Single preflight owner handoff for one App launch attempt.

一次 attempt 只允许一个 preflight owner。编排方（dev-session）与 canonical
launcher（run.sh）曾各自跑一次 app-debug-preflight，既翻倍耗时，也让两次结论
可能不一致。本模块把「App 运行模式 -> preflight purpose」的映射和 receipt 交接
收敛到唯一实现：上游执行一次并落 exact payload，下游只允许复用或显式阻断。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA = "quwoquan_ops.app_debug_preflight"

# 两个 App mode 都使用同一 test_live 严格度，只按 purpose 区分诊断面：
# content-live 保留启动后 Remote 内容 outcome 所需诊断，ui-only 只请求 runtime 诊断；
# service/Provider/TLS/transport/content/observability/capacity/drift 都不得成为
# Alpha/Beta/Gamma test_live 的编译前门。
PREFLIGHT_PURPOSE_BY_APP_MODE = {
    "content-live": "content_live",
    "ui-only": "runtime",
}


def app_debug_preflight_purpose(app_mode: str) -> str:
    normalized = str(app_mode).strip()
    try:
        return PREFLIGHT_PURPOSE_BY_APP_MODE[normalized]
    except KeyError as error:
        raise ValueError(
            "APP.LAUNCH.app_mode_invalid: --mode requires content-live|ui-only, "
            f"got {normalized or '<empty>'}"
        ) from error


def write_app_debug_preflight_receipt(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    purpose: str,
    target: str,
) -> Path:
    """Persist the exact upstream preflight payload for downstream reuse.

    信封只承载交接身份，payload 原样保留，让下游复用到的对象与自己跑一次
    preflight 得到的对象同构。
    """

    receipt_path = Path(path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "purpose": str(purpose),
                "target": str(target),
                "payload": dict(payload),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return receipt_path


def read_reusable_app_debug_preflight(
    path: str | Path,
    *,
    purpose: str,
    target: str,
) -> str:
    """Return the upstream payload JSON only when it is exact for this attempt.

    不匹配是编排错误，不是可降级的缺席：调用方必须阻断，不得静默再跑一次
    preflight，否则单一 owner 契约就退回双 preflight。
    """

    receipt_path = Path(path)
    try:
        envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(
            f"APP.LAUNCH.preflight_receipt_invalid: {receipt_path} is unreadable: "
            f"{error}"
        ) from error
    if not isinstance(envelope, dict) or envelope.get("schema") != SCHEMA:
        raise ValueError(
            f"APP.LAUNCH.preflight_receipt_invalid: {receipt_path} is not {SCHEMA}"
        )
    for field, expected in (("purpose", purpose), ("target", target)):
        observed = str(envelope.get(field) or "")
        if observed != str(expected):
            raise ValueError(
                "APP.LAUNCH.preflight_receipt_invalid: "
                f"{field}={observed or '<missing>'} does not match {expected}"
            )
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(
            "APP.LAUNCH.preflight_receipt_invalid: "
            f"{receipt_path} carries no preflight payload"
        )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
