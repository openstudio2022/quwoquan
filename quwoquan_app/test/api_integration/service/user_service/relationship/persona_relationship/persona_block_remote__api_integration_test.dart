// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-003
// readiness_case: persona_relationship_block_user_app_api
// readiness_case: persona_relationship_follow_user_app_api
// readiness_case: persona_relationship_get_relationship_capability_app_api
// readiness_case: persona_relationship_list_blocked_users_app_api
// readiness_case: persona_relationship_list_followers_app_api
// readiness_case: persona_relationship_list_following_app_api
// readiness_case: persona_relationship_unblock_user_app_api
// readiness_case: persona_relationship_unfollow_user_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  UserApiContractHarness? actor;
  UserApiContractHarness? target;
  UserApiContractHarness? secondTarget;

  tearDownAll(() async {
    await secondTarget?.close();
    await target?.close();
    await actor?.close();
  });

  test(
    'production PersonaRelationship Remote closes follow, capability and blocked-list readback',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      actor = await UserApiContractHarness.create();
      target = await UserApiContractHarness.create();
      secondTarget = await UserApiContractHarness.create();
      final actorSession = await actor!.loginDisposableAccount(
        'persona-relationship-actor-$suffix',
      );
      final targetSession = await target!.loginDisposableAccount(
        'persona-relationship-target-$suffix',
      );
      final secondTargetSession = await secondTarget!.loginDisposableAccount(
        'persona-relationship-second-target-$suffix',
      );
      final actorPersonaId = _activePersonaId(actorSession);
      final targetPersonaId = _activePersonaId(targetSession);
      final secondTargetPersonaId = _activePersonaId(secondTargetSession);

      try {
        final initialCapability = await actor!.personaRelationships
            .getRelationshipCapability(
              GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
            );
        expect(initialCapability.viewerPersonaId, actorPersonaId);
        expect(initialCapability.targetPersonaId, targetPersonaId);
        expect(initialCapability.canFollow, isTrue);
        expect(initialCapability.isBlocked, isFalse);
        expect(initialCapability.isBlockedBy, isFalse);

        for (var replay = 0; replay < 2; replay++) {
          await actor!.withIdempotencyKey(
            idempotencyKey: 'persona-follow-$suffix',
            action: () => actor!.personaRelationshipFollows.follow(
              targetPersonaId,
              sourceSurfaceId: AppUiSurfaces.userProfile.id,
            ),
          );
        }

        final following = await _pollUntil(
          () => actor!.personaRelationshipFollows.listFollowing(
            personaId: actorPersonaId,
            limit: 100,
          ),
          (page) => page.items.any(
            (item) => item.personaId == targetPersonaId && item.isFollowing,
          ),
          'following owner projection',
        );
        final followers = await _pollUntil(
          () => target!.personaRelationshipFollows.listFollowers(
            personaId: targetPersonaId,
            limit: 100,
          ),
          (page) => page.items.any((item) => item.personaId == actorPersonaId),
          'followers owner projection',
        );
        expect(
          following.items.where((item) => item.personaId == targetPersonaId),
          hasLength(1),
        );
        expect(
          followers.items.where((item) => item.personaId == actorPersonaId),
          hasLength(1),
        );
        final followedCapability = await actor!.personaRelationships
            .getRelationshipCapability(
              GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
            );
        expect(followedCapability.canUnfollow, isTrue);
        expect(followedCapability.canFollow, isFalse);

        for (var replay = 0; replay < 2; replay++) {
          await actor!.withIdempotencyKey(
            idempotencyKey: 'persona-unfollow-$suffix',
            action: () =>
                actor!.personaRelationshipFollows.unfollow(targetPersonaId),
          );
        }
        await _pollUntil(
          () => actor!.personaRelationshipFollows.listFollowing(
            personaId: actorPersonaId,
            limit: 100,
          ),
          (page) =>
              page.items.every((item) => item.personaId != targetPersonaId),
          'unfollowed owner projection',
        );

        final firstBlock = await actor!.personaRelationships
            .blockUserWithIntent(
              BlockUserCommand(targetPersonaId: targetPersonaId),
              idempotencyKey: 'persona-block-target-$suffix',
            );
        final firstBlockReplay = await actor!.personaRelationships
            .blockUserWithIntent(
              BlockUserCommand(targetPersonaId: targetPersonaId),
              idempotencyKey: 'persona-block-target-$suffix',
            );
        final secondBlock = await actor!.personaRelationships
            .blockUserWithIntent(
              BlockUserCommand(targetPersonaId: secondTargetPersonaId),
              idempotencyKey: 'persona-block-second-target-$suffix',
            );
        expect(firstBlock.blocked, isTrue);
        expect(firstBlock.idempotentReplay, isFalse);
        expect(firstBlockReplay.targetPersonaId, firstBlock.targetPersonaId);
        expect(firstBlockReplay.idempotentReplay, isTrue);
        expect(secondBlock.blocked, isTrue);

        final blockedFirstPage = await _pollUntil(
          () => actor!.personaRelationships.listBlockedUsers(
            ListBlockedUsersQuery(limit: 1),
          ),
          (page) =>
              page.items.length == 1 &&
              page.nextCursor != null &&
              page.nextCursor!.isNotEmpty,
          'blocked-list first page',
        );
        final blockedSecondPage = await actor!.personaRelationships
            .listBlockedUsers(
              ListBlockedUsersQuery(
                cursor: blockedFirstPage.nextCursor,
                limit: 1,
              ),
            );
        final blockedPersonaIds = <String>{
          ...blockedFirstPage.items.map((item) => item.targetPersonaId),
          ...blockedSecondPage.items.map((item) => item.targetPersonaId),
        };
        expect(blockedPersonaIds, <String>{
          targetPersonaId,
          secondTargetPersonaId,
        });
        expect(blockedSecondPage.nextCursor, isNull);
        final targetOwnedBlocks = await target!.personaRelationships
            .listBlockedUsers(ListBlockedUsersQuery(limit: 100));
        expect(
          targetOwnedBlocks.items.any(
            (item) => item.targetPersonaId == actorPersonaId,
          ),
          isFalse,
        );

        final blockedCapability = await actor!.personaRelationships
            .getRelationshipCapability(
              GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
            );
        expect(blockedCapability.isBlocked, isTrue);
        expect(blockedCapability.canFollow, isFalse);

        final unblocked = await actor!.personaRelationships
            .unblockUserWithIntent(
              UnblockUserCommand(targetPersonaId: targetPersonaId),
              idempotencyKey: 'persona-unblock-target-$suffix',
            );
        final unblockReplay = await actor!.personaRelationships
            .unblockUserWithIntent(
              UnblockUserCommand(targetPersonaId: targetPersonaId),
              idempotencyKey: 'persona-unblock-target-$suffix',
            );
        expect(unblocked.blocked, isFalse);
        expect(unblocked.idempotentReplay, isFalse);
        expect(unblockReplay.targetPersonaId, unblocked.targetPersonaId);
        expect(unblockReplay.idempotentReplay, isTrue);
        await _pollUntil(
          () => actor!.personaRelationships.listBlockedUsers(
            ListBlockedUsersQuery(limit: 100),
          ),
          (page) =>
              page.items.every(
                (item) => item.targetPersonaId != targetPersonaId,
              ) &&
              page.items.any(
                (item) => item.targetPersonaId == secondTargetPersonaId,
              ),
          'unblocked owner projection',
        );

        await actor!.personaRelationships.unblockUserWithIntent(
          UnblockUserCommand(targetPersonaId: secondTargetPersonaId),
          idempotencyKey: 'persona-unblock-second-target-$suffix',
        );
      } finally {
        await _closeDisposableAccount(
          actor,
          clientRequestId: 'persona-relationship-close-actor-$suffix',
        );
        await _closeDisposableAccount(
          target,
          clientRequestId: 'persona-relationship-close-target-$suffix',
        );
        await _closeDisposableAccount(
          secondTarget,
          clientRequestId: 'persona-relationship-close-second-$suffix',
        );
      }
    },
  );
}

String _activePersonaId(AuthSessionGrant session) {
  final personaId = session.activePersona?.personaId.trim() ?? '';
  if (personaId.isEmpty) {
    throw StateError('Disposable account has no active persona');
  }
  return personaId;
}

Future<T> _pollUntil<T>(
  Future<T> Function() read,
  bool Function(T value) done,
  String label,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (true) {
    final value = await read();
    if (done(value)) {
      return value;
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError('Timed out waiting for $label');
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}

Future<void> _closeDisposableAccount(
  UserApiContractHarness? harness, {
  required String clientRequestId,
}) async {
  if (harness == null) {
    return;
  }
  try {
    await harness.accountLifecycle.closeAccount(
      CloseAccountCommand(clientRequestId: clientRequestId),
    );
  } catch (_) {
    // Cleanup cannot mask the first API-contract failure.
  }
}
