import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.DEVICE_PUSH 设备推送通道错误码契约。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction/disruptionLevel 恢复语义,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 推送注册参数契约(USER.DEVICE_PUSH)', () {
    test('推送通道类型无效:400 surface', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.invalid_endpoint_kind'),
        UserErrorCode.devicePushInvalidEndpointKind,
      );
      expect(UserErrorCode.devicePushInvalidEndpointKind.httpStatus, 400);
      expect(
        UserErrorCode.devicePushInvalidEndpointKind.recoveryAction,
        'surface',
      );
    });

    test('推送凭证无效:400 surface,引导重新授权通知', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.invalid_token'),
        UserErrorCode.devicePushInvalidToken,
      );
      expect(UserErrorCode.devicePushInvalidToken.httpStatus, 400);
      expect(UserErrorCode.devicePushInvalidToken.recoveryAction, 'surface');
    });

    test('推送失效原因无效:400,后台链路 absorb + silent 不打扰用户', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.invalid_invalidation_reason'),
        UserErrorCode.devicePushInvalidInvalidationReason,
      );
      expect(
        UserErrorCode.devicePushInvalidInvalidationReason.httpStatus,
        400,
      );
      expect(
        UserErrorCode.devicePushInvalidInvalidationReason.recoveryAction,
        'absorb',
      );
      expect(
        UserErrorCode.devicePushInvalidInvalidationReason.disruptionLevel,
        'silent',
      );
    });
  });

  group('UserErrorCode — 推送通道状态契约(USER.DEVICE_PUSH)', () {
    test('通道不存在:404 absorb + silent,静默吸收不打扰用户', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.endpoint_not_found'),
        UserErrorCode.devicePushEndpointNotFound,
      );
      expect(UserErrorCode.devicePushEndpointNotFound.httpStatus, 404);
      expect(
        UserErrorCode.devicePushEndpointNotFound.recoveryAction,
        'absorb',
      );
      expect(
        UserErrorCode.devicePushEndpointNotFound.disruptionLevel,
        'silent',
      );
    });

    test('通道已失效:409 absorb + silent', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.endpoint_not_active'),
        UserErrorCode.devicePushEndpointNotActive,
      );
      expect(UserErrorCode.devicePushEndpointNotActive.httpStatus, 409);
      expect(
        UserErrorCode.devicePushEndpointNotActive.recoveryAction,
        'absorb',
      );
      expect(
        UserErrorCode.devicePushEndpointNotActive.disruptionLevel,
        'silent',
      );
    });

    test('凭证被其他设备占用:409 冲突,可刷新后 retry', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.token_conflict'),
        UserErrorCode.devicePushTokenConflict,
      );
      expect(UserErrorCode.devicePushTokenConflict.httpStatus, 409);
      expect(UserErrorCode.devicePushTokenConflict.recoveryAction, 'retry');
    });

    test('推送状态版本冲突:409 retry + silent,后台自动重试', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.version_conflict'),
        UserErrorCode.devicePushVersionConflict,
      );
      expect(UserErrorCode.devicePushVersionConflict.httpStatus, 409);
      expect(UserErrorCode.devicePushVersionConflict.recoveryAction, 'retry');
      expect(
        UserErrorCode.devicePushVersionConflict.disruptionLevel,
        'silent',
      );
    });

    test('推送凭证加密处理失败:500 retry', () {
      expect(
        UserErrorCode.fromCode('USER.DEVICE_PUSH.crypto_failure'),
        UserErrorCode.devicePushCryptoFailure,
      );
      expect(UserErrorCode.devicePushCryptoFailure.httpStatus, 500);
      expect(UserErrorCode.devicePushCryptoFailure.recoveryAction, 'retry');
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.DEVICE_PUSH)', () {
    test('version_conflict 响应解析为 typed user 域错误并保留静默重试语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.devicePushVersionConflict.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.devicePushVersionConflict.code,
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'device_push_endpoint',
          functionModule: 'user',
          userMessage: UserErrorCode.devicePushVersionConflict.defaultMessageZh,
          recoveryAction:
              UserErrorCode.devicePushVersionConflict.recoveryAction,
          disruptionLevel:
              UserErrorCode.devicePushVersionConflict.disruptionLevel,
        ),
        requestPath: '/user/device-push/endpoints',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.devicePushVersionConflict.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'retry');
      expect(recovery.disruptionLevel, 'silent');
    });
  });
}
