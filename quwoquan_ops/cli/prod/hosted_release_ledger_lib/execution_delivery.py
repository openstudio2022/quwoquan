"""Controller-side exact envelope signer；SSH仍由各plane既有身份持有。"""
from __future__ import annotations
import base64, hashlib, json, os, subprocess, tempfile
from pathlib import Path
from typing import Any
from .contract import _canonical_bytes
from .execution_guard import _validate_request


def sign_request(request: dict[str, Any], *, private_key: Path) -> dict[str, Any]:
    _validate_request(request); raw=_canonical_bytes(request)
    if not private_key.is_file() or private_key.is_symlink() or private_key.stat().st_mode & 0o077:
        raise ValueError("EXECUTION.CONTROLLER_KEY_INVALID")
    with tempfile.TemporaryDirectory() as directory:
        payload=Path(directory)/"payload"; signature=Path(directory)/"signature"; payload.write_bytes(raw)
        result=subprocess.run(["openssl","pkeyutl","-sign","-inkey",str(private_key),"-rawin","-in",str(payload),"-out",str(signature)],capture_output=True)
        if result.returncode != 0: raise RuntimeError("EXECUTION.SIGNING_FAILED")
        encoded=base64.b64encode(signature.read_bytes()).decode("ascii")
    return {"payload":request,"payloadDigest":"sha256:"+hashlib.sha256(raw).hexdigest(),"algorithm":"ed25519","keyId":request["controllerKeyId"],"signature":encoded}


def canonical_ssh_delivery_argv(*, account: str, host: str, helper_relative: str, envelope: dict[str, Any]) -> list[str]:
    if not account.startswith("prod-") or not account.endswith("-svc") or not host or helper_relative.startswith("/") or ".." in Path(helper_relative).parts:
        raise ValueError("EXECUTION.DELIVERY_SCOPE_INVALID")
    encoded=base64.b64encode(_canonical_bytes(envelope)).decode("ascii")
    return ["ssh","-F","/dev/null","-o","StrictHostKeyChecking=yes","-o","BatchMode=yes",f"{account}@{host}",helper_relative,"--envelope-base64",encoded]
