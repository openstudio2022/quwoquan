part of 'user_handlers.dart';

final class _UserPersonaHandlerPart {
  const _UserPersonaHandlerPart();
  Future<Object?> handle(
    RehearsalInvocation i,
  ) => switch (i.operation.canonicalOperationId) {
    'user.persona.CreatePersona' => _create(i),
    'user.persona.UpdatePersona' => _update(i),
    'user.persona.ActivatePersona' => _activate(i),
    'user.persona.RetirePersona' => _retire(i),
    'user.persona.ApplyPersonaProfileSync' => _sync(i),
    'user.persona.UpdateUserProfile' => _updateProfile(i),
    'user.user_account.CloseAccount' => _close(i),
    'user.user_account.GetActivePersonaContext' => _active(i),
    'user.user_account.GetMeProfile' => _profile(i, i.actorId),
    'user.user_account.GetPersonaProfile' => _profile(
      i,
      i.path('personaId').isNotEmpty
          ? i.path('personaId')
          : _text(i.body, 'personaId'),
    ),
    'user.user_account.ListPersonas' => _list(i),
    'user.user_account.GetPersonaManagementSummary' => _summary(i),
    'user.user_account.GetPersonaLifecycleGuard' => _guard(
      i,
      i.path('personaId').isNotEmpty
          ? i.path('personaId')
          : _text(i.body, 'personaId'),
    ),
    'user.user_account.GetProfileEditSnapshot' => _editSnapshot(i),
    'user.user_account.GetProfileQrCard' => _qr(i),
    'user.user_account.ResolveProfileQrToken' => _resolveQr(i),
    'user.user_account.GetUserHomepageBundle' => _homepage(i),
    'user.user_account.SearchSocialRelations' => _search(i),
    'user.user_account.PullUserSync' => _pullSync(i),
    'user.profile_update_proposal.ApplyProposal' => _proposal(i, 'applied'),
    'user.profile_update_proposal.ConfirmProposal' => _proposal(i, 'confirmed'),
    'user.profile_update_proposal.RejectProposal' => _proposal(i, 'rejected'),
    'user.profile_update_proposal.RollbackProposal' => _proposal(
      i,
      'rolled_back',
    ),
    _ => rehearsalUnsupported(),
  };

  Future<Object?> _create(RehearsalInvocation i) => i.store.commit(() {
    final identity = _requireIdentity(i);
    final owned = _records(i, 'user.personas').values
        .where(
          (r) =>
              r['ownerId'] == identity['ownerId'] && r['status'] != 'retired',
        )
        .length;
    if (owned >= 5)
      throw localDomainCloudException('USER.USER.persona_quota_reached');
    final id = i.nextId('rehearsal.persona.');
    final now = _timestamp(i);
    final row = _newPersona(
      '${identity['ownerId']}',
      id,
      _text(i.body, 'displayName'),
      now,
      false,
    );
    row['avatarUrl'] = i.body['avatarUrl'];
    row['isolationLevel'] = _text(i.body, 'isolationLevel', 'open');
    row['purposeHint'] = i.body['purposeHint'];
    _records(i, 'user.personas')[id] = row;
    return _personaItem(row);
  });

  Future<Object?> _update(RehearsalInvocation i) => i.store.commit(() {
    final id = _text(i.body, 'personaId');
    final row = _requireOwnedPersona(i, id);
    for (final key in [
      'displayName',
      'avatarUrl',
      'backgroundUrl',
      'isolationLevel',
      'purposeHint',
    ]) {
      if (i.body[key] != null) row[key] = i.body[key];
    }
    row['updatedAt'] = _timestamp(i);
    return _personaItem(row);
  });

  Future<Object?> _activate(RehearsalInvocation i) => i.store.commit(() {
    final id = _text(i.body, 'personaId');
    final row = _requireOwnedPersona(i, id);
    if (row['status'] == 'retired')
      throw localDomainCloudException('USER.USER.persona_not_found');
    for (final p in _records(
      i,
      'user.personas',
    ).values.where((p) => p['ownerId'] == row['ownerId'])) {
      p['isActive'] = p['personaId'] == id;
    }
    row['lastActivatedAt'] = _timestamp(i);
    i.store.currentPersonaId = id;
    final identity = i.store.identities['${row['ownerId']}'];
    if (identity != null) identity['personaId'] = id;
    return _activeWire(row, i, true);
  });

  Future<Object?> _retire(RehearsalInvocation i) => i.store.commit(() {
    final id = _text(i.body, 'personaId');
    final row = _requireOwnedPersona(i, id);
    final guard = _guardWire(i, row);
    if (guard['allowed'] != true) return guard;
    row['status'] = 'retired';
    row['isActive'] = false;
    row['retiredAt'] = _timestamp(i);
    return _guardWire(i, row, allowed: true);
  });

  Future<Object?> _sync(RehearsalInvocation i) => i.store.commit(() {
    final id = _text(i.body, 'personaId');
    final row = _requireOwnedPersona(i, id);
    final fields =
        (i.body['fieldsMask'] as List?)?.cast<String>() ?? <String>[];
    row['lastProfileSyncAt'] = _timestamp(i);
    row['lastProfileSyncSource'] = 'owner';
    return {
      'status': 'applied',
      'appliedCount': fields.length,
      'fieldsMask': fields,
    };
  });

  Future<Object?> _updateProfile(RehearsalInvocation i) => i.store.commit(() {
    final row = _requireOwnedPersona(i, i.actorId);
    final identity = _requireIdentity(i);
    for (final key in [
      'nickname',
      'displayName',
      'avatarUrl',
      'avatarAssetId',
      'backgroundUrl',
      'backgroundAssetId',
      'bio',
      'gender',
      'regionTagRef',
      'identityTags',
    ]) {
      if (i.body[key] != null)
        row[key == 'nickname' ? 'displayName' : key] = cloneRehearsalValue(
          i.body[key],
        );
    }
    row['updatedAt'] = _timestamp(i);
    row['version'] = (row['version'] as int? ?? 1) + 1;
    identity['displayName'] = row['displayName'];
    identity['avatarUrl'] = row['avatarUrl'] ?? '';
    return {
      'userId': '${identity['ownerId']}',
      'nickname': '${row['displayName']}',
      'nicknameCustomized': true,
      'profileVersion': row['version'],
      'accountState': identity['accountState'],
      if (row['avatarUrl'] != null) 'avatarUrl': row['avatarUrl'],
      if (row['avatarAssetId'] != null) 'avatarAssetId': row['avatarAssetId'],
      'avatarVersion': row['version'],
      if (row['backgroundUrl'] != null) 'backgroundUrl': row['backgroundUrl'],
      if (row['backgroundAssetId'] != null)
        'backgroundAssetId': row['backgroundAssetId'],
      if (row['bio'] != null) 'bio': row['bio'],
      'identityTags': row['identityTags'] ?? <String>[],
      if (row['gender'] != null) 'gender': row['gender'],
      if (row['regionTagRef'] != null) 'regionTagRef': row['regionTagRef'],
      'status': row['status'],
      'updatedAt': row['updatedAt'],
    };
  });

  Future<Object?> _close(RehearsalInvocation i) => i.store.commit(() {
    final identity = _requireIdentity(i);
    final replay = identity['accountState'] == 'closed';
    identity['accountState'] = 'closed';
    identity['closedAt'] ??= _timestamp(i);
    i.store.currentOwnerId = null;
    i.store.currentPersonaId = null;
    return {
      'accountState': 'closed',
      'closedAt': identity['closedAt'],
      'idempotentReplay': replay,
    };
  });

  Future<Object?> _active(RehearsalInvocation i) async {
    final identity = _requireIdentity(i);
    final id = i.context.actor.personaId ?? '${identity['personaId']}';
    return _activeWire(_requireOwnedPersona(i, id), i, false);
  }

  Future<Object?> _profile(RehearsalInvocation i, String id) async {
    final row =
        _records(i, 'user.personas')[id] ??
        i.store.identities.values
            .where((r) => r['personaId'] == id)
            .firstOrNull;
    if (row == null) rehearsalNotFound('USER.USER.persona_not_found');
    return _profileWire(i, row!);
  }

  Future<Object?> _list(RehearsalInvocation i) async {
    final owner = _requireIdentity(i)['ownerId'];
    return {
      'items': _records(
        i,
        'user.personas',
      ).values.where((r) => r['ownerId'] == owner).map(_personaItem).toList(),
    };
  }

  Future<Object?> _summary(RehearsalInvocation i) async {
    final owner = _requireIdentity(i)['ownerId'];
    final rows = _records(
      i,
      'user.personas',
    ).values.where((r) => r['ownerId'] == owner).toList();
    final active = rows.firstWhere((r) => r['isActive'] == true);
    return {
      'items': rows.map(_personaItem).toList(),
      'quota': {
        'used': rows.where((r) => r['status'] != 'retired').length,
        'limit': 5,
        'remaining': 5 - rows.where((r) => r['status'] != 'retired').length,
      },
      'activeContext': _activeWire(active, i, false),
    };
  }

  Future<Object?> _guard(RehearsalInvocation i, String id) async =>
      _guardWire(i, _requireOwnedPersona(i, id));
  Future<Object?> _editSnapshot(RehearsalInvocation i) async {
    final identity = _requireIdentity(i),
        row = _requireOwnedPersona(i, i.actorId);
    final qr = await _qr(i);
    return {
      'ownerUserId': identity['ownerId'],
      'personaId': row['personaId'],
      if (row['avatarUrl'] != null) 'avatarUrl': row['avatarUrl'],
      'avatarVersion': row['version'] ?? 1,
      'nickname': row['displayName'],
      'displayName': row['displayName'],
      'userHandle': row['userHandle'],
      if (row['bio'] != null) 'bio': row['bio'],
      'identityTags': row['identityTags'] ?? <String>[],
      'qrCard': qr,
      'updatedAt': row['updatedAt'],
    };
  }

  Future<Object?> _qr(RehearsalInvocation i) async {
    final row = _requireOwnedPersona(i, i.actorId);
    final token = 'rehearsal.qr.${row['personaId']}';
    return {
      'publicProfileUrl': 'https://alpha.invalid/u/${row['userHandle']}',
      'qrPayload': token,
      'qrTokenId': token,
      'displayName': row['displayName'],
      'shareText': '${row['displayName']}',
      'expiresAt': i
          .now()
          .add(const Duration(days: 1))
          .toUtc()
          .toIso8601String(),
    };
  }

  Future<Object?> _resolveQr(RehearsalInvocation i) async {
    final qr = _text(i.body, 'qr', i.query('qr'));
    final id = qr.replaceFirst('rehearsal.qr.', '');
    final row = _records(i, 'user.personas')[id];
    if (row == null) rehearsalNotFound('USER.USER.persona_not_found');
    return {
      'personaId': id,
      'userHandle': row!['userHandle'],
      'publicProfileUrl': 'https://alpha.invalid/u/${row['userHandle']}',
      'scanStatus': 'resolved',
    };
  }

  Future<Object?> _homepage(RehearsalInvocation i) async {
    final id = i.path('personaId').isNotEmpty
        ? i.path('personaId')
        : _text(i.body, 'personaId');
    final profile = await _profile(i, id) as Map<String, Object?>;
    final cap = await const _UserRelationshipHandlerPart()._capability(
      i,
    ) as Map<String, Object?>;
    return {
      'profile': profile,
      'stats': {
        'followingCount': profile['followingCount'],
        'circleCount': profile['circleCount'],
        'followerCount': profile['followerCount'],
        'likeCount': profile['likeCount'],
        'postCount': profile['postCount'],
      },
      'relationshipCapability': cap,
      'tabCounts': {
        'worksCount': profile['postCount'],
        'likesCount': profile['likeCount'],
        'circlesCount': profile['circleCount'],
        'collectionsCount': 0,
      },
      'viewerContext': {
        'viewerPersonaId': i.actorId.isEmpty ? 'guest' : i.actorId,
        'isOwner': i.actorId == id,
        'isGuest': i.actorId.isEmpty,
        'relationToTarget': cap['relationState'],
        'canViewFullProfile':
            profile['profileVisibility'] == 'public' || i.actorId == id,
      },
      'cacheVersion': '${profile['updatedAt']}',
    };
  }

  Future<Object?> _search(RehearsalInvocation i) async {
    _requireIdentity(i);
    final q = _text(i.body, 'query', i.query('query')).toLowerCase();
    final rows = _records(i, 'user.personas').values
        .where(
          (r) => '${r['displayName']} ${r['userHandle']}'
              .toLowerCase()
              .contains(q),
        )
        .map(
          (r) => <String, Object?>{
            'personaId': r['personaId'],
            'userHandle': r['userHandle'],
            'displayName': r['displayName'],
            'relationState': 'not_following',
          },
        )
        .toList();
    final page = _page(i, rows);
    return {'items': page['items'], 'cursor': page['nextCursor'] ?? ''};
  }

  Future<Object?> _pullSync(RehearsalInvocation i) async {
    _requireIdentity(i);
    return {
      'patches': <Object?>[],
      'latestSyncSeq': 0,
      'hasMore': false,
      'requiresResync': false,
    };
  }

  Future<Object?> _createProposal(RehearsalInvocation i) => i.store.commit(() {
    final owner = _requireIdentity(i)['ownerId'];
    final persona = _text(i.body, 'personaId');
    _requireOwnedPersona(i, persona);
    final id = _text(i.body, 'proposalId');
    final table = _records(i, 'user.proposals');
    final existing = table[id];
    if (existing != null) return _proposalView(existing);
    final row = <String, Object?>{
      'proposalId': id,
      'ownerId': owner,
      'personaId': persona,
      'version': 1,
      'status': 'pending',
      'source': i.body['source'],
      'displayName': i.body['displayName'],
      'bio': i.body['bio'],
      'reason': i.body['reason'],
      'evidenceRefs': i.body['evidenceRefs'] ?? <String>[],
      'impactScope': i.body['impactScope'] ?? <String>[],
      'createdAt': _timestamp(i),
      'updatedAt': _timestamp(i),
    };
    table[id] = row;
    return _proposalView(row);
  });

  Future<Object?> _getProposal(RehearsalInvocation i) async {
    final owner = _requireIdentity(i)['ownerId'];
    final id = _text(i.body, 'id', _text(i.body, 'proposalId'));
    final row = _records(i, 'user.proposals')[id];
    if (row == null || row['ownerId'] != owner) {
      rehearsalNotFound('USER.USER.profile_proposal_not_found');
    }
    return _proposalView(row!);
  }

  Future<Object?> _listProposals(RehearsalInvocation i) async {
    final owner = _requireIdentity(i)['ownerId'];
    final persona = _text(i.body, 'personaId');
    final rows = _records(i, 'user.proposals').values
        .where((row) => row['ownerId'] == owner && row['personaId'] == persona)
        .map(_proposalView)
        .toList();
    return _page(i, rows);
  }

  Map<String, Object?> _proposalView(Map<String, Object?> row) => {
    'proposalId': row['proposalId'],
    'personaId': row['personaId'],
    'version': row['version'],
    'status': row['status'],
    'source': row['source'],
    if (row['displayName'] != null) 'displayName': row['displayName'],
    if (row['bio'] != null) 'bio': row['bio'],
    'reason': row['reason'] ?? '',
    'evidenceRefs': row['evidenceRefs'] ?? <String>[],
    'impactScope': row['impactScope'] ?? <String>[],
    'createdAt': row['createdAt'],
    'updatedAt': row['updatedAt'],
  };

  Future<Object?> _proposal(RehearsalInvocation i, String status) =>
      i.store.commit(() {
        _requireIdentity(i);
        final id = _text(i.body, 'id', _text(i.body, 'proposalId'));
        final table = _records(i, 'user.proposals');
        final row = table.putIfAbsent(
          id,
          () => {
            'proposalId': id,
            'ownerId': i.context.actor.accountId,
            'version': 0,
            'status': 'pending',
          },
        );
        if (row['ownerId'] != i.context.actor.accountId)
          rehearsalUnauthorized();
        final replay = row['status'] == status;
        if (!replay) {
          row['status'] = status;
          row['version'] = (row['version'] as int) + 1;
        }
        return {
          'proposalId': id,
          'version': row['version'],
          'status': status,
          'replayed': replay,
        };
      });

  Map<String, Object?> _activeWire(
    Map<String, Object?> r,
    RehearsalInvocation i,
    bool explicit,
  ) => {
    'ownerUserId': r['ownerId'],
    'personaId': r['personaId'],
    'subjectType': 'persona',
    'displayName': r['displayName'],
    'avatarUrl': r['avatarUrl'],
    'avatarVersion': r['version'] ?? 1,
    'isPrimary': r['isPrimary'],
    'isolationLevel': r['isolationLevel'],
    'profileVisibility': r['profileVisibility'],
    'contextVersion': r['version'] ?? 1,
    'personaSnapshotVersion': r['version'] ?? 1,
    'explicitOverride': explicit,
    'switchedAt': r['lastActivatedAt'] ?? r['updatedAt'],
  };
  Map<String, Object?> _guardWire(
    RehearsalInvocation i,
    Map<String, Object?> r, {
    bool? allowed,
  }) {
    final active = r['isActive'] == true,
        primary = r['isPrimary'] == true,
        retired = r['status'] == 'retired';
    final ok = allowed ?? (!active && !primary && !retired);
    return {
      'personaId': r['personaId'],
      'requestedAction': 'retire',
      'allowed': ok,
      'reason': ok
          ? 'allowed'
          : retired
          ? 'blocked_retired_persona'
          : active
          ? 'blocked_active_persona'
          : 'blocked_primary_persona',
      'requiresSuccessor': active,
    };
  }

  Map<String, Object?> _profileWire(
    RehearsalInvocation i,
    Map<String, Object?> r,
  ) => {
    'personaId': r['personaId'],
    'subjectType': 'persona',
    'userHandle': r['userHandle'] ?? r['personaId'],
    'displayName': r['displayName'] ?? r['personaId'],
    'nicknameCustomized': true,
    'avatarUrl': r['avatarUrl'],
    'bio': r['bio'],
    'identityTags': r['identityTags'] ?? <String>[],
    'followerCount': i.store.follows.values
        .where(
          (f) => f['targetPersonaId'] == r['personaId'] && f['active'] == true,
        )
        .length,
    'followingCount': i.store.follows.values
        .where(
          (f) => f['actorPersonaId'] == r['personaId'] && f['active'] == true,
        )
        .length,
    'postCount': 0,
    'circleCount': 0,
    'likeCount': 0,
    'profileVisibility': r['profileVisibility'] ?? 'public',
    'isolationLevel': r['isolationLevel'] ?? 'open',
    'inheritsFromOwner': r['inheritsProfileFromOwner'] ?? false,
    'overriddenFields': r['overriddenProfileFields'] ?? <String>[],
    'updatedAt': r['updatedAt'] ?? _timestamp(i),
  };
}

Map<String, Object?> _newPersona(
  String owner,
  String id,
  String display,
  String now,
  bool primary,
) => {
  'ownerId': owner,
  'personaId': id,
  'displayName': display,
  'userHandle': id,
  'isolationLevel': 'open',
  'isPrimary': primary,
  'isActive': primary,
  'status': 'active',
  'inheritsProfileFromOwner': false,
  'overriddenProfileFields': <String>[],
  'profileVisibility': 'public',
  'updatedAt': now,
  'lastActivatedAt': primary ? now : null,
  'version': 1,
};
Map<String, Object?> _personaItem(Map<String, Object?> r) => {
  'personaId': r['personaId'],
  'displayName': r['displayName'],
  'userHandle': r['userHandle'],
  'avatarUrl': r['avatarUrl'],
  'backgroundUrl': r['backgroundUrl'],
  'bio': r['bio'],
  'isolationLevel': r['isolationLevel'],
  'isPrimary': r['isPrimary'],
  'isActive': r['isActive'],
  'status': r['status'],
  'retiredAt': r['retiredAt'],
  'inheritsProfileFromOwner': r['inheritsProfileFromOwner'],
  'overriddenProfileFields': r['overriddenProfileFields'],
  'lastProfileSyncAt': r['lastProfileSyncAt'],
  'lastProfileSyncSource': r['lastProfileSyncSource'],
  'profileVisibility': r['profileVisibility'],
  'purposeHint': r['purposeHint'],
  'updatedAt': r['updatedAt'],
  'lastActivatedAt': r['lastActivatedAt'],
};
