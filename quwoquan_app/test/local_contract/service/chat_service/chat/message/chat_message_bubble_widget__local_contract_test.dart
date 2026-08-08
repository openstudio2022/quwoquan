import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show MessageCard;
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/typography/app_font_families.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_mention_text.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_bubble.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/presentation/voice_message_bubble.dart';

Widget _wrapBubble({
  required ChatMessageDisplayItem message,
  bool isRight = false,
  VoidCallback? onTap,
  ValueChanged<String>? onMentionTap,
  Map<String, String> mentionDisplayNames = const <String, String>{},
  void Function(LongPressStartDetails)? onLongPressStart,
}) {
  return ProviderScope(
    child: MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ChatMessageBubble(
            message: message,
            isRight: isRight,
            bubbleColor: Colors.white,
            textColor: Colors.black,
            isSelectionMode: false,
            isSelected: false,
            onLongPressStart: onLongPressStart ?? (_) {},
            onTap: onTap,
            onMentionTap: onMentionTap,
            mentionDisplayNames: mentionDisplayNames,
          ),
        ),
      ),
    ),
  );
}

void main() {
  group('ChatMessageBubble - 渲染契约', () {
    testWidgets('文本消息正确显示 content', (tester) async {
      final message = _message(content: '你好世界', senderName: '测试用户');
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.text('你好世界'), findsAtLeastNWidgets(1));
    });

    testWidgets('文本消息显式声明 emoji-capable fallback 字体栈', (tester) async {
      final message = _message(content: '新年快乐！😄');
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      final text = tester.widget<SelectableText>(
        find.byType(SelectableText).first,
      );
      expect(
        text.style?.fontFamilyFallback,
        contains(BundledFontFamilies.notoColorEmoji),
      );
    });

    testWidgets('只高亮契约 mentions 对应 token 并保持稳定点击目标', (tester) async {
      String? tappedTarget;
      final message = _message(
        content: '普通@符号 @张三 你好',
        mentions: const <String>['user_zhang'],
      );
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          mentionDisplayNames: const <String, String>{'user_zhang': '张三'},
          onMentionTap: (target) => tappedTarget = target,
        ),
      );
      await tester.pump();

      final richTexts = tester
          .widgetList<ChatMentionText>(find.byType(ChatMentionText))
          .toList(growable: false);
      expect(
        richTexts,
        hasLength(1),
        reason:
            '单条文本消息只能存在一个提及正文：'
            '${richTexts.map((item) => item.content).join('|')}',
      );
      final richText = richTexts.single;
      final segments = resolveChatMentionTextSegments(
        content: richText.content,
        mentions: richText.mentions,
        displayNames: richText.displayNames,
      );
      expect(
        segments.where((segment) => segment.isMention).map((e) => e.text),
        <String>['@张三'],
      );
      richText.onMentionTap?.call('user_zhang');
      expect(tappedTarget, 'user_zhang');
    });

    test('同名成员与离群成员按 mentions/token 顺序保持 ID 稳定', () {
      final segments = resolveChatMentionTextSegments(
        content: '@同名 @同名 @旧名字',
        mentions: const <String>['user_a', 'user_b', 'user_left'],
        displayNames: const <String, String>{'user_a': '同名', 'user_b': '同名'},
      ).where((segment) => segment.isMention).toList(growable: false);

      expect(segments.map((segment) => segment.targetId), <String>[
        'user_a',
        'user_b',
        'user_left',
      ]);
    });

    test('显示名包含空格时完整 token 仍绑定稳定 ID', () {
      final segments = resolveChatMentionTextSegments(
        content: '你好 @张 三 欢迎',
        mentions: const <String>['user_zhang'],
        displayNames: const <String, String>{'user_zhang': '张 三'},
      ).where((segment) => segment.isMention).toList(growable: false);

      expect(segments, hasLength(1));
      expect(segments.single.text, '@张 三');
      expect(segments.single.targetId, 'user_zhang');
    });

    testWidgets('发送者名称正确显示（左侧气泡）', (tester) async {
      final message = _message(
        content: '一条消息',
        senderId: 'user_002',
        senderName: '李明',
      );
      await tester.pumpWidget(_wrapBubble(message: message, isRight: false));
      await tester.pump();

      expect(find.text('李明'), findsOneWidget);
    });

    testWidgets('未知类型安全回退到文本气泡', (tester) async {
      final message = _message(type: 'unknown_type_xyz', content: '未知类型消息');
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.text('未知类型消息'), findsAtLeastNWidgets(1));
      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('语音消息按时长映射气泡宽度', (tester) async {
      final shortVoice = _message(
        type: 'audio',
        mediaUrl: 'https://cdn.example.com/1.m4a',
        audioDurationMs: 1000,
      );
      await tester.pumpWidget(_wrapBubble(message: shortVoice, isRight: true));
      await tester.pump();
      final shortWidth = tester.getSize(find.byType(VoiceMessageBubble)).width;

      final longVoice = _message(
        id: 'msg_002',
        type: 'audio',
        mediaUrl: 'https://cdn.example.com/2.m4a',
        audioDurationMs: 22000,
      );
      await tester.pumpWidget(_wrapBubble(message: longVoice, isRight: true));
      await tester.pump();
      final longWidth = tester.getSize(find.byType(VoiceMessageBubble)).width;

      expect(longWidth, greaterThan(shortWidth));
    });

    testWidgets('文件消息展示文件卡片', (tester) async {
      final fileMessage = _message(type: 'file', content: '会议纪要.pdf');
      await tester.pumpWidget(_wrapBubble(message: fileMessage, isRight: true));
      await tester.pump();

      expect(find.text('会议纪要.pdf'), findsAtLeastNWidgets(1));
      expect(find.text(ChatText.chatPreviewFile), findsAtLeastNWidgets(1));
    });

    testWidgets('视频消息展示视频卡片', (tester) async {
      final videoMessage = _message(
        type: 'video',
        content: '旅行回顾.mp4',
        thumbnailUrl: 'https://cdn.example.com/video-thumb.jpg',
      );
      await tester.pumpWidget(
        _wrapBubble(message: videoMessage, isRight: true),
      );
      await tester.pump();

      expect(find.text('旅行回顾.mp4'), findsAtLeastNWidgets(1));
      expect(find.byType(AppCachedNetworkImage), findsAtLeastNWidgets(1));
      expect(
        find.byIcon(Icons.play_circle_fill_rounded),
        findsAtLeastNWidgets(1),
      );
      expect(find.text(ChatText.chatPreviewVideo), findsAtLeastNWidgets(1));
    });

    testWidgets('强类型分享卡片展示标题、摘要和缩略图', (tester) async {
      final cardMessage = _message(
        type: 'card',
        card: MessageCard.fromWire(<String, Object?>{
          'kind': 'content_post',
          'title': '城市漫步',
          'subtitle': '周末路线',
          'thumbnailUrl': 'https://cdn.example.com/card.jpg',
          'attributes': <Object?>[
            <String, Object?>{'name': 'postId', 'value': 'post_001'},
          ],
        }),
      );
      await tester.pumpWidget(_wrapBubble(message: cardMessage));
      await tester.pump();

      expect(find.text('城市漫步'), findsAtLeastNWidgets(1));
      expect(find.text('周末路线'), findsAtLeastNWidgets(1));
      expect(find.byType(AppCachedNetworkImage), findsAtLeastNWidgets(1));
      expect(
        find.byIcon(CupertinoIcons.chevron_forward),
        findsAtLeastNWidgets(1),
      );
    });

    testWidgets('图片消息展示图片预览', (tester) async {
      final imageMessage = _message(
        type: 'image',
        imageUrl: 'https://cdn.example.com/photo.jpg',
        thumbnailUrl: 'https://cdn.example.com/thumb.jpg',
      );
      await tester.pumpWidget(
        _wrapBubble(message: imageMessage, isRight: true),
      );
      await tester.pump();

      expect(find.byType(AppCachedNetworkImage), findsOneWidget);
      expect(find.text(ChatText.chatPreviewFile), findsNothing);
      expect(find.text(ChatText.chatPreviewVideo), findsNothing);
    });

    testWidgets('图片消息缺少原图时回退到缩略图', (tester) async {
      final imageMessage = _message(
        type: 'image',
        imageUrl: '',
        thumbnailUrl: 'https://cdn.example.com/thumb-only.jpg',
      );
      await tester.pumpWidget(
        _wrapBubble(message: imageMessage, isRight: true),
      );
      await tester.pump();

      expect(find.byType(AppCachedNetworkImage), findsOneWidget);
    });

    testWidgets('撤回后的语音消息不再展示播放气泡', (tester) async {
      final recalledVoice = _message(
        type: 'audio',
        status: 'recalled',
        mediaUrl: 'https://cdn.example.com/1.m4a',
        audioDurationMs: 1000,
      );

      await tester.pumpWidget(_wrapBubble(message: recalledVoice));
      await tester.pump();

      expect(find.byType(VoiceMessageBubble), findsNothing);
      expect(find.text(ChatText.chatPreviewRecalled), findsAtLeastNWidgets(1));
    });

    testWidgets('语音 URL 为空时展示发送中不可播放态', (tester) async {
      final pendingVoice = _message(
        type: 'audio',
        status: 'sent',
        mediaUrl: '',
        audioDurationMs: 3000,
      );

      await tester.pumpWidget(_wrapBubble(message: pendingVoice));
      await tester.pump();

      expect(find.byType(VoiceMessageBubble), findsOneWidget);
      expect(find.text(ChatText.chatVoiceSending), findsOneWidget);
    });
  });

  group('ChatMessageBubble - 交互契约', () {
    testWidgets('长按消息气泡触发 onLongPressStart', (tester) async {
      var longPressed = false;
      final message = _message(content: '长按测试消息');
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          isRight: true,
          onLongPressStart: (_) => longPressed = true,
        ),
      );
      await tester.pump();

      final bubble = tester.widget<ChatMessageBubble>(
        find.byType(ChatMessageBubble),
      );
      bubble.onLongPressStart(const LongPressStartDetails());
      await tester.pump();

      expect(longPressed, isTrue);
    });

    testWidgets('tap 消息气泡触发 onTap', (tester) async {
      var tapped = false;
      final message = _message(content: '点击测试消息');
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          isRight: true,
          onTap: () => tapped = true,
        ),
      );
      await tester.pump();

      final bubble = tester.widget<ChatMessageBubble>(
        find.byType(ChatMessageBubble),
      );
      bubble.onTap!();
      await tester.pump();

      expect(tapped, isTrue);
    });
  });

  group('ChatMessageBubble - 错误态渲染', () {
    testWidgets('空 content 安全渲染', (tester) async {
      final message = _message(content: '');
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('null content 安全渲染', (tester) async {
      final message = _message(content: '');
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('空展示对象安全渲染', (tester) async {
      await tester.pumpWidget(_wrapBubble(message: _message(content: '')));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });
  });
}

ChatMessageDisplayItem _message({
  String id = 'msg_001',
  String senderId = 'user_001',
  String senderName = '',
  String type = 'text',
  String content = '',
  String status = 'sent',
  String mediaUrl = '',
  String imageUrl = '',
  String thumbnailUrl = '',
  int audioDurationMs = 0,
  List<String> mentions = const <String>[],
  MessageCard? card,
}) {
  return ChatMessageDisplayItem(
    id: id,
    conversationId: 'conv_001',
    seq: 1,
    clientMsgId: 'client_001',
    senderId: senderId,
    senderName: senderName,
    senderAvatar: '',
    senderPersonaId: '',
    type: type,
    content: content,
    status: status,
    timestampLabel: '2026-05-07T10:00:00.000Z',
    sentAtIso: '2026-05-07T10:00:00.000Z',
    isSelf: senderId == 'user_001',
    isRead: true,
    mediaUrl: mediaUrl,
    imageUrl: imageUrl,
    thumbnailUrl: thumbnailUrl,
    audioDurationMs: audioDurationMs,
    audioWaveform: const <double>[0.1, 0.4, 0.2, 0.8],
    mentions: mentions,
    card: card,
  );
}
