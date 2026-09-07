#!/usr/bin/env python3
"""为证据签名 identity 生成本地 Ed25519 私钥并把公钥登记进仓内 keyring。

幂等：私钥已存在则复用，公钥已是 active 则不改文件。不同 active 公钥必须显式 `--rotate`
（旧 key 置 retired，仍保留审计）。keyring 是 authoring source，改动需随提交进入 dev1.0；
私钥只落在仓外 `QWQ_EVIDENCE_SIGNING_KEY_ROOT`（默认 ~/.cache/quwoquan/keys/evidence-signing）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.evidence_signing import (  # noqa: E402
    DEFAULT_KEYRING_PATH,
    SIGNER_PURPOSES,
    EvidenceSigningError,
    ensure_private_key,
    key_id_for,
    key_root,
    load_keyring,
    private_key_path,
    public_key_of,
    register_public_key,
)
from quwoquan_ops.cli.lib.openssl3_resolver import OpenSSL3CapabilityError  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--identity", action="append", choices=sorted(SIGNER_PURPOSES),
        help="只处理指定 identity；默认处理全部声明的 evidence signer",
    )
    parser.add_argument("--keyring", type=Path, default=DEFAULT_KEYRING_PATH)
    parser.add_argument("--rotate", action="store_true", help="已有不同 active 公钥时把旧 key 置 retired 并登记新 key")
    parser.add_argument("--registered-at", default="", help="RFC3339 UTC；默认当前时间")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    identities = args.identity or list(SIGNER_PURPOSES)
    registered_at = args.registered_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results: list[dict[str, str]] = []
    try:
        root = key_root()
        for identity in identities:
            pem = ensure_private_key(identity, root=root, create=True)
            public_key = public_key_of(pem)
            outcome = register_public_key(
                keyring_path=args.keyring, identity=identity, public_key=public_key,
                registered_at=registered_at, rotate=args.rotate,
            )
            results.append({**outcome, "privateKeyPath": str(private_key_path(identity, root))})
        keyring = load_keyring(args.keyring)
        for identity in identities:
            keyring.active_public_key(identity)
        payload = {
            "terminal": "bootstrapped",
            "keyring": str(args.keyring.relative_to(ROOT)) if args.keyring.is_relative_to(ROOT) else str(args.keyring),
            "keyringDigest": keyring.digest,
            "signers": results,
            "next": "keyring 若有改动请随本增量提交；私钥保持仓外 0600，不要复制进任何工作树",
        }
    except (EvidenceSigningError, OpenSSL3CapabilityError, OSError) as exc:
        code = exc.code if isinstance(exc, EvidenceSigningError) else (
            "EVIDENCE_SIGNING.OPENSSL_UNAVAILABLE" if isinstance(exc, OpenSSL3CapabilityError) else "EVIDENCE_SIGNING.IO_ERROR"
        )
        print(json.dumps({"terminal": "GATE_BLOCK", "code": code, "detail": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
