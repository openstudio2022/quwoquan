"""有界、零修复的本地保护审计；摘要冻结不是删除许可或环境 authority。"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import defaultdict
from pathlib import Path

from content.release.canonical.media_holding_closure import (
    _walk_records, media_references_in_release_manifest,
)
from core.content_library import MEDIA_KIND, library_cas_path
from core.paths import LIBRARY_ROOT, carried_media_root
from governance.production_audit import contained, write_evidence

ORIGINAL_LIMIT = 2684354560
COMPONENTS = ("original", "transcode-staging", "pool-staging", "golden-growth", "backup-growth")


def signature(value: os.stat_result) -> tuple:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class HashBudget:
    """只复用本次读取过且 stat 未变的同一 inode，不信任文件名或跨 inode 摘要声明。"""
    def __init__(self, limit: int):
        if limit <= 0:
            raise ValueError("DATA.AUDIT.HASH_BUDGET_INVALID")
        self.limit = limit
        self.read_bytes = 0
        self.cache: dict[tuple, str] = {}
        self.observed: dict[Path, tuple] = {}
        self.cache_hits = 0

    def _hash(self, path: Path, size: int) -> str:
        digest = hashlib.sha256()
        remaining = size
        with path.open("rb") as handle:
            while remaining:
                chunk = handle.read(min(1048576, remaining))
                if not chunk:
                    raise ValueError(f"DATA.AUDIT.INPUT_CHANGED: {path}")
                self.read_bytes += len(chunk)
                remaining -= len(chunk)
                digest.update(chunk)
        return digest.hexdigest()

    def inspect(self, path: Path, expected: str | None = None) -> dict:
        if not path.exists():
            return {"path": str(path), "state": "missing"}
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            return {"path": str(path), "state": "not_regular_file"}
        key = signature(before)
        cached = key in self.cache
        if not cached and self.read_bytes + before.st_size > self.limit:
            return {"path": str(path), "state": "budget_exhausted", "bytes": before.st_size}
        observed = self.cache[key] if cached else self._hash(path, before.st_size)
        after = path.lstat()
        stable = key == signature(after)
        if stable:
            self.cache[key] = observed
            self.observed[path] = key
        self.cache_hits += int(cached)
        matched = expected is None or observed == expected.removeprefix("sha256:")
        return {"path": str(path), "state": "verified" if matched and stable else "digest_drift",
                "sha256": f"sha256:{observed}", "bytes": after.st_size, "reusedInodeHash": cached,
                "device": after.st_dev, "inode": after.st_ino, "mtimeNs": after.st_mtime_ns}


class InputBudget:
    """仅遍历显式本地根，元数据读取、目录条目与 hash 字节各自有界。"""
    def __init__(self, max_files: int, max_metadata_bytes: int):
        if min(max_files, max_metadata_bytes) <= 0:
            raise ValueError("DATA.AUDIT.INPUT_BUDGET_INVALID")
        self.max_files, self.max_metadata_bytes = max_files, max_metadata_bytes
        self.nodes: dict[Path, tuple] = {}
        self.documents: dict[Path, dict] = {}
        self.metadata_bytes = 0

    def record(self, path: Path) -> os.stat_result:
        value = path.lstat()
        if path not in self.nodes and len(self.nodes) >= self.max_files:
            raise ValueError("DATA.AUDIT.FILE_BOUND_EXCEEDED")
        if not (stat.S_ISREG(value.st_mode) or stat.S_ISDIR(value.st_mode)):
            raise ValueError(f"DATA.AUDIT.UNSUPPORTED_FILE_TYPE: {path}")
        if path in self.nodes and signature(value) != self.nodes[path]:
            raise ValueError(f"DATA.AUDIT.INPUT_CHANGED: {path}")
        self.nodes[path] = signature(value)
        return value

    def tree(self, root: Path) -> list[Path]:
        pending, files = [root], []
        self.record(root)
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    value = self.record(path)
                    if stat.S_ISDIR(value.st_mode):
                        pending.append(path)
                    else:
                        files.append(path)
        return sorted(files)

    def document(self, path: Path) -> dict:
        value = self.record(path)
        if path in self.documents:
            return self.documents[path]
        size = value.st_size
        if self.metadata_bytes + size > self.max_metadata_bytes:
            raise ValueError(f"DATA.AUDIT.METADATA_BOUND_EXCEEDED: {path}")
        with path.open("rb") as handle:
            content = handle.read(size)
        self.metadata_bytes += len(content)
        self.record(path)
        document = json.loads(content)
        if not isinstance(document, dict):
            raise ValueError(f"DATA.AUDIT.DOCUMENT_INVALID: {path}")
        self.documents[path] = document
        return document


def _carried_paths(root: Path, digest: str) -> list[Path]:
    return sorted(root.glob(f"{digest}.*"))


def inspect_holders(digest: str, *, library: Path, carried: Path, backup: Path,
                    budget: HashBudget) -> dict:
    candidates = {"library": [library_cas_path(MEDIA_KIND, digest, library_root=library)],
                  "carried": _carried_paths(carried, digest), "backup": _carried_paths(backup, digest)}
    holders = {name: [budget.inspect(path, digest) for path in paths] for name, paths in candidates.items()}
    valid = {name: [row for row in rows if row["state"] == "verified"] for name, rows in holders.items()}
    copies = {(row["device"], row["inode"]) for rows in valid.values() for row in rows}
    return {"sha256": f"sha256:{digest}", "holders": holders,
            "verifiedHolderNames": [name for name, rows in valid.items() if rows],
            "distinctVerifiedInodes": len(copies),
            "distinctVerifiedDevices": len({device for device, _ in copies}),
            "libraryAndCarriedVerified": bool(valid["library"] and valid["carried"]),
            "backupVerified": bool(valid["backup"])}


def _media_inventory(publish_files: list[Path], release_files: list[Path], inputs: InputBudget) -> dict:
    references = defaultdict(list)
    for path in publish_files:
        if path.suffix != ".json":
            continue
        refs = []
        _walk_records(inputs.document(path), path="$", document_ref=str(path), found=refs)
        _add_refs(references, refs)
    for path in release_files:
        if path.name == "media_manifest.json" and path.parent.name == "payload":
            _add_refs(references, media_references_in_release_manifest(inputs.document(path), document_ref=str(path)))
    return references


def _add_refs(references: dict, refs: list | tuple) -> None:
    for ref in refs:
        references[ref.digest].append({"path": ref.document_ref, "recordPath": ref.record_path,
                                       "declaredBytes": ref.declared_bytes})


def _checked_media(references: dict, backup_root: Path, budget: HashBudget) -> list[dict]:
    media = []
    for digest, refs in sorted(references.items()):
        row = inspect_holders(digest, library=LIBRARY_ROOT, carried=carried_media_root(),
                              backup=backup_root, budget=budget)
        row["references"] = refs
        sizes = {ref["declaredBytes"] for ref in refs if ref["declaredBytes"] is not None}
        observed = {entry["bytes"] for entries in row["holders"].values()
                    for entry in entries if entry["state"] == "verified"}
        row.update(declaredSizes=sorted(sizes), declaredSizesMatched=not sizes or sizes == observed)
        media.append(row)
    return media


def _media_issues(media: list[dict]) -> list[dict]:
    codes = {"backupVerified": "BACKUP_DIGEST_CLOSURE_INCOMPLETE",
             "libraryAndCarriedVerified": "LIBRARY_CARRIED_CLOSURE_INCOMPLETE",
             "declaredSizesMatched": "MEDIA_DECLARED_SIZE_DRIFT"}
    return [{"code": f"DATA.AUDIT.{code}", "sha256s": missing}
            for field, code in codes.items() if (missing := [r["sha256"] for r in media if not r[field]])]


def _exact_refs(node: object):
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith("Ref") and isinstance(value, str) and value.startswith(("data/", "env/")):
                yield value, node.get(key[:-3] + "Digest")
            yield from _exact_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _exact_refs(value)


def _binding_ref(ref: str, expected: str | None, output_root: Path,
                 inputs: InputBudget, budget: HashBudget) -> dict:
    target = contained(output_root, ref)
    if target.is_dir():
        return {"path": str(target), "ref": ref,
                "state": "protected_tree" if target in inputs.nodes else "unprotected"}
    if target.exists():
        inputs.record(target)
    return {**budget.inspect(target, expected), "ref": ref, "declaredDigest": expected}


def _binding_row(path: Path, output_root: Path, release_ids: set[str],
                 inputs: InputBudget, budget: HashBudget) -> tuple[dict, list[dict]]:
    document = inputs.document(path)
    links = {key: document[key] for key in ("releaseId", "rollbackTo", "rollbackFromReleaseId") if key in document}
    checks = [_binding_ref(ref, expected, output_root, inputs, budget) for ref, expected in _exact_refs(document)]
    row = {**budget.inspect(path), "schema": document.get("schema"), "exactRefChecks": checks, "releaseLinks": links}
    issues = [{"code": "DATA.AUDIT.BINDING_RELEASE_MISSING", "path": str(path), "key": key}
              for key, value in links.items() if value not in release_ids]
    issues.extend({"code": "DATA.AUDIT.BINDING_TARGET_UNPROVEN", "path": str(path), "ref": check.get("ref")}
                  for check in [row, *checks] if check["state"] not in ("verified", "protected_tree"))
    return row, issues


def _binding_inputs(paths: list[Path], output_root: Path, release_roots: list[Path],
                    inputs: InputBudget, budget: HashBudget) -> tuple[list[dict], list[dict]]:
    results = [_binding_row(path, output_root, {root.name for root in release_roots}, inputs, budget) for path in paths]
    return [row for row, _ in results], [issue for _, issues in results for issue in issues]


def freeze_files(files: list[Path], budget: HashBudget) -> dict:
    rows = [budget.inspect(path) for path in sorted(set(files))]
    exact = [{key: row.get(key) for key in ("path", "sha256", "bytes", "state")} for row in rows]
    digest = hashlib.sha256(json.dumps(exact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"status": "passed" if all(row["state"] == "verified" for row in rows) else "blocked",
            "fileCount": len(rows), "logicalBytes": sum(row.get("bytes", 0) for row in rows),
            "inventorySha256": f"sha256:{digest}", "files": rows,
            "semantics": "本次逐文件摘要证据冻结，不是 chmod/拷贝/删除许可；硬链接仅同 inode 稳定签名复用 hash"}


def _unchanged(nodes: dict[Path, tuple]) -> list[dict]:
    issues = []
    for path, before in nodes.items():
        if not path.exists() or signature(path.lstat()) != before:
            issues.append({"code": "DATA.AUDIT.INPUT_CHANGED", "path": str(path)})
    return issues


def _capacity_components(budgets: dict, roots: dict, reserve_bytes: int) -> tuple:
    components, devices = [], {}
    for name in COMPONENTS:
        root, upper = roots[name], budgets.get(name)
        fs, device = os.statvfs(root), root.stat().st_dev
        available = fs.f_bavail * fs.f_frsize
        group = devices.setdefault(device, {"device": device, "availableBytes": available,
                                           "declaredPeakBytes": 0, "reserveBytes": reserve_bytes, "complete": True})
        group["availableBytes"] = min(group["availableBytes"], available)
        group["complete"] = group["complete"] and upper is not None
        group["declaredPeakBytes"] += upper or 0
        components.append({"component": name, "path": str(root), "device": device,
                           "upperBoundBytes": upper, "basis": "caller_declared_upper_bound" if upper is not None else "unknown"})
    return components, devices


def capacity_audit(*, budgets: dict[str, int | None], roots: dict[str, Path], reserve_bytes: int,
                   known: dict) -> dict:
    if reserve_bytes < 0 or any(type(value) is not int or value < 0 for value in budgets.values() if value is not None):
        raise ValueError("DATA.AUDIT.CAPACITY_BUDGET_INVALID")
    components, devices = _capacity_components(budgets, roots, reserve_bytes)
    issues = []
    if any(row["upperBoundBytes"] is None for row in components):
        issues.append({"code": "DATA.AUDIT.PEAK_CAPACITY_INPUT_MISSING",
                       "components": [r["component"] for r in components if r["upperBoundBytes"] is None]})
    if budgets.get("original") is not None and budgets["original"] > ORIGINAL_LIMIT:
        issues.append({"code": "DATA.AUDIT.ORIGINAL_BUDGET_EXCEEDS_LIMIT", "limitBytes": ORIGINAL_LIMIT})
    for group in devices.values():
        group["remainingAfterDeclaredPeakBytes"] = group["availableBytes"] - group["declaredPeakBytes"] - reserve_bytes
        if group["remainingAfterDeclaredPeakBytes"] < 0:
            issues.append({"code": "DATA.AUDIT.PEAK_CAPACITY_INSUFFICIENT", "device": group["device"]})
    return {"status": "blocked" if issues else "passed", "issues": issues, "knownExisting": known,
            "components": components, "devices": list(devices.values()), "originalLimitBytes": ORIGINAL_LIMIT,
            "semantics": "五项新增峰值按同设备同时存活保守求和；现存字节已由 statvfs 扣除，不将 hash I/O 当新增空间；声明上限非实测新视频大小，越界需重新评估"}


def _release_roots(root: Path, inputs: InputBudget) -> list[Path]:
    return sorted(path for path, value in inputs.nodes.items() if path.parent == root and stat.S_ISDIR(value[2]))


def _known_existing(publish_files: list[Path], inputs: InputBudget, frozen: dict, media: list[dict]) -> dict:
    sizes = [r["bytes"] for row in media for r in row["holders"]["library"] if r["state"] == "verified"]
    return {"publishTreeLogicalBytes": sum(inputs.nodes[p][3] for p in publish_files),
            "releaseAndReferenceLogicalBytes": frozen["logicalBytes"], "uniqueVerifiedMediaBytes": sum(sizes)}


def _protection_counts(media: list[dict]) -> dict:
    return {"digests": len(media), "backupVerified": sum(r["backupVerified"] for r in media),
            "libraryAndCarriedVerified": sum(r["libraryAndCarriedVerified"] for r in media),
            "independentDeviceCopies": sum(r["distinctVerifiedDevices"] > 1 for r in media)}


def protection_audit(*, publish_root: Path, releases_root: Path, reference_root: Path,
                     backup_root: Path, bindings: list[Path], max_digests: int, max_hash_bytes: int,
                     max_files: int, max_metadata_bytes: int, budgets: dict, budget_root: Path,
                     reserve_bytes: int = 0) -> dict:
    publish_root, releases_root, reference_root, backup_root = [
        path.absolute() for path in (publish_root, releases_root, reference_root, backup_root)]
    inputs, budget = InputBudget(max_files, max_metadata_bytes), HashBudget(max_hash_bytes)
    publish_files = inputs.tree(publish_root)
    release_files = inputs.tree(releases_root)
    reference_files = inputs.tree(reference_root)
    release_roots = _release_roots(releases_root, inputs)
    references = _media_inventory(publish_files, release_files, inputs)
    if not references or len(references) > max_digests:
        raise ValueError(f"DATA.AUDIT.DIGEST_BOUND: actual={len(references)} bound={max_digests}")
    media = _checked_media(references, backup_root, budget)
    frozen = freeze_files(release_files + reference_files, budget)
    binding_rows, issues = _binding_inputs([p.absolute() for p in bindings], releases_root.parent.parent,
                                          release_roots, inputs, budget)
    issues.extend(_media_issues(media))
    if frozen["status"] != "passed":
        issues.append({"code": "DATA.AUDIT.RELEASE_TREE_FREEZE_INCOMPLETE"})
    issues.extend({"code": "DATA.AUDIT.RELEASE_MANIFEST_MISSING", "path": str(root)}
                  for root in release_roots if root / "payload/media_manifest.json" not in release_files)
    roots = {name: budget_root for name in COMPONENTS}
    roots.update({"golden-growth": carried_media_root(), "backup-growth": backup_root})
    capacity = capacity_audit(budgets=budgets, roots=roots, reserve_bytes=reserve_bytes,
                             known=_known_existing(publish_files, inputs, frozen, media))
    issues.extend(capacity["issues"])
    issues.extend(_unchanged(inputs.nodes))
    issues.extend(_unchanged(budget.observed))
    return {"schema": "quwoquan_data.media_protection_audit.v2", "purpose": "offline_evidence_only",
            "status": "blocked" if issues else "passed", "firstTypedBlocker": issues[0] if issues else None,
            "issues": issues, "capacity": capacity, "releaseFreeze": frozen, "media": media,
            "counts": _protection_counts(media),
            "limits": {"maxDigests": max_digests, "maxHashBytes": max_hash_bytes, "actualHashBytes": budget.read_bytes,
                       "reusedInodeHashCount": budget.cache_hits, "maxFiles": max_files, "actualEntries": len(inputs.nodes),
                       "maxMetadataBytes": max_metadata_bytes, "actualMetadataReadBytes": inputs.metadata_bytes, "concurrency": 1},
            "protectedReleaseRoots": [str(p) for p in release_roots], "bindings": binding_rows,
            "scopeLayers": {"environment": "not_authorized_not_called; 只核对显式本地绑定与回滚引用，不声称四环境 authority",
                            "crossDeviceRestore": "not_executed; 本地 holder 摘要不证明异设备恢复，该层不是本计划默认硬门",
                            "retention": "保留全部显式本地旧 release 整树、reference、binding 及其引用；绝不删除或改写",
                            "activation": "not_authorized_not_called; 不迁移新池，不将旧 release 交新 reader 激活"}}


def handle_protection(args) -> None:
    document = protection_audit(publish_root=Path(args.publish_root), releases_root=Path(args.releases_root),
        reference_root=Path(args.reference_releases_root), backup_root=Path(args.backup_root).expanduser(),
        bindings=[Path(path) for path in args.binding], max_digests=args.max_digests, max_hash_bytes=args.max_hash_bytes,
        max_files=args.max_files, max_metadata_bytes=args.max_metadata_bytes,
        budgets={name: getattr(args, name.replace("-", "_") + "_bytes") for name in COMPONENTS},
        budget_root=Path(args.budget_root).expanduser(), reserve_bytes=args.reserve_bytes)
    write_evidence(Path(args.output), document)
    print(json.dumps({"output": args.output, "status": document["status"], "counts": document["counts"],
                      "limits": document["limits"], "capacity": document["capacity"],
                      "releaseFreeze": {k: v for k, v in document["releaseFreeze"].items() if k != "files"},
                      "firstTypedBlocker": document["firstTypedBlocker"],
                      "issueCodes": [row["code"] for row in document["issues"]]}, ensure_ascii=False, indent=2))
    if document["firstTypedBlocker"]:
        raise SystemExit(1)
