// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/user_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  late MemoryRehearsalPersistence persistence;
  late AlphaRehearsalStore store;
  var sequence = 0;
  final now = DateTime.utc(2026, 9, 13, 13);

  setUp(() {
    persistence = MemoryRehearsalPersistence();
    store = AlphaRehearsalStore(
      persistence: persistence,
      now: () => now,
      idFactory: () => '${sequence++}',
    );
  });

  RehearsalInvocation invocation(
    String id, {
    Map<String, Object?> body = const {},
    Map<String, String> path = const {},
    Map<String, String> query = const {},
    CloudOperationActorContext actor = const CloudOperationActorContext(),
  }) => RehearsalInvocation(
    operation: appCloudOperationContracts[id]!,
    payload: CloudOperationRequestPayload(
      body: body,
      pathParameters: path,
      queryParameters: query,
    ),
    context: CloudOperationInvocationContext(
      surfaceId: 'rehearsal',
      clientPageId: 'rehearsal.user',
      actor: actor,
    ),
    store: store,
    now: () => now,
    nextId: store.nextId,
  );

  Future<(AuthSessionGrant, CloudOperationActorContext)> login(
    String phone,
  ) async {
    const handler = UserRehearsalHandler();
    await handler.handle(
      invocation(
        'user.authentication_challenge.SendOtp',
        body: {'phone': phone},
      ),
    );
    final wire = await handler.handle(
      invocation(
        'user.account_session.LoginWithPhone',
        body: {'phone': phone, 'otpCode': rehearsalOtpCode},
      ),
    );
    final grant = decodeAuthSessionGrant(wire);
    return (
      grant,
      CloudOperationActorContext(
        accountId: grant.ownerId,
        personaId: grant.activePersona!.personaId,
      ),
    );
  }

  test('inventory 精确区分 66 个 supported 与 8 个 provider unsupported', () {
    final canonical = appCloudOperationContracts.values
        .where((operation) => operation.domain == 'user')
        .map((operation) => operation.canonicalOperationId)
        .toSet();
    expect(userRehearsalCapabilities.keys.toSet(), canonical);
    expect(
      userRehearsalCapabilities.values.where(
        (capability) =>
            capability.status == UserRehearsalCapabilityStatus.supported,
      ),
      hasLength(66),
    );
    expect(
      userRehearsalCapabilities.values
          .where(
            (capability) =>
                capability.status == UserRehearsalCapabilityStatus.unsupported,
          )
          .map((capability) => capability.canonicalOperationId),
      containsAll(<String>[
        'user.account_session.LoginOneTap',
        'user.account_session.LoginWithAlipay',
        'user.account_session.LoginWithQq',
        'user.account_session.LoginWithWechat',
        'user.authentication_challenge.CreateAlipayAuthorizationRequest',
        'user.authentication_challenge.ResolveOneTapLoginHint',
        'user.credential_binding.BindCarrierPhoneCredential',
        'user.credential_binding.CompleteFederatedPhoneBinding',
      ]),
    );
  });

  test('OTP session refresh 与重启恢复保持 canonical decoder', () async {
    final (grant, actor) = await login('00000000001');
    expect(grant.accountState, 'active');
    final refreshed = decodeTokenRefreshGrant(
      await const UserRehearsalHandler().handle(
        invocation(
          'user.account_session.RefreshToken',
          body: {'refreshToken': grant.refreshToken},
        ),
      ),
    );
    expect(refreshed.refreshToken, isNot(grant.refreshToken));

    final restored = AlphaRehearsalStore(
      persistence: persistence,
      idFactory: () => '${sequence++}',
    );
    await restored.ensureLoaded();
    expect(restored.currentOwnerId, grant.ownerId);
    expect(restored.currentPersonaId, actor.personaId);
  });

  test('persona settings follow block subject 与 greeting 写后读回', () async {
    final (_, actor) = await login('00000000002');
    const handler = UserRehearsalHandler();
    final created = decodePersonaManagementItemView(
      await handler.handle(
        invocation(
          'user.persona.CreatePersona',
          actor: actor,
          body: {'displayName': '摄影分身'},
        ),
      ),
    );
    expect(created.displayName, '摄影分身');
    expect(
      decodeListPersonasResult(
        await handler.handle(
          invocation('user.user_account.ListPersonas', actor: actor),
        ),
      ).items,
      hasLength(2),
    );

    final appearance = decodeAppearanceSettingsView(
      await handler.handle(
        invocation(
          'user.user_settings.UpdateAppearanceSettings',
          actor: actor,
          body: {
            'themeMode': 'dark',
            'fontSizePreset': 'lg',
            'applyScope': 'all_accounts',
          },
        ),
      ),
    );
    expect(appearance.themeMode, ThemeModeSetting.dark);

    const target = 'rehearsal.persona.target';
    expect(
      decodeFollowCommandResult(
        await handler.handle(
          invocation(
            'user.persona_relationship.FollowUser',
            actor: actor,
            body: {'targetPersonaId': target},
          ),
        ),
      ).relationState,
      RelationshipState.following,
    );
    expect(
      decodeFollowingRelationshipPageSlice(
        await handler.handle(
          invocation(
            'user.persona_relationship.ListFollowing',
            actor: actor,
            body: {'personaId': actor.personaId, 'limit': 20},
          ),
        ),
      ).items.single.personaId,
      target,
    );

    expect(
      decodeSubjectFollowCommandResult(
        await handler.handle(
          invocation(
            'user.subject_follow.FollowSubject',
            actor: actor,
            body: {'subjectType': 'homepage', 'subjectId': 'homepage.photo'},
          ),
        ),
      ).state,
      SubjectFollowState.following,
    );
    expect(
      decodeFollowingSubjectSlice(
        await handler.handle(
          invocation(
            'user.following_subject.ListFollowingSubjects',
            actor: actor,
            body: {'limit': 20},
          ),
        ),
      ).items.single.subjectId,
      'homepage.photo',
    );

    final greeting = decodeGreetingRequestRecord(
      await handler.handle(
        invocation(
          'user.greeting_request.SendGreetingRequest',
          actor: actor,
          body: {
            'targetPersonaId': target,
            'requestMessage': '你好',
            'source': 'profile',
          },
        ),
      ),
    );
    expect(greeting.status, GreetingRequestStatus.pending);
    expect(
      decodeGreetingRequestSlice(
        await handler.handle(
          invocation(
            'user.greeting_request.ListGreetingOutbox',
            actor: actor,
            body: {'status': 'pending', 'limit': 20},
          ),
        ),
      ).items.single.id,
      greeting.id,
    );

    expect(
      decodeBlockCommandResult(
        await handler.handle(
          invocation(
            'user.persona_relationship.BlockUser',
            actor: actor,
            body: {'targetPersonaId': target},
          ),
        ),
      ).blocked,
      isTrue,
    );
    expect(
      decodeBlockedUserSlice(
        await handler.handle(
          invocation(
            'user.persona_relationship.ListBlockedUsers',
            actor: actor,
            body: {'limit': 20},
          ),
        ),
      ).items.single.targetPersonaId,
      target,
    );
  });
}
