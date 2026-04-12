# `test/cloud/services/` — 与 `lib/cloud/services/` 路径镜像

迁移 `Mock*Repository` 时，在此目录下保持与 `lib` **相同的相对路径**（例如 `circle/circle_repository_mock.dart`），便于对照与 code review。

当前实现仍在 `lib/`；[`repository_mock_reexports.dart`](repository_mock_reexports.dart) 统一从 `package:quwoquan_app/...` 再导出，供测试逐步改用短 import。
