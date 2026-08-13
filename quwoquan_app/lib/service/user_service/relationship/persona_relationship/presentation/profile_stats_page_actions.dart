part of 'profile_stats_page.dart';

extension _ProfileStatsPageActions on _ProfileStatsPageState {
  static const Duration _authoritativeReadbackTimeout = Duration(seconds: 10);

  RelationshipCapabilityViewData? _resolvedCapability(
    ProfileSocialRelationRowViewData row,
  ) => row.relationshipCapability;

  Future<void> _handleFollowAction(ProfileSocialRelationRowViewData row) async {
    final capability = _resolvedCapability(row);
    if (capability == null ||
        capability.isSelf ||
        capability.isBlocked ||
        capability.isBlockedBy ||
        !capability.canFollow) {
      return;
    }
    _trackAction(
      'follow_click',
      targetType: 'profile',
      targetKey: row.personaId,
      payload: <String, Object?>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
        'relationState': capability.relationState,
      },
    );
    if (!await requireLogin(ref, context, AuthGateReason.follow)) {
      return;
    }
    await _runRelationshipMutation(row, shouldFollow: true);
  }

  Future<void> _showFollowingActionSheet(
    ProfileSocialRelationRowViewData row,
  ) async {
    final capability = _resolvedCapability(row);
    if (capability == null ||
        _pendingRelationshipTargets.contains(row.personaId)) {
      return;
    }
    final canMessage =
        capability.canSendMessage ||
        capability.canOpenConversation ||
        capability.hasFormalConversation ||
        capability.canCreateDirectConversation;
    final result = await showAppActionSheet<String>(
      context,
      title: row.displayName,
      message: '@${row.userHandle}',
      sections: <AppActionSheetSection<String>>[
        AppActionSheetSection<String>(
          items: <AppActionSheetItem<String>>[
            AppActionSheetItem<String>(
              label: ProfileText.profileStatsUnfollow,
              value: 'unfollow',
              isDestructive: true,
              enabled: capability.canUnfollow,
            ),
            AppActionSheetItem<String>(
              label: ProfileText.profileDirectMessage,
              value: 'message',
              description: canMessage
                  ? null
                  : ProfileText.profileStatsMessageUnavailable,
              enabled: canMessage,
            ),
          ],
        ),
      ],
    );
    if (!mounted || result == null) {
      return;
    }
    if (result == 'unfollow') {
      _trackAction(
        'unfollow_confirm',
        targetType: 'profile',
        targetKey: row.personaId,
        payload: <String, Object?>{
          'tab': _activeTab.routeValue,
          'surfaceId': 'profile_stats',
        },
      );
      await _runRelationshipMutation(row, shouldFollow: false);
      return;
    }
    await _openDirectConversation(row);
  }

  Future<void> _runRelationshipMutation(
    ProfileSocialRelationRowViewData row, {
    required bool shouldFollow,
  }) async {
    final targetPersonaId = row.personaId.trim();
    if (targetPersonaId.isEmpty ||
        _pendingRelationshipTargets.isNotEmpty ||
        !_pendingRelationshipTargets.add(targetPersonaId)) {
      return;
    }
    final attempt = ++_relationshipAttemptGeneration;
    final requestedPageUserId = _userId;
    Object? failure;
    _commitState(() {});
    try {
      final capabilityRepository = ref.read(
        relationshipCapabilityRepositoryForSurfaceProvider(
          AppUiSurfaces.profileStats,
        ),
      );
      final before = await capabilityRepository
          .getCapability(targetPersonaId)
          .timeout(_authoritativeReadbackTimeout);
      _requireCapabilityTarget(before, targetPersonaId);
      if (before.isSelf || before.isBlocked || before.isBlockedBy) {
        throw StateError('Relationship mutation is not allowed');
      }
      if (before.viewerFollowsTarget != shouldFollow) {
        if (shouldFollow && !before.canFollow) {
          throw StateError('FollowUser is not allowed');
        }
        if (!shouldFollow && !before.canUnfollow) {
          throw StateError('UnfollowUser is not allowed');
        }
        final writer = ref.read(
          personaRelationshipCommandWriterProvider(AppUiSurfaces.profileStats),
        );
        if (shouldFollow) {
          await writer.follow(
            targetPersonaId,
            sourceSurfaceId: AppUiSurfaces.profileStats.id,
          );
        } else {
          await writer.unfollow(targetPersonaId);
        }
      }
      final confirmed = await capabilityRepository
          .getCapability(targetPersonaId)
          .timeout(_authoritativeReadbackTimeout);
      _requireCapabilityTarget(confirmed, targetPersonaId);
      if (confirmed.viewerFollowsTarget != shouldFollow ||
          confirmed.isBlocked ||
          confirmed.isBlockedBy) {
        throw StateError(
          'Relationship command did not converge in authoritative state',
        );
      }
      // 权威确认后回写共享关系投影，保证 feed 卡片/主页/沉浸式等
      // watch userRelationshipStateProvider 的界面即时一致。
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(targetPersonaId, confirmed.viewerFollowsTarget);
      if (!mounted ||
          attempt != _relationshipAttemptGeneration ||
          requestedPageUserId != _userId) {
        return;
      }
      _installRelationshipReadback(
        targetPersonaId,
        confirmed,
        removeFromOwnedFollowing:
            !shouldFollow &&
            (_bundle?.viewerContext.isOwner ?? false) &&
            _activeTab == _ProfileStatsTab.following,
      );
    } catch (error) {
      if (mounted && attempt == _relationshipAttemptGeneration) {
        failure = error;
      }
    } finally {
      if (mounted && _pendingRelationshipTargets.remove(targetPersonaId)) {
        _commitState(() {});
      }
    }
    if (failure == null ||
        !mounted ||
        attempt != _relationshipAttemptGeneration ||
        requestedPageUserId != _userId) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: failure,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _runRelationshipMutation(row, shouldFollow: shouldFollow);
        }
      },
    );
  }

  void _requireCapabilityTarget(
    RelationshipCapabilityViewData capability,
    String targetPersonaId,
  ) {
    if (capability.targetPersonaId.trim() != targetPersonaId) {
      throw StateError('Relationship capability target mismatch');
    }
  }

  void _installRelationshipReadback(
    String targetPersonaId,
    RelationshipCapabilityViewData capability, {
    required bool removeFromOwnedFollowing,
  }) {
    _commitState(() {
      for (final entry in _tabMemories.entries) {
        final memory = entry.value;
        final removeFromThisTab =
            removeFromOwnedFollowing && entry.key == _ProfileStatsTab.following;
        memory.items = memory.items
            .where((item) {
              return !removeFromThisTab ||
                  item is! ProfileSocialRelationRowViewData ||
                  item.personaId != targetPersonaId;
            })
            .map((item) {
              if (item is! ProfileSocialRelationRowViewData ||
                  item.personaId != targetPersonaId) {
                return item;
              }
              return item.copyWith(
                relationState: capability.relationState,
                relationshipCapability: capability,
              );
            })
            .toList(growable: false);
      }
    });
  }

  Future<void> _openDirectConversation(
    ProfileSocialRelationRowViewData row,
  ) async {
    final targetPersonaId = row.personaId.trim();
    if (targetPersonaId.isEmpty ||
        _pendingConversationTargets.contains(targetPersonaId) ||
        !await requireLogin(ref, context, AuthGateReason.sendMessage)) {
      return;
    }
    _pendingConversationTargets.add(targetPersonaId);
    final requestedPageUserId = _userId;
    Object? failure;
    try {
      final repository = ref.read(chatConversationRepositoryProvider);
      final created = await repository.createConversation(
        type: 'direct',
        initialMemberIds: <String>[targetPersonaId],
      );
      final conversationId = created.conversationId.trim();
      if (conversationId.isEmpty) {
        throw StateError('CreateConversation returned an empty id');
      }
      final confirmed = await repository
          .getConversation(conversationId)
          .timeout(_authoritativeReadbackTimeout);
      if (confirmed.id.trim() != conversationId ||
          confirmed.type != 'direct' ||
          confirmed.status != 'active') {
        throw StateError('Direct conversation did not converge');
      }
      if (!mounted || requestedPageUserId != _userId) {
        return;
      }
      _trackAction(
        'message_open',
        targetType: 'profile',
        targetKey: targetPersonaId,
        payload: <String, Object?>{
          'tab': _activeTab.routeValue,
          'surfaceId': 'profile_stats',
        },
      );
      context.push(AppRoutePaths.chatDetail(id: conversationId));
    } catch (error) {
      if (mounted) {
        failure = error;
      }
    } finally {
      _pendingConversationTargets.remove(targetPersonaId);
    }
    if (failure == null || !mounted || requestedPageUserId != _userId) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: failure,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _openDirectConversation(row);
        }
      },
    );
  }
}
