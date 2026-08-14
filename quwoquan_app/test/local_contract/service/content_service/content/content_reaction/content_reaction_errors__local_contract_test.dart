// content_reaction 对象 generated 错误码的端侧断言覆盖:
// content_reaction_target_not_found 的枚举解析、恢复语义与
// CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

void main() {
  group('ContentErrorCode — content_reaction 错误码契约', () {
    test('content_reaction_target_not_found 解析与恢复语义与声明一致', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.USER.content_reaction_target_not_found',
      );
      expect(parsed, ContentErrorCode.contentReactionTargetNotFound);
      expect(parsed.code, 'CONTENT.USER.content_reaction_target_not_found');
      expect(parsed.httpStatus, 404);
      // 互动目标已失效属终态,提示用户而非自动重试。
      expect(parsed.recoveryAction, 'surface');
      expect(parsed.recoveryAfterSeconds, 0);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });
  });

  group('CloudErrorMapper — content_reaction 代表性映射负例', () {
    test('404 content_reaction_target_not_found → typed 解析 + surface 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        404,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.content_reaction_target_not_found',
          origin: 'user',
          kind: 'notFound',
          nature: 'permanent',
          businessObject: 'content_reaction',
          functionModule: 'content',
          recoveryAction: 'surface',
          requestId: 'req-reaction-errors-1',
          traceId: 'trace-reaction-errors-1',
        ),
        requestPath: '/content/reactions',
      );

      expect(
        exception.code,
        'CONTENT.USER.content_reaction_target_not_found',
      );
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.contentReactionTargetNotFound,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.notFound);
      expect(exception.runtimeFailure.transportStatus, 404);
      expect(exception.runtimeFailure.recovery.action, 'surface');
    });
  });
}
