import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/formatters/chat_time_formatter.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

export 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show ChatMessageView, MessageCard, MessageCardKind;

/// App-owned message state used by optimistic delivery and local timeline
/// caching. Cloud JSON is decoded only by [ChatMessageView]; this model accepts
/// that typed value through [ChatMessageViewData.fromWire].
final class ChatMessageViewData {
  const ChatMessageViewData({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    this.senderName,
    this.senderAvatar,
    required this.type,
    this.content,
    this.mediaAssetId,
    this.mediaDeliveryUrl,
    this.mediaType,
    this.mediaContentType,
    this.mediaFileSizeBytes,
    this.audioDurationMs,
    this.audioWaveform,
    this.card,
    this.replyToMessageId,
    this.mentions,
    required this.status,
    this.recalledAt,
    this.timestamp,
  });

  factory ChatMessageViewData.fromWire(ChatMessageView source) {
    return ChatMessageViewData(
      id: source.id,
      conversationId: source.conversationId,
      seq: source.seq,
      clientMsgId: source.clientMsgId,
      senderId: source.senderId,
      senderName: source.senderName,
      senderAvatar: source.senderAvatar,
      type: source.type.wireName,
      content: source.content,
      mediaAssetId: source.mediaAssetId,
      mediaDeliveryUrl: source.mediaDeliveryUrl,
      mediaType: source.mediaType,
      mediaContentType: source.mediaContentType,
      mediaFileSizeBytes: source.mediaFileSizeBytes,
      audioDurationMs: source.audioDurationMs,
      audioWaveform: source.audioWaveform,
      card: source.card,
      replyToMessageId: source.replyToMessageId,
      mentions: source.mentions,
      status: source.status.wireName,
      recalledAt: source.recalledAt,
      timestamp: source.timestamp,
    );
  }

  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String? senderName;
  final String? senderAvatar;
  final String type;
  final String? content;
  final String? mediaAssetId;
  final String? mediaDeliveryUrl;
  final String? mediaType;
  final String? mediaContentType;
  final int? mediaFileSizeBytes;
  final int? audioDurationMs;
  final List<double>? audioWaveform;
  final MessageCard? card;
  final String? replyToMessageId;
  final List<String>? mentions;
  final String status;
  final DateTime? recalledAt;
  final DateTime? timestamp;

  ChatMessageViewData copyWith({
    String? id,
    String? conversationId,
    int? seq,
    String? clientMsgId,
    String? senderId,
    String? senderName,
    String? senderAvatar,
    String? type,
    String? content,
    String? mediaAssetId,
    String? mediaDeliveryUrl,
    String? mediaType,
    String? mediaContentType,
    int? mediaFileSizeBytes,
    int? audioDurationMs,
    List<double>? audioWaveform,
    MessageCard? card,
    String? replyToMessageId,
    List<String>? mentions,
    String? status,
    DateTime? recalledAt,
    DateTime? timestamp,
  }) {
    return ChatMessageViewData(
      id: id ?? this.id,
      conversationId: conversationId ?? this.conversationId,
      seq: seq ?? this.seq,
      clientMsgId: clientMsgId ?? this.clientMsgId,
      senderId: senderId ?? this.senderId,
      senderName: senderName ?? this.senderName,
      senderAvatar: senderAvatar ?? this.senderAvatar,
      type: type ?? this.type,
      content: content ?? this.content,
      mediaAssetId: mediaAssetId ?? this.mediaAssetId,
      mediaDeliveryUrl: mediaDeliveryUrl ?? this.mediaDeliveryUrl,
      mediaType: mediaType ?? this.mediaType,
      mediaContentType: mediaContentType ?? this.mediaContentType,
      mediaFileSizeBytes: mediaFileSizeBytes ?? this.mediaFileSizeBytes,
      audioDurationMs: audioDurationMs ?? this.audioDurationMs,
      audioWaveform: audioWaveform ?? this.audioWaveform,
      card: card ?? this.card,
      replyToMessageId: replyToMessageId ?? this.replyToMessageId,
      mentions: mentions ?? this.mentions,
      status: status ?? this.status,
      recalledAt: recalledAt ?? this.recalledAt,
      timestamp: timestamp ?? this.timestamp,
    );
  }
}

class ChatMessageDisplayItem {
  const ChatMessageDisplayItem({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    required this.senderName,
    required this.senderAvatar,
    required this.senderPersonaId,
    required this.type,
    required this.content,
    required this.status,
    required this.timestampLabel,
    required this.sentAtIso,
    required this.isSelf,
    required this.isRead,
    required this.mediaUrl,
    required this.imageUrl,
    required this.thumbnailUrl,
    required this.audioDurationMs,
    required this.audioWaveform,
    this.mentions = const <String>[],
    this.card,
  });

  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String senderPersonaId;
  final String type;
  final String content;
  final String status;
  final String timestampLabel;
  final String sentAtIso;
  final bool isSelf;
  final bool isRead;
  final String mediaUrl;
  final String imageUrl;
  final String thumbnailUrl;
  final int audioDurationMs;
  final List<double> audioWaveform;
  final List<String> mentions;
  final MessageCard? card;
}

/// 气泡与长按菜单使用的展示模型（仅 UI；契约字段仍以 [ChatMessageView] 为准）。
extension ChatMessageViewDataDisplay on ChatMessageViewData {
  ChatMessageDisplayItem toDisplayItem({
    required String currentUserId,
    MediaEndpointConfig? mediaEndpointConfig,
    int peerReadSeq = 0,
  }) {
    final isSelf =
        senderId == currentUserId ||
        (senderId == 'current_user' && currentUserId.isNotEmpty);
    final timeStr = timestamp == null
        ? ''
        : ChatTimeFormatter.format(timestamp!);
    final deliveryUrl = mediaDeliveryUrl?.trim() ?? '';
    final imageUrl = type == 'image' || type == 'video' ? deliveryUrl : '';
    return ChatMessageDisplayItem(
      id: id,
      conversationId: conversationId,
      seq: seq,
      clientMsgId: clientMsgId,
      senderId: senderId,
      senderName: senderName?.trim() ?? '',
      senderAvatar: resolveAvatarImageUrl(
        senderAvatar,
        endpointConfig: mediaEndpointConfig,
      ),
      senderPersonaId: senderId,
      type: type,
      content: content?.trim() ?? '',
      status: status,
      timestampLabel: timeStr,
      sentAtIso: timestamp?.toIso8601String() ?? '',
      isSelf: isSelf,
      // 与 conversation/presentation 版本保持同一双勾判定，禁止再漂移。
      isRead: isSelf && seq > 0 && seq <= peerReadSeq,
      mediaUrl: deliveryUrl,
      imageUrl: imageUrl,
      thumbnailUrl: imageUrl,
      audioDurationMs: audioDurationMs ?? 0,
      audioWaveform: List<double>.unmodifiable(
        audioWaveform ?? const <double>[],
      ),
      mentions: List<String>.unmodifiable(mentions ?? const <String>[]),
      card: card,
    );
  }
}
