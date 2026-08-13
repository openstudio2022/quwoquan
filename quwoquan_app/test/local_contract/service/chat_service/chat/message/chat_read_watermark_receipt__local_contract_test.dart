// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/delivery-and-read-receipt/spec.md#gwt-001
//
// 1v1 已读回执真链（去 isRead 硬编码后的行为契约）：
//   - 对端 `ConversationReadWatermarkAdvanced` 实时事件推进 peerReadSeq，
//     自己发出且 seq 不超过水位的消息双勾判定翻转为已读；
//   - 自己的水位事件（多设备已读）不推进 peer 水位；
//   - 水位只单调前进，迟到的旧水位不回退已读态；
//   - 对方消息与未确认消息（seq=0）不参与双勾判定。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';

const _conversationId = 'conv_receipt_001';
const _selfUserId = 'persona_self';
const _peerUserId = 'persona_peer';

ChatMessageViewData _message({required int seq, required String senderId}) {
  return ChatMessageViewData(
    id: 'receipt_msg_$seq',
    conversationId: _conversationId,
    seq: seq,
    clientMsgId: 'receipt_client_$seq',
    senderId: senderId,
    senderName: senderId == _selfUserId ? '我' : '对端好友',
    type: 'text',
    content: '回执契约消息 $seq',
    status: 'sent',
    timestamp: DateTime.utc(2026, 8, 13, 9, seq),
  );
}

Map<String, dynamic> _watermarkEvent({
  required String readerUserId,
  required int readSeq,
}) {
  return <String, dynamic>{
    'type': 'ConversationReadWatermarkAdvanced',
    'conversationId': _conversationId,
    'payload': <String, dynamic>{
      'conversationId': _conversationId,
      'userId': readerUserId,
      'messageId': 'receipt_msg_$readSeq',
      'readSeq': readSeq,
      'unreadCount': 0,
      'mentionUnreadCount': 0,
    },
  };
}

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  late ProviderContainer container;
  late RealtimeMessageHandler handler;

  setUp(() {
    container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        ...chatTestRepositoryOverrides(),
      ],
    );
    handler = RealtimeMessageHandler(
      container.read,
      invalidate: container.invalidate,
      currentUserIdResolver: () => _selfUserId,
    );
    final controller = container.read(
      chatMessageTimelineControllerProvider(_conversationId),
    );
    controller
      ..addMessage(_message(seq: 1, senderId: _selfUserId))
      ..addMessage(_message(seq: 2, senderId: _peerUserId))
      ..addMessage(_message(seq: 3, senderId: _selfUserId));
  });

  tearDown(() => container.dispose());

  List<ChatMessageDisplayItem> displayItems() {
    final snapshot = container.read(chatMessageTimelineProvider(_conversationId));
    return snapshot.messages
        .map(
          (message) => message.toDisplayItem(
            currentUserId: _selfUserId,
            peerReadSeq: snapshot.peerReadSeq,
          ),
        )
        .toList(growable: false);
  }

  test('对端水位事件推进 peerReadSeq 并翻转自己消息的双勾判定', () {
    // 初始：未观测到对端读位，自己的消息一律未读（不再硬编码 true）。
    expect(
      displayItems().where((item) => item.isSelf).map((item) => item.isRead),
      everyElement(isFalse),
    );

    handler.handle(_watermarkEvent(readerUserId: _peerUserId, readSeq: 1));

    final afterFirst = displayItems();
    expect(
      afterFirst.singleWhere((item) => item.seq == 1).isRead,
      isTrue,
      reason: '对端读位到 seq=1，自己 seq=1 的消息必须翻转为已读',
    );
    expect(
      afterFirst.singleWhere((item) => item.seq == 3).isRead,
      isFalse,
      reason: '超出水位的消息保持未读',
    );
    expect(
      afterFirst.singleWhere((item) => item.seq == 2).isRead,
      isFalse,
      reason: '对方发出的消息不参与本端双勾判定',
    );
  });

  test('自己的多设备已读水位不推进 peer 水位', () {
    handler.handle(_watermarkEvent(readerUserId: _selfUserId, readSeq: 3));
    expect(
      container.read(chatMessageTimelineProvider(_conversationId)).peerReadSeq,
      0,
      reason: '读者是自己时属于多设备未读收敛，不得伪造对端已读',
    );
  });

  test('水位单调前进，迟到旧水位不回退', () {
    handler.handle(_watermarkEvent(readerUserId: _peerUserId, readSeq: 3));
    handler.handle(_watermarkEvent(readerUserId: _peerUserId, readSeq: 1));
    expect(
      container.read(chatMessageTimelineProvider(_conversationId)).peerReadSeq,
      3,
    );
    expect(displayItems().singleWhere((item) => item.seq == 3).isRead, isTrue);
  });

  test('缺 userId 或非法 readSeq 的水位事件被拒绝', () {
    handler.handle(<String, dynamic>{
      'type': 'ConversationReadWatermarkAdvanced',
      'conversationId': _conversationId,
      'payload': <String, dynamic>{'readSeq': 5},
    });
    handler.handle(_watermarkEvent(readerUserId: _peerUserId, readSeq: 0));
    expect(
      container.read(chatMessageTimelineProvider(_conversationId)).peerReadSeq,
      0,
    );
  });
}
