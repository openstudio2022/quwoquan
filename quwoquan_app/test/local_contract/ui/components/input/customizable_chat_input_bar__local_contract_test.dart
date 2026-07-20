import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/input/chat_mention_text_editing_controller.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/platform/app_font_families.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/test_keys.dart';

void main() {
  const inputBarFiles = <String>[
    'lib/components/input/customizable_chat_input_bar.dart',
    'lib/components/input/customizable_chat_input_bar_attachments.part.dart',
    'lib/components/input/customizable_chat_input_bar_composer.part.dart',
    'lib/components/input/customizable_chat_input_bar_layout.part.dart',
    'lib/components/input/customizable_chat_input_bar_voice.part.dart',
  ];

  test('输入栏按职责拆分且保持单一 State 与回调真相源', () {
    final sources = <String, String>{
      for (final path in inputBarFiles) path: _readAppFile(path),
    };

    for (final entry in sources.entries) {
      final lineCount = const LineSplitter().convert(entry.value).length;
      expect(
        lineCount,
        lessThan(1000),
        reason: '${entry.key} 有 $lineCount 行，必须继续按职责拆分',
      );
    }

    final mainSource = sources[inputBarFiles.first]!;
    for (final partPath in inputBarFiles.skip(1)) {
      final partName = partPath.split('/').last;
      expect(mainSource, contains("part '$partName';"));
      expect(
        sources[partPath],
        contains("part of 'customizable_chat_input_bar.dart';"),
      );
    }

    final combined = sources.values.join('\n');
    expect(
      RegExp(
        r'class\s+_CustomizableChatInputBarState\s+extends\s+State<CustomizableChatInputBar>',
      ).allMatches(combined),
      hasLength(1),
    );
    for (final callbackPattern in <String>[
      r'Future<void>\s+_addAttachments\s*\(',
      r'Future<void>\s+_send\s*\(',
      r'Future<void>\s+_startVoiceRecord\s*\(',
      r'Widget\s+_buildInputBar\s*\(',
    ]) {
      expect(
        RegExp(callbackPattern).allMatches(combined),
        hasLength(1),
        reason: '$callbackPattern 必须只存在于对应职责 part',
      );
    }
  });

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
      expect(find.text(ChatText.chatMorePhoto), findsOneWidget);
      expect(find.text(ChatText.chatMoreShoot), findsOneWidget);
      expect(find.text(ChatText.chatMoreFile), findsOneWidget);
    });

    testWidgets('emoji 面板 glyph 使用 emoji-capable fallback 字体栈', (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onSend: (_) async {},
                showEmojiButton: true,
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byKey(TestKeys.chatInputEmojiToggleButton));
      await tester.pump(const Duration(milliseconds: 300));

      final emojiGlyph = tester
          .widgetList<Text>(
            find.descendant(
              of: find.byType(UnifiedEmojiPicker),
              matching: find.byType(Text),
            ),
          )
          .firstWhere(
            (widget) =>
                widget.style?.fontSize ==
                SettingsSemanticConstants.emojiIconFontSize,
          );
      expect(
        emojiGlyph.style?.fontFamilyFallback,
        contains(BundledFontFamilies.notoColorEmoji),
      );
    });

    testWidgets('群聊输入区可插入 @小趣 上下文 mention', (tester) async {
      final controller = ChatMentionTextEditingController();
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

    testWidgets('输入 @ 后选择成员，正文与稳定 userId 原子提交', (tester) async {
      final controller = ChatMentionTextEditingController();
      ChatInputSubmitPayload? submitted;
      addTearDown(controller.dispose);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                controller: controller,
                onMentionRequested: (_) async =>
                    const ChatInputMentionCandidate(
                      id: 'user_zhang',
                      displayName: '张三',
                    ),
                onSend: (payload) async => submitted = payload,
              ),
            ),
          ),
        ),
      );

      await tester.enterText(find.byType(TextField), '@');
      await tester.pumpAndSettle();

      expect(controller.text, '@张三 ');
      expect(controller.activeMentionIds, <String>['user_zhang']);
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pump();
      expect(submitted?.text, '@张三');
      expect(submitted?.mentions, <String>['user_zhang']);
    });

    testWidgets('删除完整提及 token 后不再发送隐形 mention', (tester) async {
      final controller = ChatMentionTextEditingController();
      ChatInputSubmitPayload? submitted;
      addTearDown(controller.dispose);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                controller: controller,
                onMentionRequested: (_) async =>
                    const ChatInputMentionCandidate(
                      id: 'user_zhang',
                      displayName: '张三',
                    ),
                onSend: (payload) async => submitted = payload,
              ),
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(TextField), '@');
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '普通内容');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pump();

      expect(submitted?.text, '普通内容');
      expect(submitted?.mentions, isEmpty);
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
      expect(find.text(ChatText.chatVoiceHoldToTalk), findsOneWidget);
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

      expect(find.textContaining(ChatText.chatVoiceRecording), findsOneWidget);

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
      expect(find.text(ChatText.chatVoiceReleaseCancel), findsWidgets);

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

    testWidgets('compact 宽度下语音按住录音不产生 overflow', (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 680));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: CustomizableChatInputBar(
                onRequestMicPermission: () async => true,
                onStartRecord: () async => true,
                onStopRecord: (_) async {},
                onSend: (_) async {},
                showEmojiButton: true,
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

      expect(tester.takeException(), isNull);
      expect(find.byKey(TestKeys.chatInputVoiceRecordHud), findsOneWidget);
      expect(find.byKey(TestKeys.chatInputVoiceWaveform), findsOneWidget);

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

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
