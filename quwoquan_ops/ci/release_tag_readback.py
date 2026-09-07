#!/usr/bin/env python3
"""从 GitHub REST 精确回读生成 release tag 的 creator / ruleset readback 事实。

替代此前假设存在的外部 readback 服务与 controller GitHub App：workflow 用 GITHUB_TOKEN 只读
拉取 `repos/{r}/keys`、`git/ref/tags/{tag}`、`git/tags/{oid}`、`rulesets`（含 ETag），本模块把
这些原始响应归约为 `release_tag_admission.py` 校验的 canonical 事实；不做任何 mutation。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.release_tag_admission import (
    DEPLOY_KEY_BYPASS,
    ReleaseTagAdmissionError,
    _controller_producer,
    _fail,
    _positive_int,
    _sha,
    _text,
    _timestamp,
    _write_once,
    canonical_bytes,
    digest,
)

CREATOR_SCHEMA = "quwoquan_ops.creator_readback_fact.v1"
RULESET_SCHEMA = "quwoquan_ops.ruleset_readback_fact.v1"
TAG_PATTERN = {"include": ["refs/tags/v*"], "exclude": []}


def _load(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseTagAdmissionError("RELEASE_TAG.READBACK_INVALID", f"{label} is not readable JSON") from exc


def controller_key(keys: Sequence[Mapping[str, Any]], *, title: str) -> dict[str, Any]:
    """在 `repos/{r}/keys` 里唯一匹配 controller title 的可写 deploy key。"""
    matched = [key for key in keys if isinstance(key, Mapping) and key.get("title") == title]
    if len(matched) != 1:
        _fail("RELEASE_TAG.CONTROLLER_DENIED", f"controller deploy key '{title}' must exist exactly once")
    key = matched[0]
    if key.get("read_only") is not False:
        _fail("RELEASE_TAG.CONTROLLER_DENIED", "controller deploy key must be writable")
    public_key = _text(key.get("key"), "deployKey.key")
    # GitHub 不返回指纹；按公钥 base64 体计算 OpenSSH 风格 SHA256 指纹，与本地 ssh-keygen -lf 一致。
    import base64

    parts = public_key.split()
    if len(parts) < 2:
        _fail("RELEASE_TAG.CONTROLLER_DENIED", "controller deploy key is not OpenSSH public key text")
    raw = base64.b64decode(parts[1], validate=True)
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    return {"keyId": _positive_int(key.get("id"), "deployKey.id"), "title": title, "fingerprint": fingerprint}


def _identified(value: dict[str, Any]) -> dict[str, Any]:
    value["readbackId"] = digest(value)
    return value


def creator_readback(
    *, phase: str, repository: str, tag_name: str, producer: Mapping[str, Any], observed_at: str,
    ref_response: Mapping[str, Any] | None, tag_object: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": CREATOR_SCHEMA, "status": "verified", "phase": phase, "producer": dict(producer),
        "repository": repository, "tagRef": f"refs/tags/{tag_name}", "tagName": tag_name,
        "observedAt": _timestamp(observed_at, "observedAt"),
    }
    if phase == "pre_mutation":
        if ref_response is not None:
            _fail("RELEASE_TAG.READBACK_INVALID", "pre-mutation readback found an existing tag ref")
        return _identified({**base, "tagObjectOid": None, "peeledCommit": None, "creator": None, "creationRecord": None})
    if ref_response is None or tag_object is None:
        _fail("RELEASE_TAG.READBACK_INVALID", "post-mutation readback requires ref and tag object")
    ref_object = ref_response.get("object") if isinstance(ref_response.get("object"), Mapping) else {}
    if ref_response.get("ref") != f"refs/tags/{tag_name}" or ref_object.get("type") != "tag":
        _fail("RELEASE_TAG.READBACK_INVALID", "tag ref must point at an annotated tag object")
    oid = _sha(ref_object.get("sha"), "ref.object.sha")
    target = tag_object.get("object") if isinstance(tag_object.get("object"), Mapping) else {}
    tagger = tag_object.get("tagger") if isinstance(tag_object.get("tagger"), Mapping) else {}
    if tag_object.get("sha") != oid or target.get("type") != "commit":
        _fail("RELEASE_TAG.READBACK_INVALID", "tag object readback does not match ref or is not a direct commit tag")
    record = {
        "kind": "github_annotated_tag", "tagObjectOid": oid, "peeledCommit": _sha(target.get("sha"), "tag.object.sha"),
        "taggerName": _text(tagger.get("name"), "tagger.name"), "taggerEmail": _text(tagger.get("email"), "tagger.email"),
        "taggedAt": _timestamp(tagger.get("date"), "tagger.date"), "message": _text(tag_object.get("message"), "tag.message"),
        "deployKeyId": producer["keyId"], "deployKeyTitle": producer["title"], "deployKeyFingerprint": producer["fingerprint"],
        "deployKeyReadOnly": False, "repository": repository,
    }
    return _identified({
        **base, "tagObjectOid": oid, "peeledCommit": record["peeledCommit"],
        "creator": f"deploy-key:{producer['title']}", "creationRecord": record,
    })


def _rules(ruleset: Mapping[str, Any]) -> set[str]:
    return {str(rule.get("type")) for rule in ruleset.get("rules") or [] if isinstance(rule, Mapping)}


def _bypass(ruleset: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"actorType": str(actor.get("actor_type")), "bypassMode": str(actor.get("bypass_mode"))}
        for actor in ruleset.get("bypass_actors") or [] if isinstance(actor, Mapping)
    ]


def ruleset_readback(
    *, phase: str, repository: str, tag_name: str, producer: Mapping[str, Any], observed_at: str,
    rulesets: Sequence[Mapping[str, Any]], etags: Mapping[str, str], tag_object_oid: str | None, peeled_commit: str | None,
) -> dict[str, Any]:
    """两条 active tag ruleset 归约：创建仅 DeployKey bypass；update/delete 全 denied 无 bypass。"""
    tag_rulesets = []
    for ruleset in rulesets:
        conditions = ruleset.get("conditions") if isinstance(ruleset.get("conditions"), Mapping) else {}
        ref_name = conditions.get("ref_name") if isinstance(conditions.get("ref_name"), Mapping) else {}
        if ruleset.get("target") == "tag" and ruleset.get("enforcement") == "active" and {
            "include": list(ref_name.get("include") or []), "exclude": list(ref_name.get("exclude") or []),
        } == TAG_PATTERN:
            tag_rulesets.append(ruleset)
    creation = [r for r in tag_rulesets if _rules(r) == {"creation"} and _bypass(r) == [DEPLOY_KEY_BYPASS]]
    immutability = [r for r in tag_rulesets if _rules(r) == {"deletion", "non_fast_forward"} and _bypass(r) == []]
    if len(creation) != 1 or len(immutability) != 1:
        _fail("RELEASE_TAG.READBACK_INVALID", "hosted tag rulesets do not form the closed create-only/immutable control")
    payload = canonical_bytes({"creation": creation[0], "immutability": immutability[0]})
    create_id = _positive_int(creation[0].get("id"), "creation.id")
    immutability_id = _positive_int(immutability[0].get("id"), "immutability.id")
    etag = "|".join(_text(etags.get(str(rid)), f"etag[{rid}]") for rid in (create_id, immutability_id))
    return _identified({
        "schema": RULESET_SCHEMA, "status": "verified", "phase": phase, "producer": dict(producer),
        "repository": repository, "tagRef": f"refs/tags/{tag_name}", "tagName": tag_name,
        "tagObjectOid": tag_object_oid, "peeledCommit": peeled_commit,
        "rulesetId": create_id, "immutabilityRulesetId": immutability_id,
        "rulesetVersion": {"etag": etag, "apiPayloadDigest": "sha256:" + hashlib.sha256(payload).hexdigest()},
        "target": "tag", "enforcement": "active", "refNamePattern": TAG_PATTERN,
        "create": {"decision": "controller_only", "mode": "create_only", "bypassActors": [DEPLOY_KEY_BYPASS]},
        "update": {"decision": "denied", "bypassActors": []},
        "delete": {"decision": "denied", "bypassActors": []},
        "bypass": {"mode": "deploy_key_only", "actors": [DEPLOY_KEY_BYPASS]},
        "observedAt": _timestamp(observed_at, "observedAt"),
    })


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag-name", required=True)
    parser.add_argument("--phase", required=True, choices=("pre_mutation", "post_mutation"))
    parser.add_argument("--keys-file", required=True, type=Path, help="gh api repos/{r}/keys 的 JSON 数组")
    parser.add_argument("--controller-title", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    sub = parser.add_subparsers(dest="kind", required=True)
    creator = sub.add_parser("creator")
    creator.add_argument("--ref-file", type=Path, help="gh api repos/{r}/git/ref/tags/{tag}（pre 阶段应缺失/404）")
    creator.add_argument("--tag-object-file", type=Path, help="gh api repos/{r}/git/tags/{oid}")
    ruleset = sub.add_parser("ruleset")
    ruleset.add_argument("--rulesets-file", required=True, type=Path, help="全部 ruleset 详情的 JSON 数组")
    ruleset.add_argument("--etags-file", required=True, type=Path, help="{rulesetId: ETag} JSON")
    ruleset.add_argument("--tag-object-oid")
    ruleset.add_argument("--peeled-commit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        keys = _load(args.keys_file, "deploy keys")
        if not isinstance(keys, list):
            _fail("RELEASE_TAG.READBACK_INVALID", "deploy keys readback must be a JSON array")
        key = controller_key(keys, title=args.controller_title)
        producer = _controller_producer(key_id=key["keyId"], key_title=key["title"], key_fingerprint=key["fingerprint"])
        if args.kind == "creator":
            ref_response = _load(args.ref_file, "tag ref") if args.ref_file and args.ref_file.is_file() else None
            tag_object = _load(args.tag_object_file, "tag object") if args.tag_object_file and args.tag_object_file.is_file() else None
            if isinstance(ref_response, Mapping) and ref_response.get("status") == "404":
                ref_response = None
            fact = creator_readback(
                phase=args.phase, repository=args.repository, tag_name=args.tag_name, producer=producer,
                observed_at=args.observed_at, ref_response=ref_response, tag_object=tag_object,
            )
        else:
            rulesets = _load(args.rulesets_file, "rulesets")
            etags = _load(args.etags_file, "etags")
            if not isinstance(rulesets, list) or not isinstance(etags, Mapping):
                _fail("RELEASE_TAG.READBACK_INVALID", "rulesets/etags readback shape is invalid")
            fact = ruleset_readback(
                phase=args.phase, repository=args.repository, tag_name=args.tag_name, producer=producer,
                observed_at=args.observed_at, rulesets=rulesets, etags=etags,
                tag_object_oid=args.tag_object_oid, peeled_commit=args.peeled_commit,
            )
        path = _write_once(args.output.expanduser().resolve(), fact)
        print(json.dumps({"path": str(path), "digest": digest(path), "producer": producer}, sort_keys=True))
    except (OSError, ValueError) as error:
        code = getattr(error, "code", "RELEASE_TAG.IO_ERROR")
        print(json.dumps({"terminal": "GATE_BLOCK", "code": code, "detail": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
