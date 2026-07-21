part of 'alpha_chat_state_engine.dart';

extension AlphaChatGroupState on AlphaChatStateEngine {
  List<ChatFixtureObject> listMembers({
    required String conversationId,
    int limit = 20,
    String? role,
    String? query,
    String? sort,
  }) {
    var rows = _ensureMembers(conversationId).map(_copy).toList(growable: true);
    _sortMembers(rows, sort);
    final normalizedRole = role?.trim() ?? '';
    if (normalizedRole.isNotEmpty) {
      rows = rows
          .where((member) => _text(member['role']) == normalizedRole)
          .toList(growable: false);
    }
    final normalizedQuery = query?.trim().toLowerCase() ?? '';
    if (normalizedQuery.isNotEmpty) {
      rows = rows
          .where((member) {
            final userId = _text(member['userId']).toLowerCase();
            final displayName = _text(member['displayName']).toLowerCase();
            return userId.contains(normalizedQuery) ||
                displayName.contains(normalizedQuery);
          })
          .toList(growable: false);
    }
    return _take(rows, limit);
  }

  void addMembers({
    required String conversationId,
    required List<String> userIds,
  }) {
    final members = _ensureMembers(conversationId);
    final existing = members.map((member) => _text(member['userId'])).toSet();
    var changed = false;
    for (final userId in userIds.map((item) => item.trim())) {
      if (userId.isEmpty || !existing.add(userId)) {
        continue;
      }
      changed = true;
      members.add(<String, Object?>{
        'userId': userId,
        'displayName': displayNameFor(userId),
        'avatarUrl': avatarFor(userId),
        'role': 'member',
        'memberType': 'user',
        'isCurrentUser': false,
        'joinedAt': _now().toIso8601String(),
      });
    }
    if (changed) {
      _bumpRoster(conversationId);
    }
  }

  void removeMember({required String conversationId, required String userId}) {
    final members = _ensureMembers(conversationId);
    final before = members.length;
    members.removeWhere((member) => _text(member['userId']) == userId);
    if (members.length != before) {
      _bumpRoster(conversationId);
    }
  }

  /// 与云侧 LeaveConversation 同语义：owner 必须先转让；已不在群为 no-op。
  void leaveConversation(String conversationId) {
    final members = _ensureMembers(conversationId);
    final current = members
        .where((member) => _text(member['userId']) == currentUserId)
        .toList(growable: false);
    if (current.isEmpty) {
      return;
    }
    if (_text(current.first['role']) == 'owner') {
      throw StateError('CHAT.USER.group_owner_must_transfer_before_leave');
    }
    removeMember(conversationId: conversationId, userId: currentUserId);
  }

  /// 与云侧 UpdateAnnouncement 同语义：写权威公告并追加
  /// system_announcement 会话消息（公告即触达）。
  void updateAnnouncement(String conversationId, String announcement) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      throw StateError('CHAT.USER.conversation_not_found');
    }
    final settings = _groupSettings.putIfAbsent(
      conversationId,
      () => <String, Object?>{},
    );
    final normalized = announcement.trim();
    if (_text(settings['announcement']) == normalized) {
      return;
    }
    settings['announcement'] = normalized;
    if (normalized.isEmpty) {
      return;
    }
    _appendSystemAnnouncementMessage(conversationId, normalized);
  }

  void _appendSystemAnnouncementMessage(String conversationId, String content) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      return;
    }
    final messages = _messagesFor(conversationId);
    final nextSeq =
        <int>[
          _int(conversation['maxSeq']),
          for (final message in messages) _int(message['seq']),
        ].reduce((left, right) => left > right ? left : right) +
        1;
    final timestamp = _now();
    messages.add(<String, Object?>{
      'id': 'alpha-announcement-$conversationId-$nextSeq',
      'conversationId': conversationId,
      'seq': nextSeq,
      'clientMsgId': 'announcement-$conversationId-$nextSeq',
      'senderId': currentUserId,
      'senderName': displayNameFor(currentUserId),
      'senderAvatar': avatarFor(currentUserId),
      'type': 'system_announcement',
      'content': content,
      'status': 'sent',
      'timestamp': timestamp.toIso8601String(),
    });
    conversation['maxSeq'] = nextSeq;
    conversation['lastSeq'] = nextSeq;
    conversation['lastMessagePreview'] = content;
    conversation['lastMessageTime'] = timestamp.toIso8601String();
    conversation['messageCount'] = messages.length;
    conversation['updatedAt'] = timestamp.toIso8601String();
  }

  List<String> listMemberUserIds(String conversationId) =>
      _ensureMembers(conversationId)
          .map((member) => _text(member['userId']))
          .where((id) => id.isNotEmpty)
          .toList(growable: false);

  void inviteAssistant({required String conversationId, String? skillId}) {
    final members = _ensureMembers(conversationId);
    if (members.any((member) => _text(member['memberType']) == 'assistant')) {
      return;
    }
    members.add(<String, Object?>{
      'userId': 'fixture_assistant_primary',
      'displayName': '契约助手',
      'avatarUrl': avatarFor('fixture_assistant_primary'),
      'role': 'member',
      'memberType': 'assistant',
      if ((skillId ?? '').trim().isNotEmpty)
        'assistantSkillId': skillId!.trim(),
      'isCurrentUser': false,
      'joinedAt': _now().toIso8601String(),
    });
    _bumpRoster(conversationId);
  }

  void removeAssistant({required String conversationId}) {
    final members = _ensureMembers(conversationId);
    final before = members.length;
    members.removeWhere((member) => _text(member['memberType']) == 'assistant');
    if (members.length != before) {
      _bumpRoster(conversationId);
    }
  }

  List<ChatFixtureObject> listContacts({int limit = 20}) =>
      _take(_contacts, limit);

  List<ChatFixtureObject> listContactHome({
    String filter = 'all',
    int limit = 20,
  }) {
    final rows = <ChatFixtureObject>[];
    if (filter == 'all' || filter == 'mutual') {
      for (final contact in _contacts) {
        if (filter == 'mutual' && _text(contact['relationState']) != 'mutual') {
          continue;
        }
        final userId = _text(contact['userId']);
        final subtitle = _firstText(<Object?>[
          contact['bio'],
          contact['metFrom'],
          contact['lastInteraction'],
        ]);
        rows.add(<String, Object?>{
          'id': userId,
          'kind': 'user',
          'objectId': userId,
          'userId': userId,
          'conversationId': _matchDirectConversationId(userId),
          'circleId': '',
          'circleGroupId': '',
          'entityId': '',
          'title': _text(contact['displayName']),
          'subtitle': subtitle,
          'avatarUrl': _text(contact['avatarUrl']),
          'relationState': _text(contact['relationState']),
          'summaryIntersections': subtitle.isEmpty
              ? const <String>[]
              : <String>[subtitle],
          'sourceEntityTitle': '',
          'sourceCircleTitle': '',
          'memberCount': 0,
          'contactCount': 0,
          'lastActiveAt': _text(contact['lastInteraction']),
          'sortKey': _text(contact['lastInteraction']),
          'isStarred': _bool(contact['isStarred']),
        });
      }
    }
    if (filter == 'all' || filter == 'circle') {
      for (final circle in _contactCircles()) {
        final id = _firstText(<Object?>[circle['id'], circle['circleId']]);
        rows.add(<String, Object?>{
          'id': id,
          'kind': 'circle',
          'objectId': id,
          'userId': '',
          'conversationId': '',
          'circleId': id,
          'circleGroupId': '',
          'entityId': '',
          'title': _firstText(<Object?>[circle['name'], circle['displayName']]),
          'subtitle': _text(circle['description']),
          'avatarUrl': _firstText(<Object?>[
            circle['avatarUrl'],
            circle['coverUrl'],
          ]),
          'relationState': 'not_following',
          'summaryIntersections': const <String>[],
          'sourceEntityTitle': '',
          'sourceCircleTitle': '',
          'memberCount': _int(circle['memberCount']),
          'contactCount': 0,
          'lastActiveAt': null,
          'sortKey': '',
          'isStarred': false,
        });
      }
    }
    if (filter == 'all' || filter == 'group') {
      for (final conversation in _contactGroups()) {
        final id = _text(conversation['id']);
        rows.add(<String, Object?>{
          'id': id,
          'kind': 'group',
          'objectId': id,
          'userId': '',
          'conversationId': id,
          'circleId': _text(conversation['circleId']),
          'circleGroupId': _text(conversation['circleGroupId']),
          'entityId': '',
          'title': _text(conversation['title']),
          'subtitle': _text(conversation['lastMessagePreview']),
          'avatarUrl': _text(conversation['avatarUrl']),
          'relationState': 'not_following',
          'summaryIntersections': const <String>[],
          'sourceEntityTitle': '',
          'sourceCircleTitle': '',
          'memberCount': _int(conversation['memberCount']),
          'contactCount': 0,
          'lastActiveAt': conversation['lastMessageTime'],
          'sortKey': _text(conversation['lastMessageTime']),
          'isStarred': false,
        });
      }
    }
    return _take(rows, limit);
  }

  List<ChatFixtureObject> listGroupCandidates({
    String? conversationId,
    int limit = 20,
  }) {
    final locked = <String>{currentUserId};
    final normalizedConversationId = conversationId?.trim() ?? '';
    if (normalizedConversationId.isNotEmpty) {
      locked.addAll(listMemberUserIds(normalizedConversationId));
    }
    final rows = _contacts
        .where(
          (contact) =>
              _text(contact['relationState']) == 'mutual' &&
              !locked.contains(_text(contact['userId'])),
        )
        .map(_copy)
        .toList(growable: false);
    return _take(rows, limit);
  }

  ChatFixtureCursorPage listSelectableGroupConversations({
    String? query,
    String? source,
    String? cursor,
    int limit = 20,
  }) {
    final normalizedQuery = query?.trim().toLowerCase() ?? '';
    final normalizedSource = source?.trim() ?? '';
    if (normalizedSource.isNotEmpty &&
        normalizedSource != 'group' &&
        normalizedSource != 'circle') {
      throw ArgumentError.value(source, 'source', 'must be group or circle');
    }
    final mutualIds = _mutualContactIds();
    final rows = <ChatFixtureObject>[];
    for (final conversation in _conversations.values) {
      if (_text(conversation['type']) != 'group' ||
          _text(conversation['status']) != 'active') {
        continue;
      }
      final title = _text(conversation['title']);
      final circleId = _text(conversation['circleId']);
      if ((normalizedSource == 'group' && circleId.isNotEmpty) ||
          (normalizedSource == 'circle' && circleId.isEmpty)) {
        continue;
      }
      if (normalizedQuery.isNotEmpty &&
          !title.toLowerCase().contains(normalizedQuery)) {
        continue;
      }
      final members = _ensureMembers(_text(conversation['id']));
      final friendIds = members
          .where(
            (member) =>
                _memberType(member) == 'user' &&
                _text(member['userId']) != currentUserId &&
                mutualIds.contains(_text(member['userId'])),
          )
          .map((member) => _text(member['userId']))
          .toSet();
      if (friendIds.isEmpty) {
        continue;
      }
      rows.add(<String, Object?>{
        'conversationId': _text(conversation['id']),
        'title': title,
        'avatarUrl': _text(conversation['avatarUrl']),
        'circleId': circleId,
        'friendMemberCount': friendIds.length,
        'memberCount': _positiveInt(
          conversation['memberCount'],
          fallback: members.length,
        ),
      });
    }
    rows.sort(
      (left, right) => _text(
        left['conversationId'],
      ).compareTo(_text(right['conversationId'])),
    );
    return _fixtureCursorPage(rows, cursor: cursor, limit: limit);
  }

  ChatFixtureCursorPage listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = 20,
  }) {
    if (_conversation(conversationId) == null) {
      return const ChatFixtureCursorPage(items: <ChatFixtureObject>[]);
    }
    final normalizedQuery = query?.trim().toLowerCase() ?? '';
    final mutualIds = _mutualContactIds();
    final contactsById = <String, ChatFixtureObject>{
      for (final contact in _contacts) _text(contact['userId']): contact,
    };
    final rows = <ChatFixtureObject>[];
    final seen = <String>{};
    for (final member in _ensureMembers(conversationId)) {
      final userId = _text(member['userId']);
      if (userId.isEmpty ||
          userId == currentUserId ||
          _memberType(member) != 'user' ||
          !mutualIds.contains(userId) ||
          !seen.add(userId)) {
        continue;
      }
      final contact = contactsById[userId];
      final displayName = _firstText(<Object?>[
        contact?['displayName'],
        member['displayName'],
        userId,
      ]);
      if (normalizedQuery.isNotEmpty &&
          !displayName.toLowerCase().contains(normalizedQuery)) {
        continue;
      }
      rows.add(<String, Object?>{
        'userId': userId,
        'displayName': displayName,
        'avatarUrl': _firstText(<Object?>[
          contact?['avatarUrl'],
          member['avatarUrl'],
        ]),
        'bio': _text(contact?['bio']),
        'metFrom': _text(contact?['metFrom']),
        'lastInteraction': _text(contact?['lastInteraction']),
        'relationState': 'mutual',
        'source': 'group',
        'isStarred': _bool(contact?['isStarred']),
      });
    }
    rows.sort((left, right) {
      final displayName = _text(
        left['displayName'],
      ).compareTo(_text(right['displayName']));
      return displayName != 0
          ? displayName
          : _text(left['userId']).compareTo(_text(right['userId']));
    });
    return _fixtureCursorPage(rows, cursor: cursor, limit: limit);
  }

  ChatFixtureObject getGroupSettings(String conversationId) {
    final conversation = _conversation(conversationId);
    final settings = _groupSettings[conversationId];
    return <String, Object?>{
      'nameEditableByAdminOnly': _bool(settings?['nameEditableByAdminOnly']),
      'conversationType': _firstText(<Object?>[conversation?['type'], 'group']),
      'circleId': _text(conversation?['circleId']),
    };
  }

  ChatFixtureObject getGroupHome(String conversationId) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      return <String, Object?>{};
    }
    final members = _ensureMembers(conversationId);
    final current = members.firstWhere(
      (member) => _bool(member['isCurrentUser']),
      orElse: () => members.isEmpty ? <String, Object?>{} : members.first,
    );
    final role = _text(current['role']);
    final circleId = _text(conversation['circleId']);
    return <String, Object?>{
      'conversationId': conversationId,
      'title': _text(conversation['title']),
      'avatarUrl': _text(conversation['avatarUrl']),
      'groupAvatarVersion': _int(conversation['groupAvatarVersion']),
      'circleId': circleId,
      'circleGroupId': _text(conversation['circleGroupId']),
      'entityId': '',
      'sourceEntityTitle': '',
      'sourceCircleTitle': circleId,
      'memberCount': members.isEmpty
          ? _int(conversation['memberCount'])
          : members.length,
      'announcement': _text(_groupSettings[conversationId]?['announcement']),
      'capabilities': const <String>['album', 'file', 'event', 'member'],
      'originType': _text(conversation['originType']),
      'bindingType': _text(conversation['bindingType']),
      'lifecyclePolicy': _text(conversation['lifecyclePolicy']),
      'canManageMembers': role == 'owner' || role == 'admin',
      'canDissolve': role == 'owner' && circleId.isEmpty,
    };
  }

  void updateGroupSettings(String conversationId, ChatFixtureObject settings) {
    _groupSettings[conversationId] = _copy(settings);
  }

  void transferOwnership(String conversationId, String newOwnerId) {
    final members = _ensureMembers(conversationId);
    for (final member in members) {
      if (_text(member['userId']) == newOwnerId) {
        member['role'] = 'owner';
      } else if (_text(member['role']) == 'owner') {
        member['role'] = 'member';
      }
    }
  }

  void updateGroupAdmins(String conversationId, List<String> adminIds) {
    final adminSet = adminIds.toSet();
    for (final member in _ensureMembers(conversationId)) {
      if (_text(member['role']) == 'owner') {
        continue;
      }
      member['role'] = adminSet.contains(_text(member['userId']))
          ? 'admin'
          : 'member';
    }
  }

  void dissolveConversation(String conversationId) {
    _conversations.remove(conversationId);
    _members.remove(conversationId);
    _messages.remove(conversationId);
    _userStates.remove(conversationId);
    _groupSettings.remove(conversationId);
    _contactGroupConversationIds.remove(conversationId);
  }

  void _bumpRoster(String conversationId) {
    final conversation = _conversation(conversationId);
    if (conversation == null) {
      return;
    }
    final members = _ensureMembers(conversationId);
    conversation['memberCount'] = members.length;
    conversation['membersRosterRevision'] =
        _int(conversation['membersRosterRevision']) + 1;
    conversation['updatedAt'] = _now().toIso8601String();
    if (_text(conversation['type']) != 'group') {
      return;
    }
    final sourceHash = _groupAvatarSourceHash(members);
    if (sourceHash.isEmpty ||
        sourceHash == _text(conversation['groupAvatarSourceHash'])) {
      return;
    }
    final version = _int(conversation['groupAvatarVersion']) + 1;
    conversation['groupAvatarVersion'] = version;
    conversation['groupAvatarSourceHash'] = sourceHash;
    conversation['avatarUrl'] = groupAvatarFor(
      conversationId,
      version: version,
    );
  }

  List<ChatFixtureObject> _contactCircles() {
    if (_contactCircleIds.isEmpty) {
      return const <ChatFixtureObject>[];
    }
    return _circleRows
        .where(
          (circle) => _contactCircleIds.contains(
            _firstText(<Object?>[circle['id'], circle['circleId']]),
          ),
        )
        .map(_copy)
        .toList(growable: false);
  }

  List<ChatFixtureObject> _contactGroups() => _contactGroupConversationIds
      .map(_conversation)
      .whereType<ChatFixtureObject>()
      .map(_copy)
      .toList(growable: false);

  Set<String> _mutualContactIds() => _contacts
      .where((contact) => _text(contact['relationState']) == 'mutual')
      .map((contact) => _text(contact['userId']))
      .where((id) => id.isNotEmpty)
      .toSet();
}

void _sortMembers(List<ChatFixtureObject> members, String? sort) {
  if (sort?.trim() == 'display_name_asc') {
    members.sort((left, right) {
      final leftName = _firstText(<Object?>[
        left['displayName'],
        left['userId'],
      ]);
      final rightName = _firstText(<Object?>[
        right['displayName'],
        right['userId'],
      ]);
      final byName = leftName.compareTo(rightName);
      return byName != 0
          ? byName
          : _text(left['userId']).compareTo(_text(right['userId']));
    });
    return;
  }
  members.sort((left, right) {
    final leftJoined = _date(left['joinedAt'])?.millisecondsSinceEpoch ?? 0;
    final rightJoined = _date(right['joinedAt'])?.millisecondsSinceEpoch ?? 0;
    return leftJoined != rightJoined
        ? leftJoined.compareTo(rightJoined)
        : _text(left['userId']).compareTo(_text(right['userId']));
  });
}

String _memberType(ChatFixtureObject member) =>
    _firstText(<Object?>[member['memberType'], 'user']);
