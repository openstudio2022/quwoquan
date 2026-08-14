// trust_safety/post_moderation_case 对象 generated 错误码的端侧断言覆盖:
// moderation_case_not_found 的枚举解析、恢复语义(审核记录尚未生成属
// 可轮询的瞬态,声明为 retry)与 CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

void main() {
  group('ContentErrorCode — post_moderation_case 错误码契约', () {
    test('moderation_case_not_found 解析与恢复语义与声明一致', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.USER.moderation_case_not_found',
      );
      expect(parsed, ContentErrorCode.moderationCaseNotFound);
      expect(parsed.code, 'CONTENT.USER.moderation_case_not_found');
      expect(parsed.httpStatus, 404);
      // 与普通 not_found 不同:审核记录可能尚未生成,声明为 retry 以支持轮询。
      expect(parsed.recoveryAction, 'retry');
      expect(parsed.recoveryAfterSeconds, 0);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });
  });

  group('CloudErrorMapper — post_moderation_case 代表性映射负例', () {
    test('404 moderation_case_not_found → typed 解析 + retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        404,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.moderation_case_not_found',
          origin: 'user',
          kind: 'notFound',
          nature: 'transient',
          businessObject: 'post_moderation_case',
          functionModule: 'trust_safety',
          recoveryAction: 'retry',
          requestId: 'req-moderation-case-errors-1',
          traceId: 'trace-moderation-case-errors-1',
        ),
        requestPath: '/content/trust-safety/moderation-cases',
      );

      expect(exception.code, 'CONTENT.USER.moderation_case_not_found');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.moderationCaseNotFound,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.notFound);
      expect(exception.runtimeFailure.transportStatus, 404);
      expect(exception.runtimeFailure.recovery.action, 'retry');
    });
  });
}
