// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: a60b8ff7b0ab4b9c8092722170f993770e6f840c5f60a3ea8106f447161d19f8

part of '../../../chat/chat_operation_contracts.g.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}


void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}


String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}


int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}


double _generatedRequestDouble(Object? value, String path) {
  if (value is num) return value.toDouble();
  throw FormatException('$path must be a number');
}


bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
}


List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class ChatAddConversationMembersCommand {
  ChatAddConversationMembersCommand({
    required String conversationId,
    required Iterable<String> userIds,
  }) : conversationId = conversationId.trim(),
       userIds = _normalizeGeneratedTextList(userIds, deduplicate: false) {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.userIds.isEmpty) {
      throw ArgumentError.value(this.userIds, "userIds", 'must not be blank');
    }
  }

  final String conversationId;
  final List<String> userIds;

  factory ChatAddConversationMembersCommand.fromWire(Map<String, Object?> map, [String path = "ChatAddConversationMembersCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "userIds"}, path);
    return ChatAddConversationMembersCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      userIds: List<String>.unmodifiable(_generatedRequestList(map["userIds"], '$path.userIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.userIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "userIds": this.userIds.map((value) => value).toList(growable: false),
  };
}

final class ChatBatchGetConversationsQuery {
  ChatBatchGetConversationsQuery({
    required Iterable<String> conversationIds,
  }) : conversationIds = _normalizeGeneratedTextList(conversationIds, deduplicate: false) {
    if (this.conversationIds.isEmpty) {
      throw ArgumentError.value(this.conversationIds, "conversationIds", 'must not be blank');
    }
  }

  final List<String> conversationIds;

  factory ChatBatchGetConversationsQuery.fromWire(Map<String, Object?> map, [String path = "ChatBatchGetConversationsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"ids"}, path);
    return ChatBatchGetConversationsQuery(
      conversationIds: List<String>.unmodifiable(_generatedRequestList(map["ids"], '$path.ids').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.ids' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "ids": this.conversationIds.map((value) => value).toList(growable: false),
  };
}

final class ChatCreateConversationCommand {
  ChatCreateConversationCommand({
    required String type,
    String? title,
    int? maxGroupSize,
    Iterable<String> initialMemberIds = const <String>[],
  }) : type = type.trim(),
       title = _normalizeGeneratedOptionalText(title),
       maxGroupSize = maxGroupSize,
       initialMemberIds = _normalizeGeneratedTextList(initialMemberIds, deduplicate: false) {
    if (this.type.isEmpty) {
      throw ArgumentError.value(this.type, "type", 'must not be blank');
    }
  }

  final String type;
  final String? title;
  final int? maxGroupSize;
  final List<String> initialMemberIds;

  factory ChatCreateConversationCommand.fromWire(Map<String, Object?> map, [String path = "ChatCreateConversationCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"type", "title", "maxGroupSize", "initialMemberIds"}, path);
    return ChatCreateConversationCommand(
      type: _generatedRequestString(map["type"], '$path.type'),
      title: map["title"] == null ? null : _generatedRequestString(map["title"], '$path.title'),
      maxGroupSize: map["maxGroupSize"] == null ? null : _generatedRequestInt(map["maxGroupSize"], '$path.maxGroupSize'),
      initialMemberIds: map.containsKey("initialMemberIds") ? List<String>.unmodifiable(_generatedRequestList(map["initialMemberIds"], '$path.initialMemberIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.initialMemberIds' + '[${entry.key}]'))) : const <String>[],
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "type": this.type,
    if (this.title != null) "title": this.title!,
    if (this.maxGroupSize != null) "maxGroupSize": this.maxGroupSize!,
    if (this.initialMemberIds.isNotEmpty) "initialMemberIds": this.initialMemberIds.map((value) => value).toList(growable: false),
  };
}

final class ChatDissolveConversationCommand {
  ChatDissolveConversationCommand({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory ChatDissolveConversationCommand.fromWire(Map<String, Object?> map, [String path = "ChatDissolveConversationCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return ChatDissolveConversationCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatGetConversationQuery {
  ChatGetConversationQuery({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory ChatGetConversationQuery.fromWire(Map<String, Object?> map, [String path = "ChatGetConversationQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return ChatGetConversationQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatGetGroupHomeQuery {
  ChatGetGroupHomeQuery({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory ChatGetGroupHomeQuery.fromWire(Map<String, Object?> map, [String path = "ChatGetGroupHomeQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return ChatGetGroupHomeQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatGetMessageReceiptsQuery {
  ChatGetMessageReceiptsQuery({
    required String conversationId,
    required String messageId,
  }) : conversationId = conversationId.trim(),
       messageId = messageId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.messageId.isEmpty) {
      throw ArgumentError.value(this.messageId, "messageId", 'must not be blank');
    }
  }

  final String conversationId;
  final String messageId;

  factory ChatGetMessageReceiptsQuery.fromWire(Map<String, Object?> map, [String path = "ChatGetMessageReceiptsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "messageId"}, path);
    return ChatGetMessageReceiptsQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      messageId: _generatedRequestString(map["messageId"], '$path.messageId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "messageId": this.messageId,
  };
}

final class ChatInviteConversationAssistantCommand {
  ChatInviteConversationAssistantCommand({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory ChatInviteConversationAssistantCommand.fromWire(Map<String, Object?> map, [String path = "ChatInviteConversationAssistantCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return ChatInviteConversationAssistantCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatLeaveConversationCommand {
  ChatLeaveConversationCommand({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory ChatLeaveConversationCommand.fromWire(Map<String, Object?> map, [String path = "ChatLeaveConversationCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return ChatLeaveConversationCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatListContactHomeQuery {
  const ChatListContactHomeQuery({
    String filter = 'all',
    int limit = 50,
  }) : filter = filter,
       limit = limit;

  final String filter;
  final int limit;

  factory ChatListContactHomeQuery.fromWire(Map<String, Object?> map, [String path = "ChatListContactHomeQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"filter", "limit"}, path);
    return ChatListContactHomeQuery(
      filter: map.containsKey("filter") ? _generatedRequestString(map["filter"], '$path.filter') : 'all',
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 50,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "filter": this.filter,
    "limit": this.limit,
  };
}

final class ChatListContactsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ChatListContactsQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? cursor;
  final int limit;

  factory ChatListContactsQuery.fromWire(Map<String, Object?> map, [String path = "ChatListContactsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"cursor", "limit"}, path);
    return ChatListContactsQuery(
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListConversationAssetsQuery {
  static const int defaultLimit = 60;
  static const int maximumLimit = 200;

  ChatListConversationAssetsQuery({
    required String conversationId,
    required String kind,
    int? beforeSeq,
    int limit = 60,
  }) : conversationId = conversationId.trim(),
       kind = kind.trim(),
       beforeSeq = beforeSeq,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.kind.isEmpty) {
      throw ArgumentError.value(this.kind, "kind", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 200) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 200");
    }
  }

  final String conversationId;
  final String kind;
  final int? beforeSeq;
  final int limit;

  factory ChatListConversationAssetsQuery.fromWire(Map<String, Object?> map, [String path = "ChatListConversationAssetsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "kind", "beforeSeq", "limit"}, path);
    return ChatListConversationAssetsQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      kind: _generatedRequestString(map["kind"], '$path.kind'),
      beforeSeq: map["beforeSeq"] == null ? null : _generatedRequestInt(map["beforeSeq"], '$path.beforeSeq'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 60,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "kind": this.kind,
    if (this.beforeSeq != null) "beforeSeq": this.beforeSeq!,
    "limit": this.limit,
  };
}

final class ChatListConversationMembersQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  ChatListConversationMembersQuery({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort sort = MemberListSort.joinedAsc,
    String? query,
  }) : conversationId = conversationId.trim(),
       cursor = cursor,
       limit = limit,
       role = role,
       sort = sort,
       query = query {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String conversationId;
  final String? cursor;
  final int limit;
  final String? role;
  final MemberListSort sort;
  final String? query;

  factory ChatListConversationMembersQuery.fromWire(Map<String, Object?> map, [String path = "ChatListConversationMembersQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "cursor", "limit", "role", "sort", "query"}, path);
    return ChatListConversationMembersQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
      role: map["role"] == null ? null : _generatedRequestString(map["role"], '$path.role'),
      sort: map.containsKey("sort") ? switch (map["sort"]) { "joined_asc" => MemberListSort.joinedAsc, "display_name_asc" => MemberListSort.displayNameAsc, _ => throw FormatException('$path.sort' + ' has an invalid enum value'), } : MemberListSort.joinedAsc,
      query: map["query"] == null ? null : _generatedRequestString(map["query"], '$path.query'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.role != null) "role": this.role!,
    "sort": this.sort.wireName,
    if (this.query != null) "query": this.query!,
  };
}

final class ChatListConversationTimestampsQuery {
  const ChatListConversationTimestampsQuery();
}

final class ChatListConversationsQuery {
  const ChatListConversationsQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit;

  final String? cursor;
  final int limit;

  factory ChatListConversationsQuery.fromWire(Map<String, Object?> map, [String path = "ChatListConversationsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"cursor", "limit"}, path);
    return ChatListConversationsQuery(
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListGroupCandidatesQuery {
  static const int defaultLimit = 100;
  static const int maximumLimit = 100;

  ChatListGroupCandidatesQuery({
    String? conversationId,
    int limit = 100,
  }) : conversationId = conversationId,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? conversationId;
  final int limit;

  factory ChatListGroupCandidatesQuery.fromWire(Map<String, Object?> map, [String path = "ChatListGroupCandidatesQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "limit"}, path);
    return ChatListGroupCandidatesQuery(
      conversationId: map["conversationId"] == null ? null : _generatedRequestString(map["conversationId"], '$path.conversationId'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 100,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.conversationId != null) "conversationId": this.conversationId!,
    "limit": this.limit,
  };
}

final class ChatListInboxQuery {
  static const int defaultLimit = 50;
  static const int maximumLimit = 50;

  ChatListInboxQuery({
    String? cursor,
    int limit = 50,
  }) : cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String? cursor;
  final int limit;

  factory ChatListInboxQuery.fromWire(Map<String, Object?> map, [String path = "ChatListInboxQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"cursor", "limit"}, path);
    return ChatListInboxQuery(
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 50,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListMessageHomeQuery {
  const ChatListMessageHomeQuery({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) : filter = filter,
       cursor = cursor,
       limit = limit;

  final String filter;
  final String? cursor;
  final int limit;

  factory ChatListMessageHomeQuery.fromWire(Map<String, Object?> map, [String path = "ChatListMessageHomeQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"filter", "cursor", "limit"}, path);
    return ChatListMessageHomeQuery(
      filter: map.containsKey("filter") ? _generatedRequestString(map["filter"], '$path.filter') : 'all',
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "filter": this.filter,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListMessagesQuery {
  ChatListMessagesQuery({
    required String conversationId,
    int? afterSeq,
    int? beforeSeq,
    int limit = 20,
  }) : conversationId = conversationId.trim(),
       afterSeq = afterSeq,
       beforeSeq = beforeSeq,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final int? afterSeq;
  final int? beforeSeq;
  final int limit;

  factory ChatListMessagesQuery.fromWire(Map<String, Object?> map, [String path = "ChatListMessagesQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "afterSeq", "beforeSeq", "limit"}, path);
    return ChatListMessagesQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      afterSeq: map["afterSeq"] == null ? null : _generatedRequestInt(map["afterSeq"], '$path.afterSeq'),
      beforeSeq: map["beforeSeq"] == null ? null : _generatedRequestInt(map["beforeSeq"], '$path.beforeSeq'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.afterSeq != null) "afterSeq": this.afterSeq!,
    if (this.beforeSeq != null) "beforeSeq": this.beforeSeq!,
    "limit": this.limit,
  };
}

final class ChatListSelectableGroupContactMembersQuery {
  static const int defaultLimit = 100;
  static const int maximumLimit = 100;

  ChatListSelectableGroupContactMembersQuery({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = 100,
  }) : conversationId = conversationId.trim(),
       query = query,
       cursor = cursor,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String conversationId;
  final String? query;
  final String? cursor;
  final int limit;

  factory ChatListSelectableGroupContactMembersQuery.fromWire(Map<String, Object?> map, [String path = "ChatListSelectableGroupContactMembersQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "query", "cursor", "limit"}, path);
    return ChatListSelectableGroupContactMembersQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      query: map["query"] == null ? null : _generatedRequestString(map["query"], '$path.query'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 100,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.query != null) "query": this.query!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListSelectableGroupConversationsQuery {
  static const int defaultLimit = 50;
  static const int maximumLimit = 50;

  ChatListSelectableGroupConversationsQuery({
    String? query,
    SelectableGroupConversationSource? source,
    String? cursor,
    int limit = 50,
  }) : query = query,
       source = source,
       cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String? query;
  final SelectableGroupConversationSource? source;
  final String? cursor;
  final int limit;

  factory ChatListSelectableGroupConversationsQuery.fromWire(Map<String, Object?> map, [String path = "ChatListSelectableGroupConversationsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"query", "source", "cursor", "limit"}, path);
    return ChatListSelectableGroupConversationsQuery(
      query: map["query"] == null ? null : _generatedRequestString(map["query"], '$path.query'),
      source: map["source"] == null ? null : switch (map["source"]) { "group" => SelectableGroupConversationSource.group, "circle" => SelectableGroupConversationSource.circle, _ => throw FormatException('$path.source' + ' has an invalid enum value'), },
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 50,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.query != null) "query": this.query!,
    if (this.source != null) "source": this.source!.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatMarkConversationMessageReadCommand {
  ChatMarkConversationMessageReadCommand({
    required String conversationId,
    required String messageId,
  }) : conversationId = conversationId.trim(),
       messageId = messageId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.messageId.isEmpty) {
      throw ArgumentError.value(this.messageId, "messageId", 'must not be blank');
    }
  }

  final String conversationId;
  final String messageId;

  factory ChatMarkConversationMessageReadCommand.fromWire(Map<String, Object?> map, [String path = "ChatMarkConversationMessageReadCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "messageId"}, path);
    return ChatMarkConversationMessageReadCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      messageId: _generatedRequestString(map["messageId"], '$path.messageId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "messageId": this.messageId,
  };
}

final class ChatRecallMessageCommand {
  ChatRecallMessageCommand({
    required String conversationId,
    required String messageId,
  }) : conversationId = conversationId.trim(),
       messageId = messageId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.messageId.isEmpty) {
      throw ArgumentError.value(this.messageId, "messageId", 'must not be blank');
    }
  }

  final String conversationId;
  final String messageId;

  factory ChatRecallMessageCommand.fromWire(Map<String, Object?> map, [String path = "ChatRecallMessageCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "messageId"}, path);
    return ChatRecallMessageCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      messageId: _generatedRequestString(map["messageId"], '$path.messageId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "messageId": this.messageId,
  };
}

final class ChatRemoveConversationAssistantCommand {
  ChatRemoveConversationAssistantCommand({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory ChatRemoveConversationAssistantCommand.fromWire(Map<String, Object?> map, [String path = "ChatRemoveConversationAssistantCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return ChatRemoveConversationAssistantCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatRemoveConversationMemberCommand {
  ChatRemoveConversationMemberCommand({
    required String conversationId,
    required String userId,
  }) : conversationId = conversationId.trim(),
       userId = userId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.userId.isEmpty) {
      throw ArgumentError.value(this.userId, "userId", 'must not be blank');
    }
  }

  final String conversationId;
  final String userId;

  factory ChatRemoveConversationMemberCommand.fromWire(Map<String, Object?> map, [String path = "ChatRemoveConversationMemberCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "userId"}, path);
    return ChatRemoveConversationMemberCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      userId: _generatedRequestString(map["userId"], '$path.userId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "userId": this.userId,
  };
}

final class ChatSendMessageCommand {
  ChatSendMessageCommand({
    required String conversationId,
    required String type,
    required String content,
    required String clientMsgId,
    String? mediaAssetId,
    MessageCard? card,
    int? audioDurationMs,
    List<double>? audioWaveform,
    String? replyToMessageId,
    Iterable<String> mentions = const <String>[],
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    int? personaContextVersion,
  }) : conversationId = conversationId.trim(),
       type = type.trim(),
       content = content,
       clientMsgId = clientMsgId.trim(),
       mediaAssetId = _normalizeGeneratedOptionalText(mediaAssetId),
       card = card,
       audioDurationMs = audioDurationMs,
       audioWaveform = audioWaveform == null ? null : List.unmodifiable(audioWaveform),
       replyToMessageId = _normalizeGeneratedOptionalText(replyToMessageId),
       mentions = _normalizeGeneratedTextList(mentions, deduplicate: false),
       senderDisplayNameSnapshot = _normalizeGeneratedOptionalText(senderDisplayNameSnapshot),
       senderAvatarUrlSnapshot = _normalizeGeneratedOptionalText(senderAvatarUrlSnapshot),
       personaContextVersion = personaContextVersion {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.type.isEmpty) {
      throw ArgumentError.value(this.type, "type", 'must not be blank');
    }
    if (this.clientMsgId.isEmpty) {
      throw ArgumentError.value(this.clientMsgId, "clientMsgId", 'must not be blank');
    }
    if (this.audioDurationMs != null && this.audioDurationMs! <= 0) {
      throw ArgumentError.value(this.audioDurationMs, "audioDurationMs", "must be positive");
    }
    if (this.audioWaveform != null && this.audioWaveform!.length > 128) {
      throw ArgumentError.value(this.audioWaveform, "audioWaveform", "item count exceeds 128");
    }
    if (this.type == "image" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is image");
    }
    if (this.type == "video" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is video");
    }
    if (this.type == "audio" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is audio");
    }
    if (this.type == "file" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is file");
    }
    if (this.type == "text" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is text");
    }
    if (this.type == "card" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is card");
    }
    if (this.type == "system_call_log" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is system_call_log");
    }
    if (this.type == "system_announcement" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is system_announcement");
    }
    if (this.type == "card" && this.card == null) {
      throw ArgumentError.value(this.card, "card", "is required when type is card");
    }
    if (this.type != "card" && this.card != null) {
      throw ArgumentError.value(this.card, "card", "is forbidden unless type is card");
    }
    if (this.type != "audio" && this.audioDurationMs != null) {
      throw ArgumentError.value(this.audioDurationMs, "audioDurationMs", "is forbidden unless type is audio");
    }
    if (this.type != "audio" && this.audioWaveform != null) {
      throw ArgumentError.value(this.audioWaveform, "audioWaveform", "is forbidden unless type is audio");
    }
  }

  final String conversationId;
  final String type;
  final String content;
  final String clientMsgId;
  final String? mediaAssetId;
  final MessageCard? card;
  final int? audioDurationMs;
  final List<double>? audioWaveform;
  final String? replyToMessageId;
  final List<String> mentions;
  final String? senderDisplayNameSnapshot;
  final String? senderAvatarUrlSnapshot;
  final int? personaContextVersion;

  factory ChatSendMessageCommand.fromWire(Map<String, Object?> map, [String path = "ChatSendMessageCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "type", "content", "clientMsgId", "mediaAssetId", "card", "audioDurationMs", "audioWaveform", "replyToMessageId", "mentions", "senderDisplayNameSnapshot", "senderAvatarUrlSnapshot", "personaContextVersion"}, path);
    return ChatSendMessageCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      type: _generatedRequestString(map["type"], '$path.type'),
      content: _generatedRequestString(map["content"], '$path.content'),
      clientMsgId: _generatedRequestString(map["clientMsgId"], '$path.clientMsgId'),
      mediaAssetId: map["mediaAssetId"] == null ? null : _generatedRequestString(map["mediaAssetId"], '$path.mediaAssetId'),
      card: map["card"] == null ? null : MessageCard.fromWire(_generatedRequestObject(map["card"], '$path.card'), '$path.card'),
      audioDurationMs: map["audioDurationMs"] == null ? null : _generatedRequestInt(map["audioDurationMs"], '$path.audioDurationMs'),
      audioWaveform: map["audioWaveform"] == null ? null : List<double>.unmodifiable(_generatedRequestList(map["audioWaveform"], '$path.audioWaveform').asMap().entries.map((entry) => _generatedRequestDouble(entry.value, '$path.audioWaveform' + '[${entry.key}]'))),
      replyToMessageId: map["replyToMessageId"] == null ? null : _generatedRequestString(map["replyToMessageId"], '$path.replyToMessageId'),
      mentions: map.containsKey("mentions") ? List<String>.unmodifiable(_generatedRequestList(map["mentions"], '$path.mentions').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.mentions' + '[${entry.key}]'))) : const <String>[],
      senderDisplayNameSnapshot: map["senderDisplayNameSnapshot"] == null ? null : _generatedRequestString(map["senderDisplayNameSnapshot"], '$path.senderDisplayNameSnapshot'),
      senderAvatarUrlSnapshot: map["senderAvatarUrlSnapshot"] == null ? null : _generatedRequestString(map["senderAvatarUrlSnapshot"], '$path.senderAvatarUrlSnapshot'),
      personaContextVersion: map["personaContextVersion"] == null ? null : _generatedRequestInt(map["personaContextVersion"], '$path.personaContextVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "type": this.type,
    "content": this.content,
    "clientMsgId": this.clientMsgId,
    if (this.mediaAssetId != null) "mediaAssetId": this.mediaAssetId!,
    if (this.card != null) "card": this.card!.toWire(),
    if (this.audioDurationMs != null) "audioDurationMs": this.audioDurationMs!,
    if (this.audioWaveform != null) "audioWaveform": this.audioWaveform!.map((value) => value).toList(growable: false),
    if (this.replyToMessageId != null) "replyToMessageId": this.replyToMessageId!,
    if (this.mentions.isNotEmpty) "mentions": this.mentions.map((value) => value).toList(growable: false),
    if (this.senderDisplayNameSnapshot != null) "senderDisplayNameSnapshot": this.senderDisplayNameSnapshot!,
    if (this.senderAvatarUrlSnapshot != null) "senderAvatarUrlSnapshot": this.senderAvatarUrlSnapshot!,
    if (this.personaContextVersion != null) "personaContextVersion": this.personaContextVersion!,
  };
}

final class ChatSyncMessagesQuery {
  static const int defaultLimit = 500;
  static const int maximumLimit = 500;

  ChatSyncMessagesQuery({
    required String conversationId,
    required int lastSeq,
    int limit = 500,
  }) : conversationId = conversationId.trim(),
       lastSeq = lastSeq,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 500) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 500");
    }
  }

  final String conversationId;
  final int lastSeq;
  final int limit;

  factory ChatSyncMessagesQuery.fromWire(Map<String, Object?> map, [String path = "ChatSyncMessagesQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "lastSeq", "limit"}, path);
    return ChatSyncMessagesQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      lastSeq: _generatedRequestInt(map["lastSeq"], '$path.lastSeq'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 500,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "lastSeq": this.lastSeq,
    "limit": this.limit,
  };
}

final class ChatTransferConversationOwnershipCommand {
  ChatTransferConversationOwnershipCommand({
    required String conversationId,
    required String newOwnerId,
  }) : conversationId = conversationId.trim(),
       newOwnerId = newOwnerId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.newOwnerId.isEmpty) {
      throw ArgumentError.value(this.newOwnerId, "newOwnerId", 'must not be blank');
    }
  }

  final String conversationId;
  final String newOwnerId;

  factory ChatTransferConversationOwnershipCommand.fromWire(Map<String, Object?> map, [String path = "ChatTransferConversationOwnershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "newOwnerId"}, path);
    return ChatTransferConversationOwnershipCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      newOwnerId: _generatedRequestString(map["newOwnerId"], '$path.newOwnerId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "newOwnerId": this.newOwnerId,
  };
}

final class ChatUpdateAnnouncementCommand {
  ChatUpdateAnnouncementCommand({
    required String conversationId,
    required String announcement,
  }) : conversationId = conversationId.trim(),
       announcement = announcement {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final String announcement;

  factory ChatUpdateAnnouncementCommand.fromWire(Map<String, Object?> map, [String path = "ChatUpdateAnnouncementCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "announcement"}, path);
    return ChatUpdateAnnouncementCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      announcement: _generatedRequestString(map["announcement"], '$path.announcement'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "announcement": this.announcement,
  };
}

final class ChatUpdateConversationAdminsCommand {
  ChatUpdateConversationAdminsCommand({
    required String conversationId,
    required Iterable<String> adminIds,
  }) : conversationId = conversationId.trim(),
       adminIds = _normalizeGeneratedTextList(adminIds, deduplicate: false) {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.adminIds.isEmpty) {
      throw ArgumentError.value(this.adminIds, "adminIds", 'must not be blank');
    }
  }

  final String conversationId;
  final List<String> adminIds;

  factory ChatUpdateConversationAdminsCommand.fromWire(Map<String, Object?> map, [String path = "ChatUpdateConversationAdminsCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "adminIds"}, path);
    return ChatUpdateConversationAdminsCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      adminIds: List<String>.unmodifiable(_generatedRequestList(map["adminIds"], '$path.adminIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.adminIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "adminIds": this.adminIds.map((value) => value).toList(growable: false),
  };
}

final class ChatUpdateConversationSettingsCommand {
  ChatUpdateConversationSettingsCommand({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) : conversationId = conversationId.trim(),
       muted = muted,
       pinned = pinned {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final bool? muted;
  final bool? pinned;

  factory ChatUpdateConversationSettingsCommand.fromWire(Map<String, Object?> map, [String path = "ChatUpdateConversationSettingsCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "muted", "pinned"}, path);
    return ChatUpdateConversationSettingsCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      muted: map["muted"] == null ? null : _generatedRequestBool(map["muted"], '$path.muted'),
      pinned: map["pinned"] == null ? null : _generatedRequestBool(map["pinned"], '$path.pinned'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.muted != null) "muted": this.muted!,
    if (this.pinned != null) "pinned": this.pinned!,
  };
}

final class ChatUpdateConversationTitleCommand {
  ChatUpdateConversationTitleCommand({
    required String conversationId,
    required String title,
  }) : conversationId = conversationId.trim(),
       title = title.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
  }

  final String conversationId;
  final String title;

  factory ChatUpdateConversationTitleCommand.fromWire(Map<String, Object?> map, [String path = "ChatUpdateConversationTitleCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "title"}, path);
    return ChatUpdateConversationTitleCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      title: _generatedRequestString(map["title"], '$path.title'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "title": this.title,
  };
}

final class ChatUpdateGroupGovernanceSettingsCommand {
  ChatUpdateGroupGovernanceSettingsCommand({
    required String conversationId,
    required bool nameEditableByAdminOnly,
  }) : conversationId = conversationId.trim(),
       nameEditableByAdminOnly = nameEditableByAdminOnly {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final bool nameEditableByAdminOnly;

  factory ChatUpdateGroupGovernanceSettingsCommand.fromWire(Map<String, Object?> map, [String path = "ChatUpdateGroupGovernanceSettingsCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId", "nameEditableByAdminOnly"}, path);
    return ChatUpdateGroupGovernanceSettingsCommand(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
      nameEditableByAdminOnly: _generatedRequestBool(map["nameEditableByAdminOnly"], '$path.nameEditableByAdminOnly'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
    "nameEditableByAdminOnly": this.nameEditableByAdminOnly,
  };
}

final class GatheringChatBoardQuery {
  GatheringChatBoardQuery({
    required String conversationId,
  }) : conversationId = conversationId {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  factory GatheringChatBoardQuery.fromWire(Map<String, Object?> map, [String path = "GatheringChatBoardQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"conversationId"}, path);
    return GatheringChatBoardQuery(
      conversationId: _generatedRequestString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

CloudOperationRequestPayload encodeChatChatInboxViewListInboxGeneratedRequest(ChatListInboxQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationBatchGetConversationsGeneratedRequest(ChatBatchGetConversationsQuery request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "ids": request.conversationIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationCreateConversationGeneratedRequest(ChatCreateConversationCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "type": request.type,
      if (request.title != null) "title": request.title!,
      if (request.maxGroupSize != null) "maxGroupSize": request.maxGroupSize!,
      if (request.initialMemberIds.isNotEmpty) "initialMemberIds": request.initialMemberIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationDissolveConversationGeneratedRequest(ChatDissolveConversationCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationGetConversationGeneratedRequest(ChatGetConversationQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationGetGatheringChatBoardGeneratedRequest(GatheringChatBoardQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationGetGroupHomeGeneratedRequest(ChatGetGroupHomeQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListContactHomeGeneratedRequest(ChatListContactHomeQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "filter": request.filter,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListContactsGeneratedRequest(ChatListContactsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListConversationTimestampsGeneratedRequest(ChatListConversationTimestampsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeChatConversationListConversationsGeneratedRequest(ChatListConversationsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListGroupCandidatesGeneratedRequest(ChatListGroupCandidatesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.conversationId != null) "conversationId": request.conversationId!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListMessageHomeGeneratedRequest(ChatListMessageHomeQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "filter": request.filter,
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListSelectableGroupContactMembersGeneratedRequest(ChatListSelectableGroupContactMembersQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.query != null) "query": request.query!,
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListSelectableGroupConversationsGeneratedRequest(ChatListSelectableGroupConversationsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.query != null) "query": request.query!,
      if (request.source != null) "source": (request.source!.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUpdateAnnouncementGeneratedRequest(ChatUpdateAnnouncementCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "announcement": request.announcement,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUpdateConversationTitleGeneratedRequest(ChatUpdateConversationTitleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "title": request.title,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUpdateGroupGovernanceSettingsGeneratedRequest(ChatUpdateGroupGovernanceSettingsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "nameEditableByAdminOnly": request.nameEditableByAdminOnly,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipAddMembersGeneratedRequest(ChatAddConversationMembersCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "userIds": request.userIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipInviteAssistantGeneratedRequest(ChatInviteConversationAssistantCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipLeaveConversationGeneratedRequest(ChatLeaveConversationCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipListMembersGeneratedRequest(ChatListConversationMembersQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      if (request.role != null) "role": request.role!,
      "sort": (request.sort.wireName).toString(),
      if (request.query != null) "query": request.query!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipRemoveAssistantGeneratedRequest(ChatRemoveConversationAssistantCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipRemoveMemberGeneratedRequest(ChatRemoveConversationMemberCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "userId": request.userId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipTransferOwnershipGeneratedRequest(ChatTransferConversationOwnershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "newOwnerId": request.newOwnerId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipUpdateGroupAdminsGeneratedRequest(ChatUpdateConversationAdminsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "adminIds": request.adminIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUserStateMarkAsReadGeneratedRequest(ChatMarkConversationMessageReadCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUserStateUpdateConversationSettingsGeneratedRequest(ChatUpdateConversationSettingsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      if (request.muted != null) "muted": request.muted!,
      if (request.pinned != null) "pinned": request.pinned!,
    },
  );
}

CloudOperationRequestPayload encodeChatMessageListConversationAssetsGeneratedRequest(ChatListConversationAssetsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      "kind": request.kind,
      "limit": (request.limit).toString(),
      if (request.beforeSeq != null) "beforeSeq": (request.beforeSeq!).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatMessageListMessagesGeneratedRequest(ChatListMessagesQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.afterSeq != null) "afterSeq": (request.afterSeq!).toString(),
      if (request.beforeSeq != null) "beforeSeq": (request.beforeSeq!).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatMessageRecallMessageGeneratedRequest(ChatRecallMessageCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeChatMessageSendMessageGeneratedRequest(ChatSendMessageCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "type": request.type,
      "content": request.content,
      "clientMsgId": request.clientMsgId,
      if (request.mediaAssetId != null) "mediaAssetId": request.mediaAssetId!,
      if (request.card != null) "card": request.card!.toWire(),
      if (request.audioDurationMs != null) "audioDurationMs": request.audioDurationMs!,
      if (request.audioWaveform != null) "audioWaveform": request.audioWaveform!.map((value) => value).toList(growable: false),
      if (request.replyToMessageId != null) "replyToMessageId": request.replyToMessageId!,
      if (request.mentions.isNotEmpty) "mentions": request.mentions.map((value) => value).toList(growable: false),
      if (request.senderDisplayNameSnapshot != null) "senderDisplayNameSnapshot": request.senderDisplayNameSnapshot!,
      if (request.senderAvatarUrlSnapshot != null) "senderAvatarUrlSnapshot": request.senderAvatarUrlSnapshot!,
      if (request.personaContextVersion != null) "personaContextVersion": request.personaContextVersion!,
    },
  );
}

CloudOperationRequestPayload encodeChatMessageSyncMessagesGeneratedRequest(ChatSyncMessagesQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "lastSeq": request.lastSeq,
      "limit": request.limit,
    },
  );
}

CloudOperationRequestPayload encodeChatMessageReceiptFactGetReceiptsGeneratedRequest(ChatGetMessageReceiptsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "messageId": request.messageId,
    },
  );
}

