#!/usr/bin/env python3
"""打印单轨解析出的真实 Flutter SDK 可执行路径。

canonical launcher（run.sh）在 `QWQ_REAL_FLUTTER` 缺席时调用本入口补齐并
export，使 pub get、platform driver 与 Xcode backend 消费同一 SDK 事实；
解析规则唯一归属 `flutter_facade.resolve_real_flutter`，本文件不含逻辑。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flutter_facade import FacadeError, resolved_flutter_identity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("path", "json"), default="path")
    args = parser.parse_args(argv)
    try:
        identity = resolved_flutter_identity(dict(os.environ))
    except FacadeError as error:
        print(f"[flutter-facade] GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(identity, ensure_ascii=False, sort_keys=True))
    else:
        print(identity["executable"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
