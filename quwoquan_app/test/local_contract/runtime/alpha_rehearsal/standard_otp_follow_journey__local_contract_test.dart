// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/alpha_rehearsal_install.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/rehearsal_auth_port.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/authentication_challenge_remote.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/authentication_challenge_writer.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_follow_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../support/runtime/config/runtime_package_test_hydration.dart';
import '../auth/auth_session_store__local_contract_test.dart' as auth_support;
import 'alpha_rehearsal_synthetic_login__local_contract_test.dart'
    as storage_support;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('standard 安装经 typed readiness、OTP、auth grant 后关注并读回', () async {
    final journey = await _StandardOtpFollowJourney.create();
    final registry = journey.composition.executor.registry;
    const readinessId = 'user.authentication_challenge.GetOtpDeliveryReadiness';
    expect(registry.supportedCanonicalIds, contains(readinessId));
    expect(registry.unsupportedCanonicalIds, isNot(contains(readinessId)));
    expect(
      registry.supportedCanonicalIds,
      containsAll([
        'user.subject_follow.FollowSubject',
        'user.subject_follow.UnfollowSubject',
        'user.following_subject.ListFollowingSubjects',
      ]),
    );
    expect(journey.container.read(loginCapabilityFailureProvider), isNull);
    expect(journey.composition.space.isIsolated, isFalse);
    expect(journey.composition.space.instanceId, 'default');
    expect(journey.composition.synthetic, isNull);
    expect(journey.composition.challengePort, isNull);
    expect(journey.composition.sessionPort, isNull);
    expect(rehearsalAuthInstalled, isTrue);

    // generated decoder 拒绝 reasonCode 等非 canonical 字段，而不是直接调 handler。
    final readiness = await journey.client
        .userAuthenticationChallengeGetOtpDeliveryReadiness(
          const OtpDeliveryReadinessQuery(),
          context: journey.context('login'),
        );
    expect(readiness.toWire(), {
      'availability': 'ready',
      'retryAfterSeconds': 0,
    });
    await journey.issueOtp();
    expect(journey.session.isGuest, isTrue);
    await journey.completeAndFollow();
    expect(journey.session.isAuthenticated, isTrue);
    expect(journey.session.isRehearsalSession, isTrue);
    expect(journey.session.accessToken, startsWith(rehearsalCredentialPrefix));
    await journey.expectFollowing();
    expect(journey.followEvents, hasLength(1));
  });

  test('错误 OTP 保持 guest 且不续接关注，正确重试后仅执行一次', () async {
    final journey = await _StandardOtpFollowJourney.create();
    await journey.issueOtp();
    await expectLater(
      journey.completeAndFollow(otpCode: '111111'),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          'USER.AUTH.otp_mismatch',
        ),
      ),
    );
    expect(journey.session.isGuest, isTrue);
    expect(journey.composition.store.identities, isEmpty);
    expect(journey.composition.store.follows, isEmpty);
    expect(journey.followEvents, isEmpty);
    expect(
      journey.composition.store.otpChallenges.values.single['attempts'],
      1,
    );
    await journey.completeAndFollow();
    await journey.expectFollowing();
    expect(journey.followEvents, hasLength(1));
  });

  test('登录提交中取消不落身份或续接关注，原挑战可重新登录后关注', () async {
    final journey = await _StandardOtpFollowJourney.create();
    await journey.issueOtp();
    final before = Map<String, String>.from(journey.files.files);
    final entered = Completer<void>();
    final release = Completer<void>();
    journey.files.entered = entered;
    journey.files.release = release;
    final cancellation = CloudOperationCancellationSignal();
    journey.cancellation = cancellation;
    final pending = journey.completeAndFollow();
    final rejected = expectLater(
      pending,
      throwsA(isA<CloudOperationCancelledException>()),
    );
    await entered.future;
    cancellation.cancel();
    release.complete();
    await rejected;
    journey.files.entered = null;
    journey.files.release = null;
    journey.cancellation = null;
    expect(journey.files.files, before);
    expect(journey.session.isGuest, isTrue);
    expect(journey.composition.store.identities, isEmpty);
    expect(journey.composition.store.follows, isEmpty);
    expect(journey.followEvents, isEmpty);
    expect(
      journey.composition.store.otpChallenges.values.single['used'],
      isFalse,
    );
    await journey.completeAndFollow();
    await journey.expectFollowing();
    expect(journey.followEvents, hasLength(1));
  });
}

/// 仅替换物理存储边界；身份、OTP、授权和关注事实均由真实 production ports 产生。
/// 这是 local_contract 编排，不冒充登录页面续接或真实设备 UAT。
final class _StandardOtpFollowJourney {
  _StandardOtpFollowJourney(this.composition, this.container, this.files) {
    client = GeneratedCloudOperationClient(composition.executor);
    challenges = RemoteAuthenticationChallengeCommandWriter(
      client: client,
      invocationContext: context,
    );
    sessions = RemoteAccountSessionCommandWriter(
      client: client,
      invocationContext: (page) => context(page),
    );
    relationships = RemotePersonaRelationshipFollowAdapter(
      client: client,
      invocationContext: (page, operation) => context(page),
    );
  }

  final AlphaRehearsalComposition composition;
  final ProviderContainer container;
  final storage_support.PrivateStorage files;
  late final GeneratedCloudOperationClient client;
  late final RemoteAuthenticationChallengeCommandWriter challenges;
  late final RemoteAccountSessionCommandWriter sessions;
  late final RemotePersonaRelationshipFollowAdapter relationships;
  CloudOperationCancellationSignal? cancellation;
  static const _phone = '00000000000';
  static const _target = 'rehearsal.persona.follow-target';

  AuthSessionState get session => container.read(authSessionControllerProvider);
  Iterable<Map<String, Object?>> get followEvents =>
      composition.store.events.where(
        (event) => event['operation'] == 'user.persona_relationship.FollowUser',
      );

  static Future<_StandardOtpFollowJourney> create() async {
    clearAlphaRehearsalRuntime();
    await hydrateRuntimePackageForTests(environment: 'alpha');
    SharedPreferences.setMockInitialValues({});
    final files = storage_support.PrivateStorage();
    final store = AlphaRehearsalStore(
      persistence: FileRehearsalPersistence(
        gateway: files,
        snapshotDigest: offlineContentManifestDigest,
      ),
    );
    final composition = installAlphaRehearsalRuntime(store: store);
    addTearDown(() {
      composition.dispose();
      clearAlphaRehearsalRuntime();
    });
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        authSessionStoreProvider.overrideWithValue(
          AuthSessionStore(
            secureStorage: auth_support.PrivateAuthStorage(),
            storageNamespace: 'standard-otp-follow-private',
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final journey = _StandardOtpFollowJourney(composition, container, files);
    await container.read(authSessionControllerProvider.notifier).restore();
    expect(journey.session.isGuest, isTrue);
    expect(CloudRuntimeConfig.rehearsalSpace, same(composition.space));
    return journey;
  }

  CloudOperationInvocationContext context(
    String page, {
    String? idempotencyKey,
  }) {
    final current = session;
    return CloudOperationInvocationContext(
      surfaceId: 'login',
      clientPageId: page,
      actor: CloudOperationActorContext(
        deviceActorId: deriveDeviceActorId(current.installId),
        accountId: current.isAuthenticated ? current.ownerId : null,
        personaId: current.isAuthenticated ? current.activePersonaId : null,
      ),
      idempotencyKey: idempotencyKey,
      cancellation: cancellation,
    );
  }

  Future<void> issueOtp() async {
    final readiness = await challenges.getOtpDeliveryReadiness();
    expect(readiness.availability, OtpDeliveryReadinessAvailability.ready);
    final issued = await challenges.sendOtp(
      SendOtpCommand(
        phone: _phone,
        deviceId: session.installId,
        platform: OtpClientPlatform.android,
      ),
      idempotencyKey: 'standard-follow-otp',
    );
    expect(issued.deliveryStatus.wireName, 'delivered');
    expect(issued.challengeId, isNotEmpty);
    expect(installedRehearsalAuth!.lastIssuedOtp, isNotNull);
  }

  Future<void> completeAndFollow({String? otpCode}) async {
    final grant = await sessions.loginWithPhone(
      LoginWithPhoneCommand(
        phone: _phone,
        otpCode: otpCode ?? installedRehearsalAuth!.lastIssuedOtp!,
        deviceId: session.installId,
        platform: 'android',
        appVersion: '1.0.0',
        agreementVersion: 'v1',
        privacyVersion: 'v1',
      ),
    );
    await container
        .read(authSessionControllerProvider.notifier)
        .applyLoginGrant(grant);
    await relationships.follow(_target, sourceSurfaceId: 'login');
  }

  Future<void> expectFollowing() async {
    final page = await relationships.listFollowing(
      personaId: session.activePersonaId,
    );
    expect(page.items.map((item) => item.personaId), [_target]);
    expect(page.items.single.relationState, 'following');
  }
}
