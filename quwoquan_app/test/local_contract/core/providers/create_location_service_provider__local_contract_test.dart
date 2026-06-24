import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';

/// 回归守卫：createLocationServiceProvider 必须随 appDataSourceModeProvider 切换实现，
/// 杜绝「附近地点访问失败」断点（mock 环境误走 Remote → 命中网关/定位失败整页错误）。
///
/// 规范：specs/ux/error-and-permission-semantics.md、.cursor/rules/08-mock-data-isolation.mdc
void main() {
  test('mock 模式返回 MockCreateLocationService（不发 HTTP / 不依赖系统定位）', () {
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(
          () => _FixedModeNotifier(AppDataSourceMode.mock),
        ),
      ],
    );
    addTearDown(container.dispose);

    final service = container.read(createLocationServiceProvider);
    expect(service, isA<MockCreateLocationService>());
  });

  test('remote 模式返回 RemoteCreateLocationService', () {
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(
          () => _FixedModeNotifier(AppDataSourceMode.remote),
        ),
      ],
    );
    addTearDown(container.dispose);

    final service = container.read(createLocationServiceProvider);
    expect(service, isA<RemoteCreateLocationService>());
  });

  test('mock 模式下 nearby 始终有 POI，永不触发附近地点访问失败', () async {
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(
          () => _FixedModeNotifier(AppDataSourceMode.mock),
        ),
      ],
    );
    addTearDown(container.dispose);

    final service = container.read(createLocationServiceProvider);
    final nearby = await service.nearby();
    expect(nearby, isNotEmpty);
  });
}

class _FixedModeNotifier extends AppDataSourceModeNotifier {
  _FixedModeNotifier(this.mode);

  final AppDataSourceMode mode;

  @override
  AppDataSourceMode build() => mode;
}
