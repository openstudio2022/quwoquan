import "package:quwoquan_app/cloud/services/chat/chat_view_data.dart";
import 'package:quwoquan_app/core/models/search_models.dart';

class LocalChatSearchContactRecord {
  const LocalChatSearchContactRecord({
    required this.contactId,
    this.userHandle = '',
    this.displayName = '',
    this.nickname = '',
    this.subtitle = '',
    this.headline = '',
    this.remark = '',
    this.avatarUrl = '',
    this.conversationId = '',
    this.highlightText,
    this.matchedField,
  });

  final String contactId;
  final String userHandle;
  final String displayName;
  final String nickname;
  final String subtitle;
  final String headline;
  final String remark;
  final String avatarUrl;
  final String conversationId;
  final String? highlightText;
  final String? matchedField;

  factory LocalChatSearchContactRecord.fromChatContactRowDto(
    ChatContactRowViewData dto,
  ) {
    return LocalChatSearchContactRecord(
      contactId: dto.userId.trim(),
      userHandle: dto.userHandle.trim(),
      displayName: dto.displayName.trim(),
      headline: dto.bio.trim(),
      avatarUrl: dto.avatarUrl.trim(),
    );
  }

  /// SQLite index record codec; this Map never crosses a Cloud boundary.
  factory LocalChatSearchContactRecord.fromStorageMap(
    Map<String, Object?> map,
  ) {
    final contactId = _string(map['contactId']);
    return LocalChatSearchContactRecord(
      contactId: contactId,
      userHandle: _string(map['userHandle']),
      displayName: _firstNonEmpty(<Object?>[map['displayName'], contactId]),
      nickname: _string(map['nickname']),
      subtitle: _string(map['subtitle']),
      headline: _string(map['headline']),
      remark: _string(map['remark']),
      avatarUrl: _string(map['avatarUrl']),
      conversationId: _string(map['conversationId']),
      highlightText: _optionalString(map['highlightText']),
      matchedField: _optionalString(map['matchedField']),
    );
  }

  Map<String, Object?> toStorageMap() {
    return <String, Object?>{
      'contactId': contactId,
      'userHandle': userHandle,
      'displayName': displayName,
      if (nickname.isNotEmpty) 'nickname': nickname,
      if (subtitle.isNotEmpty) 'subtitle': subtitle,
      if (headline.isNotEmpty) 'headline': headline,
      if (remark.isNotEmpty) 'remark': remark,
      if (avatarUrl.isNotEmpty) 'avatarUrl': avatarUrl,
      if (conversationId.isNotEmpty) 'conversationId': conversationId,
      if (highlightText != null) 'highlightText': highlightText,
      if (matchedField != null) 'matchedField': matchedField,
    };
  }

  ChatContactSearchItemViewData toSearchItemViewData() {
    return ChatContactSearchItemViewData(
      contactId: contactId,
      userHandle: userHandle,
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
    String? userHandle,
    String? displayName,
    String? nickname,
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
      userHandle: userHandle ?? this.userHandle,
      displayName: displayName ?? this.displayName,
      nickname: nickname ?? this.nickname,
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
