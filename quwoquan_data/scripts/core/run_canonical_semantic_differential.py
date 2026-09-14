from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from core.canonical_semantic_markdown import (
    parse_canonical_markdown,
    safe_projection,
    serialize_envelope,
)


def run_differential(source: Path, output_root: Path) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[3]
    source = source.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    envelope = json.loads(source.read_text())
    outputs = {"python": serialize_envelope(envelope).encode()}
    env = {**os.environ, "PATH": "/Users/zhaoyuxi/Workspace/flutter/bin:" + os.environ.get("PATH", "")}
    commands = {
        "go": ["go", "run", "./services/content-service/internal/content/post/application/cmd/canonicalcodec", str(source)],
        "typescript": ["node", "tests/canonical-codec-runner.mjs", str(source)],
        "dart": ["dart", "run", "--verbosity=error", "test/support/canonical_semantic_markdown_runner.dart", str(source)],
    }
    working_dirs = {
        "go": repo_root / "quwoquan_service",
        "typescript": repo_root / "quwoquan_data/control_plane/content_workbench/portal",
        "dart": repo_root / "quwoquan_app",
    }
    subprocess.run(["npx", "tsc", "-p", "tsconfig.test.json"], cwd=working_dirs["typescript"], check=True, env=env)
    for language, command in commands.items():
        try:
            outputs[language] = subprocess.run(command, cwd=working_dirs[language], check=True, env=env, stdout=subprocess.PIPE, timeout=150).stdout
        except subprocess.TimeoutExpired as exc:
            raise SystemExit(f"{language} runner timeout after 150s") from exc
    expected = outputs["python"]
    rows = []
    for language, data in outputs.items():
        (output_root / f"{language}.page.md").write_bytes(data)
        rows.append({"language": language, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "matchesPython": data == expected})
        if data != expected:
            raise SystemExit(f"differential mismatch: {language}")
        if parse_canonical_markdown(data.decode()) != envelope:
            raise SystemExit(f"payload mismatch: {language}")
    safe = {"python": safe_projection(envelope).encode()}
    for language in ("go", "typescript", "dart"):
        safe[language] = subprocess.run(commands[language] + ["safe"], cwd=working_dirs[language], check=True, env=env, stdout=subprocess.PIPE, timeout=150).stdout
    for language, data in safe.items():
        (output_root / f"{language}.safe-projection.json").write_bytes(data)
        if data != safe["python"]:
            raise SystemExit(f"safe projection mismatch: {language}")
    evidence = {
        "schema": "canonical_semantic_cross_language_differential.v1",
        "source": str(source),
        "allMarkdownBytesEqual": True,
        "normalizedPayloadEqual": True,
        "allSafeProjectionBytesEqual": True,
        "safeProjectionSha256": hashlib.sha256(safe["python"]).hexdigest(),
        "languages": rows,
    }
    raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (output_root / f"cross-language-differential.sha256-{digest}.json").write_bytes(raw + b"\n")
    return evidence
