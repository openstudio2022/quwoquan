// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

void main() {
  test('首页服务访问失败文案共享标题但保留分因说明', () {
    final connection = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.connectionUnavailable,
    );
    final timeout = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.requestTimedOut,
    );
    final service = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.serviceUnavailable,
    );

    expect(connection.title, '暂时无法访问服务');
    expect(timeout.title, connection.title);
    expect(service.title, connection.title);
    expect(connection.message, '本次内容请求未能到达服务。');
    expect(timeout.message, '服务响应时间较长，这次请求已停止等待。');
    expect(service.message, '服务暂时没有完成这次内容请求。');
    expect({
      connection.message,
      timeout.message,
      service.message,
    }, hasLength(3));
  });

  test('全部恢复组不重复标题说明动作且不泄露品牌或技术字段', () {
    for (final group in AppUserRecoveryGroup.values) {
      final copy = AppUserRecoveryContract.copyFor(group, retryAfterSeconds: 3);
      final visible = '${copy.title}${copy.message}${copy.action.label}';
      expect(copy.title.trim(), isNot(copy.message.trim()), reason: group.name);
      expect(
        copy.title.trim(),
        isNot(copy.action.label.trim()),
        reason: group.name,
      );
      expect(
        visible,
        isNot(
          anyOf(
            contains('趣我圈'),
            contains('DNS'),
            contains('TLS'),
            contains('HTTP'),
          ),
        ),
        reason: group.name,
      );
    }
  });

  test('页面重试动作统一为重新加载且不提供次级圈子操作', () {
    for (final group in <AppUserRecoveryGroup>{
      AppUserRecoveryGroup.connectNetwork,
      AppUserRecoveryGroup.connectionUnavailable,
      AppUserRecoveryGroup.requestTimedOut,
      AppUserRecoveryGroup.serviceUnavailable,
      AppUserRecoveryGroup.invalidContent,
      AppUserRecoveryGroup.guestSessionUnavailable,
      AppUserRecoveryGroup.reloadLater,
    }) {
      final copy = AppUserRecoveryContract.copyFor(group);
      expect(copy.action.type, UiErrorActionType.retry, reason: group.name);
      expect(copy.action.label, SearchText.reload, reason: group.name);
    }
  });
}
