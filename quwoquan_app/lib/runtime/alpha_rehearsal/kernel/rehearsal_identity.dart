import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/rehearsal_auth_port.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

/// Rehearsal 身份事实的唯一 typed owner。合成登录标签索引与业务执行器
/// 使用的 canonical actor 索引必须在同一事务内共同提交。
final class AlphaRehearsalIdentityOwner {
  const AlphaRehearsalIdentityOwner(this.store);

  final AlphaRehearsalStore store;

  Map<String, Map<String, Object?>> get syntheticIdentities =>
      store.records.putIfAbsent(
        'synthetic.identities',
        () => <String, Map<String, Object?>>{},
      );

  SyntheticSessionResult? syntheticSession(String identityLabel) {
    final wire = syntheticIdentities[identityLabel];
    return wire == null ? null : SyntheticSessionResult.fromWire(wire);
  }

  void recordSyntheticSession(
    String identityLabel,
    SyntheticSessionResult result,
  ) {
    final validated = SyntheticSessionResult.fromWire(result.toWire());
    syntheticIdentities[identityLabel] = validated.toWire();
    store.identities[validated.accountId] = <String, Object?>{
      ...?store.identities[validated.accountId],
      'ownerId': validated.accountId,
      'personaId': validated.personaId,
      'accountState': 'rehearsal',
      'identityOrigin': 'synthetic',
      'displayName': identityLabel,
      'avatarUrl': '',
      'maskedPhone': '',
    };
  }

  String? canonicalPersonaId({String? accountId, String? personaId}) {
    final persona = personaId?.trim() ?? '';
    final account = accountId?.trim() ?? '';
    for (final row in store.identities.values) {
      if (persona.isNotEmpty && row['personaId'] == persona) {
        return persona;
      }
      if (persona.isEmpty && account.isNotEmpty && row['ownerId'] == account) {
        final resolved = '${row['personaId'] ?? ''}'.trim();
        return resolved.isEmpty ? null : resolved;
      }
    }
    return persona.isNotEmpty ? persona : (account.isEmpty ? null : account);
  }

  bool knowsActor({String? accountId, String? personaId}) {
    final account = accountId?.trim() ?? '';
    final persona = personaId?.trim() ?? '';
    return store.identities.values.any(
      (row) =>
          (account.isEmpty || row['ownerId'] == account) &&
          (persona.isEmpty || row['personaId'] == persona),
    );
  }
}

final class AlphaRehearsalAuth implements RehearsalAuthPort {
  AlphaRehearsalAuth(this.store);

  final AlphaRehearsalStore store;

  @override
  bool isRehearsalCredential(String token) =>
      token.startsWith(rehearsalCredentialPrefix);

  @override
  String? get lastIssuedOtp => store.lastIssuedOtp;

  @override
  Future<AuthSessionState?> restore({required String installId}) async {
    await store.ensureLoaded();
    final ownerId = store.currentOwnerId;
    if (ownerId == null || ownerId.isEmpty) {
      return null;
    }
    final identity = store.identities[ownerId];
    if (identity == null) {
      return null;
    }
    return _stateFromIdentity(identity, installId: installId);
  }

  @override
  Future<AuthSessionState> applyGrant(
    AuthSessionGrant grant, {
    required String installId,
  }) async {
    await store.commit(() {
      final issued = store.identities[grant.ownerId];
      if (issued == null ||
          issued['accessToken'] != grant.accessToken ||
          issued['refreshToken'] != grant.refreshToken ||
          issued['personaId'] != grant.activePersona?.personaId ||
          !isRehearsalCredential(grant.accessToken)) {
        rehearsalUnauthorized();
      }
      store.currentOwnerId = grant.ownerId;
      store.currentPersonaId = grant.activePersona?.personaId ?? grant.ownerId;
      store.identities[grant.ownerId] = <String, Object?>{
        ...?store.identities[grant.ownerId],
        'ownerId': grant.ownerId,
        'personaId': grant.activePersona?.personaId ?? grant.ownerId,
        'accessToken': grant.accessToken,
        'refreshToken': grant.refreshToken,
        'accountState': grant.accountState,
        'identityOrigin': grant.identityOrigin,
        'displayName': grant.accountHint?.displayName ?? '演练账号',
        'avatarUrl': grant.accountHint?.avatarUrl ?? '',
        'maskedPhone': grant.accountHint?.maskedPhone ?? '',
      };
    });
    return _stateFromGrant(grant, installId: installId);
  }

  @override
  Future<void> clear() async {
    await store.commit(() {
      store.currentOwnerId = null;
      store.currentPersonaId = null;
    });
  }

  AuthSessionState _stateFromGrant(
    AuthSessionGrant grant, {
    required String installId,
  }) {
    return AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: grant.accessToken,
      refreshToken: grant.refreshToken,
      ownerId: grant.ownerId,
      activePersonaId: grant.activePersona?.personaId ?? grant.ownerId,
      accountState: grant.accountState,
      identityOrigin: grant.identityOrigin,
      installId: installId,
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: grant.accountHint?.maskedPhone ?? '',
      rememberedDisplayName: grant.accountHint?.displayName ?? '',
      rememberedAvatarUrl: grant.accountHint?.avatarUrl ?? '',
      rehearsalIdentityId: grant.ownerId,
    );
  }

  AuthSessionState _stateFromIdentity(
    Map<String, Object?> identity, {
    required String installId,
  }) {
    return AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: '${identity['accessToken'] ?? ''}',
      refreshToken: '${identity['refreshToken'] ?? ''}',
      ownerId: '${identity['ownerId'] ?? ''}',
      activePersonaId: '${identity['personaId'] ?? ''}',
      accountState: '${identity['accountState'] ?? 'active'}',
      identityOrigin:
          '${identity['identityOrigin'] ?? rehearsalIdentityOrigin}',
      installId: installId,
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: '${identity['maskedPhone'] ?? ''}',
      rememberedDisplayName: '${identity['displayName'] ?? ''}',
      rememberedAvatarUrl: '${identity['avatarUrl'] ?? ''}',
      rehearsalIdentityId: '${identity['ownerId'] ?? ''}',
    );
  }
}
