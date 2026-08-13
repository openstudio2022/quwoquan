# spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
SERVICE = ROOT / "quwoquan_service/services/content-service"
CONFIG_KEY = "sys.content-service.media_processing.hls_cmaf_enabled"


def test_hls_cmaf_rollout_defaults_off_in_all_four_environments() -> None:
    schema = yaml.safe_load((SERVICE / "config/schema.yaml").read_text(encoding="utf-8"))
    declaration = next(
        item for item in schema["configs"] if item.get("key") == CONFIG_KEY
    )
    assert declaration == {
        "key": CONFIG_KEY,
        "type": "bool",
        "scope": "workload",
        "reload": "restart",
        "rollout": "progressive",
        "sensitive": False,
        "default": False,
    }

    for environment in ("alpha", "beta", "gamma", "prod"):
        config = yaml.safe_load(
            (SERVICE / f"environments/{environment}/config.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert config.get("overrides", {}).get(CONFIG_KEY, False) is False


def test_app_hls_cmaf_feature_flag_is_runtime_overridable_and_off_by_default() -> None:
    ui_config = yaml.safe_load(
        (SERVICE / "contracts/content/post/ui_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    declaration = next(
        item
        for item in ui_config["feature_flags"]
        if item.get("flag") == "enable_hls_cmaf_abr"
    )
    assert declaration["default"] is False
    assert declaration["runtime_overridable"] is True
