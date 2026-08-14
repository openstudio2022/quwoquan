/// NotificationErrorCode generated 错误码断言覆盖：
///
/// 1. wire code -> typed 枚举 + generated httpStatus 声明逐码锁定；
/// 2. 恢复语义按类别锁定——未登录/参数/幂等冲突类为 4xx 用户侧语义，
///    storage 写失败与 internal_error 为 5xx 系统语义（transient，可重试）；
/// 3. 代表码走 CloudErrorMapper canonical RuntimeErrorResponse 负例，锁定
///    typed domain code 解析与 recovery 指令透传。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/notification/notification_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

final class _NotificationErrorCodeCase {
  const _NotificationErrorCodeCase(this.wire, this.expected, this.httpStatus);

  final String wire;
  final NotificationErrorCode expected;
  final int httpStatus;
}

void main() {
  group('NotificationErrorCode 解码契约（generated 声明逐码锁定）', () {
    const cases = <_NotificationErrorCodeCase>[
      _NotificationErrorCodeCase(
        'NOTIFICATION.USER.unauthorized',
        NotificationErrorCode.unauthorized,
        401,
      ),
      _NotificationErrorCodeCase(
        'NOTIFICATION.USER.invalid_argument',
        NotificationErrorCode.invalidArgument,
        400,
      ),
      _NotificationErrorCodeCase(
        'NOTIFICATION.USER.idempotency_conflict',
        NotificationErrorCode.idempotencyConflict,
        409,
      ),
      _NotificationErrorCodeCase(
        'NOTIFICATION.SYSTEM.storage_write_failed',
        NotificationErrorCode.storageWriteFailed,
        500,
      ),
      _NotificationErrorCodeCase(
        'NOTIFICATION.SYSTEM.internal_error',
        NotificationErrorCode.internalError,
        500,
      ),
    ];

    for (final testCase in cases) {
      test('${testCase.wire} → ${testCase.expected.name} / '
          '${testCase.httpStatus}', () {
        final code = NotificationErrorCode.fromCode(testCase.wire);
        expect(code, testCase.expected);
        expect(code.httpStatus, testCase.httpStatus);
        expect(code.defaultMessage, isNotEmpty);
      });
    }

    test('未知码回退 unknown 兜底', () {
      expect(
        NotificationErrorCode.fromCode('NOTIFICATION.USER.__nonexistent__'),
        NotificationErrorCode.unknown,
      );
      expect(NotificationErrorCode.fromCode(''), NotificationErrorCode.unknown);
    });
  });

  group('NotificationErrorCode 恢复语义类别', () {
    test('未登录为 401 登录门语义，参数/幂等冲突为 400/409 校验语义', () {
      expect(NotificationErrorCode.unauthorized.httpStatus, 401);
      expect(NotificationErrorCode.unauthorized.defaultMessage, contains('登录'));
      expect(NotificationErrorCode.invalidArgument.httpStatus, 400);
      expect(NotificationErrorCode.idempotencyConflict.httpStatus, 409);
    });

    test('storage 写失败与 internal_error 为 500 系统语义（可重试）', () {
      const systemFailures = <NotificationErrorCode>[
        NotificationErrorCode.storageWriteFailed,
        NotificationErrorCode.internalError,
      ];
      for (final code in systemFailures) {
        expect(
          code.httpStatus,
          500,
          reason: '${code.name} 是系统侧失败，必须是 500',
        );
        expect(code.code, startsWith('NOTIFICATION.SYSTEM.'));
      }
    });
  });

  group('CloudErrorMapper canonical 负例', () {
    test('storage 写失败：typed domain code 解析 + retry 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        500,
        body: canonicalRuntimeErrorBody(
          code: NotificationErrorCode.storageWriteFailed.code,
          origin: 'system',
          kind: 'storage',
          nature: 'transient',
          businessObject: 'notification',
          functionModule: 'notification_delivery',
          requestId: 'req-notification-storage-write',
          traceId: 'trace-notification-storage-write',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 5,
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/notification/messages/read',
      );

      expect(exception.domainErrorCode?.domain, 'notification');
      expect(
        exception.domainErrorCode?.code,
        'NOTIFICATION.SYSTEM.storage_write_failed',
      );
      expect(
        exception.domainErrorCode?.value,
        NotificationErrorCode.storageWriteFailed,
      );
      expect(
        exception.runtimeFailure.code,
        NotificationErrorCode.storageWriteFailed.code,
      );
      // storage 写失败是 transient：wire 下发的 retry 指令必须被如实透传。
      expect(exception.runtimeFailure.recovery.isPresent, isTrue);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 5);
    });
  });
}
