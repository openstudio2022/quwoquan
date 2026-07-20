#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "[verify] engineering directory"

ruby -ryaml -e '
  root = Dir.pwd
  manifest_file = File.join(root, "specs/engineering_directory_manifest.yaml")
  abort("[verify] FAIL: missing specs/engineering_directory_manifest.yaml") unless File.exist?(manifest_file)

  m = YAML.load_file(manifest_file) || {}

  (m["required_directories"] || []).each do |d|
    path = File.join(root, d)
    abort("[verify] FAIL: missing required directory: #{d}") unless Dir.exist?(path)
  end

  (m["required_files"] || []).each do |f|
    path = File.join(root, f)
    abort("[verify] FAIL: missing required file: #{f}") unless File.file?(path)
  end

  puts "[verify] OK: engineering directory validated"
'

python3 - <<'PY'
from __future__ import annotations

import subprocess
from pathlib import Path

root = Path.cwd()
service_root = root / "quwoquan_service"
magic = (
    b"\x7fELF",
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"MZ",
)
violations: list[str] = []
tracked = subprocess.run(
    ["git", "ls-files", "-z", "quwoquan_service"],
    cwd=root,
    check=True,
    capture_output=True,
).stdout
for raw in tracked.split(b"\0"):
    if not raw:
        continue
    path = root / raw.decode("utf-8")
    if not path.exists():
        continue
    if path.suffix == ".test":
        violations.append(f"tracked service test binary: {path.relative_to(root)}")
        continue
    try:
        prefix = path.read_bytes()[:4]
    except OSError:
        continue
    if any(prefix.startswith(signature) for signature in magic):
        violations.append(f"tracked service executable binary: {path.relative_to(root)}")

if service_root.is_dir():
    for path in service_root.iterdir():
        if path.is_file() and (path.name == "api" or path.suffix == ".test"):
            violations.append(f"service root build output: {path.relative_to(root)}")

if violations:
    print("[verify] FAIL: tracked service build artifacts detected")
    for violation in violations:
        print(f"  - {violation}")
    raise SystemExit(1)
print("[verify] OK: no tracked service build artifacts")
PY
