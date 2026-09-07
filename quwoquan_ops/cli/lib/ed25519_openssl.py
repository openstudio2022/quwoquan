"""OpenSSL 3 Ed25519 原语：生成私钥、派生公钥、rawin 签名与验签。

只做四个纯函数，不解释任何业务语义；调用方（证据签名 keyring 等）负责
身份、信任与编码。执行体一律经 `resolve_openssl3()` 取得能力已证明的 OpenSSL 3，
LibreSSL 或缺 `-rawin` 的实现不会成为隐式回退。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .openssl3_resolver import OpenSSL3Executable, resolve_openssl3

RAW_PUBLIC_KEY_SIZE = 32
SIGNATURE_SIZE = 64
SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


class Ed25519Error(ValueError):
    """Ed25519 材料或 OpenSSL 调用失败（能力缺失由 OpenSSL3CapabilityError 单独表达）。"""


def _selected(openssl: OpenSSL3Executable | None) -> OpenSSL3Executable:
    return openssl or resolve_openssl3()


def generate_private_key_pem(*, openssl: OpenSSL3Executable | None = None) -> bytes:
    selected = _selected(openssl)
    with tempfile.TemporaryDirectory(prefix="qwq-ed25519-genpkey-") as temporary:
        private_path = Path(temporary) / "private.pem"
        result = subprocess.run(
            selected.argv("genpkey", "-algorithm", "ED25519", "-out", str(private_path)),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not private_path.is_file():
            raise Ed25519Error("Ed25519 private key generation failed")
        private_pem = private_path.read_bytes()
    if b"PRIVATE KEY" not in private_pem:
        raise Ed25519Error("Ed25519 private key generation produced no PEM")
    return private_pem


def derive_public_key(private_pem: bytes, *, openssl: OpenSSL3Executable | None = None) -> bytes:
    selected = _selected(openssl)
    result = subprocess.run(
        selected.argv("pkey", "-pubout", "-outform", "DER"),
        input=private_pem,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise Ed25519Error("Ed25519 private key is not a valid PEM")
    expected_size = len(SPKI_PREFIX) + RAW_PUBLIC_KEY_SIZE
    if not result.stdout.startswith(SPKI_PREFIX) or len(result.stdout) != expected_size:
        raise Ed25519Error("private key is not Ed25519")
    return result.stdout[-RAW_PUBLIC_KEY_SIZE:]


def sign(private_pem: bytes, payload: bytes, *, openssl: OpenSSL3Executable | None = None) -> bytes:
    selected = _selected(openssl)
    with tempfile.TemporaryDirectory(prefix="qwq-ed25519-sign-") as temporary:
        root = Path(temporary)
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        payload_path.write_bytes(payload)
        result = subprocess.run(
            selected.argv(
                "pkeyutl", "-sign", "-rawin", "-inkey", "/dev/stdin",
                "-in", str(payload_path), "-out", str(signature_path),
            ),
            input=private_pem,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise Ed25519Error("Ed25519 signing failed")
        signature = signature_path.read_bytes()
    if len(signature) != SIGNATURE_SIZE:
        raise Ed25519Error("Ed25519 signing produced a non-Ed25519 signature")
    return signature


def verify(
    public_key: bytes, payload: bytes, signature: bytes, *, openssl: OpenSSL3Executable | None = None,
) -> bool:
    """验签结果只有 True/False；材料尺寸错误直接 raise，避免把畸形输入当成“签名不对”。"""

    if len(public_key) != RAW_PUBLIC_KEY_SIZE or len(signature) != SIGNATURE_SIZE:
        raise Ed25519Error("Ed25519 verification material is invalid")
    selected = _selected(openssl)
    with tempfile.TemporaryDirectory(prefix="qwq-ed25519-verify-") as temporary:
        root = Path(temporary)
        public_path = root / "public.der"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        public_path.write_bytes(SPKI_PREFIX + public_key)
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            selected.argv(
                "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER",
                "-inkey", str(public_path), "-in", str(payload_path), "-sigfile", str(signature_path),
            ),
            capture_output=True,
            check=False,
        )
    return result.returncode == 0
