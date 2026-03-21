import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

void main() {
  group('CustomizableChatInputBar', () {
    testWidgets('输入文本后通过发送按钮提交 payload', (tester) async {
      ChatInputSubmitPayload? submitted;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CustomizableChatInputBar(
              onSend: (payload) async {
                submitted = payload;
              },
            ),
          ),
        ),
      );

      await tester.enterText(find.byType(TextField), '你好，小趣');
      await tester.pump();

      expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);

      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pump();

      expect(submitted, isNotNull);
      expect(submitted!.text, '你好，小趣');
      expect(submitted!.isVoiceMessage, isFalse);
      expect(submitted!.attachments, isEmpty);
    });

    testWidgets('展开更多操作后展示共享能力入口', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CustomizableChatInputBar(
              onSend: (_) async {},
              onPickImages: (_) async => const <ChatInputAttachment>[],
              onPickFiles: (_) async => const <ChatInputAttachment>[],
              onCapturePhoto: () async => null,
              extraPanelItems: <ChatInputExtraPanelItem>[
                ChatInputExtraPanelItem(
                  icon: Icons.video_call_outlined,
                  text: UITextConstants.chatMoreAudioVideo,
                  onTap: () async {},
                ),
              ],
            ),
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.add));
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text(UITextConstants.chatMorePhoto), findsOneWidget);
      expect(find.text(UITextConstants.chatMoreShoot), findsOneWidget);
      expect(find.text(UITextConstants.chatMoreFile), findsOneWidget);
      expect(find.text(UITextConstants.chatMoreAudioVideo), findsOneWidget);
    });
  });
}
