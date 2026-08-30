from __future__ import annotations

import json
from pathlib import Path


def write_valid_web_artifact(path: Path) -> None:
    path.mkdir()
    (path / "index.html").write_text(
        '<html lang="zh-CN"><head><meta charset="utf-8"></head></html>',
        encoding="utf-8",
    )
    (path / "main.dart.js").write_text("main();", encoding="utf-8")
    (path / "flutter_service_worker.js").write_text("worker();", encoding="utf-8")
    (path / "qwq_bootstrap.css").write_text(":root{}", encoding="utf-8")
    (path / "qwq_bootstrap.js").write_text("bootstrap();", encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps({"display": "standalone", "start_url": "/", "scope": "/"}),
        encoding="utf-8",
    )
    fonts = path / "assets"
    font = fonts / "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf"
    font.parent.mkdir(parents=True)
    font.write_bytes(b"font")
    (fonts / "FontManifest.json").write_text(
        json.dumps(
            [
                {
                    "family": "Noto Sans SC",
                    "fonts": [
                        {"asset": "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf"}
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
