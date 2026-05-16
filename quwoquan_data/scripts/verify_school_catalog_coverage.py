"""学校数据源覆盖率验证

检查项：
  S1 - source_manifest.json 存在且每个 source 含必要字段
  S2 - universities_national.ndjson 行数 == manifest rowCount
  S3 - schools_beijing.ndjson 行数 == manifest rowCount
  S4 - schools_shanghai.ndjson 行数 == manifest rowCount
  S5 - 每行必含必填字段
  S6 - 无完全重复行（name+province/district+city 去重）

用法:
  python3 verify_school_catalog_coverage.py
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import RUNTIME_ROOT

CATALOG_DIR = RUNTIME_ROOT / "seed" / "school_catalog"
MANIFEST_PATH = CATALOG_DIR / "source_manifest.json"

errors: list[str] = []


def count_lines(fpath: Path) -> int:
    data = fpath.read_bytes()
    n = data.count(b"\n")
    if data and not data.endswith(b"\n"):
        n += 1
    return n


def s1_manifest():
    if not MANIFEST_PATH.exists():
        errors.append("S1: source_manifest.json 不存在")
        return None
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for src in manifest.get("sources", []):
        for field in ["url", "publishedAt", "fetchedAt", "sha256", "rowCount"]:
            if not src.get(field):
                errors.append(f"S1: source {src.get('id', '?')} 缺少 {field}")
    print(f"  S1: manifest 含 {len(manifest.get('sources', []))} 个数据源")
    return manifest


def s2_s4_row_counts(manifest):
    if not manifest:
        return
    for src in manifest.get("sources", []):
        fname = src.get("file", "")
        fpath = CATALOG_DIR / fname
        if not fpath.exists():
            errors.append(f"S2-S4: 文件不存在: {fname}")
            continue
        actual = count_lines(fpath)
        expected = src.get("rowCount", 0)
        if actual != expected:
            errors.append(f"S2-S4: {fname} 行数 {actual} != manifest {expected}")
        else:
            print(f"  S2-S4 OK: {fname} = {actual} 行")


def s5_required_fields():
    uni_file = CATALOG_DIR / "universities_national.ndjson"
    if uni_file.exists():
        n_err = _check_fields(uni_file, ["name", "province", "city"])
        if n_err == 0:
            print(f"  S5 OK: universities_national 字段完备")

    for fname, fields in [
        ("schools_beijing.ndjson", ["name", "district", "etype"]),
        ("schools_shanghai.ndjson", ["name", "district", "etype"]),
    ]:
        fpath = CATALOG_DIR / fname
        if fpath.exists():
            n_err = _check_fields(fpath, fields)
            if n_err == 0:
                print(f"  S5 OK: {fname} 字段完备")


def _check_fields(fpath: Path, required: list[str]) -> int:
    n_err = 0
    with open(fpath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            for field in required:
                if field not in obj or not obj[field]:
                    errors.append(f"S5: {fpath.name} 行 {i} 缺少 {field}")
                    n_err += 1
    return n_err


def s6_no_duplicates():
    for fname, key_fields in [
        ("universities_national.ndjson", ["name", "province", "city"]),
        ("schools_beijing.ndjson", ["name", "district"]),
        ("schools_shanghai.ndjson", ["name", "district"]),
    ]:
        fpath = CATALOG_DIR / fname
        if not fpath.exists():
            continue
        seen = set()
        dupes = 0
        with open(fpath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                key = tuple(obj.get(k, "") for k in key_fields)
                if key in seen:
                    errors.append(f"S6: {fname} 行 {i} 重复: {key}")
                    dupes += 1
                seen.add(key)
        if dupes == 0:
            print(f"  S6 OK: {fname} 无重复 ({len(seen)} 唯一)")


def main():
    print("=" * 60)
    print("学校数据源覆盖率验证")
    print("=" * 60)

    manifest = s1_manifest()
    s2_s4_row_counts(manifest)
    s5_required_fields()
    s6_no_duplicates()

    print(f"\n{'ERROR' if errors else '(无错误)'}（{len(errors)} 条）:")
    for e in errors:
        print(f"  ✗ {e}")
    print(f"\n{'验证通过' if not errors else '验证失败'}: {len(errors)} 错误")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
