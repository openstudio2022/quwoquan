import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';

void main() {
  group('CustomizableChatInputBar', () {
    testWidgets('输入文本后通过发送按钮提交 payload', (tester) async {
      ChatInputSubmitPayload? submitted;

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onSend: (payload) async {
                  submitted = payload;
                },
              ),
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

    testWidgets('emoji 与更多面板按微信式互斥切换', (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onSend: (_) async {},
                showEmojiButton: true,
                onPickImages: (_) async => const <ChatInputAttachment>[],
                onPickFiles: (_) async => const <ChatInputAttachment>[],
                onCapturePhoto: () async => null,
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byKey(TestKeys.chatInputEmojiToggleButton));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byType(UnifiedEmojiPicker), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.chatInputMoreButton));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byType(UnifiedEmojiPicker), findsNothing);
      expect(find.text(UITextConstants.chatMorePhoto), findsOneWidget);
      expect(find.text(UITextConstants.chatMoreShoot), findsOneWidget);
      expect(find.text(UITextConstants.chatMoreFile), findsOneWidget);
    });

    testWidgets('超过五行后出现展开入口', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.binding.setSurfaceSize(const Size(800, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final longText = List<String>.filled(7, '这是较长的一行输入内容').join('\n');

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                controller: controller,
                textFieldKey: const ValueKey<String>('inline_field'),
                onSend: (_) async {},
                showEmojiButton: true,
              ),
            ),
          ),
        ),
      );

      await tester.enterText(find.byKey(const ValueKey<String>('inline_field')), longText);
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.byKey(TestKeys.chatInputExpandButton), findsOneWidget);
    });

    testWidgets('语音模式切换后左侧按钮变为键盘', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onSend: (_) async {},
              ),
            ),
          ),
        ),
      );

      expect(find.byIcon(CupertinoIcons.waveform), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.chatInputVoiceToggleButton));
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.byIcon(CupertinoIcons.keyboard), findsOneWidget);
      expect(find.text(UITextConstants.chatVoiceHoldToTalk), findsOneWidget);
    });
  });
}
