import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
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

    testWidgets('群聊输入区可插入 @小趣 上下文 mention', (tester) async {
      final controller = TextEditingController();
      const sendButtonKey = ValueKey<String>('send_button');
      ChatInputSubmitPayload? submitted;
      addTearDown(controller.dispose);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                controller: controller,
                onSend: (payload) async => submitted = payload,
                sendButtonKey: sendButtonKey,
                showXiaoquMentionButton: true,
              ),
            ),
          ),
        ),
      );

      expect(find.byKey(TestKeys.chatInputAtXiaoquButton), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.chatInputAtXiaoquButton));
      await tester.pump();

      expect(controller.text, startsWith('@小趣 '));
      await tester.tap(find.byKey(sendButtonKey));
      await tester.pump();

      expect(submitted?.mentions, contains('assistant'));
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

      await tester.enterText(
        find.byKey(const ValueKey<String>('inline_field')),
        longText,
      );
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.byKey(TestKeys.chatInputExpandButton), findsOneWidget);
    });

    testWidgets('语音入口默认关闭，启用后左侧按钮可切换键盘', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(onSend: (_) async {}),
            ),
          ),
        ),
      );

      expect(find.byKey(TestKeys.chatInputVoiceToggleButton), findsNothing);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onSend: (_) async {},
                enableVoiceInput: true,
              ),
            ),
          ),
        ),
      );

      expect(find.byIcon(CupertinoIcons.mic), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.chatInputVoiceToggleButton));
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.byIcon(Icons.keyboard_outlined), findsOneWidget);
      expect(find.text(UITextConstants.chatVoiceHoldToTalk), findsOneWidget);
    });

    testWidgets('语音按住松手只交给录音回调，不产生文本 payload', (tester) async {
      var startCount = 0;
      var stopCount = 0;
      var sendCount = 0;

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onRequestMicPermission: () async => true,
                onStartRecord: () async {
                  startCount++;
                  return true;
                },
                onStopRecord: (_) async => stopCount++,
                onSend: (_) async {
                  sendCount++;
                },
                enableVoiceInput: true,
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byKey(TestKeys.chatInputVoiceToggleButton));
      await tester.pump();
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.chatInputVoiceHoldButton)),
      );
      await tester.pump();
      expect(find.byKey(TestKeys.chatInputVoiceRecordHud), findsOneWidget);

      await gesture.up();
      await tester.pump();

      expect(startCount, 1);
      expect(stopCount, 1);
      expect(sendCount, 0);
    });

    testWidgets('语音录制 HUD 显示录音计时', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onRequestMicPermission: () async => true,
                onStartRecord: () async => true,
                onStopRecord: (_) async {},
                onSend: (_) async {},
                enableVoiceInput: true,
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byKey(TestKeys.chatInputVoiceToggleButton));
      await tester.pump();
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.chatInputVoiceHoldButton)),
      );
      await tester.pump(const Duration(seconds: 2));

      expect(
        find.textContaining(UITextConstants.chatVoiceRecording),
        findsOneWidget,
      );

      await gesture.up();
      await tester.pump();
    });

    testWidgets('语音上滑取消不会提交 payload', (tester) async {
      var cancelCount = 0;
      var sendCount = 0;

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onRequestMicPermission: () async => true,
                onCancelRecord: () async => cancelCount++,
                onSend: (_) async {
                  sendCount++;
                },
                enableVoiceInput: true,
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byKey(TestKeys.chatInputVoiceToggleButton));
      await tester.pump();
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.chatInputVoiceHoldButton)),
      );
      await tester.pump();
      await gesture.moveBy(Offset(0, -AppSpacing.buttonHeight * 2));
      await tester.pump();
      expect(find.text(UITextConstants.chatVoiceReleaseCancel), findsWidgets);

      await gesture.up();
      await tester.pump();

      expect(cancelCount, 1);
      expect(sendCount, 0);
    });

    testWidgets('语音录制 HUD 消费真实振幅流渲染时间序列波形', (tester) async {
      final amplitudes = StreamController<List<double>>.broadcast();
      addTearDown(amplitudes.close);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onRequestMicPermission: () async => true,
                onStartRecord: () async => true,
                onStopRecord: (_) async {},
                voiceAmplitudeStream: amplitudes.stream,
                onSend: (_) async {},
                enableVoiceInput: true,
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byKey(TestKeys.chatInputVoiceToggleButton));
      await tester.pump();
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.chatInputVoiceHoldButton)),
      );
      await tester.pump();

      amplitudes.add(const <double>[-60, -30, -6]);
      await tester.pump(const Duration(milliseconds: 80));

      expect(find.byKey(TestKeys.chatInputVoiceRecordHud), findsOneWidget);
      expect(find.byKey(TestKeys.chatInputVoiceWaveform), findsWidgets);

      await gesture.up();
      await tester.pump();
    });

    testWidgets('compact 宽度下群聊输入栏不挤出 overflow', (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 680));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onSend: (_) async {},
                showEmojiButton: true,
                showXiaoquMentionButton: true,
              ),
            ),
          ),
        ),
      );

      await tester.pump();

      expect(tester.takeException(), isNull);
      expect(find.byKey(TestKeys.chatInputAtXiaoquButton), findsNothing);
      expect(find.byKey(TestKeys.chatInputEmojiToggleButton), findsOneWidget);
      expect(find.byKey(TestKeys.chatInputMoreButton), findsOneWidget);
    });

    testWidgets('默认单行输入槽保持统一高度，多行输入可自然撑高', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                controller: controller,
                textFieldKey: const ValueKey<String>('single_line_field'),
                onSend: (_) async {},
              ),
            ),
          ),
        ),
      );

      final fieldFinder = find.byKey(
        const ValueKey<String>('single_line_field'),
      );
      final singleLineHeight = tester.getSize(fieldFinder).height;
      expect(
        singleLineHeight,
        lessThanOrEqualTo(AppSpacing.commentInputHeight + 1),
      );

      await tester.enterText(fieldFinder, '第一行\n第二行\n第三行');
      await tester.pump();

      final multiLineHeight = tester.getSize(fieldFinder).height;
      expect(multiLineHeight, greaterThan(singleLineHeight));
    });
  });
}
