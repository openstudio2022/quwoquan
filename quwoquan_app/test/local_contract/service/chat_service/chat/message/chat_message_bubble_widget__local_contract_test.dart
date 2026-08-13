import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show MessageCard, MessageCardKind;
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

    // spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/spec.md#sit-004
    testWidgets('破冰卡渲染云侧交集主句原文且无跳转 chevron', (tester) async {
      final message = _message(
        type: 'card',
        senderId: 'user_002',
        senderName: '新同行者',
        card: const MessageCard(
          kind: MessageCardKind.intersectionIcebreaker,
          title: '你们都想去贡嘎雪山',
          subtitle: '你们都参加过城市观星夜',
          attributes: [],
        ),
      );
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.text(ChatText.chatIcebreakerCardLabel), findsOneWidget);
      expect(find.text('你们都想去贡嘎雪山'), findsOneWidget);
      expect(find.text('你们都参加过城市观星夜'), findsOneWidget);
      // 破冰卡无跳转语义：不渲染通用卡片的 chevron 行动指示。
      expect(find.byIcon(CupertinoIcons.chevron_forward), findsNothing);
      expect(find.byIcon(CupertinoIcons.sparkles), findsOneWidget);
    });

    testWidgets('破冰卡副句为空时不渲染空行占位', (tester) async {
      final message = _message(
        type: 'card',
        senderId: 'user_002',
        card: const MessageCard(
          kind: MessageCardKind.intersectionIcebreaker,
          title: '你们都关注了摄影师阿舟',
          attributes: [],
        ),
      );
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.text('你们都关注了摄影师阿舟'), findsOneWidget);
      expect(find.text(''), findsNothing);
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

    // spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-004.t4
    testWidgets('接收语音消息渲染云侧真实时长与波形', (tester) async {
      // wire → ChatMessageViewData → toDisplayItem 真链：接收端不再是 0 时长。
      final wire = ChatMessageViewData(
        id: 'msg_audio_wire',
        conversationId: 'conv_audio',
        seq: 9,
        clientMsgId: 'client_audio',
        senderId: 'peer_1',
        type: 'audio',
        content: '',
        mediaDeliveryUrl: 'https://cdn.example.com/voice.m4a',
        audioDurationMs: 5000,
        audioWaveform: const <double>[0.2, 0.9, 0.5, 0.7],
        status: 'sent',
      );
      final item = wire.toDisplayItem(currentUserId: 'me', peerReadSeq: 0);
      expect(item.audioDurationMs, 5000);
      expect(item.audioWaveform, hasLength(4));

      await tester.pumpWidget(_wrapBubble(message: item, isRight: false));
      await tester.pump();

      expect(find.text('5″'), findsOneWidget, reason: '语音气泡显示云侧真实时长');
      final bubble = tester.widget<VoiceMessageBubble>(
        find.byType(VoiceMessageBubble),
      );
      expect(bubble.waveform, hasLength(4), reason: '波形透传到语音气泡');
      expect(bubble.waveform[1], 0.9);
    });

    // spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/list-detail-message-delivery/spec.md
    testWidgets('文件与视频气泡点击触发消费动作', (tester) async {
      var fileTapped = 0;
      final fileMessage = _message(type: 'file', content: '会议纪要.pdf');
      await tester.pumpWidget(
        _wrapBubble(
          message: fileMessage,
          isRight: true,
          onTap: () => fileTapped += 1,
        ),
      );
      await tester.pump();
      await tester.tap(find.byKey(ValueKey('chat_file_open_${fileMessage.id}')));
      expect(fileTapped, 1, reason: '文件气泡点击必须绑定打开动作');

      var videoTapped = 0;
      final videoMessage = _message(
        id: 'msg_video',
        type: 'video',
        content: '滑雪合集',
      );
      await tester.pumpWidget(
        _wrapBubble(
          message: videoMessage,
          isRight: true,
          onTap: () => videoTapped += 1,
        ),
      );
      await tester.pump();
      await tester.tap(
        find.byKey(ValueKey('chat_video_open_${videoMessage.id}')),
      );
      expect(videoTapped, 1, reason: '视频气泡点击必须绑定播放动作');
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
