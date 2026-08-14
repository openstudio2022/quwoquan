// comment 对象 generated 错误码的端侧断言覆盖:
// 每个 wire 码必须解析到正确的 ContentErrorCode 常量,且 httpStatus /
// recoveryAction / recoveryAfterSeconds 与 codegen 声明一致;
// 并以一个代表性码走 CloudErrorMapper 映射负例,验证 typed
// domainErrorCode 与结构化恢复语义贯通。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

typedef _DeclaredCase = ({
  String wire,
  ContentErrorCode value,
  String recoveryAction,
  int recoveryAfterSeconds,
  int httpStatus,
});

void main() {
  const declared = <_DeclaredCase>[
    (
      wire: 'CONTENT.USER.comment_forbidden_delete',
      value: ContentErrorCode.commentForbiddenDelete,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 403,
    ),
    (
      wire: 'CONTENT.USER.comment_pin_forbidden',
      value: ContentErrorCode.commentPinForbidden,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 403,
    ),
    (
      wire: 'CONTENT.USER.comment_pin_invalid_target',
      value: ContentErrorCode.commentPinInvalidTarget,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.comment_parent_invalid',
      value: ContentErrorCode.commentParentInvalid,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.USER.comment_too_long',
      value: ContentErrorCode.commentTooLong,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.comment_attachment_limit_exceeded',
      value: ContentErrorCode.commentAttachmentLimitExceeded,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.comment_attachment_not_ready',
      value: ContentErrorCode.commentAttachmentNotReady,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 3,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.comment_moderation_forbidden',
      value: ContentErrorCode.commentModerationForbidden,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 403,
    ),
    (
      wire: 'CONTENT.USER.comment_status_transition_invalid',
      value: ContentErrorCode.commentStatusTransitionInvalid,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.USER.comment_sort_invalid',
      value: ContentErrorCode.commentSortInvalid,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
  ];

  group('ContentErrorCode — comment 错误码契约', () {
    for (final entry in declared) {
      test('${entry.wire} 解析与恢复语义与声明一致', () {
        final parsed = ContentErrorCode.fromCode(entry.wire);
        expect(parsed, entry.value);
        expect(parsed.code, entry.wire);
        expect(parsed.httpStatus, entry.httpStatus);
        expect(parsed.recoveryAction, entry.recoveryAction);
        expect(parsed.recoveryAfterSeconds, entry.recoveryAfterSeconds);
        expect(ContentErrorMessages.zh[parsed], isNotEmpty);
        expect(ContentErrorMessages.en[parsed], isNotEmpty);
      });
    }

    test('恢复语义横向不变量:403 surface、409 冲突为 retry/surface 之一', () {
      for (final entry in declared) {
        if (entry.httpStatus == 403) {
          expect(
            entry.value.recoveryAction,
            'surface',
            reason: '${entry.wire}: 权限类错误应 surface 而非静默重试',
          );
        }
        if (entry.httpStatus == 409) {
          expect(
            <String>{'retry', 'surface'},
            contains(entry.value.recoveryAction),
            reason: '${entry.wire}: 冲突类错误恢复动作必须是 retry 或 surface',
          );
        }
      }
    });
  });

  group('CloudErrorMapper — comment 代表性映射负例', () {
    test('409 comment_status_transition_invalid → typed 解析 + retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        409,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.comment_status_transition_invalid',
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'comment',
          functionModule: 'content',
          recoveryAction: 'retry',
          requestId: 'req-comment-errors-1',
          traceId: 'trace-comment-errors-1',
        ),
        requestPath: '/content/comments/moderate',
      );

      expect(exception.code, 'CONTENT.USER.comment_status_transition_invalid');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.commentStatusTransitionInvalid,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.validation);
      expect(exception.runtimeFailure.transportStatus, 409);
      expect(exception.runtimeFailure.recovery.action, 'retry');
    });
  });
}
