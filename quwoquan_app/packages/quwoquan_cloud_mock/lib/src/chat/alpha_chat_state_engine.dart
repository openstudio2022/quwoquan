library;

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/chat_contracts.dart';
import 'package:quwoquan_cloud_mock/src/generated/alpha_fixture_bundle.g.dart';

part 'alpha_chat_state_engine_conversations.dart';
part 'alpha_chat_state_engine_groups.dart';
part 'alpha_chat_state_engine_messages.dart';

typedef ChatFixtureObject = Map<String, Object?>;

final class ChatFixtureSyncPage {
  const ChatFixtureSyncPage({required this.messages, required this.hasMore});

  final List<ChatFixtureObject> messages;
  final bool hasMore;
}

/// Alpha/test 共用的纯 Dart chat fixture 与可变状态引擎。
///
/// 真相数据来自构建期生成的 [AlphaFixtureBundle]。该类不依赖 Flutter、
/// `quwoquan_app` DTO 或 production composition；App runner/test 只负责薄 DTO 映射。
final class AlphaChatStateEngine {
  AlphaChatStateEngine({
    AlphaFixtureBundle bundle = alphaFixtureBundle,
    List<ChatFixtureObject>? seedConversations,
    Map<String, List<ChatFixtureObject>>? seedMembers,
    Map<String, List<ChatFixtureObject>>? seedMessages,
  }) {
    final chatRoot = _fixtureRoot(bundle, 'chat');
    final seedSets = _asObject(chatRoot['seedSets']);
    final core = _asObject(seedSets['chat_core']);
    final contacts = _asObject(seedSets['chat_contacts_core']);
    final settings = _asObject(seedSets['chat_settings_core']);

    currentUserId = _text(core['currentUserId']);
    if (currentUserId.isEmpty) {
      throw const FormatException('chat_core.currentUserId is required');
    }

    final conversationRows =
        seedConversations ?? _objectList(core['conversations']);
    for (final row in conversationRows) {
      final id = _text(row['id']);
      if (id.isNotEmpty) {
        _conversations[id] = _copy(row);
      }
    }

    final memberRows = seedMembers ?? _objectListMap(core['members']);
    for (final entry in memberRows.entries) {
      _members[entry.key] = entry.value.map(_copy).toList(growable: true);
    }

    final messageRows = seedMessages ?? _objectListMap(core['messages']);
    for (final entry in messageRows.entries) {
      _messages[entry.key] = entry.value.map(_copy).toList(growable: true);
    }

    for (final row in _objectList(core['userStates'])) {
      if (_text(row['userId']) == currentUserId) {
        final conversationId = _text(row['conversationId']);
        if (conversationId.isNotEmpty) {
          _userStates[conversationId] = _copy(row);
        }
      }
    }

    _contacts.addAll(
      _objectList(contacts['contacts']).where(_hasAvatarMediaObject).map(_copy),
    );
    _contactCircleIds.addAll(_stringList(contacts['circleIds']));
    _contactGroupConversationIds.addAll(
      _stringList(contacts['groupConversationIds']),
    );

    for (final row in _objectList(settings['settings'])) {
      final conversationId = _text(row['conversationId']);
      if (conversationId.isNotEmpty) {
        _groupSettings[conversationId] = _copy(row);
      }
    }

    _circleRows.addAll(_readCircleRows(bundle));
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
  final Map<String, _AlphaChatSendReceipt> _sendReceipts =
      <String, _AlphaChatSendReceipt>{};

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

  static ChatFixtureObject _fixtureRoot(
    AlphaFixtureBundle bundle,
    String assetId,
  ) {
    final asset = bundle.assets[assetId];
    if (asset == null) {
      throw StateError('$assetId alpha fixture asset is missing');
    }
    return _asObject(jsonDecode(asset.sourceJson));
  }

  static List<ChatFixtureObject> _readCircleRows(AlphaFixtureBundle bundle) {
    final root = _fixtureRoot(bundle, 'circle');
    final seedSets = _asObject(root['seedSets']);
    final core = _asObject(seedSets['circle_core']);
    return _objectList(core['circles']).map(_copy).toList(growable: false);
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
