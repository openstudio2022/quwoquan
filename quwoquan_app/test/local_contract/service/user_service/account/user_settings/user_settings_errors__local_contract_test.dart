import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.SETTING 用户设置错误码契约。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction/disruptionLevel 恢复语义,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 用户设置契约(USER.SETTING)', () {
    test('外观设置作用范围无效:400 surface', () {
      expect(
        UserErrorCode.fromCode('USER.SETTING.invalid_appearance_scope'),
        UserErrorCode.invalidAppearanceScope,
      );
      expect(UserErrorCode.invalidAppearanceScope.httpStatus, 400);
      expect(UserErrorCode.invalidAppearanceScope.recoveryAction, 'surface');
    });

    test('设置版本冲突:409 retry + silent,刷新后台重放即可恢复', () {
      expect(
        UserErrorCode.fromCode('USER.SETTING.settings_version_conflict'),
        UserErrorCode.settingsVersionConflict,
      );
      expect(UserErrorCode.settingsVersionConflict.httpStatus, 409);
      expect(UserErrorCode.settingsVersionConflict.recoveryAction, 'retry');
      expect(UserErrorCode.settingsVersionConflict.disruptionLevel, 'silent');
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.SETTING)', () {
    test('settings_version_conflict 响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.settingsVersionConflict.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.settingsVersionConflict.code,
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'user_settings',
          functionModule: 'user',
          userMessage: UserErrorCode.settingsVersionConflict.defaultMessageZh,
          recoveryAction: UserErrorCode.settingsVersionConflict.recoveryAction,
          disruptionLevel:
              UserErrorCode.settingsVersionConflict.disruptionLevel,
        ),
        requestPath: '/user/settings',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.settingsVersionConflict.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'retry');
      expect(recovery.disruptionLevel, 'silent');
    });
  });
}
