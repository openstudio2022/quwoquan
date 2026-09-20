"""Plane-local DEC-015 guard：验签、单调消费、durable journal 与显式 reconcile。"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .contract import (EXECUTION_ACTION_PARAMETERS, EXECUTION_REQUEST_SCHEMA,
                           EXECUTION_RESULT_SCHEMA, EXECUTION_STEP_FIELDS, SHA256_RE, _canonical_bytes)
except ImportError:  # 由 bootstrap 封存为 plane-local helper 时直接执行同目录副本。
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from contract import (EXECUTION_ACTION_PARAMETERS, EXECUTION_REQUEST_SCHEMA,
                          EXECUTION_RESULT_SCHEMA, EXECUTION_STEP_FIELDS, SHA256_RE, _canonical_bytes)

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_SAFE_UNIT = re.compile(r"^quwoquan-[a-z0-9-]+\.service$")
_SAFE_STAGE = frozenset({"canary", "5", "20", "50", "100", "prevalidate"})


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _relative(value: object) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or str(path) != text:
        raise ValueError("EXECUTION.PARAMETER_PATH_INVALID")
    return text


def _validate_request(request: dict[str, Any]) -> None:
    if set(request) != EXECUTION_STEP_FIELDS or request.get("schema") != EXECUTION_REQUEST_SCHEMA:
        raise ValueError("EXECUTION.REQUEST_INVALID")
    action = request.get("action")
    parameters = request.get("parameters")
    if action not in EXECUTION_ACTION_PARAMETERS or not isinstance(parameters, dict) or set(parameters) != EXECUTION_ACTION_PARAMETERS[action]:
        raise ValueError("EXECUTION.ACTION_PARAMETERS_INVALID")
    for field in ("attemptId", "inventoryDigest", "materialDigest"):
        if SHA256_RE.fullmatch(str(request.get(field) or "")) is None:
            raise ValueError("EXECUTION.IDENTITY_INVALID")
    for field in ("executionGeneration", "releaseGeneration", "sequence", "guardIncarnation"):
        if type(request.get(field)) is not int or int(request[field]) < (1 if field in {"sequence", "guardIncarnation", "executionGeneration"} else 0):
            raise ValueError("EXECUTION.FENCE_INVALID")
    if not _SAFE_NAME.fullmatch(str(request.get("controllerIdentity") or "")):
        raise ValueError("EXECUTION.CONTROLLER_INVALID")
    if not str(request.get("controllerKeyId") or "").startswith("prod-execution-controller-ed25519-"):
        raise ValueError("EXECUTION.CONTROLLER_INVALID")
    for key, value in parameters.items():
        if key.endswith("Relative") or key == "relativePath":
            _relative(value)
        elif key == "service" and _SAFE_NAME.fullmatch(str(value or "")) is None:
            raise ValueError("EXECUTION.SERVICE_INVALID")
        elif key == "unitName" and _SAFE_UNIT.fullmatch(str(value or "")) is None:
            raise ValueError("EXECUTION.UNIT_INVALID")
        elif key == "stage" and str(value) not in _SAFE_STAGE:
            raise ValueError("EXECUTION.STAGE_INVALID")
        elif key.endswith("Digest") and SHA256_RE.fullmatch(str(value or "")) is None:
            raise ValueError("EXECUTION.DIGEST_INVALID")
        elif key == "expectedReleaseGeneration" and (type(value) is not int or value < 0):
            raise ValueError("EXECUTION.RELEASE_GENERATION_INVALID")


def verify_envelope(envelope: dict[str, Any], *, public_key: Path, expected_identity: str, expected_key_id: str) -> dict[str, Any]:
    if set(envelope) != {"payload", "payloadDigest", "algorithm", "keyId", "signature"} or envelope.get("algorithm") != "ed25519":
        raise ValueError("EXECUTION.ENVELOPE_INVALID")
    request = envelope.get("payload")
    if not isinstance(request, dict):
        raise ValueError("EXECUTION.ENVELOPE_INVALID")
    _validate_request(request)
    raw = _canonical_bytes(request)
    if envelope.get("payloadDigest") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("EXECUTION.ENVELOPE_DIGEST_INVALID")
    if envelope.get("keyId") != expected_key_id or request["controllerKeyId"] != expected_key_id or request["controllerIdentity"] != expected_identity:
        raise ValueError("EXECUTION.CONTROLLER_UNTRUSTED")
    try:
        signature = base64.b64decode(str(envelope["signature"]), validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("EXECUTION.SIGNATURE_INVALID") from error
    import tempfile
    with tempfile.TemporaryDirectory(dir=str(public_key.parent)) as directory:
        payload = Path(directory) / "payload"; sig = Path(directory) / "signature"
        payload.write_bytes(raw); sig.write_bytes(signature)
        verified = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key), "-rawin", "-in", str(payload), "-sigfile", str(sig)], capture_output=True)
    if verified.returncode != 0:
        raise ValueError("EXECUTION.SIGNATURE_INVALID")
    return request


def _group_closed(pgid: int) -> bool:
    try: os.killpg(pgid, 0)
    except ProcessLookupError: return True
    except PermissionError: return False
    return False



_CAS_PROGRAM = r"""import hashlib,os,sys
from pathlib import Path
target,desired=Path(sys.argv[1]),Path(sys.argv[2])
def d(p): return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'sha256:'+'0'*64
if d(target)!=sys.argv[3] or d(desired)!=sys.argv[4]: raise SystemExit(3)
tmp=target.with_name('.'+target.name+'.guard-cas');tmp.write_bytes(desired.read_bytes());os.replace(tmp,target)
if d(target)!=sys.argv[4]: raise SystemExit(4)
"""

_PROMOTE_PROGRAM = r"""import hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
source,destination,expected=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
def tree_digest(root):
 h=hashlib.sha256()
 for path in sorted(p for p in root.rglob('*') if p.is_file()):
  h.update(path.relative_to(root).as_posix().encode());h.update(b'\0');h.update(hashlib.sha256(path.read_bytes()).digest())
 return 'sha256:'+h.hexdigest()
if not source.is_dir() or source.is_symlink() or tree_digest(source)!=expected: raise SystemExit(3)
identity=json.loads((source/'runtime/artifact-identity.json').read_bytes())
if identity.get('schema')!='qwq.environment-artifact-identity' or identity.get('environment')!='prod': raise SystemExit(4)
if destination.exists():
 if destination.is_symlink() or not destination.is_dir() or tree_digest(destination)!=expected: raise SystemExit(5)
 print(json.dumps({'status':'reused','treeDigest':expected},sort_keys=True));raise SystemExit(0)
destination.parent.mkdir(parents=True,exist_ok=True)
temporary=destination.parent/('.'+destination.name+'.promote-'+str(os.getpid()))
if temporary.exists(): raise SystemExit(6)
shutil.copytree(source,temporary,symlinks=False)
if tree_digest(temporary)!=expected: shutil.rmtree(temporary);raise SystemExit(7)
os.replace(temporary,destination)
print(json.dumps({'status':'promoted','treeDigest':expected},sort_keys=True))
"""

_UNIT_PROGRAM = r"""import hashlib,os,sys,tempfile
from pathlib import Path
source,target,expected=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
def digest(path): return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
if source.is_symlink() or not source.is_file() or digest(source)!=expected: raise SystemExit(3)
target.parent.mkdir(parents=True,exist_ok=True)
if target.exists():
 if target.is_symlink() or digest(target)!=expected: raise SystemExit(4)
 raise SystemExit(0)
fd,tmp=tempfile.mkstemp(prefix='.unit-',dir=target.parent)
with os.fdopen(fd,'wb') as output: output.write(source.read_bytes());os.fchmod(output.fileno(),0o600);output.flush();os.fsync(output.fileno())
os.replace(tmp,target)
"""

_STATUS_PROGRAM = r"""import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); identity=root/'runtime/artifact-identity.json'
if root.is_symlink() or identity.is_symlink() or not identity.is_file(): raise SystemExit(3)
value=json.loads(identity.read_bytes())
print(json.dumps({'status':'ready','candidateDigest':value.get('configDigest'),'identityDigest':'sha256:'+hashlib.sha256(identity.read_bytes()).hexdigest()},sort_keys=True))
"""

_LEDGER_CAS_PROGRAM = r"""import json,os,sys
from pathlib import Path
p=Path(sys.argv[1]); expected=int(sys.argv[2]); service=sys.argv[3]; action=sys.argv[4]
v=json.loads(p.read_bytes());
if v.get('service')!=service or v.get('expectedGeneration')!=expected or v.get('action')!=action: raise SystemExit(3)
print(json.dumps(v,sort_keys=True,separators=(',',':')))
"""

class DurablePlaneGuard:
    """不读取service ledger；只消费已验签exact envelope并记录本地终态。"""
    def __init__(self, root: Path, runtime_root: Path):
        self.root = root.resolve(); self.runtime_root = runtime_root.resolve()
        if not self.root.is_dir() or not self.runtime_root.is_dir() or self.root.is_symlink() or self.runtime_root.is_symlink():
            raise ValueError("EXECUTION.GUARD_ROOT_INVALID")
        self.lock_path = self.root / "guard.lock"; self.journal_path = self.root / "journal.json"
        if not self.lock_path.is_file(): raise ValueError("EXECUTION.GUARD_NOT_INSTALLED")

    def _load(self) -> dict[str, Any]:
        if not self.journal_path.exists():
            return {"schema": "quwoquan.prod.execution-guard-journal.v1", "incarnation": 1, "lastGeneration": 0, "lastSequence": 0, "mode": "ready", "steps": {}}
        value = json.loads(self.journal_path.read_bytes())
        if value.get("schema") != "quwoquan.prod.execution-guard-journal.v1": raise RuntimeError("EXECUTION.JOURNAL_INVALID")
        if any(step.get("status") == "running" for step in value.get("steps", {}).values()): value["mode"] = "reconcile-only"
        return value

    def _write(self, value: dict[str, Any]) -> None:
        temporary = self.root / (".journal." + str(os.getpid()))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream: stream.write(_canonical_bytes(value)+b"\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.journal_path)

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        _validate_request(request); key = _digest(request)
        with self.lock_path.open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self._load(); prior = state["steps"].get(key)
            if prior is not None: return dict(prior["result"]) if prior.get("status") == "terminal" else self._pending_result(request, key)
            if state["mode"] == "reconcile-only": raise RuntimeError("EXECUTION.RECONCILE_ONLY")
            if state["mode"] not in {"ready", "held"}: raise RuntimeError("EXECUTION.GUARD_STATE_INVALID")
            generation_advanced = request["executionGeneration"] > state["lastGeneration"]
            expected_sequence = 1 if generation_advanced else state["lastSequence"] + 1
            if request["guardIncarnation"] != state["incarnation"] or request["executionGeneration"] < state["lastGeneration"] or request["sequence"] != expected_sequence:
                raise RuntimeError("EXECUTION.MONOTONIC_FENCE_REJECTED")
            state["lastGeneration"] = request["executionGeneration"]; state["lastSequence"] = request["sequence"]
            if request["action"] == "guard-prepare":
                state.update({"mode": "held", "attemptId": request["attemptId"], "generation": request["executionGeneration"]})
            elif state.get("mode") != "held" or state.get("attemptId") != request["attemptId"] or state.get("generation") != request["executionGeneration"]:
                raise RuntimeError("EXECUTION.GUARD_OWNER_MISMATCH")
            state["steps"][key] = {"status": "running", "request": request, "processGroup": 0}; self._write(state)
            argv = self._argv(request)
            child = subprocess.Popen(argv, cwd=self.runtime_root, start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            state["steps"][key]["processGroup"] = child.pid; self._write(state)
            output, error = child.communicate()
            if not _group_closed(child.pid): state["mode"] = "reconcile-only"; self._write(state); raise RuntimeError("EXECUTION.PROCESS_GROUP_NOT_CLOSED")
            effect = "sha256:" + hashlib.sha256(output + error).hexdigest()
            result = {"schema": EXECUTION_RESULT_SCHEMA, "requestDigest": key, "placementId": request["placementId"], "guardIncarnation": state["incarnation"], "sequence": request["sequence"], "status": "completed" if child.returncode == 0 else "failed", "effectDigest": effect, "processGroup": child.pid, "returnCode": child.returncode, "terminal": True, "reconciled": False}
            state["steps"][key] = {"status": "terminal", "request": request, "result": result}
            if request["action"] == "guard-close": state.update({"mode": "ready", "attemptId": "", "generation": request["executionGeneration"]})
            self._write(state)
            return result

    def _pending_result(self, request: dict[str, Any], key: str) -> dict[str, Any]:
        return {"schema": EXECUTION_RESULT_SCHEMA, "requestDigest": key, "placementId": request["placementId"], "guardIncarnation": request["guardIncarnation"], "sequence": request["sequence"], "status": "unknown", "effectDigest": "sha256:"+"0"*64, "processGroup": 0, "returnCode": -1, "terminal": False, "reconciled": False}

    def reconcile(self, request_digest: str, *, effect_digest: str, isolation_authorization: str = "") -> dict[str, Any]:
        with self.lock_path.open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX); state = self._load(); step = state["steps"].get(request_digest)
            if not step or step.get("status") != "running": raise RuntimeError("EXECUTION.RECONCILE_STEP_INVALID")
            pgid = int(step.get("processGroup") or 0)
            if pgid and not _group_closed(pgid) and not isolation_authorization.startswith("sha256:"):
                raise RuntimeError("EXECUTION.PROCESS_GROUP_NOT_CLOSED")
            if SHA256_RE.fullmatch(effect_digest) is None: raise ValueError("EXECUTION.EFFECT_READBACK_REQUIRED")
            req=step["request"]; result={"schema":EXECUTION_RESULT_SCHEMA,"requestDigest":request_digest,"placementId":req["placementId"],"guardIncarnation":state["incarnation"],"sequence":req["sequence"],"status":"reconciled","effectDigest":effect_digest,"processGroup":pgid,"returnCode":-1,"terminal":True,"reconciled":True}
            state["steps"][request_digest]={"status":"terminal","request":req,"result":result}
            state["mode"]="ready" if not any(x.get("status")=="running" for x in state["steps"].values()) else "reconcile-only"; self._write(state); return result

    def _argv(self, request: dict[str, Any]) -> list[str]:
        action=request["action"]; p=request["parameters"]
        if action in {"guard-prepare", "guard-close"}: return ["/usr/bin/true"]
        if action == "prevalidate-promote-runtime":
            return [sys.executable, "-I", "-B", "-c", _PROMOTE_PROGRAM, str(self.runtime_root/_relative(p["sourceRelative"])), str(self.runtime_root/_relative(p["destinationRelative"])), p["treeDigest"]]
        if action == "prevalidate-install-unit":
            return [sys.executable, "-I", "-B", "-c", _UNIT_PROGRAM, str(self.runtime_root/_relative(p["sourceRelative"])), str(Path.home()/".config/systemd/user"/p["unitName"]), p["sourceDigest"]]
        if action in {"prevalidate-start", "prevalidate-stop"}:
            return ["/usr/bin/systemctl", "--user", "start" if action.endswith("start") else "stop", p["unitName"]]
        if action == "prevalidate-status":
            return [sys.executable, "-I", "-B", "-c", _STATUS_PROGRAM, str(self.runtime_root/_relative(p["relativePath"]))]
        if action.startswith("observe-"):
            path=self.runtime_root/_relative(p["relativePath"]); return [sys.executable,"-I","-B","-c","import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())",str(path)]
        if action in {"promote-active-config","promote-caddy-config"}:
            return ["/usr/bin/install","-m","600",str(self.runtime_root/_relative(p["sourceRelative"])),str(self.runtime_root/_relative(p["destinationRelative"]))]
        if action=="promote-systemd-unit": return ["/usr/bin/install","-m","600",str(self.runtime_root/_relative(p["sourceRelative"])),str(Path.home()/".config/systemd/user"/p["unitName"])]
        if action in {"candidate-start","candidate-stop"}: return ["/usr/bin/systemctl","--user","start" if action.endswith("start") else "stop",p["unitName"]]
        if action in {"route-current-cas", "distribution-current-cas"}:
            return [sys.executable, "-I", "-B", "-c", _CAS_PROGRAM, str(self.runtime_root/_relative(p["relativePath"])), str(self.runtime_root/_relative(p["desiredRelative"])), p["expectedDigest"], p["desiredDigest"]]
        if action in {"ledger-activation-cas", "ledger-stage-cas", "ledger-recovery-cas"}:
            request_path = self.runtime_root/_relative(p["requestRelative"])
            request = json.loads(request_path.read_bytes())
            if request.get("service") != p["service"] or request.get("expectedGeneration") != p["expectedReleaseGeneration"]:
                raise RuntimeError("EXECUTION.LEDGER_REQUEST_DRIFT")
            encoded = base64.b64encode(_canonical_bytes(request)).decode("ascii")
            helper = self.runtime_root/"process/execution-guard/lib/hosted_release_ledger.py"
            return [sys.executable, "-I", "-B", str(helper), "--root", str(self.runtime_root/"release-ledger"), "--action", "commit", "--service", p["service"], "--request-base64", encoded]
        raise RuntimeError("EXECUTION.ACTION_REQUIRES_AUTHORITY_ADAPTER")



def _runtime_helper_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quwoquan-plane-execution-guard runtime-helper")
    parser.add_argument("action", choices=("restart-admitted", "stop-admitted"))
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--compose-file", default="")
    parser.add_argument("--env-file", action="append", default=[])
    parser.add_argument("--services", nargs="*")
    return parser


def _runtime_helper_main(argv: list[str]) -> int:
    """systemd 的受限常规 restart/stop；只解释固定 compose 操作，不接受 shell/argv 注入。"""
    args = _runtime_helper_parser().parse_args(argv)
    root = Path(args.runtime_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("EXECUTION.RUNTIME_ROOT_INVALID")
    identity = root / "runtime/artifact-identity.json"
    if identity.is_symlink() or not identity.is_file():
        raise ValueError("EXECUTION.RUNTIME_IDENTITY_INVALID")
    identity_value = json.loads(identity.read_bytes())
    if (set(identity_value) != {"schema", "environment", "configDigest"}
            or identity_value.get("schema") != "qwq.environment-artifact-identity"
            or identity_value.get("environment") != "prod"
            or SHA256_RE.fullmatch(str(identity_value.get("configDigest") or "")) is None):
        raise ValueError("EXECUTION.RUNTIME_IDENTITY_INVALID")
    if _SAFE_NAME.fullmatch(args.project) is None:
        raise ValueError("EXECUTION.PROJECT_INVALID")
    services = list(args.services or [])
    if any(_SAFE_NAME.fullmatch(value) is None for value in services) or len(services) != len(set(services)):
        raise ValueError("EXECUTION.SERVICE_INVALID")
    guard = root / "process/execution-guard"
    guard.mkdir(parents=True, exist_ok=True, mode=0o700)
    guard.chmod(0o700)
    if guard.is_symlink() or guard.stat().st_uid != os.getuid() or guard.stat().st_mode & 0o077:
        raise ValueError("EXECUTION.RUNTIME_GUARD_INVALID")
    lock_path = guard / "runtime.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        compose_file = _relative(args.compose_file)
        env_files = [_relative(value) if not Path(value).is_absolute() else value for value in args.env_file]
        if not env_files or any(Path(value).is_absolute() and not str(value).startswith(str(Path.home()) + "/") for value in env_files):
            raise ValueError("EXECUTION.ENV_FILE_INVALID")
        compose = ["/usr/bin/podman", "compose"]
        for env_file in env_files:
            compose.extend(["--env-file", env_file])
        compose.extend(["-f", compose_file, "-p", args.project])
        if args.action == "stop-admitted":
            command = [*compose, "stop"]
        else:
            if not services:
                raise ValueError("EXECUTION.SERVICES_REQUIRED")
            command = [*compose, "up", "-d", "--remove-orphans", *services]
        completed = subprocess.run(command, cwd=root, timeout=300 if args.action == "restart-admitted" else 120)
        if completed.returncode != 0 and args.action == "restart-admitted":
            cleanup = subprocess.run([*compose, "stop"], cwd=root, timeout=120)
            if cleanup.returncode != 0:
                print("FAIL: EXECUTION.RUNTIME_FAILURE_CLEANUP_FAILED", file=sys.stderr)
        return completed.returncode
    except BlockingIOError as error:
        raise RuntimeError("EXECUTION.RUNTIME_BUSY") from error
    finally:
        os.close(descriptor)

def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "runtime-helper":
        try:
            return _runtime_helper_main(sys.argv[2:])
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as error:
            print(f"FAIL: {error}", file=sys.stderr); return 2
    parser=argparse.ArgumentParser(); parser.add_argument("--root",required=True); parser.add_argument("--runtime-root",required=True); parser.add_argument("--public-key",required=True); parser.add_argument("--controller-identity",required=True); parser.add_argument("--controller-key-id",required=True); parser.add_argument("--envelope-base64",required=True)
    args=parser.parse_args()
    try:
        envelope=json.loads(base64.b64decode(args.envelope_base64,validate=True)); request=verify_envelope(envelope,public_key=Path(args.public_key),expected_identity=args.controller_identity,expected_key_id=args.controller_key_id)
        result=DurablePlaneGuard(Path(args.root),Path(args.runtime_root)).submit(request)
    except (OSError,ValueError,RuntimeError,json.JSONDecodeError) as error: print(f"FAIL: {error}",file=sys.stderr); return 2
    print(json.dumps(result,separators=(",",":"),sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
