// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-007
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';

String _chatConversationSource() => <String>[
  'lib/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart',
  'lib/service/chat_service/chat/conversation/presentation/chat_conversation_page_actions.dart',
].map((path) => File(path).readAsStringSync()).join('\n');

void main() {
  group('聊天语音失败 UX — 单一载体 contract', () {
    test('chat_conversation_page 不调用 _showVoiceSendFailure modal', () {
      final source = _chatConversationSource();
      expect(source, isNot(contains('_showVoiceSendFailure')));
    });

    test('失败 status bar 使用 chatVoicePendingRetry 与 retry 按钮', () {
      final source = _chatConversationSource();
      expect(source, contains('ChatText.chatVoicePendingRetry'));
      expect(source, contains('FoundationText.retry'));
      // 失败态与重试仍然只由发送 outbox 这一个载体驱动；页面读队列长度、点重试触发
      // 同一个 outbox 的 drain，不得自建第二条重发通道。
      expect(source, contains('chatSendOutboxQueueLengthProvider'));
      expect(source, contains('chatSendOutboxControlProvider'));
      expect(source, contains('.drain()'));
      final failedBarSection = source.split('_buildVoiceSendStatusBar').last;
      expect(failedBarSection, isNot(contains('ContentText.gotIt')));
    });

    test('modal 与 status bar 不同时出现：失败呈现链路零 dialog 载体', () {
      // GWT-007：语音发送失败只允许 status bar 单一低打扰载体。
      // 页面与发送状态机内不得存在任何 dialog/modal 呈现入口，从源头排除
      // 「modal + status bar 同屏」的可能。
      final voiceSendSource = File(
        'lib/service/chat_service/chat/message/application/voice_send_provider.dart',
      ).readAsStringSync();
      expect(voiceSendSource, isNot(contains('AppActionErrorFeedback')));
      expect(voiceSendSource, isNot(contains('showAppCupertinoDialog')));
      expect(voiceSendSource, isNot(contains('CupertinoAlertDialog')));

      final conversationSource = _chatConversationSource();
      final voiceSections = conversationSource
          .split('\n')
          .where((line) => line.toLowerCase().contains('voice'))
          .join('\n');
      expect(voiceSections, isNot(contains('AppActionErrorFeedback')));
      expect(voiceSections, isNot(contains('showAppCupertinoDialog')));
    });

    test('语音失败 modal 死文案已删除，不再提供第二载体入口', () {
      final copySource = File(
        'lib/l10n/copy/chat_text_constants.dart',
      ).readAsStringSync();
      expect(copySource, isNot(contains('chatVoiceSendFailedTitle')));
      expect(copySource, isNot(contains('chatVoiceSendFailed ')));
    });
  });

  group('文案 — chatVoicePendingRetry', () {
    test('用户向失败文案已登记', () {
      expect(ChatText.chatVoicePendingRetry, contains('重试'));
      expect(ChatText.chatVoicePendingRetry, isNotEmpty);
    });
  });
}
