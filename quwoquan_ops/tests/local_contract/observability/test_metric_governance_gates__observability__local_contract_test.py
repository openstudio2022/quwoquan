"""指标治理三门禁的判定契约。

被测对象：
- quwoquan_ops/gate/verify_metric_threshold_homology.py（注册表阈值 ↔ 告警定义同源）
- quwoquan_ops/gate/verify_prometheus_scrape_homology.py（scrape target ↔ deploy 拓扑同源）
- quwoquan_ops/gate/verify_grafana_dashboard_lint.py（bare model / uid 层级 / expr 非空 / 必备看板）

锁住每个门禁「仓库现状必须过、注入漂移必须拦」，防止判定被放宽成恒真。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load(name: str):
    path = REPO_ROOT / f"quwoquan_ops/gate/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


threshold_gate = _load("verify_metric_threshold_homology")
scrape_gate = _load("verify_prometheus_scrape_homology")
dashboard_gate = _load("verify_grafana_dashboard_lint")


# ── 阈值同源 ────────────────────────────────────────────────


def test_threshold_gate_passes_repository_state():
    assert threshold_gate.main() == 0


def test_threshold_gate_blocks_catalog_threshold_drift(monkeypatch, tmp_path):
    original = threshold_gate.GOLDEN_METRIC_CATALOG.read_text(encoding="utf-8")
    drifted = original.replace("threshold: 0.0047", "threshold: 0.0099")
    assert drifted != original
    catalog = tmp_path / "golden_metric_catalog.yaml"
    catalog.write_text(drifted, encoding="utf-8")
    monkeypatch.setattr(threshold_gate, "GOLDEN_METRIC_CATALOG", catalog)
    assert threshold_gate.main() == 1


def test_threshold_gate_blocks_unknown_alert_binding(monkeypatch, tmp_path):
    original = threshold_gate.GOLDEN_METRIC_CATALOG.read_text(encoding="utf-8")
    drifted = original.replace(
        "alert_name: AppANREventRateHigh", "alert_name: AppANREventRateGhost"
    )
    catalog = tmp_path / "golden_metric_catalog.yaml"
    catalog.write_text(drifted, encoding="utf-8")
    monkeypatch.setattr(threshold_gate, "GOLDEN_METRIC_CATALOG", catalog)
    assert threshold_gate.main() == 1


def test_es_sample_guard_clauses_are_excluded_from_thresholds():
    document = {
        "spec": {
            "alerts": [
                {
                    "name": "sample-alert",
                    "condition": "sampleCount >= 100 AND p95Ms > 3000",
                }
            ]
        }
    }
    thresholds = threshold_gate._elasticsearch_alert_thresholds(document)
    # 样本量门槛 100 不得被当作业务阈值。
    assert thresholds["sample-alert"] == {3000.0}


# ── scrape 同源 ────────────────────────────────────────────


def test_scrape_gate_passes_repository_state():
    assert scrape_gate.main() == 0


def test_scrape_gate_blocks_missing_service_target(monkeypatch, tmp_path):
    config = yaml.safe_load(
        scrape_gate.PROMETHEUS_CONFIG.read_text(encoding="utf-8")
    )
    for job in config.get("scrape_configs", []):
        for static in job.get("static_configs", []):
            static["targets"] = [
                target for target in static.get("targets", [])
                if not str(target).startswith("api-edge:")
            ]
    drifted = tmp_path / "prometheus.yml"
    drifted.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(scrape_gate, "PROMETHEUS_CONFIG", drifted)
    assert scrape_gate.main() == 1


def test_scrape_gate_ignores_blackbox_probe_urls():
    targets = scrape_gate.prometheus_targets()
    assert "https" not in targets, "probe URL 不得进入 host:port 同源集合"
    assert "api-edge" in targets


# ── dashboard lint ─────────────────────────────────────────


def test_dashboard_lint_passes_repository_state():
    assert dashboard_gate.main() == 0


def _copy_dashboards(tmp_path: Path) -> Path:
    root = tmp_path / "dashboards"
    root.mkdir()
    for source in dashboard_gate.DASHBOARDS_ROOT.glob("*.json"):
        (root / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return root


def test_dashboard_lint_blocks_wrapped_api_payload(monkeypatch, tmp_path):
    root = _copy_dashboards(tmp_path)
    wrapped = root / "l3_error_governance.json"
    model = json.loads(wrapped.read_text(encoding="utf-8"))
    wrapped.write_text(json.dumps({"dashboard": model}), encoding="utf-8")
    monkeypatch.setattr(dashboard_gate, "DASHBOARDS_ROOT", root)
    assert dashboard_gate.main() == 1


def test_dashboard_lint_blocks_missing_spec_required_dashboard(monkeypatch, tmp_path):
    root = _copy_dashboards(tmp_path)
    (root / "l2_content_flywheel.json").unlink()
    monkeypatch.setattr(dashboard_gate, "DASHBOARDS_ROOT", root)
    assert dashboard_gate.main() == 1


def test_dashboard_lint_blocks_empty_panel_expression(monkeypatch, tmp_path):
    root = _copy_dashboards(tmp_path)
    target = root / "l3_error_governance.json"
    model = json.loads(target.read_text(encoding="utf-8"))
    model["panels"][0]["targets"][0]["expr"] = "  "
    target.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(dashboard_gate, "DASHBOARDS_ROOT", root)
    assert dashboard_gate.main() == 1


def test_dashboard_lint_blocks_level_mismatch_between_file_and_uid(monkeypatch, tmp_path):
    root = _copy_dashboards(tmp_path)
    source = root / "l3_error_governance.json"
    model = json.loads(source.read_text(encoding="utf-8"))
    (root / "l2_error_governance_misfiled.json").write_text(
        json.dumps(model, ensure_ascii=False), encoding="utf-8"
    )
    source.unlink()
    monkeypatch.setattr(dashboard_gate, "DASHBOARDS_ROOT", root)
    assert dashboard_gate.main() == 1
