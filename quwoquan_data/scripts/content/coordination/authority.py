"""Immutable authority artifact readback through an external authenticated provider verifier."""
from __future__ import annotations
import hashlib,json,os,subprocess
from pathlib import Path
from .store import CoordinationError

def digest_bytes(raw: bytes) -> str:
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def verify_authority_artifact(ref: str, digest: str, *, purpose: str) -> dict:
    path=Path(ref).expanduser().absolute()
    try:
        if path.is_symlink() or not path.is_file(): raise OSError("authority artifact missing or symlink")
        raw=path.read_bytes()
    except OSError as exc:
        raise CoordinationError("COORDINATION.AUTHORIZATION_READBACK_INVALID",str(path)) from exc
    if digest_bytes(raw)!=digest:
        raise CoordinationError("COORDINATION.AUTHORIZATION_DIGEST_DRIFT",str(path))
    verifier=os.environ.get("QWQ_CONTENT_AUTHORITY_VERIFIER","").strip()
    if not verifier:
        raise CoordinationError("COORDINATION.AUTHORITY_PROVIDER_UNAVAILABLE",purpose)
    request=json.dumps({"ref":str(path),"digest":digest,"purpose":purpose},sort_keys=True)
    try:
        result=subprocess.run([verifier],input=request,text=True,capture_output=True,timeout=10,check=False)
        response=json.loads(result.stdout)
    except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        raise CoordinationError("COORDINATION.AUTHORITY_PROVIDER_UNAVAILABLE",purpose) from exc
    if result.returncode or response!={"digest":digest,"purpose":purpose,"ref":str(path),"state":"verified"}:
        raise CoordinationError("COORDINATION.AUTHORIZATION_SIGNATURE_INVALID",str(path))
    try: document=json.loads(raw)
    except json.JSONDecodeError as exc: raise CoordinationError("COORDINATION.AUTHORIZATION_READBACK_INVALID",str(path)) from exc
    if not isinstance(document,dict): raise CoordinationError("COORDINATION.AUTHORIZATION_READBACK_INVALID",str(path))
    return document
