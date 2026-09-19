part of 'user_handlers.dart';

final class _UserAccountHandlerPart {
  const _UserAccountHandlerPart();

  Future<Object?> handle(
    RehearsalInvocation i,
  ) => switch (i.operation.canonicalOperationId) {
    'user.authentication_challenge.GetOtpDeliveryReadiness' => _otpReadiness(i),
    'user.authentication_challenge.SendOtp' => _sendOtp(i),
    'user.account_session.LoginAnonymous' => _loginAnonymous(i),
    'user.account_session.LoginWithPhone' => _loginPhone(i),
    'user.account_session.RefreshToken' => _refresh(i),
    'user.account_session.Logout' => _logout(i),
    'user.credential_binding.BindPhoneCredential' => _bindPhone(i),
    'user.credential_binding.ListCredentials' => _listCredentials(i),
    'user.credential_binding.UnbindCredential' => _unbindCredential(i),
    'user.device_registration.UpsertDevicePushEndpoint' => _device(i, true),
    'user.device_registration.RemoveDevicePushEndpoint' => _device(i, false),
    'user.user_settings.GetAppearanceSettings' => _settings(i, 'appearance'),
    'user.user_settings.GetCallSettings' => _settings(i, 'call'),
    'user.user_settings.GetNotificationSettings' => _settings(
      i,
      'notification',
    ),
    'user.user_settings.GetPrivacySettings' => _settings(i, 'privacy'),
    'user.user_settings.UpdateAppearanceSettings' => _updateSettings(
      i,
      'appearance',
    ),
    'user.user_settings.UpdateCallSettings' => _updateSettings(i, 'call'),
    'user.user_settings.UpdateNotificationSettings' => _updateSettings(
      i,
      'notification',
    ),
    'user.user_settings.UpdatePrivacySettings' => _updateSettings(i, 'privacy'),
    _ => rehearsalUnsupported(),
  };

  Future<Object?> _otpReadiness(RehearsalInvocation i) async => {
    'availability': 'ready',
    'retryAfterSeconds': 0,
  };

  Future<Object?> _contactDiscovery(RehearsalInvocation i) =>
      i.store.commit(() {
        final owner = _requireIdentity(i)['ownerId'];
        final id = i.nextId('discovery.');
        final row = <String, Object?>{
          'id': id,
          'ownerId': owner,
          'status': 'completed',
          'matches': <Object?>[],
          'submittedCount': (i.body['hashedPhones'] as List?)?.length ?? 0,
          'matchedCount': 0,
          'createdAt': _timestamp(i),
          'updatedAt': _timestamp(i),
        };
        _records(i, 'user.contact_discovery')[id] = row;
        return Map<String, Object?>.from(row)..remove('ownerId');
      });

  Future<Object?> _latestDiscovery(RehearsalInvocation i) async {
    final owner = _requireIdentity(i)['ownerId'];
    final rows = _records(
      i,
      'user.contact_discovery',
    ).values.where((row) => row['ownerId'] == owner).toList();
    if (rows.isEmpty)
      rehearsalNotFound('USER.USER.contact_discovery_not_found');
    return Map<String, Object?>.from(rows.last)..remove('ownerId');
  }

  Future<Object?> _dismissDiscovery(RehearsalInvocation i) =>
      i.store.commit(() {
        final owner = _requireIdentity(i)['ownerId'];
        final id = _text(i.body, 'id', _text(i.body, 'discoveryId'));
        final row = _records(i, 'user.contact_discovery')[id];
        if (row == null || row['ownerId'] != owner) {
          rehearsalNotFound('USER.USER.contact_discovery_not_found');
        }
        row!['status'] = 'dismissed';
        row['updatedAt'] = _timestamp(i);
        return {'status': 'dismissed'};
      });

  Future<Object?> _sendOtp(RehearsalInvocation i) => i.store.commit(() {
    final phone = _text(i.body, 'phone');
    if (phone.isEmpty)
      throw localDomainCloudException('USER.AUTH.otp_mismatch');
    final id = i.nextId('otp_');
    final owner =
        i.context.actor.deviceActorId ?? _text(i.body, 'deviceId', 'guest');
    i.store.lastIssuedOtp = rehearsalOtpCode;
    i.store.otpChallenges[id] = {
      'challengeId': id,
      'phone': phone,
      'code': rehearsalOtpCode,
      'owner': owner,
      'expiresAt': i
          .now()
          .add(const Duration(minutes: 5))
          .toUtc()
          .toIso8601String(),
      'used': false,
      'attempts': 0,
    };
    return {
      'maskedPhone': _mask(phone),
      'challengeId': id,
      'requestId': id,
      'deliveryStatus': 'delivered',
      'expiresInSeconds': 300,
      'retryAfterSeconds': 0,
    };
  });

  Future<Object?> _loginAnonymous(RehearsalInvocation i) => i.store.commit(() {
    final install = _text(i.body, 'installId');
    final owner = 'rehearsal.account.anonymous.$install';
    return _issue(
      i,
      owner: owner,
      persona: 'rehearsal.persona.anonymous.$install',
      state: 'anonymous',
      display: '匿名演练用户',
      phone: '',
      retention: 'device_bound',
    );
  });

  Future<Object?> _loginPhone(RehearsalInvocation i) => i.store.commit(() {
    final phone = _text(i.body, 'phone');
    final otp = _text(i.body, 'otpCode');
    final requested = _text(i.body, 'challengeId');
    final owner =
        i.context.actor.deviceActorId ?? _text(i.body, 'deviceId', 'guest');
    final matches = i.store.otpChallenges.values
        .where(
          (r) =>
              r['phone'] == phone &&
              r['owner'] == owner &&
              (requested.isEmpty || r['challengeId'] == requested),
        )
        .toList();
    final challenge = matches.isEmpty ? null : matches.last;
    if (challenge == null ||
        challenge['used'] != false ||
        (challenge['attempts'] as int) >= 5 ||
        !DateTime.parse(challenge['expiresAt'] as String).isAfter(i.now())) {
      throw localDomainCloudException('USER.AUTH.otp_mismatch');
    }
    if (otp != challenge['code']) {
      challenge['attempts'] = (challenge['attempts'] as int) + 1;
      return RehearsalRejected(
        localDomainCloudException('USER.AUTH.otp_mismatch'),
      );
    }
    challenge['used'] = true;
    final existing = i.store.identities.values
        .where((r) => r['phone'] == phone)
        .firstOrNull;
    return _issue(
      i,
      owner: existing?['ownerId'] as String? ?? i.nextId('rehearsal.account.'),
      persona:
          existing?['personaId'] as String? ?? i.nextId('rehearsal.persona.'),
      state: 'active',
      display: existing?['displayName'] as String? ?? '演练用户',
      phone: phone,
      retention: 'none',
    );
  });

  Map<String, Object?> _issue(
    RehearsalInvocation i, {
    required String owner,
    required String persona,
    required String state,
    required String display,
    required String phone,
    required String retention,
  }) {
    final access = '$rehearsalCredentialPrefix$owner.${i.nextId('access.')}';
    final refresh = '$rehearsalCredentialPrefix$owner.${i.nextId('refresh.')}';
    final now = _timestamp(i);
    final identity = <String, Object?>{
      'ownerId': owner,
      'personaId': persona,
      'phone': phone,
      'accessToken': access,
      'refreshToken': refresh,
      'accountState': state,
      'identityOrigin': rehearsalIdentityOrigin,
      'displayName': display,
      'avatarUrl': '',
      'maskedPhone': _mask(phone),
      'createdAt': now,
    };
    i.store.identities[owner] = identity;
    _records(i, 'user.personas').putIfAbsent(
      persona,
      () => _newPersona(owner, persona, display, now, true),
    );
    i.store.currentOwnerId = owner;
    i.store.currentPersonaId = persona;
    return {
      'accessToken': access,
      'refreshToken': refresh,
      'ownerId': owner,
      'accountState': state,
      'identityOrigin': rehearsalIdentityOrigin,
      'logicalShard': 1,
      'anonymousRetentionPolicy': retention,
      'personaCount': 1,
      'sessionRememberTtlSeconds': 2592000,
      'activePersona': {'personaId': persona},
      'accountHint': {
        'displayName': display,
        'nicknameCustomized': true,
        'avatarUrl': '',
        'avatarAssetId': '',
        'maskedPhone': _mask(phone),
        'identityOrigin': rehearsalIdentityOrigin,
      },
    };
  }

  Future<Object?> _refresh(RehearsalInvocation i) => i.store.commit(() {
    final token = _text(i.body, 'refreshToken');
    final row = i.store.identities.values
        .where(
          (r) => r['refreshToken'] == token && r['accountState'] != 'closed',
        )
        .firstOrNull;
    if (row == null) rehearsalUnauthorized();
    final access =
        '$rehearsalCredentialPrefix${row!['ownerId']}.${i.nextId('access.')}';
    final refresh =
        '$rehearsalCredentialPrefix${row['ownerId']}.${i.nextId('refresh.')}';
    row['accessToken'] = access;
    row['refreshToken'] = refresh;
    return {
      'accessToken': access,
      'refreshToken': refresh,
      'sessionRememberTtlSeconds': 2592000,
    };
  });

  Future<Object?> _logout(RehearsalInvocation i) => i.store.commit(() {
    i.store.currentOwnerId = null;
    i.store.currentPersonaId = null;
    return {'revoked': true};
  });

  Future<Object?> _bindPhone(RehearsalInvocation i) => i.store.commit(() {
    final identity = _requireIdentity(i);
    final phone = _text(i.body, 'phone');
    if (_text(i.body, 'otpCode') != rehearsalOtpCode) {
      throw localDomainCloudException('USER.AUTH.otp_mismatch');
    }
    identity['phone'] = phone;
    identity['maskedPhone'] = _mask(phone);
    final table = _records(i, 'user.credentials');
    final key = '${identity['ownerId']}::phone';
    final old = table[key];
    final version = (old?['version'] as int? ?? 0) + 1;
    table[key] = {
      'id': key,
      'ownerId': identity['ownerId'],
      'credentialType': 'phone',
      'displayLabel': i.body['displayLabel'],
      'isActive': true,
      'boundAt': _timestamp(i),
      'version': version,
    };
    return {
      'credentialType': 'phone',
      'isActive': true,
      'version': version,
      'idempotentReplay': old?['isActive'] == true,
      if (i.body['displayLabel'] != null)
        'displayLabel': i.body['displayLabel'],
    };
  });

  Future<Object?> _listCredentials(RehearsalInvocation i) async {
    final owner = _requireIdentity(i)['ownerId'];
    return {
      'credentials': _records(i, 'user.credentials').values
          .where((r) => r['ownerId'] == owner)
          .map((r) => Map<String, Object?>.from(r)..remove('ownerId'))
          .toList(),
    };
  }

  Future<Object?> _unbindCredential(RehearsalInvocation i) =>
      i.store.commit(() {
        final owner = _requireIdentity(i)['ownerId'];
        final type = _text(i.body, 'credentialType');
        final row = _records(i, 'user.credentials')['$owner::$type'];
        final replay = row == null || row['isActive'] == false;
        final version = (row?['version'] as int? ?? 0) + 1;
        if (row != null) {
          row['isActive'] = false;
          row['version'] = version;
        }
        return {
          'credentialType': type,
          'isActive': false,
          'version': version,
          'idempotentReplay': replay,
        };
      });

  Future<Object?> _device(RehearsalInvocation i, bool active) =>
      i.store.commit(() {
        final owner = _requireIdentity(i)['ownerId'];
        final device = _text(i.body, 'deviceId');
        final kind = _text(i.body, 'endpointKind');
        final key = '$owner::$device::$kind';
        final table = _records(i, 'user.devices');
        final old = table[key];
        final same =
            old != null &&
            old['status'] == (active ? 'active' : 'revoked') &&
            (!active || old['token'] == i.body['token']);
        final version = (old?['version'] as int? ?? 0) + (same ? 0 : 1);
        final row = {
          'ownerId': owner,
          'endpointRef': key,
          'deviceId': device,
          'endpointKind': kind,
          'status': active ? 'active' : 'revoked',
          'token': i.body['token'],
          'version': version,
          'aggregateVersion': version,
          'updatedAt': _timestamp(i),
        };
        table[key] = row;
        return {
          'endpointRef': key,
          'deviceId': device,
          'endpointKind': kind,
          'status': row['status'],
          'version': version,
          'aggregateVersion': version,
          'idempotentReplay': same,
          'updatedAt': row['updatedAt'],
        };
      });

  Map<String, Object?> _defaults(RehearsalInvocation i, String kind) {
    final id = '${_requireIdentity(i)['ownerId']}::$kind';
    final now = _timestamp(i);
    return switch (kind) {
      'appearance' => {
        'themeMode': 'system',
        'fontSizePreset': 'md',
        'source': 'owner_default',
        'ownerDefaultThemeMode': 'system',
        'ownerDefaultFontSizePreset': 'md',
        'hasPersonaOverride': false,
        'version': 1,
        'updatedAt': now,
      },
      'call' => {
        'userId': '${_requireIdentity(i)['ownerId']}',
        'allowCallerRingtoneOverride': true,
        'enableCallVibration': true,
        'enableGroupCallRing': true,
        'version': 1,
        'updatedAt': now,
      },
      'notification' => {
        'userId': '${_requireIdentity(i)['ownerId']}',
        'enablePush': true,
        'enableMarketing': false,
        'version': 1,
        'updatedAt': now,
      },
      _ => {
        'userId': '${_requireIdentity(i)['ownerId']}',
        'allowStrangerMsg': true,
        'profileVisibility': 'public',
        'assistantEnabled': true,
        'blockedKeywords': <String>[],
        'version': 1,
        'updatedAt': now,
      },
    }..['recordId'] = id;
  }

  Future<Object?> _settings(RehearsalInvocation i, String kind) async {
    final id = '${_requireIdentity(i)['ownerId']}::$kind';
    final row = _records(i, 'user.settings')[id] ?? _defaults(i, kind);
    return Map<String, Object?>.from(row)..remove('recordId');
  }

  Future<Object?> _updateSettings(RehearsalInvocation i, String kind) =>
      i.store.commit(() async {
        final id = '${_requireIdentity(i)['ownerId']}::$kind';
        final table = _records(i, 'user.settings');
        final row = Map<String, Object?>.from(table[id] ?? _defaults(i, kind));
        final before = jsonEncode(row);
        for (final entry in i.body.entries) {
          if (entry.value != null && entry.key != 'applyScope')
            row[entry.key] = cloneRehearsalValue(entry.value);
        }
        final replay = jsonEncode(row) == before;
        row['version'] = (row['version'] as int) + (replay ? 0 : 1);
        if (!replay) row['updatedAt'] = _timestamp(i);
        table[id] = row;
        if (kind == 'appearance')
          return Map<String, Object?>.from(row)..remove('recordId');
        return {
          'userId': '${_requireIdentity(i)['ownerId']}',
          'version': row['version'],
          'idempotentReplay': replay,
        };
      });

  String _mask(String phone) {
    final d = phone.replaceAll(RegExp(r'\D'), '');
    return d.length < 7
        ? '****'
        : '${d.substring(0, 3)}****${d.substring(d.length - 4)}';
  }
}
