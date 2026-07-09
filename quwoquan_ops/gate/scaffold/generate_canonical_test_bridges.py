#!/usr/bin/env python3
"""Generate canonical three-layer test bridges across App/Service/Data/Ops."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from test_directory_inventory_lib import (
    APP_BRIDGE_HEADER,
    GENERATED_BRIDGE_HEADER,
    PAGE_INVENTORY_PATH,
    ROOT,
    build_inventory,
    go_suite_names,
    page_wrapper_target_path,
)


def rel_posix(from_path: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, start=from_path).replace(os.sep, "/")


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def build_dart_wrapper(target_path: Path, source_paths: list[Path], *, generated_header: str) -> str:
    imports: list[str] = []
    main_calls: list[str] = []
    for index, source_path in enumerate(source_paths):
        rel_import = rel_posix(target_path.parent, source_path)
        alias = f"source_{index}"
        imports.append(f"import '{rel_import}' as {alias};")
        main_calls.append(f"  {alias}.main();")
    return (
        generated_header
        + "\n"
        + "\n".join(imports)
        + "\n\n"
        + "void main() {\n"
        + "\n".join(main_calls)
        + "\n}\n"
    )


def build_python_wrapper(target_path: Path, source_path: Path) -> str:
    rel_source = rel_posix(target_path.parent, source_path)
    return f"""# {GENERATED_BRIDGE_HEADER}
from __future__ import annotations

import importlib.util
from pathlib import Path

_SOURCE = (Path(__file__).resolve().parent / "{rel_source}").resolve()
_SPEC = importlib.util.spec_from_file_location("source_test_module", _SOURCE)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - generation/runtime guard
    raise RuntimeError(f"unable to load source test module: {{_SOURCE}}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name, _value in vars(_MODULE).items():
    if _name.startswith("__") and _name not in {{"__doc__", "__all__"}}:
        continue
    globals()[_name] = _value
"""


def camel_case(value: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", value) if part)


def build_go_bridge(target_path: Path, source_path: Path, layer: str) -> str:
    tests, benches = go_suite_names(source_path)
    rel_pkg = rel_posix(target_path.parent, source_path.parent)
    if not rel_pkg.startswith("."):
        rel_pkg = f"./{rel_pkg}"
    target_name = camel_case(target_path.stem)
    test_regex = "^$"
    if tests:
        test_regex = "^(" + "|".join(tests) + ")$"
    bench_arg = ""
    if benches:
        bench_arg = '\n\t\t"-bench",\n\t\t"^(' + "|".join(benches) + ')$",'
    return f"""// {GENERATED_BRIDGE_HEADER}
package {layer}

import (
\t"os"
\t"os/exec"
\t"path/filepath"
\t"runtime"
\t"testing"
)

func Test{target_name}(t *testing.T) {{
\texists := func(path string) bool {{
\t\tinfo, err := os.Stat(path)
\t\treturn err == nil && info.IsDir()
\t}}
\trepoRoot := func() string {{
\t\t_, filename, _, ok := runtime.Caller(0)
\t\tif !ok {{
\t\t\tt.Fatal("cannot resolve bridge file path")
\t\t}}
\t\tfor dir := filepath.Dir(filename); ; dir = filepath.Dir(dir) {{
\t\t\tif exists(filepath.Join(dir, "quwoquan_service")) && exists(filepath.Join(dir, "quwoquan_ops")) {{
\t\t\t\treturn dir
\t\t\t}}
\t\t\tparent := filepath.Dir(dir)
\t\t\tif parent == dir {{
\t\t\t\tt.Fatal("cannot locate quwoquan repo root")
\t\t\t}}
\t\t}}
\t\treturn ""
\t}}
\tcmd := exec.Command(
\t\t"go",
\t\t"test",
\t\t"{rel_pkg}",
\t\t"-run",
\t\t"{test_regex}",{bench_arg}
\t\t"-count=1",
\t)
\tcmd.Env = append(os.Environ(), "QWQ_OUTPUT_ROOT="+filepath.Join(repoRoot(), ".qwq_output"))
\toutput, err := cmd.CombinedOutput()
\tif err != nil {{
\t\tt.Fatalf("source bridge failed for {source_path.relative_to(ROOT).as_posix()}: %v\\n%s", err, output)
\t}}
}}
"""


def generate_inventory_bridges() -> dict[str, int]:
    counts = {"app": 0, "service": 0, "data": 0, "quwoquan_ops": 0}
    inventory = build_inventory()
    for area_name, area in (inventory.get("areas") or {}).items():
        if not isinstance(area, dict):
            continue
        for entry in area.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            current_path = ROOT / str(entry["current_path"])
            target_path = ROOT / str(entry["target_path"])
            layer = str(entry["layer"])
            if target_path.suffix == ".dart":
                content = build_dart_wrapper(target_path, [current_path], generated_header=APP_BRIDGE_HEADER)
            elif target_path.suffix == ".py":
                content = build_python_wrapper(target_path, current_path)
            elif target_path.suffix == ".go":
                content = build_go_bridge(target_path, current_path, layer)
            else:  # pragma: no cover - defensive
                continue
            if write_if_changed(target_path, content):
                counts[str(area_name)] += 1
    return counts


def generate_page_wrappers() -> int:
    if not PAGE_INVENTORY_PATH.exists():
        return 0
    data = yaml.safe_load(PAGE_INVENTORY_PATH.read_text(encoding="utf-8")) or {}
    written = 0
    for surface in data.get("surfaces", []):
        if not isinstance(surface, dict):
            continue
        owner = str(surface.get("owner") or "").strip()
        surface_id = str(surface.get("surface_id") or "").strip()
        source_tests = surface.get("source_tests") or []
        if not owner or not surface_id or not isinstance(source_tests, list) or not source_tests:
            continue
        target_path = ROOT / page_wrapper_target_path(owner, surface_id)
        source_paths = [ROOT / str(path) for path in source_tests]
        content = build_dart_wrapper(
            target_path,
            source_paths,
            generated_header=f"// {GENERATED_BRIDGE_HEADER}\n",
        )
        if write_if_changed(target_path, content):
            written += 1
    return written


def main() -> int:
    bridge_counts = generate_inventory_bridges()
    page_count = generate_page_wrappers()
    print(
        "[bridge] app={app} service={service} data={data} quwoquan_ops={quwoquan_ops} page_wrappers={page}".format(
            page=page_count,
            **bridge_counts,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
