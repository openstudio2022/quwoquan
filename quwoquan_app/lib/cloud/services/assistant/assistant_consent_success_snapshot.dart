part of 'assistant_consent_store.dart';

/// 只记录 Remote 成功终态的 SkillConsent 快照装饰器。
///
/// [remote] 始终是唯一业务真相源。本类不从 [snapshot] 返回授权结果，
/// Remote 失败、账号归属不符或 scope 不完整时都直接 fail-closed。
final class AssistantConsentSuccessSnapshotDecorator
    implements AssistantSkillConsentFacet {
  AssistantConsentSuccessSnapshotDecorator(this._remote, this._snapshot);

  final AssistantSkillConsentFacet _remote;
  final AssistantConsentStore _snapshot;

  @override
  Future<List<SkillConsent>> listConsents() async {
    final remoteItems = await _remote.listConsents();
    _snapshot._validateActiveSnapshot(remoteItems);
    await _persistSnapshot(() => _snapshot.save(remoteItems));
    return remoteItems;
  }

  @override
  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  }) async {
    final remoteConsent = await _remote.grantSkillConsent(
      skillId: skillId,
      grantedScopes: grantedScopes,
      clientRequestId: clientRequestId,
    );
    _snapshot._validateGrantResponse(
      remoteConsent,
      requestedSkillId: skillId,
      requestedScopes: grantedScopes,
    );
    await _persistSnapshot(() => _snapshot.upsert(remoteConsent));
    return remoteConsent;
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) async {
    final normalizedSkillId = skillId.trim();
    if (normalizedSkillId.isEmpty) {
      throw ArgumentError.value(
        skillId,
        'skillId',
        'SkillConsent revoke requires a non-empty skill identity',
      );
    }
    await _remote.revokeSkillConsent(
      skillId: normalizedSkillId,
      clientRequestId: clientRequestId,
    );
    await _persistSnapshot(() => _snapshot.revoke(normalizedSkillId));
  }

  Future<void> _persistSnapshot(Future<void> Function() persist) async {
    try {
      await persist();
    } catch (error, stackTrace) {
      // 快照是可重建投影；本地 IO 不得把已完成的 Remote 业务结果改写为失败。
      developer.log(
        'assistant consent success snapshot persistence failed',
        name: 'AssistantConsentSuccessSnapshotDecorator',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }
}
