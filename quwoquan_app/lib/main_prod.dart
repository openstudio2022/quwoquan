// 生产/发布用入口：不经由 lib/main.dart，强制云侧数据源且忽略切到 Mock 的写入。
// 推荐：flutter build ... -t lib/main_prod.dart --dart-define=APP_DATA_SOURCE=remote
import 'package:quwoquan_app/app_bootstrap.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

Future<void> main() async {
  await runQuwoquanApp(
    providerScopeOverrides: [
      appDataSourceModeProvider.overrideWith(_ProdLockedRemoteDataSource.new),
    ],
  );
}

/// Release/正式包：数据源恒为 Remote；非 remote 的 setMode 直接忽略（防误配）。
final class _ProdLockedRemoteDataSource extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.remote;

  @override
  void setMode(AppDataSourceMode mode) {
    if (mode == AppDataSourceMode.remote) {
      super.setMode(mode);
    }
  }
}
