import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';

final class ChatRehearsalHandler implements RehearsalObjectHandler {
  const ChatRehearsalHandler();

  @override
  Stream<Object?>? stream(RehearsalInvocation invocation) => null;

  @override
  Future<Object?> handle(RehearsalInvocation invocation) {
    final id = invocation.operation.canonicalOperationId;
    return switch (id) {
      'chat.conversation.CreateConversation' => _createConversation(invocation),
      'chat.conversation.GetConversation' => _getConversation(invocation),
      'chat.conversation.ListConversations' => _listConversations(invocation),
      'chat.conversation.BatchGetConversations' => _batchGet(invocation),
      'chat.conversation.UpdateConversationTitle' => _updateConversation(
        invocation,
        'title',
      ),
      'chat.conversation.UpdateAnnouncement' => _updateConversation(
        invocation,
        'announcement',
      ),
      'chat.conversation.UpdateGroupGovernanceSettings' => _updateGovernance(
        invocation,
      ),
      'chat.conversation.DissolveConversation' => _dissolve(invocation),
      'chat.conversation_membership.AddMembers' => _addMembers(invocation),
      'chat.conversation_membership.ListMembers' => _listMembers(invocation),
      'chat.conversation_membership.RemoveMember' => _removeMember(invocation),
      'chat.conversation_membership.LeaveConversation' => _leave(invocation),
      'chat.conversation_membership.TransferOwnership' => _transfer(invocation),
      'chat.conversation_membership.UpdateGroupAdmins' => _updateAdmins(
        invocation,
      ),
      'chat.conversation_membership.InviteAssistant' => _assistantMembership(
        invocation,
        true,
      ),
      'chat.conversation_membership.RemoveAssistant' => _assistantMembership(
        invocation,
        false,
      ),
      'chat.conversation_user_state.MarkAsRead' => _markRead(invocation),
      'chat.conversation_user_state.UpdateConversationSettings' =>
        _updateUserSettings(invocation),
      'chat.chat_inbox_view.ListInbox' => _listInbox(invocation),
      'chat.message.SendMessage' => _sendMessage(invocation),
      'chat.message.ListMessages' => _listMessages(invocation),
      'chat.message.SyncMessages' => _syncMessages(invocation),
      'chat.message.RecallMessage' => _recall(invocation),
      'chat.message_receipt_fact.GetReceipts' => _getReceipts(invocation),
      _ => _generic(invocation),
    };
  }

  Future<Object?> _createConversation(RehearsalInvocation invocation) {
    invocation.requireActor();
    return invocation.store.commit(() {
      final conversationId = invocation.nextId('conv_');
      final members = <String>{
        invocation.actorId,
        ...((invocation.body['initialMemberIds'] as List?) ?? const []).map(
          (item) => '$item',
        ),
      };
      final now = invocation.now().toUtc().toIso8601String();
      final type = '${invocation.body['type'] ?? 'direct'}';
      if ((type == 'direct' && members.length != 2) ||
          (type == 'group' && (members.length < 2 || members.length > 200)) ||
          !const {'direct', 'group'}.contains(type)) {
        _fail('CHAT.USER.invalid_argument');
      }
      final wire = <String, Object?>{
        'avatarUrl': '',
        'groupAvatarVersion': 0,
        'circleId': '',
        'circleGroupId': '',
        'gatheringId': '',
        'gatheringSourceVersion': 0,
        'gatheringSourceEventId': '',
        'accessMode': 'active',
        'postingPolicy': 'member_chat',
        'entityId': '',
        'originType': 'direct',
        'intersectionFacts': <Object>[],
        'maxSeq': 0,
        'membersRosterRevision': 1,
        'maxGroupSize': type == 'direct' ? 2 : 200,
        'receiptEnabled': type == 'group',
        'announcement': '',
        'announcementUpdatedBy': '',
        'nameEditableByAdminOnly': false,
        'lastMessageId': '',
        'lastMessagePreview': '',
        'lastMessageType': 'text',
        'lastMessageTime': now,
        'messageCount': 0,
      };
      wire['id'] = conversationId;
      wire['conversationId'] = conversationId;
      wire['type'] = type;
      wire['title'] = invocation.body['title'] ?? '';
      wire['creatorId'] = invocation.actorId;
      wire['memberCount'] = members.length;
      wire['createdAt'] = now;
      wire['updatedAt'] = now;
      wire['status'] = 'active';
      invocation.store.conversations[conversationId] = <String, Object?>{
        ...wire,
        'memberIds': members.toList(growable: false),
        'adminIds': <String>[],
        'assistantInvited': false,
        'joinedAt': <String, Object?>{
          for (final member in members) member: now,
        },
      };
      return wire;
    });
  }

  Future<Object?> _getConversation(RehearsalInvocation invocation) async {
    invocation.requireActor();
    final id = invocation.path('conversationId');
    final row = invocation.store.conversations[id];
    if (row == null) {
      throw localDomainCloudException('CHAT.USER.conversation_not_found');
    }
    _requireMember(invocation, row);
    return _publicConversation(row);
  }

  Future<Object?> _listConversations(RehearsalInvocation invocation) async {
    invocation.requireActor();
    final items = invocation.store.conversations.values
        .where((row) {
          final members = (row['memberIds'] as List?) ?? const [];
          return members.contains(invocation.actorId);
        })
        .map(_publicConversation)
        .toList(growable: false);
    items.sort((a, b) => '${b['updatedAt']}'.compareTo('${a['updatedAt']}'));
    return _page(invocation, items, maximum: 50);
  }

  Future<Object?> _sendMessage(RehearsalInvocation invocation) {
    invocation.requireActor();
    return invocation.store.commit(() {
      final conversationId = invocation.path('conversationId');
      final conversation = invocation.store.conversations[conversationId];
      if (conversation == null) {
        throw localDomainCloudException('CHAT.USER.conversation_not_found');
      }
      _requireMember(invocation, conversation);
      final seq =
          invocation.store.messages.values
              .where((row) => row['conversationId'] == conversationId)
              .length +
          1;
      final messageId = invocation.nextId('msg_');
      final now = invocation.now().toUtc().toIso8601String();
      final message = <String, Object?>{
        'id': messageId,
        'conversationId': conversationId,
        'seq': seq,
        'clientMsgId': invocation.body['clientMsgId'] ?? messageId,
        'senderId': invocation.actorId,
        'type': invocation.body['type'] ?? 'text',
        'content': invocation.body['content'] ?? '',
        'status': 'sent',
        if (invocation.body['replyToMessageId'] != null)
          'replyToMessageId': invocation.body['replyToMessageId'],
        if (invocation.body['mentions'] is List)
          'mentions': List<Object?>.from(invocation.body['mentions'] as List),
        'timestamp': now,
      };
      invocation.store.messages[messageId] = message;
      conversation['maxSeq'] = seq;
      conversation['lastMessageId'] = messageId;
      conversation['lastMessagePreview'] = message['content'];
      conversation['lastMessageType'] = message['type'];
      conversation['lastMessageTime'] = now;
      conversation['messageCount'] = seq;
      conversation['updatedAt'] = now;
      return <String, Object?>{
        'messageId': messageId,
        'seq': seq,
        'timestamp': now,
      };
    });
  }

  Future<Object?> _listMessages(RehearsalInvocation invocation) async {
    invocation.requireActor();
    final conversationId = invocation.path('conversationId');
    final conversation = invocation.store.conversations[conversationId];
    if (conversation == null) {
      throw localDomainCloudException('CHAT.USER.conversation_not_found');
    }
    _requireMember(invocation, conversation);
    final items =
        invocation.store.messages.values
            .where((row) => row['conversationId'] == conversationId)
            .toList(growable: false)
          ..sort(
            (a, b) => ((a['seq'] as num?)?.toInt() ?? 0).compareTo(
              (b['seq'] as num?)?.toInt() ?? 0,
            ),
          );
    final after = int.tryParse(invocation.query('afterSeq'));
    final before = int.tryParse(invocation.query('beforeSeq'));
    final filtered = items
        .where((row) {
          final seq = (row['seq'] as num).toInt();
          return (after == null || seq > after) &&
              (before == null || seq < before);
        })
        .toList(growable: false);
    return _page(invocation, filtered, maximum: 200);
  }

  Future<Object?> _recall(RehearsalInvocation invocation) {
    invocation.requireActor();
    return invocation.store.commit(() {
      final messageId = invocation.path('messageId');
      final row = invocation.store.messages[messageId];
      if (row == null) {
        throw localDomainCloudException('CHAT.USER.message_not_found');
      }
      if (row['senderId'] != invocation.actorId) {
        throw localDomainCloudException('CHAT.USER.message_recall_forbidden');
      }
      row['status'] = 'recalled';
      row['recalledAt'] = invocation.now().toUtc().toIso8601String();
      row['content'] = null;
      return <String, Object?>{'status': 'recalled'};
    });
  }

  Future<Object?> _batchGet(RehearsalInvocation i) async {
    i.requireActor();
    final ids = _strings(i.body['conversationIds']);
    return <String, Object?>{
      'items': [
        for (final id in ids)
          if (i.store.conversations[id] case final row?)
            if (_isMember(i, row)) _publicConversation(row),
      ],
    };
  }

  Future<Object?> _updateConversation(RehearsalInvocation i, String field) =>
      i.store.commit(() {
        final row = _conversation(i);
        _requireActive(row);
        if (field == 'announcement') _requireAdmin(i, row);
        if (field == 'title' && row['nameEditableByAdminOnly'] == true) {
          _requireAdmin(i, row);
        }
        final value = '${i.body[field] ?? ''}'.trim();
        if (value.length > (field == 'announcement' ? 2000 : 100)) {
          _fail('CHAT.USER.message_too_long');
        }
        final now = i.now().toUtc().toIso8601String();
        row[field] = value;
        if (field == 'announcement') {
          row['announcementUpdatedBy'] = i.actorId;
          row['announcementUpdatedAt'] = now;
        }
        row['updatedAt'] = now;
        return _publicConversation(row);
      });

  Future<Object?> _updateGovernance(RehearsalInvocation i) =>
      i.store.commit(() {
        final row = _conversation(i);
        _requireAdmin(i, row);
        _requireGroup(row);
        for (final field in ['nameEditableByAdminOnly', 'receiptEnabled']) {
          if (i.body.containsKey(field)) {
            if (i.body[field] is! bool) _fail('CHAT.USER.invalid_argument');
            row[field] = i.body[field];
          }
        }
        row['updatedAt'] = i.now().toUtc().toIso8601String();
        return _publicConversation(row);
      });

  Future<Object?> _dissolve(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    _requireOwner(i, row);
    _requireGroup(row);
    row['status'] = 'dissolved';
    row['updatedAt'] = i.now().toUtc().toIso8601String();
    return <String, Object?>{'status': 'dissolved'};
  });

  Future<Object?> _addMembers(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    _requireMember(i, row);
    _requireActive(row);
    _requireGroup(row);
    final members = List<String>.from(row['memberIds'] as List);
    final additions = _strings(i.body['userIds'] ?? i.body['memberIds']);
    if (members.toSet().union(additions.toSet()).length >
        (row['maxGroupSize'] as int)) {
      _fail('CHAT.USER.group_full');
    }
    final joined = Map<String, Object?>.from(row['joinedAt'] as Map);
    for (final id in additions) {
      if (!members.contains(id)) {
        members.add(id);
        joined[id] = i.now().toUtc().toIso8601String();
      }
    }
    row['memberIds'] = members;
    row['joinedAt'] = joined;
    _touchRoster(i, row);
    return <String, Object?>{'status': 'updated'};
  });

  Future<Object?> _listMembers(RehearsalInvocation i) async {
    final row = _conversation(i);
    final role = i.query('role');
    final admins = Set<String>.from(row['adminIds'] as List);
    final joined = row['joinedAt'] as Map;
    var members = List<String>.from(row['memberIds'] as List);
    if (role.isNotEmpty) {
      members = members.where((id) => _role(row, admins, id) == role).toList();
    }
    final q = i.query('query').toLowerCase();
    if (q.isNotEmpty) {
      members = members.where((id) => id.toLowerCase().contains(q)).toList();
    }
    final items = [
      for (final id in members)
        <String, Object?>{
          'userId': id,
          'userHandle': id,
          'displayName': id,
          'avatarUrl': '',
          'role': _role(row, admins, id),
          'memberType': 'user',
          'joinedAt': joined[id],
          'isCurrentUser': id == i.actorId,
        },
    ];
    return _page(i, items, maximum: 50);
  }

  Future<Object?> _removeMember(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    _requireAdmin(i, row);
    _requireGroup(row);
    final target = i.path('userId');
    if (target == row['creatorId']) {
      _fail('CHAT.USER.group_governance_forbidden');
    }
    _remove(row, target);
    _touchRoster(i, row);
    return <String, Object?>{'status': 'updated'};
  });
  Future<Object?> _leave(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    _requireGroup(row);
    if (row['creatorId'] == i.actorId) {
      _fail('CHAT.USER.group_owner_must_transfer_before_leave');
    }
    _remove(row, i.actorId);
    _touchRoster(i, row);
    return <String, Object?>{'status': 'left'};
  });
  Future<Object?> _transfer(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    _requireOwner(i, row);
    _requireGroup(row);
    final target = '${i.body['userId'] ?? i.body['newOwnerId'] ?? ''}';
    if (!(row['memberIds'] as List).contains(target)) {
      _fail('CHAT.USER.group_governance_forbidden');
    }
    row['creatorId'] = target;
    final admins = List<String>.from(row['adminIds'] as List)..remove(target);
    row['adminIds'] = admins;
    _touchRoster(i, row);
    return <String, Object?>{'status': 'updated'};
  });
  Future<Object?> _updateAdmins(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    _requireOwner(i, row);
    _requireGroup(row);
    final admins = _strings(i.body['adminIds']);
    if (admins.any(
      (id) =>
          !(row['memberIds'] as List).contains(id) || id == row['creatorId'],
    )) {
      _fail('CHAT.USER.group_governance_forbidden');
    }
    row['adminIds'] = admins;
    _touchRoster(i, row);
    return <String, Object?>{'status': 'updated'};
  });
  Future<Object?> _assistantMembership(RehearsalInvocation i, bool invited) =>
      i.store.commit(() {
        final row = _conversation(i);
        _requireMember(i, row);
        _requireGroup(row);
        row['assistantInvited'] = invited;
        _touchRoster(i, row);
        return <String, Object?>{'status': invited ? 'invited' : 'removed'};
      });

  Future<Object?> _markRead(RehearsalInvocation i) => i.store.commit(() {
    final row = _conversation(i);
    final message = i.store.messages[i.path('messageId')];
    if (message == null || message['conversationId'] != row['conversationId']) {
      _fail('CHAT.USER.message_not_found');
    }
    final states = _records(i, 'chat.user_state');
    final key = '${i.actorId}::${row['conversationId']}';
    final now = i.now().toUtc().toIso8601String();
    states[key] = <String, Object?>{
      'actorId': i.actorId,
      'conversationId': row['conversationId'],
      'lastReadSeq': message['seq'],
      'readAt': now,
      ...?states[key],
    };
    states[key]!['lastReadSeq'] = message['seq'];
    states[key]!['readAt'] = now;
    return <String, Object?>{'status': 'read'};
  });

  Future<Object?> _updateUserSettings(RehearsalInvocation i) =>
      i.store.commit(() {
        final row = _conversation(i);
        final states = _records(i, 'chat.user_state');
        final key = '${i.actorId}::${row['conversationId']}';
        final old = states[key] ?? <String, Object?>{};
        states[key] = <String, Object?>{
          ...old,
          'actorId': i.actorId,
          'conversationId': row['conversationId'],
          'muted': i.body['muted'] ?? old['muted'] ?? false,
          'pinned': i.body['pinned'] ?? old['pinned'] ?? false,
          'settingsUpdatedAt': i.now().toUtc().toIso8601String(),
        };
        return <String, Object?>{'status': 'updated'};
      });

  Future<Object?> _listInbox(RehearsalInvocation i) async {
    i.requireActor();
    final states = _records(i, 'chat.user_state');
    final rows = i.store.conversations.values
        .where((r) => _isMember(i, r) && r['status'] == 'active')
        .map((r) {
          final st =
              states['${i.actorId}::${r['conversationId']}'] ??
              const <String, Object?>{};
          final read = (st['lastReadSeq'] as num?)?.toInt() ?? 0;
          return <String, Object?>{
            'id': r['conversationId'],
            'type': r['type'],
            'title': r['title'],
            'avatarUrl': r['avatarUrl'],
            'groupAvatarVersion': r['groupAvatarVersion'],
            'lastMessagePreview': r['lastMessagePreview'],
            'lastMessageType': r['lastMessageType'],
            'lastMessageTime': r['lastMessageTime'],
            'lastSeq': r['maxSeq'],
            'unreadCount': ((r['maxSeq'] as int) - read).clamp(0, 1 << 31),
            'mentionUnreadCount': 0,
            'muted': st['muted'] ?? false,
            'pinned': st['pinned'] ?? false,
            if ('${r['circleId']}'.isNotEmpty) 'circleId': r['circleId'],
          };
        })
        .toList();
    rows.sort(
      (a, b) => ('${b['pinned']}|${b['lastMessageTime']}').compareTo(
        '${a['pinned']}|${a['lastMessageTime']}',
      ),
    );
    return _page(i, rows, maximum: 50);
  }

  Future<Object?> _syncMessages(RehearsalInvocation i) async {
    final row = _conversation(i);
    final after = (i.body['afterSeq'] as num?)?.toInt() ?? 0;
    final limit = ((i.body['limit'] as num?)?.toInt() ?? 500).clamp(1, 500);
    final all =
        i.store.messages.values
            .where(
              (m) =>
                  m['conversationId'] == row['conversationId'] &&
                  (m['seq'] as int) > after,
            )
            .toList()
          ..sort((a, b) => (a['seq'] as int).compareTo(b['seq'] as int));
    return <String, Object?>{
      'messages': all.take(limit).toList(),
      'hasMore': all.length > limit,
    };
  }

  Future<Object?> _getReceipts(RehearsalInvocation i) async {
    final row = _conversation(i);
    final mid = i.path('messageId');
    if (i.store.messages[mid]?['conversationId'] != row['conversationId']) {
      _fail('CHAT.USER.message_not_found');
    }
    final states = _records(i, 'chat.user_state');
    final seq = i.store.messages[mid]!['seq'] as int;
    return <String, Object?>{
      'items': [
        for (final st in states.values)
          if (st['conversationId'] == row['conversationId'] &&
              ((st['lastReadSeq'] as num?)?.toInt() ?? 0) >= seq)
            <String, Object?>{
              'id': '$mid::${st['actorId']}',
              'messageId': mid,
              'conversationId': row['conversationId'],
              'userId': st['actorId'],
              'readAt': st['readAt'],
            },
      ],
    };
  }

  Map<String, Map<String, Object?>> _records(
    RehearsalInvocation i,
    String key,
  ) => i.store.records.putIfAbsent(key, () => <String, Map<String, Object?>>{});
  Map<String, Object?> _conversation(RehearsalInvocation i) {
    i.requireActor();
    final row = i.store.conversations[i.path('conversationId')];
    if (row == null) _fail('CHAT.USER.conversation_not_found');
    _requireMember(i, row);
    return row;
  }

  Map<String, Object?> _publicConversation(Map<String, Object?> row) =>
      Map<String, Object?>.from(row)
        ..remove('memberIds')
        ..remove('adminIds')
        ..remove('assistantInvited')
        ..remove('joinedAt');
  bool _isMember(RehearsalInvocation i, Map<String, Object?> row) =>
      (row['memberIds'] as List).contains(i.actorId);
  void _requireActive(Map<String, Object?> row) {
    if (row['status'] != 'active') _fail('CHAT.USER.conversation_dissolved');
  }

  void _requireGroup(Map<String, Object?> row) {
    if (row['type'] != 'group') _fail('CHAT.USER.group_governance_forbidden');
  }

  void _requireOwner(RehearsalInvocation i, Map<String, Object?> row) {
    if (row['creatorId'] != i.actorId) {
      _fail('CHAT.USER.group_governance_forbidden');
    }
  }

  void _requireAdmin(RehearsalInvocation i, Map<String, Object?> row) {
    if (row['creatorId'] != i.actorId &&
        !(row['adminIds'] as List).contains(i.actorId)) {
      _fail('CHAT.USER.group_governance_forbidden');
    }
  }

  String _role(Map<String, Object?> row, Set<String> admins, String id) =>
      id == row['creatorId']
      ? 'owner'
      : admins.contains(id)
      ? 'admin'
      : 'member';
  void _remove(Map<String, Object?> row, String id) {
    (row['memberIds'] as List).remove(id);
    (row['adminIds'] as List).remove(id);
    (row['joinedAt'] as Map).remove(id);
  }

  void _touchRoster(RehearsalInvocation i, Map<String, Object?> row) {
    row['memberCount'] = (row['memberIds'] as List).length;
    row['membersRosterRevision'] = (row['membersRosterRevision'] as int) + 1;
    row['updatedAt'] = i.now().toUtc().toIso8601String();
  }

  List<String> _strings(Object? value) {
    if (value is! List) _fail('CHAT.USER.invalid_argument');
    final result = value
        .map((e) => '$e'.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList();
    if (result.isEmpty) _fail('CHAT.USER.invalid_argument');
    return result;
  }

  Map<String, Object?> _page(
    RehearsalInvocation i,
    List<Map<String, Object?>> items, {
    required int maximum,
  }) {
    final limit = (int.tryParse(i.query('limit')) ?? maximum).clamp(1, maximum);
    final cursor = i.query('cursor');
    var offset = 0;
    if (cursor.isNotEmpty) {
      try {
        final d = jsonDecode(
          utf8.decode(base64Url.decode(base64Url.normalize(cursor))),
        ) as Map;
        if (d['actor'] != i.actorId) throw const FormatException();
        offset = d['offset'] as int;
      } catch (_) {
        _fail('CHAT.USER.invalid_argument');
      }
    }
    final end = (offset + limit).clamp(0, items.length);
    return <String, Object?>{
      'items': items.sublist(offset, end),
      if (end < items.length)
        'nextCursor': base64Url.encode(
          utf8.encode(jsonEncode({'actor': i.actorId, 'offset': end})),
        ),
    };
  }

  Never _fail(String code) => throw localDomainCloudException(code);

  Future<Object?> _generic(RehearsalInvocation invocation) async {
    if (invocation.operation.authMode == 'required') {
      invocation.requireActor();
    }
    return rehearsalUnsupported();
  }

  void _requireMember(
    RehearsalInvocation invocation,
    Map<String, Object?> conversation,
  ) {
    final members = (conversation['memberIds'] as List?) ?? const [];
    if (!members.contains(invocation.actorId)) {
      rehearsalUnauthorized();
    }
  }
}
