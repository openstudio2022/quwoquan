import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';

class LocalChatSearchMessageRecord {
  const LocalChatSearchMessageRecord({
    required this.messageId,
    required this.conversationId,
    this.conversationType = '',
    this.conversationTitle = '',
    this.conversationAvatarUrl = '',
    this.senderSubAccountId = '',
    this.senderDisplayName = '',
    this.senderAvatarUrl = '',
    this.messageType = 'text',
    this.contentPreview = '',
    this.seq = 0,
    this.timestamp = '',
    this.status = 'sent',
    this.recalledAt = '',
    this.deleted = false,
    this.highlightText,
    this.matchedField,
  });

  final String messageId;
  final String conversationId;
  final String conversationType;
  final String conversationTitle;
  final String conversationAvatarUrl;
  final String senderSubAccountId;
  final String senderDisplayName;
  final String senderAvatarUrl;
  final String messageType;
  final String contentPreview;
  final int seq;
  final String timestamp;
  final String status;
  final String recalledAt;
  final bool deleted;
  final String? highlightText;
  final String? matchedField;

  factory LocalChatSearchMessageRecord.fromMessageDto(
    MessageDto dto, {
    ConversationCacheRecord? conversation,
  }) {
    final conversationId = dto.conversationId.trim();
    return LocalChatSearchMessageRecord(
      messageId: dto.id.trim(),
      conversationId: conversationId,
      conversationType: conversation?.type ?? '',
      conversationTitle: conversation?.title ?? '',
      conversationAvatarUrl: conversation?.avatarUrl ?? '',
      senderSubAccountId: (dto.senderSubAccountId?.trim().isNotEmpty ?? false)
          ? dto.senderSubAccountId!.trim()
          : dto.senderId.trim(),
      senderDisplayName: dto.senderName?.trim() ?? '',
      senderAvatarUrl: dto.senderAvatar?.trim() ?? '',
      messageType: dto.type.trim().isEmpty ? 'text' : dto.type.trim(),
      contentPreview: dto.content?.trim() ?? '',
      seq: dto.seq,
      timestamp: dto.timestamp?.toIso8601String() ?? '',
      status: dto.status.trim().isEmpty ? 'sent' : dto.status.trim(),
      recalledAt: dto.recalledAt?.toIso8601String() ?? '',
      deleted:
          dto.recalledAt != null ||
          dto.status == 'recalled' ||
          dto.status == 'deleted',
    );
  }

  factory LocalChatSearchMessageRecord.fromWireMap(
    Map<String, dynamic> map, {
    ConversationCacheRecord? conversation,
  }) {
    final dto = MessageDto.fromMap(map);
    final base = LocalChatSearchMessageRecord.fromMessageDto(
      dto,
      conversation: conversation,
    );
    return base.copyWith(
      conversationType: _firstNonEmpty(<Object?>[
        map['conversationType'],
        base.conversationType,
      ]),
      conversationTitle: _firstNonEmpty(<Object?>[
        map['conversationTitle'],
        base.conversationTitle,
      ]),
      conversationAvatarUrl: _firstNonEmpty(<Object?>[
        map['conversationAvatarUrl'],
        base.conversationAvatarUrl,
      ]),
      senderDisplayName: _firstNonEmpty(<Object?>[
        map['senderDisplayName'],
        map['senderDisplayNameSnapshot'],
        base.senderDisplayName,
      ]),
      senderAvatarUrl: _firstNonEmpty(<Object?>[
        map['senderAvatarUrl'],
        map['senderAvatarUrlSnapshot'],
        base.senderAvatarUrl,
      ]),
      contentPreview: _firstNonEmpty(<Object?>[
        map['contentPreview'],
        map['content'],
        base.contentPreview,
      ]),
      deleted:
          map['deleted'] == true || map['isDeleted'] == true || base.deleted,
      matchedField: map['matchedField']?.toString(),
      highlightText: map['highlightText']?.toString(),
    );
  }

  MessageSearchItemView toMessageSearchItemView() {
    return MessageSearchItemView(
      messageId: messageId,
      conversationId: conversationId,
      conversationTitle: conversationTitle.isEmpty ? null : conversationTitle,
      conversationAvatarUrl: conversationAvatarUrl.isEmpty
          ? null
          : conversationAvatarUrl,
      senderSubAccountId: senderSubAccountId.isEmpty ? null : senderSubAccountId,
      senderDisplayName: senderDisplayName.isEmpty ? null : senderDisplayName,
      senderAvatarUrl: senderAvatarUrl.isEmpty ? null : senderAvatarUrl,
      messageType: messageType,
      contentPreview: contentPreview,
      seq: seq > 0 ? seq : null,
      timestamp: _parseTimestamp(timestamp),
      highlightText: highlightText,
      matchedField: matchedField,
    );
  }

  LocalChatSearchMessageRecord copyWith({
    String? messageId,
    String? conversationId,
    String? conversationType,
    String? conversationTitle,
    String? conversationAvatarUrl,
    String? senderSubAccountId,
    String? senderDisplayName,
    String? senderAvatarUrl,
    String? messageType,
    String? contentPreview,
    int? seq,
    String? timestamp,
    String? status,
    String? recalledAt,
    bool? deleted,
    String? highlightText,
    String? matchedField,
  }) {
    return LocalChatSearchMessageRecord(
      messageId: messageId ?? this.messageId,
      conversationId: conversationId ?? this.conversationId,
      conversationType: conversationType ?? this.conversationType,
      conversationTitle: conversationTitle ?? this.conversationTitle,
      conversationAvatarUrl:
          conversationAvatarUrl ?? this.conversationAvatarUrl,
      senderSubAccountId: senderSubAccountId ?? this.senderSubAccountId,
      senderDisplayName: senderDisplayName ?? this.senderDisplayName,
      senderAvatarUrl: senderAvatarUrl ?? this.senderAvatarUrl,
      messageType: messageType ?? this.messageType,
      contentPreview: contentPreview ?? this.contentPreview,
      seq: seq ?? this.seq,
      timestamp: timestamp ?? this.timestamp,
      status: status ?? this.status,
      recalledAt: recalledAt ?? this.recalledAt,
      deleted: deleted ?? this.deleted,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }

  Map<String, dynamic> toWireMap() {
    return <String, dynamic>{
      'messageId': messageId,
      'id': messageId,
      '_id': messageId,
      'conversationId': conversationId,
      if (conversationType.isNotEmpty) 'conversationType': conversationType,
      if (conversationTitle.isNotEmpty) 'conversationTitle': conversationTitle,
      if (conversationAvatarUrl.isNotEmpty)
        'conversationAvatarUrl': conversationAvatarUrl,
      if (senderSubAccountId.isNotEmpty)
        'senderSubAccountId': senderSubAccountId,
      if (senderDisplayName.isNotEmpty) ...<String, dynamic>{
        'senderDisplayName': senderDisplayName,
        'senderDisplayNameSnapshot': senderDisplayName,
        'senderName': senderDisplayName,
      },
      if (senderAvatarUrl.isNotEmpty) ...<String, dynamic>{
        'senderAvatarUrl': senderAvatarUrl,
        'senderAvatarUrlSnapshot': senderAvatarUrl,
      },
      'messageType': messageType,
      'type': messageType,
      if (contentPreview.isNotEmpty) ...<String, dynamic>{
        'contentPreview': contentPreview,
        'content': contentPreview,
      },
      'seq': seq,
      if (timestamp.isNotEmpty) ...<String, dynamic>{
        'timestamp': timestamp,
        'createdAt': timestamp,
      },
      'status': status,
      'messageStatus': status,
      if (recalledAt.isNotEmpty) 'recalledAt': recalledAt,
      if (deleted) ...<String, dynamic>{'deleted': true, 'isDeleted': true},
    };
  }
}

String _firstNonEmpty(List<Object?> values) {
  for (final value in values) {
    final text = value?.toString().trim() ?? '';
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}

DateTime _parseTimestamp(String value) {
  return DateTime.tryParse(value.trim()) ?? DateTime.now();
}
