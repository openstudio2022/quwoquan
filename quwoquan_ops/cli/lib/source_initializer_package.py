"""source-init随runtime-shared封装；启动只消费精确制品，不编译源码。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

import yaml

from quwoquan_ops.cli.lib.deployment_candidate_manifest.candidate_fs import _read_candidate_bytes

ROOT = Path(__file__).resolve().parents[3]


def contract():
    return yaml.safe_load((ROOT / "quwoquan_ops/policies/source_allocation.yaml").read_text())


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_source_initializer(shared_root: Path, source_root: Path, environment: str, target: str):
    policy = contract()
    if target not in policy["targets"] or target != environment+"-local":
        raise ValueError("initializer requires a managed nonproduction target")
    spec = policy["initializer"]
    destination = shared_root / Path(spec["root"]).name
    destination.mkdir(mode=0o700, exist_ok=False)
    executable = destination/spec["executable"]
    # 只有package期执行固定编译目标；运行阶段无任意源码或可执行路径参数。
    result = subprocess.run(["go","build","-trimpath","-buildvcs=false","-o",str(executable),"./services/user-service/cmd/source-init"],cwd=source_root/"quwoquan_service",capture_output=True)
    if result.returncode:
        raise RuntimeError("managed User initializer build failed")
    shutil.copytree(source_root/spec["migrations"],destination/"resources/migrations")
    files = {path.relative_to(destination).as_posix():digest(path.read_bytes()) for path in sorted(destination.rglob("*")) if path.is_file()}
    manifest = {"schema":spec["schema"],"environment":environment,"target":target,"platform":platform.system()+"/"+platform.machine(),"executable":spec["executable"],"files":files}
    raw = json.dumps(manifest,sort_keys=True,separators=(",", ":")).encode()
    (destination/spec["manifest"]).write_bytes(raw)
    return {"ref":spec["root"]+"/"+spec["manifest"],"digest":digest(raw)}


def load_source_initializer(candidate_root: Path, descriptor, environment: str, target: str):
    policy = contract(); spec = policy["initializer"]
    reference = spec["root"]+"/"+spec["manifest"]
    if target not in policy["targets"] or target != environment+"-local" or not isinstance(descriptor,dict) or set(descriptor)!={"ref","digest"} or descriptor["ref"]!=reference:
        raise ValueError("source initializer descriptor rejected")
    raw = _read_candidate_bytes(candidate_root,reference,label="source initializer manifest")
    if (candidate_root/reference).stat(follow_symlinks=False).st_nlink != 1:
        raise ValueError("initializer manifest hardlink rejected")
    if digest(raw)!=descriptor["digest"]:
        raise ValueError("source initializer manifest drift")
    manifest=json.loads(raw)
    if set(manifest)!=set(spec["fields"]) or manifest["schema"]!=spec["schema"] or manifest["environment"]!=environment or manifest["target"]!=target or manifest["platform"]!=platform.system()+"/"+platform.machine() or manifest["executable"]!=spec["executable"]:
        raise ValueError("source initializer identity rejected")
    files=manifest["files"]
    if not isinstance(files,dict) or spec["executable"] not in files or not any(name.startswith("resources/migrations/") for name in files):
        raise ValueError("source initializer migration closure missing")
    for name, expected in files.items():
        if name!=spec["executable"] and not (name.startswith("resources/migrations/") and name.endswith(".sql")):
            raise ValueError("unexpected initializer payload")
        if digest(_read_candidate_bytes(candidate_root,spec["root"]+"/"+name,label="source initializer payload"))!=expected:
            raise ValueError("source initializer payload drift")
        if (candidate_root/spec["root"]/name).stat(follow_symlinks=False).st_nlink != 1:
            raise ValueError("initializer payload hardlink rejected")
    root=candidate_root/spec["root"]
    actual={path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() or path.is_symlink()}
    if actual != set(files)|{spec["manifest"]}:
        raise ValueError("source initializer extra payload")
    executable=root/spec["executable"]
    if not os.access(executable,os.X_OK):
        raise ValueError("source initializer is not executable")
    return executable
