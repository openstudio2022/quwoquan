part of 'alpha_chat_state_engine.dart';

extension AlphaChatConversationState on AlphaChatStateEngine {
  List<ChatFixtureObject> listInbox({int limit = 20}) {
    final rows = <ChatFixtureObject>[];
    for (final conversation in _conversations.values) {
      final status = _text(conversation['status']);
      if (status != 'active' && status != 'blocked') {
        continue;
      }
      final id = _text(conversation['id']);
      final state = _stateFor(id);
      final messages = _messagesFor(id);
      final lastMessage = _lastMessage(messages);
      rows.add(<String, Object?>{
        'id': id,
        'type': _text(conversation['type']),
        'title': _text(conversation['title']),
        'avatarUrl': _text(conversation['avatarUrl']),
        'groupAvatarVersion': _int(conversation['groupAvatarVersion']),
        'lastMessagePreview': _firstText(<Object?>[
          conversation['lastMessagePreview'],
          lastMessage?['content'],
        ]),
        'lastMessageType': _firstText(<Object?>[lastMessage?['type'], 'text']),
        'lastMessageTime': _firstText(<Object?>[
          conversation['lastMessageTime'],
          lastMessage?['timestamp'],
        ]),
        'lastSeq': _positiveInt(
          conversation['lastSeq'],
          fallback: _int(conversation['maxSeq']),
        ),
        'unreadCount': _int(state['unreadCount']),
        'mentionUnreadCount': _int(state['mentionUnreadCount']),
        'muted': _bool(state['muted']),
        'pinned': _bool(state['pinned']),
        'circleId': _text(conversation['circleId']),
      });
    }
    rows.sort((a, b) {
      final aPinned = _bool(a['pinned']);
      final bPinned = _bool(b['pinned']);
      if (aPinned != bPinned) {
        return aPinned ? -1 : 1;
      }
      final timeCompare = _text(
        b['lastMessageTime'],
      ).compareTo(_text(a['lastMessageTime']));
      if (timeCompare != 0) {
        return timeCompare;
      }
      return _text(a['title']).compareTo(_text(b['title']));
    });
    return _take(rows, limit);
  }

  List<ChatFixtureObject> listMessageHome({
    String filter = 'all',
    int limit = 20,
  }) {
    final rows = <ChatFixtureObject>[];
    for (final inbox in listInbox(limit: 0)) {
      final include = switch (filter) {
        'unread' => _int(inbox['unreadCount']) > 0,
        'group' => _text(inbox['type']) == 'group',
        'direct' =>
          _text(inbox['type']) == 'direct' ||
              _text(inbox['type']) == 'encrypted',
        'notification' => false,
        _ => true,
      };
      if (!include) {
        continue;
      }
      rows.add(<String, Object?>{
        'id': inbox['id'],
        'kind': 'conversation',
        'conversationId': inbox['id'],
        'notificationId': '',
        'conversationType': inbox['type'],
        'title': inbox['title'],
        'summary': inbox['lastMessagePreview'],
        'avatarUrl': inbox['avatarUrl'],
        'groupAvatarVersion': inbox['groupAvatarVersion'],
        'lastActiveAt': inbox['lastMessageTime'],
        'unreadCount': inbox['unreadCount'],
        'mentionUnreadCount': inbox['mentionUnreadCount'],
        'muted': inbox['muted'],
        'pinned': inbox['pinned'],
        'notificationType': '',
        'read': _int(inbox['unreadCount']) == 0,
      });
    }
    return _take(rows, limit);
  }

  List<ChatFixtureObject> listConversations({int limit = 20}) =>
      listInbox(limit: limit);

  ChatFixtureObject createConversation({
    required String type,
    String? title,
    String? circleId,
    String? circleGroupId,
    String? originType,
    String? bindingType,
    String? lifecyclePolicy,
    int? maxGroupSize,
    List<String>? initialMemberIds,
  }) {
    final memberIds = initialMemberIds ?? const <String>[];
    final resolvedMaxGroupSize = type == 'group' ? maxGroupSize ?? 1000 : 2;
    if (resolvedMaxGroupSize > 1000 ||
        (type == 'group' && memberIds.length + 1 > resolvedMaxGroupSize)) {
      throw StateError('CHAT.USER.group_full');
    }
    if ((type == 'direct' || type == 'encrypted') && memberIds.length == 1) {
      final reused = _matchDirectConversationId(memberIds.first);
      if (reused.isNotEmpty) {
        return <String, Object?>{'conversationId': reused};
      }
    }

    _newConversationSerial += 1;
    final id = 'fixture_conv_created_$_newConversationSerial';
    final now = _now().toIso8601String();
    final normalizedCircleId = circleId?.trim() ?? '';
    final normalizedCircleGroupId = circleGroupId?.trim() ?? '';
    final conversation = <String, Object?>{
      'id': id,
      'type': type,
      'title': title?.trim() ?? '',
      'avatarUrl': type == 'group' ? groupAvatarFor(id) : '',
      'groupAvatarVersion': type == 'group' ? 1 : 0,
      'creatorId': currentUserId,
      'circleId': normalizedCircleId,
      if (normalizedCircleGroupId.isNotEmpty)
        'circleGroupId': normalizedCircleGroupId,
      'originType':
          originType ??
          _defaultOriginType(type, normalizedCircleId, normalizedCircleGroupId),
      'bindingType':
          bindingType ??
          _defaultBindingType(normalizedCircleId, normalizedCircleGroupId),
      'lifecyclePolicy':
          lifecyclePolicy ??
          _defaultLifecyclePolicy(normalizedCircleId, normalizedCircleGroupId),
      'maxSeq': 0,
      'lastSeq': 0,
      'memberCount': memberIds.length + 1,
      'maxGroupSize': resolvedMaxGroupSize,
      'receiptEnabled': true,
      'lastMessagePreview': '',
      'lastMessageTime': now,
      'messageCount': 0,
      'status': 'active',
      'createdAt': now,
      'updatedAt': now,
      'membersRosterRevision': 1,
    };
    final members = <ChatFixtureObject>[
      <String, Object?>{
        'userId': currentUserId,
        'displayName': displayNameFor(currentUserId),
        'avatarUrl': avatarFor(currentUserId),
        'role': 'owner',
        'memberType': 'user',
        'isCurrentUser': true,
        'joinedAt': now,
      },
      for (var index = 0; index < memberIds.length; index += 1)
        <String, Object?>{
          'userId': memberIds[index],
          'displayName': displayNameFor(memberIds[index]),
          'avatarUrl': avatarFor(memberIds[index]),
          'role': 'member',
          'memberType': 'user',
          'isCurrentUser': false,
          'joinedAt': _now().toIso8601String(),
        },
    ];
    conversation['groupAvatarSourceHash'] = _groupAvatarSourceHash(members);
    _conversations[id] = conversation;
    _members[id] = members;
    _messages[id] = <ChatFixtureObject>[];
    _stateFor(id);
    if (type == 'group') {
      _contactGroupConversationIds.add(id);
    }
    return <String, Object?>{'conversationId': id};
  }

  ChatFixtureObject getConversation(String conversationId) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      throw StateError('conversation not found: $conversationId');
    }
    return _conversationWire(conversation);
  }

  void updateConversationTitle(String conversationId, String title) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      return;
    }
    conversation['title'] = title;
    conversation['updatedAt'] = _now().toIso8601String();
  }

  void updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      return;
    }
    final state = _stateFor(conversationId);
    if (muted != null) {
      state['muted'] = muted;
    }
    if (pinned != null) {
      state['pinned'] = pinned;
    }
    final now = _now().toIso8601String();
    state['updatedAt'] = now;
    conversation['settingsUpdatedAt'] = now;
    conversation['updatedAt'] = now;
  }

  List<ChatFixtureObject> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) {
    var rows = _messagesFor(conversationId);
    final beforeId = before?.trim() ?? '';
    if (beforeId.isNotEmpty) {
      final pivot = rows.indexWhere((row) => _text(row['id']) == beforeId);
      if (pivot >= 0) {
        rows = rows.take(pivot).toList(growable: false);
      }
    }
    return _take(rows.map(_messageWire).toList(growable: false), limit);
  }

  void recallMessage({
    required String conversationId,
    required String messageId,
  }) {
    final messages = _messagesFor(conversationId);
    final index = messages.indexWhere((row) => _text(row['id']) == messageId);
    if (index < 0) {
      return;
    }
    messages[index]['status'] = 'recalled';
    messages[index]['recalledAt'] = _now().toIso8601String();
  }

  ChatFixtureSyncPage syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = 100,
  }) {
    final all = _messagesFor(conversationId)
        .where((row) => _int(row['seq']) > lastSeq)
        .map(_messageWire)
        .toList(growable: false);
    final page = _take(all, limit);
    return ChatFixtureSyncPage(
      messages: page,
      hasMore: all.length > page.length,
    );
  }

  void markAsRead({required String conversationId, required String messageId}) {
    final state = _stateFor(conversationId);
    final messages = _messagesFor(conversationId);
    ChatFixtureObject? target;
    for (final message in messages) {
      if (_text(message['id']) == messageId) {
        target = message;
        break;
      }
    }
    if (target == null) {
      throw StateError('CHAT.USER.message_not_found');
    }
    final targetSeq = _int(target['seq']);
    if (targetSeq <= _int(state['readSeq'])) {
      return;
    }
    final unread = messages
        .where((message) {
          return _int(message['seq']) > targetSeq &&
              _text(message['senderId']) != currentUserId;
        })
        .toList(growable: false);
    state['readSeq'] = targetSeq;
    state['unreadCount'] = unread.length;
    state['mentionUnreadCount'] = unread.where((message) {
      final mentions = _stringList(message['mentions']);
      return mentions.contains(currentUserId) || mentions.contains('__all__');
    }).length;
    state['lastReadAt'] = _now().toIso8601String();
    state['updatedAt'] = _now().toIso8601String();
  }

  List<ChatFixtureObject> getReceipts({
    required String conversationId,
    required String messageId,
  }) {
    final exists = _messagesFor(
      conversationId,
    ).any((row) => _text(row['id']) == messageId);
    if (!exists) {
      return const <ChatFixtureObject>[];
    }
    return <ChatFixtureObject>[
      <String, Object?>{
        'userId': currentUserId,
        'readAt': _now().toIso8601String(),
      },
    ];
  }

  List<ChatFixtureObject> getConversationTimestamps() {
    return _conversations.values
        .where((conversation) {
          final status = _text(conversation['status']);
          return status == 'active' || status == 'blocked';
        })
        .map((conversation) {
          final id = _text(conversation['id']);
          final state = _stateFor(id);
          final messageTime = _text(conversation['lastMessageTime']);
          return <String, Object?>{
            'conversationId': id,
            'updatedAt': _text(conversation['updatedAt']),
            'settingsUpdatedAt': _firstText(<Object?>[
              conversation['settingsUpdatedAt'],
              state['updatedAt'],
              conversation['updatedAt'],
            ]),
            'lastMessageAt': messageTime,
            'lastMessageTime': messageTime,
            'lastMessagePreview': _text(conversation['lastMessagePreview']),
            'unreadCount': _int(state['unreadCount']),
            'type': _text(conversation['type']),
          };
        })
        .toList(growable: false);
  }

  List<ChatFixtureObject> batchGetConversations(List<String> ids) => ids
      .map(_conversation)
      .whereType<ChatFixtureObject>()
      .map(_conversationWire)
      .toList(growable: false);

  String _matchDirectConversationId(String userId) {
    final target = userId.trim();
    for (final conversation in _conversations.values) {
      final type = _text(conversation['type']);
      if (type != 'direct' && type != 'encrypted') {
        continue;
      }
      final members = _ensureMembers(_text(conversation['id']));
      if (members.any((member) => _text(member['userId']) == target)) {
        return _text(conversation['id']);
      }
    }
    return '';
  }
}

ChatFixtureObject _conversationWire(ChatFixtureObject conversation) {
  final now = DateTime.utc(2026, 7, 20).toIso8601String();
  return <String, Object?>{
    'id': _text(conversation['id']),
    'type': _text(conversation['type']),
    'title': _text(conversation['title']),
    'avatarUrl': _text(conversation['avatarUrl']),
    'groupAvatarVersion': _int(conversation['groupAvatarVersion']),
    'groupAvatarSourceHash': _text(conversation['groupAvatarSourceHash']),
    'creatorId': _text(conversation['creatorId']),
    'circleId': _text(conversation['circleId']),
    if (_text(conversation['circleGroupId']).isNotEmpty)
      'circleGroupId': _text(conversation['circleGroupId']),
    'originType': _firstText(<Object?>[
      conversation['originType'],
      'direct_init',
    ]),
    'bindingType': _firstText(<Object?>[conversation['bindingType'], 'none']),
    'lifecyclePolicy': _firstText(<Object?>[
      conversation['lifecyclePolicy'],
      'persistent',
    ]),
    'maxSeq': _int(conversation['maxSeq']),
    'memberCount': _int(conversation['memberCount']),
    'maxGroupSize': _positiveInt(conversation['maxGroupSize'], fallback: 1000),
    'receiptEnabled': _bool(conversation['receiptEnabled'], fallback: true),
    if (_text(conversation['lastMessageId']).isNotEmpty)
      'lastMessageId': _text(conversation['lastMessageId']),
    'lastMessagePreview': _text(conversation['lastMessagePreview']),
    if (_text(conversation['lastMessageTime']).isNotEmpty)
      'lastMessageTime': _text(conversation['lastMessageTime']),
    'messageCount': _int(conversation['messageCount']),
    'status': _firstText(<Object?>[conversation['status'], 'active']),
    'createdAt': _firstText(<Object?>[conversation['createdAt'], now]),
    'updatedAt': _firstText(<Object?>[conversation['updatedAt'], now]),
    if (conversation['membersRosterRevision'] != null)
      'membersRosterRevision': _int(conversation['membersRosterRevision']),
  };
}

ChatFixtureObject _messageWire(ChatFixtureObject message) {
  return <String, Object?>{
    'id': _text(message['id']),
    'conversationId': _text(message['conversationId']),
    'seq': _int(message['seq']),
    'clientMsgId': _text(message['clientMsgId']),
    'senderId': _text(message['senderId']),
    'senderName': message['senderName']?.toString(),
    'senderAvatar': message['senderAvatar']?.toString(),
    'type': _text(message['type']),
    'content': message['content']?.toString(),
    'mediaAssetId': message['mediaAssetId']?.toString(),
    'mediaDeliveryUrl': message['mediaDeliveryUrl']?.toString(),
    'mediaType': message['mediaType']?.toString(),
    'mediaContentType': message['mediaContentType']?.toString(),
    'mediaFileSizeBytes': message['mediaFileSizeBytes'] is num
        ? (message['mediaFileSizeBytes'] as num).toInt()
        : null,
    'card': message['card'],
    'replyToMessageId': message['replyToMessageId']?.toString(),
    'mentions': message['mentions'] is List
        ? List<String>.unmodifiable(_stringList(message['mentions']))
        : null,
    'status': _firstText(<Object?>[message['status'], 'sent']),
    'recalledAt': message['recalledAt']?.toString(),
    'timestamp': message['timestamp']?.toString(),
  };
}

ChatFixtureObject? _lastMessage(List<ChatFixtureObject> messages) {
  ChatFixtureObject? result;
  var resultSeq = -1;
  for (final message in messages) {
    final seq = _int(message['seq']);
    if (seq >= resultSeq) {
      result = message;
      resultSeq = seq;
    }
  }
  return result;
}

List<ChatFixtureObject> _take(List<ChatFixtureObject> rows, int limit) {
  if (limit <= 0 || rows.length <= limit) {
    return rows.map(_copy).toList(growable: false);
  }
  return rows.take(limit).map(_copy).toList(growable: false);
}

String _groupAvatarSourceHash(List<ChatFixtureObject> members) {
  final sorted = members.map(_copy).toList(growable: true)
    ..sort((left, right) {
      final joined = _text(
        left['joinedAt'],
      ).compareTo(_text(right['joinedAt']));
      return joined != 0
          ? joined
          : _text(left['userId']).compareTo(_text(right['userId']));
    });
  return sorted
      .take(9)
      .map(
        (member) => '${_text(member['userId'])}:${_text(member['avatarUrl'])}',
      )
      .join('|');
}

String _defaultOriginType(String type, String circleId, String circleGroupId) {
  if (type != 'group') {
    return 'direct_init';
  }
  if (circleGroupId.isNotEmpty) {
    return 'circle_self_built_group';
  }
  if (circleId.isNotEmpty) {
    return 'circle_default_group';
  }
  return 'ad_hoc_group';
}

String _defaultBindingType(String circleId, String circleGroupId) {
  if (circleGroupId.isNotEmpty) {
    return 'circle_group';
  }
  if (circleId.isNotEmpty) {
    return 'circle';
  }
  return 'none';
}

String _defaultLifecyclePolicy(String circleId, String circleGroupId) =>
    circleGroupId.isNotEmpty || circleId.isNotEmpty
    ? 'bound_to_circle'
    : 'persistent';
