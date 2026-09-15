part of 'user_handlers.dart';

final class _UserRelationshipHandlerPart {
  const _UserRelationshipHandlerPart();
  Future<Object?> handle(RehearsalInvocation i) =>
      switch (i.operation.canonicalOperationId) {
        'user.persona_relationship.FollowUser' => _follow(i, true),
        'user.persona_relationship.UnfollowUser' => _follow(i, false),
        'user.persona_relationship.BlockUser' => _block(i, true),
        'user.persona_relationship.UnblockUser' => _block(i, false),
        'user.persona_relationship.GetRelationshipCapability' => _capability(i),
        'user.persona_relationship.ListFollowing' => _listPeople(i, true),
        'user.persona_relationship.ListFollowers' => _listPeople(i, false),
        'user.persona_relationship.ListBlockedUsers' => _listBlocked(i),
        'user.subject_follow.FollowSubject' => _subject(i, true),
        'user.subject_follow.UnfollowSubject' => _subject(i, false),
        'user.following_subject.ListFollowingSubjects' => _listSubjects(i),
        'user.followed_subject_visit_state.MarkFollowedSubjectVisited' =>
          _markSubjectVisited(i),
        'user.greeting_request.SendGreetingRequest' => _sendGreeting(i),
        'user.greeting_request.ReplyGreetingRequest' => _decideGreeting(
          i,
          'replied',
        ),
        'user.greeting_request.IgnoreGreetingRequest' => _decideGreeting(
          i,
          'ignored',
        ),
        'user.greeting_request.CancelGreetingRequest' => _decideGreeting(
          i,
          'cancelled',
        ),
        'user.greeting_request.ListGreetingInbox' => _listGreeting(i, true),
        'user.greeting_request.ListGreetingOutbox' => _listGreeting(i, false),
        _ => rehearsalUnsupported(),
      };

  Future<Object?> _follow(RehearsalInvocation i, bool desired) =>
      i.store.commit(() {
        _requireIdentity(i);
        final target = i.path('targetPersonaId').isNotEmpty
            ? i.path('targetPersonaId')
            : _text(i.body, 'targetPersonaId');
        if (target == i.actorId || target.isEmpty) {
          throw localDomainCloudException('USER.USER.invalid_relationship');
        }
        final key = i.store.followKey(i.actorId, target);
        final existed = i.store.follows[key]?['active'] == true;
        if (desired && i.store.blocks[key]?['active'] == true) {
          throw localDomainCloudException('USER.USER.relationship_blocked');
        }
        i.store.follows[key] = {
          'actorPersonaId': i.actorId,
          'targetPersonaId': target,
          'active': desired,
          'updatedAt': _timestamp(i),
        };
        return {
          'actorPersonaId': i.actorId,
          'targetPersonaId': target,
          'relationState': desired ? 'following' : 'not_following',
          'idempotentReplay': desired == existed,
          'updatedAt': _timestamp(i),
        };
      });

  Future<Object?> _block(RehearsalInvocation i, bool desired) =>
      i.store.commit(() {
        _requireIdentity(i);
        final target = i.path('targetPersonaId').isNotEmpty
            ? i.path('targetPersonaId')
            : _text(i.body, 'targetPersonaId');
        if (target == i.actorId || target.isEmpty) {
          throw localDomainCloudException('USER.USER.invalid_relationship');
        }
        final key = i.store.followKey(i.actorId, target);
        final existed = i.store.blocks[key]?['active'] == true;
        i.store.blocks[key] = {
          'actorPersonaId': i.actorId,
          'targetPersonaId': target,
          'active': desired,
          'updatedAt': _timestamp(i),
        };
        if (desired) {
          i.store.follows[key] = {
            'actorPersonaId': i.actorId,
            'targetPersonaId': target,
            'active': false,
            'updatedAt': _timestamp(i),
          };
        }
        return {
          'targetPersonaId': target,
          'blocked': desired,
          'idempotentReplay': desired == existed,
          'updatedAt': _timestamp(i),
        };
      });

  Future<Object?> _capability(RehearsalInvocation i) async {
    final target = i.path('targetPersonaId').isNotEmpty
        ? i.path('targetPersonaId')
        : (i.path('personaId').isNotEmpty
              ? i.path('personaId')
              : _text(i.body, 'targetPersonaId'));
    final viewer = i.actorId;
    final following =
        i.store.follows[i.store.followKey(viewer, target)]?['active'] == true;
    final followedBy =
        i.store.follows[i.store.followKey(target, viewer)]?['active'] == true;
    final blocked =
        i.store.blocks[i.store.followKey(viewer, target)]?['active'] == true;
    final blockedBy =
        i.store.blocks[i.store.followKey(target, viewer)]?['active'] == true;
    final self = viewer.isNotEmpty && viewer == target;
    final pending = _records(i, 'user.greetings').values.any(
      (r) =>
          r['requesterPersonaId'] == viewer &&
          r['targetPersonaId'] == target &&
          r['status'] == 'pending',
    );
    final relation = self
        ? 'self'
        : following && followedBy
        ? 'mutual'
        : following
        ? 'following'
        : followedBy
        ? 'followed_by'
        : 'not_following';
    return {
      'viewerPersonaId': viewer.isEmpty ? 'guest' : viewer,
      'targetPersonaId': target,
      'relationState': relation,
      'canFollow':
          viewer.isNotEmpty && !self && !following && !blocked && !blockedBy,
      'canUnfollow': following,
      'canFollowBack': followedBy && !following && !blocked,
      'canGreet':
          viewer.isNotEmpty && !self && !blocked && !blockedBy && !pending,
      'canOpenConversation': following || followedBy || self,
      'canCreateDirectConversation':
          viewer.isNotEmpty && !self && !blocked && !blockedBy,
      'canSendMessage': following || followedBy || self,
      'hasPendingGreeting': pending,
      'hasFormalConversation': false,
      'canStartVoiceCall': following || followedBy,
      'canStartVideoCall': following || followedBy,
      'isBlocked': blocked,
      'isBlockedBy': blockedBy,
    };
  }

  Future<Object?> _listPeople(RehearsalInvocation i, bool following) async {
    final persona = i.path('personaId').isNotEmpty
        ? i.path('personaId')
        : _text(i.body, 'personaId', i.actorId);
    final query =
        (i.query('query').isNotEmpty
                ? i.query('query')
                : _text(i.body, 'query'))
            .toLowerCase();
    final rows = <Map<String, Object?>>[];
    for (final r in i.store.follows.values) {
      if (r['active'] != true) continue;
      final actor = '${r['actorPersonaId']}',
          target = '${r['targetPersonaId']}';
      if ((following ? actor == persona : target == persona) == false) continue;
      final other = following ? target : actor;
      final p = _findPersona(i, other);
      if (query.isNotEmpty &&
          !'${p?['displayName'] ?? other} ${p?['userHandle'] ?? other}'
              .toLowerCase()
              .contains(query)) {
        continue;
      }
      rows.add({
        'personaId': other,
        'userHandle': p?['userHandle'] ?? other,
        'displayName': p?['displayName'] ?? other,
        if (p?['avatarUrl'] != null) 'avatarUrl': p!['avatarUrl'],
        'profileVisibility': p?['profileVisibility'] ?? 'public',
        'relationState': following ? 'following' : 'followed_by',
        'followedAt': r['updatedAt'],
      });
    }
    rows.sort((a, b) => '${a['personaId']}'.compareTo('${b['personaId']}'));
    return _page(i, rows);
  }

  Future<Object?> _listBlocked(RehearsalInvocation i) async {
    _requireIdentity(i);
    final rows = <Map<String, Object?>>[];
    for (final r in i.store.blocks.values.where(
      (r) => r['actorPersonaId'] == i.actorId && r['active'] == true,
    )) {
      final target = '${r['targetPersonaId']}', p = _findPersona(i, target);
      rows.add({
        'targetPersonaId': target,
        'displayName': p?['displayName'] ?? target,
        'userHandle': p?['userHandle'] ?? target,
        if (p?['avatarUrl'] != null) 'avatarUrl': p!['avatarUrl'],
        'blockedAt': r['updatedAt'] ?? _timestamp(i),
      });
    }
    return _page(i, rows);
  }

  Future<Object?> _subject(RehearsalInvocation i, bool desired) =>
      i.store.commit(() {
        _requireIdentity(i);
        final type = i.path('subjectType'),
            subject = i.path('subjectId');
        final key = '${i.actorId}::$type::$subject';
        final table = _records(i, 'user.subject_follows');
        final existed = table[key]?['active'] == true;
        table[key] = {
          'personaId': i.actorId,
          'subjectType': type,
          'subjectId': subject,
          'active': desired,
          'displayName': subject,
          'followedAt': table[key]?['followedAt'] ?? _timestamp(i),
          'updatedAt': _timestamp(i),
        };
        return {
          'personaId': i.actorId,
          'subjectType': type,
          'subjectId': subject,
          'state': desired ? 'following' : 'unfollowed',
          'idempotentReplay': desired == existed,
          'updatedAt': _timestamp(i),
        };
      });

  Future<Object?> _listSubjects(RehearsalInvocation i) async {
    _requireIdentity(i);
    final filter = i.query('subjectType');
    final rows = _records(i, 'user.subject_follows').values
        .where(
          (r) =>
              r['personaId'] == i.actorId &&
              r['active'] == true &&
              (filter.isEmpty || r['subjectType'] == filter),
        )
        .map(
          (r) => <String, Object?>{
            'subjectId': r['subjectId'],
            'subjectType': r['subjectType'],
            'displayName': r['displayName'],
            'targetRouteId': 'user.followed_subject',
            'targetObjectId': r['subjectId'],
            'followedAt': r['followedAt'],
            'unreadChangeCount': 0,
            'hasUnreadChanges': false,
          },
        )
        .toList();
    return _page(i, rows);
  }

  Future<Object?> _markSubjectVisited(RehearsalInvocation i) =>
      i.store.commit(() {
        _requireIdentity(i);
        final type = _text(i.body, 'subjectType');
        final subject = _text(i.body, 'subjectId');
        final row = _records(
          i,
          'user.subject_follows',
        )['${i.actorId}::$type::$subject'];
        if (row == null || row['active'] != true) {
          rehearsalNotFound('USER.USER.subject_follow_not_found');
        }
        final visitedAt = _text(i.body, 'visitedAt', _timestamp(i));
        final replay = row['lastVisitedAt'] == visitedAt;
        row['lastVisitedAt'] = visitedAt;
        return {
          'personaId': i.actorId,
          'subjectType': type,
          'subjectId': subject,
          'lastVisitedAt': visitedAt,
          'idempotentReplay': replay,
        };
      });

  Future<Object?> _sendGreeting(RehearsalInvocation i) => i.store.commit(() {
    _requireIdentity(i);
    final target = _text(i.body, 'targetPersonaId');
    if (target == i.actorId ||
        target.isEmpty ||
        i.store.blocks[i.store.followKey(i.actorId, target)]?['active'] ==
            true) {
      throw localDomainCloudException('USER.USER.relationship_blocked');
    }
    final table = _records(i, 'user.greetings');
    final existing = table.values
        .where(
          (r) =>
              r['requesterPersonaId'] == i.actorId &&
              r['targetPersonaId'] == target &&
              r['status'] == 'pending',
        )
        .firstOrNull;
    if (existing != null) {
      return Map<String, Object?>.from(existing)..remove('ownerId');
    }
    final id = i.nextId('greeting.');
    final now = _timestamp(i);
    final row = <String, Object?>{
      'id': id,
      'requesterPersonaId': i.actorId,
      'targetPersonaId': target,
      if (i.body['requestMessage'] != null)
        'requestMessage': i.body['requestMessage'],
      if (i.body['intersectionRef'] != null)
        'intersectionRef': cloneRehearsalValue(i.body['intersectionRef']),
      'status': 'pending',
      'source': _text(i.body, 'source', 'profile'),
      'createdAt': now,
      'updatedAt': now,
    };
    table[id] = row;
    return row;
  });

  Future<Object?> _decideGreeting(RehearsalInvocation i, String status) =>
      i.store.commit(() {
        _requireIdentity(i);
        final id = _text(i.body, 'requestId');
        final row = _records(i, 'user.greetings')[id];
        if (row == null) rehearsalNotFound('USER.USER.greeting_not_found');
        final allowed = status == 'cancelled'
            ? row['requesterPersonaId'] == i.actorId
            : row['targetPersonaId'] == i.actorId;
        if (!allowed) rehearsalUnauthorized();
        if (row['status'] == 'pending') {
          row['status'] = status;
          row['decisionAt'] = _timestamp(i);
          row['updatedAt'] = _timestamp(i);
        }
        return Map<String, Object?>.from(row)..remove('ownerId');
      });

  Future<Object?> _listGreeting(RehearsalInvocation i, bool inbox) async {
    _requireIdentity(i);
    final status = i.query('status').isNotEmpty
        ? i.query('status')
        : _text(i.body, 'status', 'pending');
    final rows = _records(i, 'user.greetings').values
        .where(
          (r) =>
              r[inbox ? 'targetPersonaId' : 'requesterPersonaId'] ==
                  i.actorId &&
              (status.isEmpty || r['status'] == status),
        )
        .map((r) => Map<String, Object?>.from(r)..remove('ownerId'))
        .toList();
    return _page(i, rows);
  }

  Map<String, Object?>? _findPersona(RehearsalInvocation i, String id) =>
      _records(i, 'user.personas')[id] ??
      i.store.identities.values.where((r) => r['personaId'] == id).firstOrNull;
}
