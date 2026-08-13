library;

import 'dart:convert' show jsonEncode, utf8;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/chat_contracts.dart';

import 'chat_state_seed_builder.dart';

part 'conversation_state_typed_double_conversations.dart';
part 'conversation_state_typed_double_groups.dart';
part 'conversation_state_typed_double_messages.dart';

typedef ChatFixtureObject = Map<String, Object?>;

final class ChatFixtureSyncPage {
  ChatFixtureSyncPage({required this.messages, required this.hasMore});

  final List<ChatFixtureObject> messages;
  final bool hasMore;
}

final class ChatFixtureCursorPage {
  ChatFixtureCursorPage({required this.items, this.nextCursor});

  final List<ChatFixtureObject> items;
  final String? nextCursor;
}

ChatFixtureCursorPage _fixtureCursorPage(
  List<ChatFixtureObject> rows, {
  required String? cursor,
  required int limit,
}) {
  final normalizedLimit = limit <= 0 ? 20 : limit;
  final normalizedCursor = cursor?.trim() ?? '';
  if (normalizedCursor.isNotEmpty && !normalizedCursor.startsWith('offset:')) {
    throw FormatException('invalid fixture cursor');
  }
  final offset = normalizedCursor.isEmpty
      ? 0
      : int.tryParse(normalizedCursor.substring('offset:'.length));
  if (offset == null || offset < 0) {
    throw FormatException('invalid fixture cursor');
  }
  final start = offset;
  if (start >= rows.length) {
    return ChatFixtureCursorPage(items: <ChatFixtureObject>[]);
  }
  final end = (start + normalizedLimit).clamp(0, rows.length);
  return ChatFixtureCursorPage(
    items: rows.sublist(start, end),
    nextCursor: end < rows.length ? 'offset:$end' : null,
  );
}

/// local_contract 使用的纯 Dart chat 对象状态引擎。
///
/// 初始数据只接受当前 suite 显式给出的 Chat 对象 seed；production composition 与
/// Patrol/UAT 不可达。
final class InMemoryChatStateEngine {
  InMemoryChatStateEngine({
    required ChatStateSeed seed,
    List<ChatFixtureObject>? seedConversations,
    Map<String, List<ChatFixtureObject>>? seedMembers,
    Map<String, List<ChatFixtureObject>>? seedMessages,
  }) {
    currentUserId = seed.currentUserId.trim();
    if (currentUserId.isEmpty) {
      throw const FormatException('ChatStateSeed.currentUserId is required');
    }

    final conversationRows = seedConversations ?? seed.conversations;
    for (final row in conversationRows) {
      final id = _text(row['id']);
      if (id.isNotEmpty) {
        _conversations[id] = _copy(row);
      }
    }

    final memberRows = seedMembers ?? seed.members;
    for (final entry in memberRows.entries) {
      _members[entry.key] = entry.value.map(_copy).toList(growable: true);
    }

    final messageRows = seedMessages ?? seed.messages;
    for (final entry in messageRows.entries) {
      _messages[entry.key] = entry.value.map(_copy).toList(growable: true);
    }

    for (final row in seed.userStates) {
      if (_text(row['userId']) == currentUserId) {
        final conversationId = _text(row['conversationId']);
        if (conversationId.isNotEmpty) {
          _userStates[conversationId] = _copy(row);
        }
      }
    }

    _contacts.addAll(
      seed.contacts.where(_hasAvatarMediaObject).map((row) {
        final contact = _copy(row);
        contact['userHandle'] = _text(row['userHandle']);
        return contact;
      }),
    );
    _contactCircleIds.addAll(seed.contactCircleIds);
    _contactGroupConversationIds.addAll(seed.contactGroupConversationIds);
    _circleRows.addAll(seed.circleRows.map(_copy));
    for (final row in seed.settings) {
      final conversationId = _text(row['conversationId']);
      if (conversationId.isNotEmpty) {
        _groupSettings[conversationId] = _copy(row);
      }
    }
    _materializeGroupAvatarMetadata();
  }

  late final String currentUserId;

  final Map<String, ChatFixtureObject> _conversations =
      <String, ChatFixtureObject>{};
  final Map<String, List<ChatFixtureObject>> _members =
      <String, List<ChatFixtureObject>>{};
  final Map<String, List<ChatFixtureObject>> _messages =
      <String, List<ChatFixtureObject>>{};
  final Map<String, ChatFixtureObject> _userStates =
      <String, ChatFixtureObject>{};
  final Map<String, ChatFixtureObject> _groupSettings =
      <String, ChatFixtureObject>{};
  final List<ChatFixtureObject> _contacts = <ChatFixtureObject>[];
  final List<ChatFixtureObject> _circleRows = <ChatFixtureObject>[];
  final Set<String> _contactCircleIds = <String>{};
  final Set<String> _contactGroupConversationIds = <String>{};
  final Map<String, _InMemoryChatSendReceipt> _sendReceipts =
      <String, _InMemoryChatSendReceipt>{};

  int _newConversationSerial = 0;
  int _clockTick = 0;

  List<ChatFixtureObject> get conversationSeeds =>
      _conversations.values.map(_copy).toList(growable: false);

  List<ChatFixtureObject> membersFor(String conversationId) =>
      _ensureMembers(conversationId).map(_copy).toList(growable: false);

  String displayNameFor(String userId) {
    final normalized = userId.trim();
    for (final contact in _contacts) {
      if (_text(contact['userId']) == normalized) {
        return _text(contact['displayName']);
      }
    }
    for (final rows in _members.values) {
      for (final member in rows) {
        if (_text(member['userId']) == normalized) {
          final displayName = _text(member['displayName']);
          if (displayName.isNotEmpty) {
            return displayName;
          }
        }
      }
    }
    return normalized;
  }

  String userHandleFor(String userId) {
    final normalized = userId.trim();
    for (final contact in _contacts) {
      if (_text(contact['userId']) == normalized) {
        return _text(contact['userHandle']);
      }
    }
    for (final rows in _members.values) {
      for (final member in rows) {
        if (_text(member['userId']) == normalized) {
          final userHandle = _text(member['userHandle']);
          if (userHandle.isNotEmpty) {
            return userHandle;
          }
        }
      }
    }
    return '';
  }

  String avatarFor(String userId) {
    final normalized = userId.trim();
    for (final contact in _contacts) {
      if (_text(contact['userId']) == normalized) {
        final avatar = _text(contact['avatarUrl']);
        if (avatar.isNotEmpty) {
          return avatar;
        }
      }
    }
    for (final rows in _members.values) {
      for (final member in rows) {
        if (_text(member['userId']) == normalized) {
          final avatar = _text(member['avatarUrl']);
          if (avatar.isNotEmpty) {
            return avatar;
          }
        }
      }
    }
    return _contacts.isEmpty ? '' : _text(_contacts.first['avatarUrl']);
  }

  ChatFixtureObject conversationSeedById(String conversationId) {
    final row = _conversations[conversationId];
    if (row == null) {
      throw StateError('conversation not found: $conversationId');
    }
    return _copy(row);
  }

  String groupAvatarFor(String conversationId, {int version = 1}) =>
      'media/avatar/s/archived-avatar/conversation/'
      '$conversationId/v$version/mock.png';

  DateTime _now() {
    final value = DateTime.utc(
      2026,
      7,
      20,
      0,
      0,
    ).add(Duration(milliseconds: _clockTick));
    _clockTick += 1;
    return value;
  }

  List<ChatFixtureObject> _ensureMembers(String conversationId) =>
      _members.putIfAbsent(conversationId, () => <ChatFixtureObject>[]);

  List<ChatFixtureObject> _messagesFor(String conversationId) =>
      _messages.putIfAbsent(conversationId, () => <ChatFixtureObject>[]);

  ChatFixtureObject? _conversation(String conversationId) =>
      _conversations[conversationId];

  ChatFixtureObject _stateFor(String conversationId) => _userStates.putIfAbsent(
    conversationId,
    () => <String, Object?>{
      'conversationId': conversationId,
      'userId': currentUserId,
      'readSeq': 0,
      'unreadCount': 0,
      'mentionUnreadCount': 0,
      'muted': false,
      'pinned': false,
      'updatedAt': _now().toIso8601String(),
    },
  );

  void _materializeGroupAvatarMetadata() {
    for (final entry in _conversations.entries) {
      final conversation = entry.value;
      if (_text(conversation['type']) != 'group') {
        continue;
      }
      final members = _ensureMembers(entry.key);
      final sourceHash = _groupAvatarSourceHash(members);
      if (sourceHash.isEmpty) {
        continue;
      }
      conversation['memberCount'] = members.length;
      conversation['groupAvatarVersion'] = _positiveInt(
        conversation['groupAvatarVersion'],
        fallback: 1,
      );
      conversation['groupAvatarSourceHash'] = sourceHash;
      if (_text(conversation['avatarUrl']).isEmpty) {
        conversation['avatarUrl'] = groupAvatarFor(
          entry.key,
          version: _int(conversation['groupAvatarVersion']),
        );
      }
    }
  }

  static bool _hasAvatarMediaObject(ChatFixtureObject row) =>
      _text(row['avatarUrl']).toLowerCase().startsWith('media/avatar/');
}

ChatFixtureObject _asObject(Object? value) {
  if (value is! Map) {
    return <String, Object?>{};
  }
  return value.map<String, Object?>(
    (key, item) => MapEntry(key.toString(), item),
  );
}

List<ChatFixtureObject> _objectList(Object? value) {
  if (value is! List) {
    return <ChatFixtureObject>[];
  }
  return value.whereType<Map>().map(_asObject).toList(growable: false);
}

Map<String, List<ChatFixtureObject>> _objectListMap(Object? value) {
  final object = _asObject(value);
  return <String, List<ChatFixtureObject>>{
    for (final entry in object.entries) entry.key: _objectList(entry.value),
  };
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    return const <String>[];
  }
  return value
      .map(_text)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

ChatFixtureObject _copy(ChatFixtureObject value) =>
    Map<String, Object?>.from(value);

String _text(Object? value) => value?.toString().trim() ?? '';

int _int(Object? value, {int fallback = 0}) =>
    value is num ? value.toInt() : fallback;

int _positiveInt(Object? value, {required int fallback}) {
  final parsed = _int(value);
  return parsed > 0 ? parsed : fallback;
}

bool _bool(Object? value, {bool fallback = false}) =>
    value is bool ? value : fallback;

DateTime? _date(Object? value) {
  if (value is DateTime) {
    return value;
  }
  return DateTime.tryParse(_text(value));
}

String _firstText(Iterable<Object?> values) {
  for (final value in values) {
    final text = _text(value);
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}
