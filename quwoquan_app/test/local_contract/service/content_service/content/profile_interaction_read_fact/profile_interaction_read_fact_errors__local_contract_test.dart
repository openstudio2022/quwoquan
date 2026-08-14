// profile_interaction_read_fact 对象 generated 错误码的端侧断言覆盖:
// owner_forbidden / target_unavailable 的枚举解析、恢复语义与
// CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

void main() {
  group('ContentErrorCode — profile_interaction_read_fact 错误码契约', () {
    test('profile_interaction_read_fact_owner_forbidden 解析与恢复语义', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.USER.profile_interaction_read_fact_owner_forbidden',
      );
      expect(
        parsed,
        ContentErrorCode.profileInteractionReadFactOwnerForbidden,
      );
      expect(parsed.httpStatus, 403);
      // 越权更新他人互动记录属权限终态,提示用户而非自动重试。
      expect(parsed.recoveryAction, 'surface');
      expect(parsed.recoveryAfterSeconds, 0);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });

    test('profile_interaction_read_fact_target_unavailable 解析与恢复语义', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.SYSTEM.profile_interaction_read_fact_target_unavailable',
      );
      expect(
        parsed,
        ContentErrorCode.profileInteractionReadFactTargetUnavailable,
      );
      expect(parsed.httpStatus, 503);
      // 系统侧读模型暂不可用属瞬态,必须 retry 且带退避。
      expect(parsed.recoveryAction, 'retry');
      expect(parsed.recoveryAfterSeconds, greaterThan(0));
      expect(parsed.recoveryAfterSeconds, 3);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });
  });

  group('CloudErrorMapper — profile_interaction_read_fact 代表性映射负例', () {
    test('503 target_unavailable → typed 解析 + 带退避的 retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        503,
        body: canonicalRuntimeErrorBody(
          code:
              'CONTENT.SYSTEM.profile_interaction_read_fact_target_unavailable',
          origin: 'system',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'profile_interaction_read_fact',
          functionModule: 'content',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 3,
          requestId: 'req-read-fact-errors-1',
          traceId: 'trace-read-fact-errors-1',
        ),
        requestPath: '/content/profile-interactions/read-facts',
      );

      expect(
        exception.code,
        'CONTENT.SYSTEM.profile_interaction_read_fact_target_unavailable',
      );
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.profileInteractionReadFactTargetUnavailable,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.unavailable);
      expect(exception.runtimeFailure.transportStatus, 503);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 3);
    });
  });
}
