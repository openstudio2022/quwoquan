import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';

void main() {
  group('聊天语音失败 UX — 单一载体 contract', () {
    test('chat_conversation_page 不调用 _showVoiceSendFailure modal', () {
      final source = File(
        'lib/ui/chat/pages/chat_conversation_page.dart',
      ).readAsStringSync();
      expect(source, isNot(contains('_showVoiceSendFailure')));
    });

    test('失败 status bar 使用 chatVoicePendingRetry 与 retry 按钮', () {
      final source = File(
        'lib/ui/chat/pages/chat_conversation_page.dart',
      ).readAsStringSync();
      expect(source, contains('ChatText.chatVoicePendingRetry'));
      expect(source, contains('UITextConstants.retry'));
      expect(source, contains('chatSendOutboxProvider'));
      final failedBarSection = source.split('_buildVoiceSendStatusBar').last;
      expect(failedBarSection, isNot(contains('UITextConstants.gotIt')));
    });
  });

  group('文案 — chatVoicePendingRetry', () {
    test('用户向失败文案已登记', () {
      expect(ChatText.chatVoicePendingRetry, contains('重试'));
      expect(ChatText.chatVoicePendingRetry, isNotEmpty);
    });
  });
}
