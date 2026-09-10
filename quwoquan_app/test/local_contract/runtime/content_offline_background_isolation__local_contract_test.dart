import 'package:flutter_test/flutter_test.dart';
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
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/local_content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t1
void main() {
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
  });

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
