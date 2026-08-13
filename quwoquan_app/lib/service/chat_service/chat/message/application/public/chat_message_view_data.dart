import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

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

/// App-owned message synchronization result.
///
/// Cloud decoding is exclusively owned by the generated [ChatMessageSyncSlice];
/// this type carries the mapped local timeline state only.
final class ChatMessageSyncViewData {
  const ChatMessageSyncViewData({
    required this.messages,
    required this.hasMore,
  });

  final List<ChatMessageViewData> messages;
  final bool hasMore;
}
