import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';

/// Typed DTO for the Message entity.
/// Maps to contracts/metadata/messages/conversation/fields.yaml → Message.
class MessageDto {
  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String? senderName;
  final String? senderAvatar;
  final String? senderPersonaId;
  final String type;
  final String? content;
  final String? mediaUrl;
  final Map<String, dynamic>? media;
  final Map<String, dynamic>? cardPayload;
  final String? replyToMessageId;
  final List<String>? mentions;
  final String status;
  final DateTime? recalledAt;
  final Map<String, dynamic>? metadata;
  final DateTime? timestamp;

  const MessageDto({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    this.senderName,
    this.senderAvatar,
    this.senderPersonaId,
    required this.type,
    this.content,
    this.mediaUrl,
    this.media,
    this.cardPayload,
    this.replyToMessageId,
    this.mentions,
    required this.status,
    this.recalledAt,
    this.metadata,
    this.timestamp,
  });

  factory MessageDto.fromMap(Map<String, dynamic> map) {
    return MessageDto(
      id: (map['_id'] ?? map['id'] ?? '') as String,
      conversationId: (map['conversationId'] ?? '') as String,
      seq: (map['seq'] as num?)?.toInt() ?? 0,
      clientMsgId: (map['clientMsgId'] ?? '') as String,
      senderId:
          (map['senderProfileSubjectId'] ?? map['senderId'] ?? '').toString(),
      senderName:
          (map['senderDisplayNameSnapshot'] ?? map['senderName'])?.toString(),
      senderAvatar:
          (map['senderAvatarUrlSnapshot'] ?? map['senderAvatar'])?.toString(),
      senderPersonaId:
          (map['senderPersonaId'] ?? map['senderSubAccountId'])?.toString(),
      type: (map['type'] ?? 'text') as String,
      content: map['content'] as String?,
      mediaUrl: map['mediaUrl'] as String?,
      media: map['media'] is Map
          ? (map['media'] as Map).cast<String, dynamic>()
          : null,
      cardPayload: map['cardPayload'] is Map
          ? (map['cardPayload'] as Map).cast<String, dynamic>()
          : null,
      replyToMessageId: map['replyToMessageId'] as String?,
      mentions: map['mentions'] is List
          ? (map['mentions'] as List).cast<String>()
          : null,
      status: (map['status'] ?? 'sent') as String,
      recalledAt: map['recalledAt'] != null
          ? DateTime.tryParse(map['recalledAt'] as String)
          : null,
      metadata: map['metadata'] is Map
          ? (map['metadata'] as Map).cast<String, dynamic>()
          : null,
      timestamp:
          ChatTimeFormatter.tryParseServerTime(
            (map['timestamp'] ?? map['createdAt'] ?? '') as String,
          ),
    );
  }

  MessageDto copyWith({
    String? id,
    String? conversationId,
    int? seq,
    String? clientMsgId,
    String? senderId,
    String? senderName,
    String? senderAvatar,
    String? senderPersonaId,
    String? type,
    String? content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? status,
    DateTime? recalledAt,
    Map<String, dynamic>? metadata,
    DateTime? timestamp,
  }) {
    return MessageDto(
      id: id ?? this.id,
      conversationId: conversationId ?? this.conversationId,
      seq: seq ?? this.seq,
      clientMsgId: clientMsgId ?? this.clientMsgId,
      senderId: senderId ?? this.senderId,
      senderName: senderName ?? this.senderName,
      senderAvatar: senderAvatar ?? this.senderAvatar,
      senderPersonaId: senderPersonaId ?? this.senderPersonaId,
      type: type ?? this.type,
      content: content ?? this.content,
      mediaUrl: mediaUrl ?? this.mediaUrl,
      media: media ?? this.media,
      cardPayload: cardPayload ?? this.cardPayload,
      replyToMessageId: replyToMessageId ?? this.replyToMessageId,
      mentions: mentions ?? this.mentions,
      status: status ?? this.status,
      recalledAt: recalledAt ?? this.recalledAt,
      metadata: metadata ?? this.metadata,
      timestamp: timestamp ?? this.timestamp,
    );
  }

  Map<String, dynamic> toMap() => {
    'id': id,
    'conversationId': conversationId,
    'seq': seq,
    'clientMsgId': clientMsgId,
    'senderId': senderId,
    'senderProfileSubjectId': senderId,
    if (senderName != null) 'senderName': senderName,
    if (senderName != null) 'senderDisplayNameSnapshot': senderName,
    if (senderAvatar != null) 'senderAvatar': senderAvatar,
    if (senderAvatar != null) 'senderAvatarUrlSnapshot': senderAvatar,
    if (senderPersonaId != null) 'senderPersonaId': senderPersonaId,
    'type': type,
    if (content != null) 'content': content,
    if (mediaUrl != null) 'mediaUrl': mediaUrl,
    if (media != null) 'media': media,
    if (cardPayload != null) 'cardPayload': cardPayload,
    if (replyToMessageId != null) 'replyToMessageId': replyToMessageId,
    if (mentions != null) 'mentions': mentions,
    'status': status,
    if (recalledAt != null) 'recalledAt': recalledAt!.toIso8601String(),
    if (metadata != null) 'metadata': metadata,
    if (timestamp != null) 'timestamp': timestamp!.toIso8601String(),
  };

  /// Converts to the display-oriented Map expected by ChatMessageBubble.
  /// Bridges typed DTO to legacy `Map<String, dynamic>` UI contract.
  Map<String, dynamic> toDisplayMap({required String currentUserId}) {
    final isSelf =
        senderId == currentUserId ||
        (senderId == 'current_user' && currentUserId.isNotEmpty);
    final timeStr = timestamp != null
        ? ChatTimeFormatter.format(timestamp!)
        : '';
    return {
      'id': id,
      '_id': id,
      'conversationId': conversationId,
      'seq': seq,
      'clientMsgId': clientMsgId,
      'senderId': senderId,
      'senderProfileSubjectId': senderId,
      if (senderName != null) 'senderName': senderName,
      if (senderAvatar != null) 'senderAvatar': senderAvatar,
      if (senderPersonaId != null) 'senderPersonaId': senderPersonaId,
      'type': type,
      'content': content ?? '',
      if (mediaUrl != null) 'mediaUrl': mediaUrl,
      if (media != null) 'media': media,
      if (cardPayload != null) 'cardPayload': cardPayload,
      if (replyToMessageId != null) 'replyToMessageId': replyToMessageId,
      if (mentions != null) 'mentions': mentions,
      'status': status,
      'timestamp': timeStr,
      if (timestamp != null) 'sentAtIso': timestamp!.toIso8601String(),
      'isSelf': isSelf,
      'isRead': true,
    };
  }
}
