/// ChatErrorCode generated 错误码断言覆盖：
///
/// 1. wire code -> typed 枚举 + generated httpStatus 声明逐码锁定；
/// 2. 恢复语义按类别锁定——群治理/关系门/撤回类 4xx 属用户侧 surface 语义
///    （重试不改变结果），绑定/投影类 SYSTEM/MIDDLEWARE 码 httpStatus 声明
///    为 0（非 HTTP 语义），恢复依赖 wire recovery 指令；
/// 3. 代表码走 CloudErrorMapper canonical RuntimeErrorResponse 负例，锁定
///    typed domain code 解析与 recovery 指令透传。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/chat/chat_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

final class _ChatErrorCodeCase {
  const _ChatErrorCodeCase(this.wire, this.expected, this.httpStatus);

  final String wire;
  final ChatErrorCode expected;
  final int httpStatus;
}

void main() {
  group('ChatErrorCode 解码契约（generated 声明逐码锁定）', () {
    const cases = <_ChatErrorCodeCase>[
      _ChatErrorCodeCase(
        'CHAT.USER.invalid_argument',
        ChatErrorCode.invalidArgument,
        400,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.source_managed_binding_write_forbidden',
        ChatErrorCode.sourceManagedBindingWriteForbidden,
        400,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.gathering_binding_conflict',
        ChatErrorCode.gatheringBindingConflict,
        409,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.message_recall_forbidden',
        ChatErrorCode.messageRecallForbidden,
        403,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.message_recall_expired',
        ChatErrorCode.messageRecallExpired,
        409,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.message_idempotency_conflict',
        ChatErrorCode.messageIdempotencyConflict,
        409,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.conversation_idempotency_conflict',
        ChatErrorCode.conversationIdempotencyConflict,
        409,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.message_too_long',
        ChatErrorCode.messageTooLong,
        400,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.message_invalid',
        ChatErrorCode.messageInvalid,
        400,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.message_media_invalid',
        ChatErrorCode.messageMediaInvalid,
        400,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.not_mutual',
        ChatErrorCode.notMutual,
        403,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.greeting_required',
        ChatErrorCode.greetingRequired,
        403,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.blocked',
        ChatErrorCode.blocked,
        403,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.group_governance_forbidden',
        ChatErrorCode.groupGovernanceForbidden,
        403,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.source_managed_conversation',
        ChatErrorCode.sourceManagedConversation,
        409,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.conversation_dissolved',
        ChatErrorCode.conversationDissolved,
        409,
      ),
      _ChatErrorCodeCase(
        'CHAT.USER.group_owner_must_transfer_before_leave',
        ChatErrorCode.groupOwnerMustTransferBeforeLeave,
        409,
      ),
      // 绑定/投影类码由 generated 文件声明 httpStatus = 0：它们不承载 HTTP
      // 语义，恢复动作只能来自 wire recovery 指令（见下方 mapper 负例）。
      _ChatErrorCodeCase(
        'CHAT.SYSTEM.circle_group_binding_conflict',
        ChatErrorCode.circleGroupBindingConflict,
        0,
      ),
      _ChatErrorCodeCase(
        'CHAT.MIDDLEWARE.conversation_projection_unavailable',
        ChatErrorCode.conversationProjectionUnavailable,
        0,
      ),
    ];

    for (final testCase in cases) {
      test('${testCase.wire} → ${testCase.expected.name} / '
          '${testCase.httpStatus}', () {
        final code = ChatErrorCode.fromCode(testCase.wire);
        expect(code, testCase.expected);
        expect(code.httpStatus, testCase.httpStatus);
        expect(code.defaultMessage, isNotEmpty);
      });
    }
  });

  group('ChatErrorCode 恢复语义类别', () {
    test('群治理/关系门/撤回/解散类为用户侧 4xx：surface 给用户，重试不改变结果', () {
      const userSurfaceLike = <ChatErrorCode>[
        ChatErrorCode.messageRecallForbidden,
        ChatErrorCode.messageRecallExpired,
        ChatErrorCode.groupGovernanceForbidden,
        ChatErrorCode.groupOwnerMustTransferBeforeLeave,
        ChatErrorCode.conversationDissolved,
        ChatErrorCode.sourceManagedConversation,
        ChatErrorCode.sourceManagedBindingWriteForbidden,
        ChatErrorCode.notMutual,
        ChatErrorCode.greetingRequired,
        ChatErrorCode.blocked,
      ];
      for (final code in userSurfaceLike) {
        expect(
          code.httpStatus,
          inInclusiveRange(400, 499),
          reason: '${code.name} 是用户侧终态拒绝，必须是 4xx 而非可重试的 5xx',
        );
        expect(code.code, startsWith('CHAT.USER.'));
      }
    });

    test('参数与幂等冲突类为 400/409 校验语义', () {
      expect(ChatErrorCode.invalidArgument.httpStatus, 400);
      expect(ChatErrorCode.messageMediaInvalid.httpStatus, 400);
      expect(ChatErrorCode.messageTooLong.httpStatus, 400);
      expect(ChatErrorCode.messageInvalid.httpStatus, 400);
      expect(ChatErrorCode.conversationIdempotencyConflict.httpStatus, 409);
      expect(ChatErrorCode.messageIdempotencyConflict.httpStatus, 409);
      expect(ChatErrorCode.gatheringBindingConflict.httpStatus, 409);
    });

    test('绑定/投影类 SYSTEM/MIDDLEWARE 码不承载 HTTP 语义（httpStatus = 0）', () {
      expect(ChatErrorCode.circleGroupBindingConflict.httpStatus, 0);
      expect(ChatErrorCode.conversationProjectionUnavailable.httpStatus, 0);
    });
  });

  group('CloudErrorMapper canonical 负例', () {
    test('撤回过期：typed domain code 解析 + surface 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        409,
        body: canonicalRuntimeErrorBody(
          code: ChatErrorCode.messageRecallExpired.code,
          origin: 'user',
          kind: 'validation',
          nature: 'permanent',
          businessObject: 'message',
          functionModule: 'chat',
          userMessage: '消息已超过可撤回时间',
          requestId: 'req-chat-recall-expired',
          traceId: 'trace-chat-recall-expired',
          recoveryAction: 'surface',
          disruptionLevel: 'inlineCard',
        ),
        requestPath: '/chat/messages/recall',
      );

      expect(exception.domainErrorCode?.domain, 'chat');
      expect(
        exception.domainErrorCode?.code,
        'CHAT.USER.message_recall_expired',
      );
      expect(
        exception.domainErrorCode?.value,
        ChatErrorCode.messageRecallExpired,
      );
      expect(exception.runtimeFailure.code, ChatErrorCode.messageRecallExpired.code);
      // 撤回过期是用户侧终态：恢复语义必须是 surface（告知用户），不得改写成 retry。
      expect(exception.runtimeFailure.recovery.isPresent, isTrue);
      expect(exception.runtimeFailure.recovery.action, 'surface');
      expect(exception.userMessage, '消息已超过可撤回时间');
    });

    test('会话投影不可用：typed domain code 解析 + retry 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        503,
        body: canonicalRuntimeErrorBody(
          code: ChatErrorCode.conversationProjectionUnavailable.code,
          origin: 'middleware',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'conversation',
          functionModule: 'chat',
          requestId: 'req-chat-projection',
          traceId: 'trace-chat-projection',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 5,
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/chat/conversations',
      );

      expect(exception.domainErrorCode?.domain, 'chat');
      expect(
        exception.domainErrorCode?.value,
        ChatErrorCode.conversationProjectionUnavailable,
      );
      expect(
        exception.runtimeFailure.code,
        'CHAT.MIDDLEWARE.conversation_projection_unavailable',
      );
      // 投影暂不可用是 transient：wire 下发的 retry 指令必须被如实透传。
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 5);
    });
  });
}
