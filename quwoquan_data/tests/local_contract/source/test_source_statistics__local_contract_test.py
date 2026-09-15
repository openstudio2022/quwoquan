# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
"""真实 producer CLI 读取临时 canonical 包；不读生产库、不人工填写聚合行。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / ".agents/skills/content-production/scripts/producer.py"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def source(url="https://commons.wikimedia.org/wiki/File:山.jpg", *, native=None, **extra):
    row = {"schema": "quwoquan_data.publish_source", "sourceId": "s001", "sourceUrl": url,
           "sourceUseMode": "licensed_adaptation", "metadata": {}, "assets": [], "evidence": [], **extra}
    if native:
        row["sourceWork"] = {"identity": {"provider": native[0], "nativeId": native[1], "pageUrl": url}}
    return row


def package(root, name, *, carrier="image", identity=None, version=1, sources=None, **fields):
    relative = f"{'entities' if carrier == 'homepage' else 'posts/' + carrier}/测试/p0001/{name}/1/manifest.json"
    manifest = {"schema": "quwoquan_data.entity_object" if carrier == "homepage" else "quwoquan_data.post_object",
                "entityId" if carrier == "homepage" else "contentId": identity or name,
                "version": version, "contentType": carrier, "sourceRefs": [], "assets": [], **fields}
    for index, row in enumerate(sources or []):
        ref = f"sources/s{index:03}/source.json"
        manifest["sourceRefs"].append(ref)
        write_json((root / relative).parent / ref, row)
    write_json(root / relative, manifest)
    return relative


def run(root, *paths, ok=True):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "QWQ_PUBLISH_ROOT": str(root / "unused-publish"),
           "QWQ_LIBRARY_ROOT": str(root / "unused-library"), "QWQ_CARRIED_MEDIA_ROOT": str(root / "unused-media")}
    result = subprocess.run([sys.executable, "-B", str(CLI), "--workspace", str(root), "source-stats", "--manifest", *paths],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == (0 if ok else 1), result.stdout + result.stderr
    return json.loads(result.stdout)


def sites(result, role="adopted", carrier=None):
    group = result["overall"] if carrier is None else result["byCarrier"][carrier]
    return {row["website"]: row for row in group[role]["websites"]}


def test_zero_scope_is_explicit_and_read_only(tmp_path):
    before = list(tmp_path.iterdir())
    result = run(tmp_path)
    assert result["overall"]["adopted"] == {"total": 0, "withSource": 0, "missingSource": 0,
        "invalidURL": 0, "websiteCount": 0, "associationCount": 0, "websites": []}
    assert list(tmp_path.iterdir()) == before


def test_single_multiimage_duplicate_work_and_version_not_assets(tmp_path):
    first = package(tmp_path, "one", identity="same", sources=[source(native=("commons", "10"))],
                    assets=[{"originalAssetUrl": "https://upload.wikimedia.org/one.jpg"}] * 3)
    latest = package(tmp_path, "latest", identity="same", version=2,
                     sources=[source("https://tuchong.com/work/10", native=("tuchong", "10"))])
    duplicate = package(tmp_path, "copy", sources=[source("https://tuchong.com/work/10", native=("tuchong", "10"))])
    result = run(tmp_path, first, latest, duplicate, duplicate)
    assert result["overall"]["adopted"]["total"] == 1
    assert result["scope"]["ignoredVersions"] == [first]
    assert sites(result) == {"tuchong.com": {"website": "tuchong.com", "works": 1, "coverageRate": 1, "associationShare": 1}}
    assert result["deduplicatedWorks"] == [[latest, duplicate]]


def test_multisource_same_host_coverage_and_share_with_missing_denominator(tmp_path):
    article = package(tmp_path, "article", carrier="article", sources=[source("https://zh.wikipedia.org/wiki/A"),
        source("https://en.wikipedia.org/wiki/B"), source("https://travel.example.com.cn/story")])
    missing = package(tmp_path, "missing", carrier="article")
    result = run(tmp_path, article)
    assert sum(row["coverageRate"] for row in sites(result).values()) == 2
    result = run(tmp_path, article, missing)
    assert sum(row["associationShare"] for row in sites(result).values()) == 1
    assert sites(result)["travel.example.com.cn"]["coverageRate"] == 0.5
    assert result["byCarrier"]["article"]["adopted"]["missingSource"] == 1
    assert result["byCarrier"]["image"]["adopted"]["total"] == 0


def test_cdn_license_original_asset_are_not_works_and_commons_page_is(tmp_path):
    image = package(tmp_path, "commons", sources=[source(assets=[{"originalAssetUrl": "https://upload.wikimedia.org/a.jpg",
        "licenseUrl": "https://creativecommons.org/licenses/by/4.0/"}])])
    invalid_role = package(tmp_path, "asset-only", sources=[source("https://cdn.example.com/file.jpg")])
    license_only = package(tmp_path, "license", sources=[source("https://licenses.example.org/custom",
        metadata={"licenseUrl": "https://licenses.example.org/custom"})])
    result = run(tmp_path, image, invalid_role, license_only)
    assert set(sites(result)) == {"commons.wikimedia.org"}
    assert result["overall"]["adopted"]["missingSource"] == 2
    assert result["overall"]["original"]["withSource"] == 0


def test_baidu_discovery_and_pinterest_original_are_separate(tmp_path):
    video = package(tmp_path, "video", carrier="video", sources=[source("https://www.bilibili.com/video/BV1",
        metadata={"discoveryUrl": "https://video.baidu.com/search?word=山"})])
    discovery_only = package(tmp_path, "discovery", carrier="video", sources=[source("https://video.baidu.com/search?word=水")])
    pin = source("https://www.pinterest.com/pin/10", native=("pinterest", "10"))
    pin["sourceWork"]["identity"]["originalUrl"] = "https://photographer.example/gallery/山"
    image = package(tmp_path, "pin", sources=[pin])
    result = run(tmp_path, video, discovery_only, image)
    assert set(sites(result)) == {"www.bilibili.com", "pinterest.com"}
    assert sites(result, "discovery")["video.baidu.com"]["works"] == 2
    assert set(sites(result, "original")) == {"photographer.example"}
    assert result["overall"]["adopted"]["missingSource"] == 1


@pytest.mark.parametrize("bad", ["not a URL", "https://", "https://site.test:wrong/a", "https://" + "placeholder.invalid:invalid" + "@" + "site.test/a", 42])
def test_invalid_urls_remain_in_denominator(tmp_path, bad):
    path = package(tmp_path, "invalid", sources=[source(bad)])
    result = run(tmp_path, path)["overall"]["adopted"]
    assert result["total"] == result["missingSource"] == result["invalidURL"] == 1


def test_missing_ref_and_raw_provenance_not_parsed(tmp_path):
    path = package(tmp_path, "raw", sources=[source()])
    source_path = (tmp_path / path).parent / "sources/s000/source.json"
    row = json.loads(source_path.read_text())
    row["metadata"]["Credit"] = '<a href="https://vimeo.com/123">Original</a>'
    row["evidence"] = [{"path": "evidence.raw"}]
    write_json(source_path, row)
    (source_path.parent / "evidence.raw").write_text('https://vimeo.com/123')
    result = run(tmp_path, path)
    assert result["overall"]["original"]["websiteCount"] == 0
    assert result["nativeIdentityUnknown"] == 1
    source_path.unlink()
    result = run(tmp_path, path)
    assert result["objects"][0]["missingSourceRefs"] == ["sources/s000/source.json"]
    assert result["overall"]["adopted"]["missingSource"] == 1


def test_shared_reference_does_not_merge_articles_or_unknown_native(tmp_path):
    paths = [package(tmp_path, f"a{i}", carrier="article", sources=[source(native=("wiki", "1"))]) for i in range(2)]
    paths += [package(tmp_path, f"i{i}", sources=[source()]) for i in range(2)]
    result = run(tmp_path, *paths)
    assert result["overall"]["adopted"]["total"] == 4
    assert result["nativeIdentityUnknown"] == 2


def test_provider_native_id_pair_does_not_guess_cross_platform_repost(tmp_path):
    paths = [package(tmp_path, provider, carrier="video", sources=[source(f"https://{provider}.com/video/1", native=(provider, "1"))])
             for provider in ("douyin", "tiktok")]
    assert run(tmp_path, *paths)["overall"]["adopted"]["total"] == 2


@pytest.mark.parametrize("mutation", ["stage", "schema", "path"])
def test_draft_download_review_are_not_mixed(tmp_path, mutation):
    path = package(tmp_path, "draft")
    if mutation == "path":
        staged = "execution/4.draft/manifest.json"
        write_json(tmp_path / staged, json.loads((tmp_path / path).read_text()))
        path = staged
    else:
        doc = json.loads((tmp_path / path).read_text())
        doc[mutation] = "4.draft" if mutation == "stage" else "quwoquan_data.post_manifest"
        write_json(tmp_path / path, doc)
    assert "CANONICAL_ONLY" in run(tmp_path, path, ok=False)["message"]


def test_same_id_version_conflict_and_carrier_conflict_are_rejected(tmp_path):
    first = package(tmp_path, "first", identity="same")
    second = package(tmp_path, "second", identity="same", title="changed")
    assert "VERSION_CONFLICT" in run(tmp_path, first, second, ok=False)["message"]
    second = package(tmp_path, "second", identity="same", version=2, carrier="video")
    assert "CARRIER_CONFLICT" in run(tmp_path, first, second, ok=False)["message"]


@pytest.mark.parametrize("escape", ["../outside/manifest.json", "/tmp/manifest.json"])
def test_scope_rejects_escape(tmp_path, escape):
    assert "PATH_OUTSIDE_ROOT" in run(tmp_path, escape, ok=False)["message"]


def test_symlink_in_manifest_source_and_root_rejected(tmp_path):
    root = tmp_path / "root"
    path = package(root, "real", sources=[source()])
    (root / "linked").symlink_to((root / path).parent, target_is_directory=True)
    assert "SYMLINK_FORBIDDEN" in run(root, "linked/manifest.json", ok=False)["message"]
    source_path = (root / path).parent / "sources/s000/source.json"
    outside = tmp_path / "outside.json"
    source_path.rename(outside)
    source_path.symlink_to(outside)
    assert "SYMLINK_FORBIDDEN" in run(root, path, ok=False)["message"]
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    assert "INVALID_ROOT" in run(linked_root, ok=False)["message"]


def test_conflicting_source_identity_is_reported_not_repaired(tmp_path):
    row = source("https://commons.wikimedia.org/wiki/File:A", native=("commons", "a"),
                 metadata={"canonicalUrl": "https://vimeo.com/123", "originalUrl": "https://vimeo.com/123"})
    row["sourceWork"]["identity"].update(pageUrl="https://vimeo.com/123", originalUrl="https://commons.wikimedia.org/wiki/File:A")
    path = package(tmp_path, "conflict", sources=[row])
    result = run(tmp_path, path)
    assert result["objects"][0]["nativeIdentity"] == "unknown"
    assert len(result["objects"][0]["sourceConflicts"]) == 3
    assert set(sites(result)) == {"commons.wikimedia.org"}


def test_identical_manifest_different_locator_is_not_silently_merged(tmp_path):
    first = package(tmp_path, "first", identity="same")
    second = package(tmp_path, "second", identity="same")
    assert "VERSION_CONFLICT" in run(tmp_path, first, second, ok=False)["message"]


def test_explicit_scope_does_not_read_unselected_bad_file_or_write_outputs(tmp_path):
    path = package(tmp_path, "selected", carrier="homepage", sources=[source("https://zh.wikipedia.org/wiki/A")])
    (tmp_path / "manifest.json").write_text("not json")
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert run(tmp_path, path)["byCarrier"]["homepage"]["adopted"]["total"] == 1
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
