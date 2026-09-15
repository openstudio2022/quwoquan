# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t5
"""真实 yt-dlp 离线元数据输出；不以网络或模拟退出码代替条数边界验证。"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_single_metadata_output_is_not_aborted_by_limit(tmp_path, monkeypatch):
    executable = shutil.which("yt-dlp")
    if executable is None:
        pytest.skip("真实离线命令验证需要本机 yt-dlp")
    skill = Path(__file__).resolve().parents[4] / ".agents/skills/content-production"
    monkeypatch.syspath_prepend(str(skill / "scripts"))
    spec = importlib.util.spec_from_file_location("bounded_ytdlp_inputs", skill / "scripts/inputs.py")
    inputs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inputs)
    monkeypatch.setitem(sys.modules, "inputs", inputs)
    parser = inputs.load("video", "youtube")
    metadata = {"id": "offline-one", "title": "Offline one", "extractor": "Generic",
                "extractor_key": "Generic", "webpage_url": "https://example.invalid/watch/one",
                "url": "https://example.invalid/media.mp4", "ext": "mp4", "format_id": "one",
                "duration": 1}
    source = tmp_path / "info.json"
    source.write_text(json.dumps(metadata), encoding="utf-8")
    run = subprocess.run

    def run_from_local_info(command, **kwargs):
        assert command[-2] == "--" and "--skip-download" in command and "--no-playlist" in command
        return run([executable, *command[1:-2], "--load-info-json", str(source)], **kwargs)

    monkeypatch.setattr(parser.client.subprocess, "run", run_from_local_info)
    transport = type("OfflineTransport", (), {"user_agent": "QuWoQuan offline contract test"})()
    body = parser.fetch({"url": "https://www.youtube.com/watch?v=offline", "mode": "single", "limit": 1}, transport)
    payload = json.loads(body)
    assert payload["id"] == "offline-one" and payload["duration"] == 1
