import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only ProfileUpdateProposal adapter.
///
/// production 依赖图不可达本文件；状态迁移与 Remote Facet 使用同一 typed
/// contract。proposalId 是 alpha 内稳定业务重放标识，同一目标状态重放返回
/// `replayed=true`，不会虚增 version。
final class AlphaProfileUpdateProposalFacet
    implements
        ProfileUpdateProposalCommandWriter,
        ProfileUpdateProposalQueryReader {
  final Map<String, ProfileUpdateProposalView> _proposals =
      <String, ProfileUpdateProposalView>{};

  @override
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  ) async {
    final existing = _proposals[command.proposalId];
    if (existing != null) {
      return _result(existing, replayed: true);
    }
    final now = DateTime.now().toUtc();
    final proposal = ProfileUpdateProposalView(
      id: command.proposalId,
      personaId: command.personaId,
      source: command.source,
      reason: command.reason,
      evidenceRefs: command.evidenceRefs,
      impactScope: command.impactScope,
      createdBy: command.personaId,
      status: ProposalStatus.pending,
      displayName: command.displayName,
      bio: command.bio,
      avatarMediaAssetId: command.avatarMediaAssetId,
      backgroundMediaAssetId: command.backgroundMediaAssetId,
      isPrivate: command.isPrivate,
      isolationLevel: command.isolationLevel,
      purposeHint: command.purposeHint,
      reviewedBy: null,
      applyAuditId: null,
      rollbackDeadline: null,
      rollbackAuditId: null,
      version: 1,
      createdAt: now,
      updatedAt: now,
      resolvedAt: null,
    );
    _proposals[proposal.id] = proposal;
    return _result(proposal, replayed: false);
  }

  @override
  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  ) async {
    final current = _required(command.proposalId);
    if (current.status == ProposalStatus.confirmed ||
        current.status == ProposalStatus.applying ||
        current.status == ProposalStatus.applied) {
      return _result(current, replayed: true);
    }
    _requireStatus(current, ProposalStatus.pending);
    final next = _copy(
      current,
      status: ProposalStatus.confirmed,
      reviewedBy: current.personaId,
    );
    _proposals[next.id] = next;
    return _result(next, replayed: false);
  }

  @override
  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  ) async {
    final current = _required(command.proposalId);
    if (current.status == ProposalStatus.applied) {
      return _result(current, replayed: true);
    }
    if (current.status != ProposalStatus.confirmed &&
        current.status != ProposalStatus.applying) {
      throw StateError('only confirmed/applying proposal can be applied');
    }
    final next = _copy(
      current,
      status: ProposalStatus.applied,
      applyAuditId: 'alpha-apply-audit-${current.id}',
      rollbackDeadline: DateTime.now().toUtc().add(const Duration(days: 7)),
      resolvedAt: DateTime.now().toUtc(),
    );
    _proposals[next.id] = next;
    return _result(next, replayed: false);
  }

  @override
  Future<ProfileUpdateProposalCommandResult> rollback(
    RollbackProfileUpdateProposalCommand command,
  ) async {
    final current = _required(command.proposalId);
    if (current.status == ProposalStatus.rolledBack) {
      return _result(current, replayed: true);
    }
    _requireStatus(current, ProposalStatus.applied);
    final next = _copy(
      current,
      status: ProposalStatus.rolledBack,
      rollbackAuditId: 'alpha-rollback-audit-${current.id}',
      resolvedAt: DateTime.now().toUtc(),
    );
    _proposals[next.id] = next;
    return _result(next, replayed: false);
  }

  @override
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  ) async {
    final current = _required(command.proposalId);
    if (current.status == ProposalStatus.rejected) {
      return _result(current, replayed: true);
    }
    _requireStatus(current, ProposalStatus.pending);
    final next = _copy(
      current,
      status: ProposalStatus.rejected,
      reviewedBy: current.personaId,
      resolvedAt: DateTime.now().toUtc(),
    );
    _proposals[next.id] = next;
    return _result(next, replayed: false);
  }

  @override
  Future<ProfileUpdateProposalView> get(
    ProfileUpdateProposalQuery query,
  ) async => _required(query.proposalId);

  @override
  Future<ProfileUpdateProposalSlice> list(
    ProfileUpdateProposalListQuery query,
  ) async {
    final items =
        _proposals.values
            .where((proposal) => proposal.personaId == query.personaId)
            .toList(growable: false)
          ..sort((left, right) => right.updatedAt.compareTo(left.updatedAt));
    return ProfileUpdateProposalSlice(
      items: items.take(query.limit).toList(growable: false),
    );
  }

  ProfileUpdateProposalView _required(String proposalId) {
    final proposal = _proposals[proposalId];
    if (proposal == null) {
      throw StateError('profile update proposal not found');
    }
    return proposal;
  }

  void _requireStatus(
    ProfileUpdateProposalView proposal,
    ProposalStatus expected,
  ) {
    if (proposal.status != expected) {
      throw StateError(
        'proposal ${proposal.id} must be ${expected.wireName}, '
        'got ${proposal.status.wireName}',
      );
    }
  }

  ProfileUpdateProposalView _copy(
    ProfileUpdateProposalView current, {
    required ProposalStatus status,
    String? reviewedBy,
    String? applyAuditId,
    DateTime? rollbackDeadline,
    String? rollbackAuditId,
    DateTime? resolvedAt,
  }) {
    final now = DateTime.now().toUtc();
    return ProfileUpdateProposalView(
      id: current.id,
      personaId: current.personaId,
      source: current.source,
      reason: current.reason,
      evidenceRefs: current.evidenceRefs,
      impactScope: current.impactScope,
      createdBy: current.createdBy,
      status: status,
      displayName: current.displayName,
      bio: current.bio,
      avatarMediaAssetId: current.avatarMediaAssetId,
      backgroundMediaAssetId: current.backgroundMediaAssetId,
      isPrivate: current.isPrivate,
      isolationLevel: current.isolationLevel,
      purposeHint: current.purposeHint,
      reviewedBy: reviewedBy ?? current.reviewedBy,
      applyAuditId: applyAuditId ?? current.applyAuditId,
      rollbackDeadline: rollbackDeadline ?? current.rollbackDeadline,
      rollbackAuditId: rollbackAuditId ?? current.rollbackAuditId,
      version: current.version + 1,
      createdAt: current.createdAt,
      updatedAt: now,
      resolvedAt: resolvedAt ?? current.resolvedAt,
    );
  }

  ProfileUpdateProposalCommandResult _result(
    ProfileUpdateProposalView proposal, {
    required bool replayed,
  }) {
    return ProfileUpdateProposalCommandResult(
      proposalId: proposal.id,
      version: proposal.version,
      status: proposal.status,
      replayed: replayed,
    );
  }
}
