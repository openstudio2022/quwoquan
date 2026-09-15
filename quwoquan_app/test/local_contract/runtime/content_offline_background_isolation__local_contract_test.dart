import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_state_bridge.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

import '../../support/runtime/cloud_boundary_test_scope.dart';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/state/appearance_settings_provider.dart';

import '../../support/runtime/config/runtime_package_test_hydration.dart';

import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

import '../../support/runtime/errors/runtime_failure_fixtures.dart';

import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/local_content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

final class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t1
void main() {
  // spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-018
  testWidgets('真实点赞拒绝显示 unavailable，原状态和 outbox 均不变', (tester) async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final semantics = tester.ensureSemantics();
    late WidgetRef captured;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(_GuestSession.new),
        ],
        child: CupertinoApp(
          home: Consumer(
            builder: (context, ref, _) {
              captured = ref;
              return CupertinoButton(
                child: const Text('like'),
                onPressed: () =>
                    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                      syncPostLikeIntent(
                        ref,
                        postId: 'post',
                        previousLiked: false,
                        isLiked: true,
                        likeCount: 1,
                      );
                    }),
              );
            },
          ),
        ),
      ),
    );
    try {
      await tester.tap(find.text('like'));
      await tester.pumpAndSettle();
      expect(
        find.text(SearchText.recoveryCapabilityUnavailableTitle),
        findsOneWidget,
      );
      expect(
        find.text(SearchText.recoveryCapabilityUnavailableMessage),
        findsOneWidget,
      );
      expect(
        find.text(SearchText.recoveryContentUnavailableTitle),
        findsNothing,
      );
      expect(find.text(SearchText.recoveryContentGoneTitle), findsNothing);
      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.byType(CupertinoDialogAction), findsOneWidget);
      expect(find.text(SearchText.recoveryReturnAction), findsOneWidget);
      expect(
        captured.read(postInteractionStateProvider).isLiked('post'),
        isFalse,
      );
      expect(
        find.bySemanticsIdentifier('capability-unavailable:like'),
        findsOneWidget,
      );
      expect(captured.read(clientStateSyncOutboxProvider).entries, isEmpty);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text(SearchText.recoveryReturnAction));
      await tester.pumpAndSettle();
      expect(
        find.text(SearchText.recoveryCapabilityUnavailableTitle),
        findsNothing,
      );
      expect(find.text('like'), findsOneWidget);
      expect(find.byType(CupertinoAlertDialog), findsNothing);
      expect(
        captured.read(postInteractionStateProvider).isLiked('post'),
        isFalse,
      );
      expect(captured.read(clientStateSyncOutboxProvider).entries, isEmpty);
      expect(
        captured.read(authSessionControllerProvider).isAuthenticated,
        isFalse,
      );
    } finally {
      semantics.dispose();
      await tester.pumpWidget(const SizedBox.shrink());
      await hydrateRuntimePackageForTests(environment: 'beta');
    }
  });

  test('Alpha HTTP 直连及媒体流式入口均在出站前拒绝', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    var requests = 0;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        requests++;
        return http.Response('{}', 200);
      }),
    );
    try {
      await expectLater(
        client.get(Uri.parse('https://api.example.test/content/feed')),
        throwsA(isA<CloudException>()),
      );
      await expectLater(
        client.send(
          http.Request(
            'GET',
            Uri.parse('https://api.example.test/content/feed'),
          ),
        ),
        throwsA(isA<CloudException>()),
      );
      await expectLater(
        client.sendDataPlaneStream(
          http.Request(
            'GET',
            Uri.parse('https://cdn.example.test/media/video'),
          ),
        ),
        throwsA(isA<CloudException>()),
      );
      expect(requests, 0);
    } finally {
      client.close();
      await hydrateRuntimePackageForTests(environment: 'beta');
    }
  });

  test('Alpha 实际组合不恢复同步队列或装配网络遥测', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        clientStateSyncRuntimeDependenciesProvider.overrideWith(
          (ref) => throw StateError('离线不得创建同步引擎依赖'),
        ),
        actorQueueStorageProvider.overrideWith(
          (ref) => throw StateError('离线不得恢复远端队列'),
        ),
        appTelemetryTransportProvider.overrideWith(
          (ref) => throw StateError('离线不得创建远端遥测'),
        ),
      ],
    );
    try {
      expect(container.read(clientStateSyncOutboxProvider).entries, isEmpty);
      expect(
        container.read(behaviorRepositoryProvider),
        isA<LocalContentBehaviorRepository>(),
      );
      expect(
        container.read(appearanceSettingsControllerProvider).hasLoaded,
        isTrue,
      );
      expect(container.read(appTelemetryReporterProvider), isNotNull);
      expect(
        () => container
            .read(clientStateSyncOutboxProvider.notifier)
            .enqueuePostLike(
              postId: 'local-post',
              currentLiked: false,
              isLiked: true,
            ),
        throwsA(isA<CloudException>()),
      );
      expect(container.read(clientStateSyncOutboxProvider).entries, isEmpty);
    } finally {
      container.dispose();
      await hydrateRuntimePackageForTests(environment: 'beta');
    }
  });

  test('离线能力拒绝是 unsupported，不伪造 HTTP 成功或网络故障', () {
    final error = contentCapabilityUnavailable('client_state_sync');
    expect(error.statusCode, isNull);
    expect(error.code, RuntimeFailureCodes.clientPlatformCapabilityUnavailable);
    expect(error.runtimeFailure.kind, RuntimeFailureKind.unsupported);
    expect(error.runtimeFailure.nature, RuntimeFailureNature.permanent);
    expect(
      error.runtimeFailure.semanticReason,
      'content_source_capability_unavailable',
    );
    final group = AppUserRecoveryContract.classify(
      error: error,
      failure: error.runtimeFailure,
      category: UiErrorCategory.backgroundAction,
    );
    expect(group, AppUserRecoveryGroup.capabilityUnavailable);
    final copy = AppUserRecoveryContract.copyFor(group);
    expect(copy.title, SearchText.recoveryCapabilityUnavailableTitle);
    expect(copy.message, SearchText.recoveryCapabilityUnavailableMessage);
    expect(copy.action.type, UiErrorActionType.dismiss);
    expect(copy.action.label, SearchText.recoveryReturnAction);
  });

  // spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-018
  for (final notFound in [false, true]) {
    test('普通 unsupported 或404不能冒充内容源能力限制 notFound=$notFound', () {
      final failure = testRuntimeFailure(
        kind: notFound
            ? RuntimeFailureKind.notFound
            : RuntimeFailureKind.unsupported,
      );
      final error = CloudException(
        type: notFound ? CloudErrorType.notFound : CloudErrorType.unknown,
        statusCode: notFound ? 404 : null,
        message: 'test-only failure',
        runtimeFailure: failure,
      );
      final group = AppUserRecoveryContract.classify(
        error: error,
        failure: failure,
        category: UiErrorCategory.backgroundAction,
      );
      expect(group, AppUserRecoveryGroup.contentUnavailable);
      expect(group, isNot(AppUserRecoveryGroup.capabilityUnavailable));
      final copy = AppUserRecoveryContract.copyFor(group);
      expect(copy.title, SearchText.recoveryContentUnavailableTitle);
      expect(copy.message, SearchText.recoveryContentUnavailableMessage);
      expect(copy.action.type, UiErrorActionType.dismiss);
      expect(copy.action.label, SearchText.recoveryReturnAction);
    });
  }

  test('本地浏览观测不持有网络依赖或持久待投递事件', () async {
    final repository = LocalContentBehaviorRepository();
    await repository.reportEvents(
      events: <BehaviorEvent>[
        BehaviorEvent(
          contentId: 'local-post',
          action: BehaviorEventType.impression,
        ),
      ],
    );
    await repository.clearPendingForLogout();
    await repository.reportEvents(events: const <BehaviorEvent>[]);
  });

  test('需要服务端确认的首启偏好不能在离线模式伪成功', () async {
    final repository = LocalContentBehaviorRepository();
    await expectLater(
      repository.submitOnboardingInterest(
        clientEventId: 'local-event',
        taxonomyReleaseId: 'taxonomy',
        tagRefs: const <String>['topic'],
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.runtimeFailure.kind,
          'kind',
          RuntimeFailureKind.unsupported,
        ),
      ),
    );
  });
}
