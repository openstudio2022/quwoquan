import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/app_localizations_zh.dart';

/// L1a 契约测试（过渡保留）：content 领域 location 集成所需的 l10n key 存在且非空
///
/// 规范：specs/ux/error-and-permission-semantics.md §5.3
/// 注：纯 l10n key 存在性测试价值低，将由 L1b 交互测试覆盖。本文件过渡保留，待 L1b
/// location_selector_page_widget_test 实现后可删除。
/// 领域：content，集成：location（content 使用的 location）
void main() {
  late AppLocalizationsZh l10n;

  setUpAll(() {
    l10n = AppLocalizationsZh();
  });

  group('ErrorPermissionL10n — 常规契约', () {
    test('l10n_keys_exist_for_error_permission_semantics', () {
      expect(l10n.loadFailed, isNotEmpty, reason: 'loadFailed 必须存在');
      expect(l10n.locationLoadFailed, isNotEmpty, reason: 'locationLoadFailed 必须存在');
      expect(l10n.locationPermissionRequired, isNotEmpty,
          reason: 'locationPermissionRequired 必须存在');
      expect(l10n.locationAppPermissionRequired, isNotEmpty,
          reason: 'locationAppPermissionRequired 必须存在');
      expect(l10n.locationOpenSettings, isNotEmpty,
          reason: 'locationOpenSettings 必须存在');
      expect(l10n.locationUpstreamTimeout, isNotEmpty,
          reason: 'locationUpstreamTimeout 必须存在');
      expect(l10n.locationInternalError, isNotEmpty,
          reason: 'locationInternalError 必须存在');
      expect(l10n.locationFetchingResult, isNotEmpty,
          reason: 'locationFetchingResult 必须存在');
    });
  });

  group('ErrorPermissionL10n — 兼容性契约', () {
    test('location keys match integration errors.yaml semantics', () {
      // integration/location/errors.yaml 文案约定
      expect(l10n.locationPermissionRequired, contains('权限'),
          reason: 'location_permission_required 语义');
      expect(
        l10n.locationLoadFailed,
        anyOf(contains('位置'), contains('重试')),
        reason: 'location_unavailable 语义',
      );
    });
  });
}
