# Content post `mock.yaml` 与 Flutter 测试目录对应

权威场景列表：`quwoquan_service/contracts/metadata/content/post/tests/mock.yaml`。

| mock.yaml 分层 | 实际测试根目录 |
|----------------|----------------|
| dto / error / behavior / ui_config 契约 | `quwoquan_app/test/cloud/content/**`、`test/ui/content/post/contract/**` |
| widget | `quwoquan_app/test/ui/content/**`、`test/ui/discovery/**` |
| journey | `quwoquan_app/test/ui/content/entry/journeys/**` |

门禁脚本（仅校验目录存在）：仓库根 `scripts/verify_content_post_mock_test_roots.py`。
