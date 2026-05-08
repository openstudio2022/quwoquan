import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';

class LocalChatSearchContactRecord {
  const LocalChatSearchContactRecord({
    required this.contactId,
    this.displayName = '',
    this.nickname = '',
    this.username = '',
    this.subtitle = '',
    this.headline = '',
    this.remark = '',
    this.avatarUrl = '',
    this.conversationId = '',
    this.highlightText,
    this.matchedField,
  });

  final String contactId;
  final String displayName;
  final String nickname;
  final String username;
  final String subtitle;
  final String headline;
  final String remark;
  final String avatarUrl;
  final String conversationId;
  final String? highlightText;
  final String? matchedField;

  factory LocalChatSearchContactRecord.fromWireMap(Map<String, dynamic> map) {
    final contactId = _firstNonEmpty(<Object?>[
      map['contactId'],
      map['subAccountId'],
      map['userId'],
      map['profileSubjectId'],
      map['id'],
    ]);
    return LocalChatSearchContactRecord(
      contactId: contactId,
      displayName: _firstNonEmpty(<Object?>[
        map['displayName'],
        map['nickname'],
        map['username'],
        contactId,
      ]),
      nickname: _string(map['nickname']),
      username: _string(map['username']),
      subtitle: _string(map['subtitle']),
      headline: _firstNonEmpty(<Object?>[map['headline'], map['bio']]),
      remark: _string(map['remark']),
      avatarUrl: _firstNonEmpty(<Object?>[
        map['avatarUrl'],
        map['avatar'],
      ]),
      conversationId: _firstNonEmpty(<Object?>[
        map['conversationId'],
        map['directConversationId'],
      ]),
      highlightText: _optionalString(map['highlightText']),
      matchedField: _optionalString(map['matchedField']),
    );
  }

  Map<String, dynamic> toWireMap() {
    return <String, dynamic>{
      'contactId': contactId,
      'userId': contactId,
      'id': contactId,
      'displayName': displayName,
      if (nickname.isNotEmpty) 'nickname': nickname,
      if (username.isNotEmpty) 'username': username,
      if (subtitle.isNotEmpty) 'subtitle': subtitle,
      if (headline.isNotEmpty) 'headline': headline,
      if (remark.isNotEmpty) 'remark': remark,
      if (avatarUrl.isNotEmpty) 'avatarUrl': avatarUrl,
      if (conversationId.isNotEmpty) 'conversationId': conversationId,
      if (highlightText != null) 'highlightText': highlightText,
      if (matchedField != null) 'matchedField': matchedField,
    };
  }

  ChatContactSearchItemDto toSearchItemDto() {
    return ChatContactSearchItemDto(
      contactId: contactId,
      displayName: displayName,
      avatarUrl: avatarUrl.isEmpty ? null : avatarUrl,
      conversationId: conversationId.isEmpty ? null : conversationId,
      subtitle: subtitle.isEmpty ? null : subtitle,
      highlightText: highlightText,
      matchedField: matchedField,
    );
  }

  LocalChatSearchContactRecord copyWith({
    String? contactId,
    String? displayName,
    String? nickname,
    String? username,
    String? subtitle,
    String? headline,
    String? remark,
    String? avatarUrl,
    String? conversationId,
    String? highlightText,
    String? matchedField,
  }) {
    return LocalChatSearchContactRecord(
      contactId: contactId ?? this.contactId,
      displayName: displayName ?? this.displayName,
      nickname: nickname ?? this.nickname,
      username: username ?? this.username,
      subtitle: subtitle ?? this.subtitle,
      headline: headline ?? this.headline,
      remark: remark ?? this.remark,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      conversationId: conversationId ?? this.conversationId,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }
}

String _string(Object? value) => value?.toString().trim() ?? '';

String _firstNonEmpty(List<Object?> values) {
  for (final value in values) {
    final text = _string(value);
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}

String? _optionalString(Object? value) {
  final text = _string(value);
  return text.isEmpty ? null : text;
}
