// original_access_quota 对象 generated 错误码的端侧断言覆盖:
// original_access_denied / original_access_rate_limited 的枚举解析、
// 恢复语义(429 限流类必须 retry 且带退避)与 CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

void main() {
  group('ContentErrorCode — original_access_quota 错误码契约', () {
    test('original_access_denied 解析与恢复语义与声明一致', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.USER.original_access_denied',
      );
      expect(parsed, ContentErrorCode.originalAccessDenied);
      expect(parsed.httpStatus, 403);
      // 内容不支持原图访问属权限终态,提示用户而非自动重试。
      expect(parsed.recoveryAction, 'surface');
      expect(parsed.recoveryAfterSeconds, 0);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });

    test('original_access_rate_limited 解析与恢复语义与声明一致', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.USER.original_access_rate_limited',
      );
      expect(parsed, ContentErrorCode.originalAccessRateLimited);
      expect(parsed.httpStatus, 429);
      // 429 限流类必须 retry 且带正退避秒数。
      expect(parsed.recoveryAction, 'retry');
      expect(parsed.recoveryAfterSeconds, greaterThan(0));
      expect(parsed.recoveryAfterSeconds, 60);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });
  });

  group('CloudErrorMapper — original_access_quota 代表性映射负例', () {
    test('429 original_access_rate_limited → typed 解析 + 带退避的 retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        429,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.original_access_rate_limited',
          origin: 'user',
          kind: 'rateLimited',
          nature: 'transient',
          businessObject: 'original_access_quota',
          functionModule: 'content',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 60,
          requestId: 'req-original-access-errors-1',
          traceId: 'trace-original-access-errors-1',
        ),
        requestPath: '/content/media/original',
      );

      expect(exception.code, 'CONTENT.USER.original_access_rate_limited');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.originalAccessRateLimited,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.rateLimited);
      expect(exception.runtimeFailure.transportStatus, 429);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 60);
    });
  });
}
