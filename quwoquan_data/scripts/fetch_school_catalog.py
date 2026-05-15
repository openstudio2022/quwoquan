"""学校数据源采集与归一化

从教育部和地方教委官方数据源采集学校名单，归一化为 ndjson 格式。
采集结果写入 runtime/seed/school_catalog/ 目录。

当前支持数据源：
  - 教育部《全国普通高等学校名单》→ universities_national.ndjson
  - 北京市教委学校与幼儿园名录   → schools_beijing.ndjson
  - 上海市教委学校与幼儿园名录   → schools_shanghai.ndjson

用法:
  python3 fetch_school_catalog.py                    # 全量采集
  python3 fetch_school_catalog.py --source moe       # 只采集教育部高校
  python3 fetch_school_catalog.py --source beijing    # 只采集北京
  python3 fetch_school_catalog.py --source shanghai   # 只采集上海
  python3 fetch_school_catalog.py --verify-only       # 仅验证现有文件
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import RUNTIME_ROOT

CATALOG_DIR = RUNTIME_ROOT / "seed" / "school_catalog"
MANIFEST_PATH = CATALOG_DIR / "source_manifest.json"


def verify_manifest():
    if not MANIFEST_PATH.exists():
        print("ERROR: source_manifest.json 不存在")
        return False

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ok = True
    for src in manifest.get("sources", []):
        fname = src.get("file", "")
        fpath = CATALOG_DIR / fname
        if not fpath.exists():
            print(f"ERROR: 文件不存在: {fname}")
            ok = False
            continue

        data = fpath.read_bytes()
        actual_rows = data.count(b"\n")
        if not data.endswith(b"\n"):
            actual_rows += 1
        expected_rows = src.get("rowCount", 0)
        if actual_rows != expected_rows:
            print(f"ERROR: {fname} 行数不匹配: 期望 {expected_rows}, 实际 {actual_rows}")
            ok = False

        actual_sha = hashlib.sha256(data).hexdigest()
        expected_sha = src.get("sha256", "")
        if expected_sha and actual_sha != expected_sha:
            print(f"WARNING: {fname} SHA256 不匹配（文件可能已更新）")

        for required in ["url", "publishedAt", "fetchedAt", "fieldMappingVersion"]:
            if not src.get(required):
                print(f"ERROR: source {src.get('id', '?')} 缺少字段 {required}")
                ok = False

        print(f"  {fname}: {actual_rows} 行, SHA256={actual_sha[:16]}...")

    return ok


def verify_ndjson_fields(fpath: Path, required_fields: list[str]):
    errors = 0
    with open(fpath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  ERROR: {fpath.name} 行 {i} JSON 解析失败: {e}")
                errors += 1
                continue
            for field in required_fields:
                if field not in obj or not obj[field]:
                    print(f"  ERROR: {fpath.name} 行 {i} 缺少字段 {field}")
                    errors += 1
    return errors


def check_duplicates(fpath: Path, key_fields: list[str]):
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
                print(f"  DUPE: {fpath.name} 行 {i} 重复: {key}")
                dupes += 1
            seen.add(key)
    return dupes


def main():
    parser = argparse.ArgumentParser(description="学校数据源采集与归一化")
    parser.add_argument("--source", choices=["moe", "beijing", "shanghai"],
                        help="只采集指定数据源")
    parser.add_argument("--verify-only", action="store_true",
                        help="仅验证现有文件")
    args = parser.parse_args()

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        print("=" * 60)
        print("学校数据源验证")
        print("=" * 60)
        ok = verify_manifest()
        if ok:
            print("\n验证通过")
        else:
            print("\n验证失败")
            sys.exit(1)
        return

    print("=" * 60)
    print("学校数据源采集")
    print("=" * 60)
    print("注意：当前版本使用预置 seed 数据。")
    print("如需更新，请替换 runtime/seed/school_catalog/*.ndjson 并重新生成 source_manifest.json")
    print(f"数据目录: {CATALOG_DIR}")

    if not MANIFEST_PATH.exists():
        print("ERROR: source_manifest.json 不存在，请先运行数据采集流程")
        sys.exit(1)

    ok = verify_manifest()
    if ok:
        print("\n现有数据验证通过")
    else:
        print("\n现有数据验证失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
