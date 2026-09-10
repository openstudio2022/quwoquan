# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-008
"""真实 canonical 小 cohort 的离线派生合同；不运行 producer 或修改媒体库。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_data/scripts"))

from content.release.canonical.offline_snapshot import build_bundle, export_bundle, write_dart_identity
from content.release.canonical.offline_snapshot_contract import OfflineSnapshotError, canonical_bytes, digest, validate_selection
from content.release.canonical.offline_snapshot_projection import runtime_post_id, runtime_homepage_id
from content.release.canonical.offline_snapshot_source import _read_media
from content.release.canonical.offline_snapshot_contract import PublicContractValidator, validate_bundle
from core.content_library import library_cas_path

SELECTION = ROOT / "quwoquan_app/assets/content/alpha/operator_selection.json"
REVISION = "b0164eae05dab590209997d27356b372a0634bdc"


def selection():
    return json.loads(SELECTION.read_bytes())


def test_operator_selection_is_engineering_only_and_explicit():
    value = selection()
    validate_selection(value)
    assert value["authority"]["grantsProductionPremium"] is False
    assert value["channels"][1]["orderedObjectRefs"] == ["posts/video/风光/西湖灯光秀/1"]
    value["qualityScore"] = 0.85
    with pytest.raises(ValueError):
        validate_selection(value)


def test_selection_rejects_outside_cohort_and_duplicate_channels():
    value = selection()
    value["channels"][1]["orderedObjectRefs"] = ["posts/video/outside/1"]
    with pytest.raises(OfflineSnapshotError, match="OUTSIDE_COHORT"):
        validate_selection(value)
    value = selection()
    value["channels"].append(copy.deepcopy(value["channels"][0]))
    with pytest.raises(OfflineSnapshotError, match="CHANNEL_SELECTION"):
        validate_selection(value)


def test_runtime_post_id_executes_current_go_function_for_parity(tmp_path):
    source = (ROOT / "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport/runtime.go").read_text()
    function = re.search(r"func RuntimePostID\(contentID string\) string \{.*?\n\}", source, re.S).group()
    ids = ["qwq_data_faaf0b1d1dfe1a7fb1524e66", "qwq_data_c38c8eb7aa343f94e3a54ffa", "qwq_data_2140521c2de8b435c8c72db7"]
    program = 'package main\nimport("crypto/sha256";"encoding/hex";"strings";"fmt")\n' + function
    program += '\nfunc main(){' + ''.join('fmt.Println(RuntimePostID(' + json.dumps(v) + '));' for v in ids) + '}\n'
    path = tmp_path / "identity.go"
    path.write_text(program)
    env = {**os.environ, "GOCACHE": str(ROOT / ".qwq_output/env/repo/local/offline-go-cache"), "GOTOOLCHAIN": "local", "GOPROXY": "off"}
    result = subprocess.run(["go", "run", str(path)], capture_output=True, text=True, check=True, env=env)
    assert result.stdout.splitlines() == [runtime_post_id(v) for v in ids]
    assert runtime_post_id("") == ""


def test_real_cohort_complete_and_deterministic(tmp_path):
    first = build_bundle(repo=ROOT, publish_root=ROOT / "quwoquan_data/publish", selection=selection(), source_revision=REVISION, library_root=Path.home() / ".local/share/quwoquan/content_library", carried_root=Path.home() / ".local/share/quwoquan/golden_media")
    second = build_bundle(repo=ROOT, publish_root=ROOT / "quwoquan_data/publish", selection=selection(), source_revision=REVISION, library_root=Path.home() / ".local/share/quwoquan/content_library", carried_root=Path.home() / ".local/share/quwoquan/golden_media")
    assert canonical_bytes(first.manifest) == canonical_bytes(second.manifest)
    bundle = first.manifest
    assert bundle["counts"] == {"posts": 3, "article": 1, "image": 1, "video": 1, "creators": 3, "homepages": 1, "tags": 23, "media": 6, "mediaBytes": 17177336}
    assert "home_channels" not in bundle["configuration"]["content"]
    assert "sourceReleaseId" not in bundle and "sourceManifestDigest" not in bundle
    assert "releaseClass" not in bundle["provenance"]
    article = bundle["posts"][0]["detail"]
    assert article["articleMarkdown"] == (ROOT / "quwoquan_data/publish/posts/article/文化/西湖十景漫读/1/article.md").read_text()
    assert article["articleAssetManifest"]["assets"] == []
    assert "coverUrl" not in article
    for source_attribution in bundle["provenance"]["sourceAttributions"]:
        ref = source_attribution["sourceObjectRef"]
        assert source_attribution["document"] == json.loads((ROOT / "quwoquan_data/publish" / ref / "manifest.json").read_bytes())["sourceAttribution"]
    video = bundle["posts"][2]["detail"]
    assert video["sourceAttribution"]["commercialAuthorizationStatus"] == "unverified"
    assert video["sourceAttribution"]["publicationAdmission"] == "research_release"
    assert all(m["canonicalReference"].startswith("media/") and "://" not in m["canonicalReference"] for m in bundle["media"])
    result = export_bundle(first, tmp_path / "alpha")
    assert export_bundle(first, tmp_path / "alpha", check=True) == result
    pin = tmp_path / "pin.g.dart"
    write_dart_identity(result, pin)
    write_dart_identity(result, pin, check=True)
    assert result["manifestDigest"] in pin.read_text()
    pin.write_text(pin.read_text().replace(result["manifestDigest"], "sha256:" + "0" * 64))
    with pytest.raises(OfflineSnapshotError, match="IDENTITY_OUTPUT_DRIFT"):
        write_dart_identity(result, pin, check=True)
    raw = (tmp_path / "alpha/manifest.json").read_bytes()
    assert result["manifestDigest"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    for m in bundle["media"]:
        path = tmp_path / "alpha/media" / Path(m["assetPath"]).name
        assert path.stat().st_size == m["byteLength"]
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == m["sha256"]
    assert export_bundle(first, tmp_path / "alpha") == result
    print("OFFLINE_EXPORT_IDENTITY=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


def test_missing_or_corrupt_media_does_not_publish_manifest(tmp_path):
    first = build_bundle(repo=ROOT, publish_root=ROOT / "quwoquan_data/publish", selection=selection(), source_revision=REVISION, library_root=Path.home() / ".local/share/quwoquan/content_library", carried_root=Path.home() / ".local/share/quwoquan/golden_media")
    asset = next(iter(first.media_bytes))
    first.media_bytes[asset] = b"corrupted"
    with pytest.raises(OfflineSnapshotError, match="MEDIA"):
        export_bundle(first, tmp_path / "alpha")
    assert not (tmp_path / "alpha/manifest.json").exists()


def test_symlink_output_rejected(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "alpha").symlink_to(target, target_is_directory=True)
    first = build_bundle(repo=ROOT, publish_root=ROOT / "quwoquan_data/publish", selection=selection(), source_revision=REVISION, library_root=Path.home() / ".local/share/quwoquan/content_library", carried_root=Path.home() / ".local/share/quwoquan/golden_media")
    with pytest.raises(OfflineSnapshotError, match="SYMLINK"):
        export_bundle(first, tmp_path / "alpha")
    assert not list(target.iterdir())


def test_holding_backup_missing_corrupt_and_symlink_are_distinct(tmp_path):
    library, carried = tmp_path / "library", tmp_path / "carried"
    raw = b"exact-test-image-body"
    sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(OfflineSnapshotError, match="HOLDING_MISSING"):
        _read_media(sha, len(raw), ".jpg", library=library, carried=carried)
    carried.mkdir()
    backup = carried / (sha[7:] + ".jpg")
    backup.write_bytes(raw)
    assert _read_media(sha, len(raw), ".jpg", library=library, carried=carried) == raw
    primary = library_cas_path("media", sha, library_root=library)
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b"corrupt")
    with pytest.raises(OfflineSnapshotError, match="HASH_OR_SIZE_DRIFT"):
        _read_media(sha, len(raw), ".jpg", library=library, carried=carried)
    primary.unlink()
    primary.symlink_to(backup)
    with pytest.raises(OfflineSnapshotError, match="SYMLINK"):
        _read_media(sha, len(raw), ".jpg", library=library, carried=carried)


def test_strict_public_projection_rejects_internal_and_unknown_fields():
    validator = PublicContractValidator(ROOT)
    view = {"postId": "post", "contentType": "article", "likeCount": 0, "commentCount": 0, "shareCount": 0}
    validator.validate_projection(view, "content_post_projection")
    for key in ("payloadDigest", "qualityScore", "releaseClass", "unexpected"):
        with pytest.raises(OfflineSnapshotError, match="PUBLIC_PROJECTION_INVALID"):
            validator.validate_projection({**view, key: "forbidden"}, "content_post_projection")


def test_current_homepage_identity_parity(tmp_path):
    source = (ROOT / "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model/homepage.go").read_text()
    functions = [re.search(r"func " + name + r"\(.*?\n\}", source, re.S).group() for name in ("StableID", "CanonicalEntityID", "canonicalSlug")]
    program = 'package main\nimport("crypto/sha256";"encoding/hex";"strings";"unicode";"fmt")\n' + '\n'.join(functions)
    program += '\nfunc main(){fmt.Println(StableID("", "qwq_data", "地点/景区/西湖", "sight", "西湖"))}\n'
    path = tmp_path / "homepage_identity.go"
    path.write_text(program)
    env = {**os.environ, "GOCACHE": str(ROOT / ".qwq_output/env/repo/local/offline-go-cache"), "GOTOOLCHAIN": "local", "GOPROXY": "off"}
    result = subprocess.run(["go", "run", str(path)], capture_output=True, text=True, check=True, env=env)
    assert result.stdout.strip() == runtime_homepage_id("/entity/地点/景区/西湖")


def test_bundle_mutation_never_writes_a_manifest(tmp_path):
    bundle = build_bundle(repo=ROOT, publish_root=ROOT / "quwoquan_data/publish", selection=selection(), source_revision=REVISION, library_root=Path.home() / ".local/share/quwoquan/content_library", carried_root=Path.home() / ".local/share/quwoquan/golden_media")
    bundle.manifest["posts"][0]["projection"]["title"] = "changed"
    with pytest.raises(OfflineSnapshotError, match="BUNDLE_IDENTITY_DRIFT"):
        export_bundle(bundle, tmp_path / "alpha")
    assert not (tmp_path / "alpha/manifest.json").exists()


def test_nonprod_only_asset_registration():
    import yaml
    pubspec = yaml.safe_load((ROOT / "quwoquan_app/pubspec.yaml").read_text())
    registrations = [r for r in pubspec["flutter"]["assets"] if isinstance(r, dict) and r["path"].startswith("assets/content/alpha/")]
    assert {r["path"] for r in registrations} == {"assets/content/alpha/manifest.json", "assets/content/alpha/media/"}
    assert all(r["flavors"] == ["nonprod"] for r in registrations)


def test_cli_registers_downstream_export_without_producer_fields():
    import argparse
    from content.release.canonical.handler_cli import register_parser
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    args = parser.parse_args(["release", "export-offline", "--selection-file", "selection.json", "--source-revision", REVISION,
                              "--publish-root", "publish", "--output-dir", "alpha"])
    assert args.handler.__name__ == "handle_export_offline"
    assert not hasattr(args, "release_class") and not hasattr(args, "milestone")


def test_partial_media_binding_and_wrong_detail_identity_fail_closed():
    built = build_bundle(repo=ROOT, publish_root=ROOT / "quwoquan_data/publish", selection=selection(), source_revision=REVISION, library_root=Path.home() / ".local/share/quwoquan/content_library", carried_root=Path.home() / ".local/share/quwoquan/golden_media")
    validator = PublicContractValidator(ROOT)
    value = copy.deepcopy(built.manifest)
    value["posts"][2]["detail"]["mediaItems"][0]["coverUrl"] = "media/not-selected"
    with pytest.raises(OfflineSnapshotError, match="POSTER_BINDING_INVALID"):
        validate_bundle(value, validator)
    value = copy.deepcopy(built.manifest)
    value["posts"][0]["detail"]["postId"] = "another-post"
    with pytest.raises(OfflineSnapshotError, match="POST_DETAIL_IDENTITY_DRIFT"):
        validate_bundle(value, validator)
