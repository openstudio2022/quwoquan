import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// 组合根：按 [AppDataSourceMode] 在 Remote / Mock 实现间二选一（业务代码不分支）。
///
/// 需要 [Ref] 的仓库（如行为上报依赖其它 Provider）仍在 `app_providers.dart` 内组装，避免循环依赖。
T cloudRepositoryImplForMode<T>(
  AppDataSourceMode mode, {
  required T Function() remote,
  required T Function() mock,
}) =>
    mode == AppDataSourceMode.remote ? remote() : mock();
