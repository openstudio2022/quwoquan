import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_command_remote.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_publication_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_delete_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const contentApiContractDeviceId = 'content-api-contract-device';

/// Real generated-client -> production object adapters -> process harness.
final class ContentApiContractHarness {
  ContentApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.feed,
    required this.posts,
    required this.postDeletion,
    required this.publication,
    required this.behaviors,
    required this.reports,
    required this.session,
  });

  static Future<ContentApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _ContentApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.values.firstWhere(
          (candidate) => candidate.name == _apiContractEnv,
          orElse: () => throw StateError(
            'Unsupported API_CONTRACT_ENV: $_apiContractEnv',
          ),
        ),
        gatewayBaseUri: Uri.parse(_apiBase),
      ),
    );

    try {
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: contentApiContractDeviceId,
          ),
        ),
      );
      final session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'content-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'content-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      CloudOperationInvocationContext queryContext(String clientPageId) {
        final surface = switch (clientPageId) {
          ContentRequestPageIds.getFeed => AppUiSurfaces.homeFeed,
          ContentRequestPageIds.reportBehaviors =>
            AppUiSurfaces.interestOnboarding,
          ContentRequestPageIds.getPost => AppUiSurfaces.workBrowser,
          ContentRequestPageIds.listUserPosts => AppUiSurfaces.userProfile,
          ContentRequestPageIds.deletePost => AppUiSurfaces.workBrowser,
          ContentRequestPageIds.createReport => AppUiSurfaces.homeFeed,
          _ => throw StateError(
            'Unsupported Content API contract clientPageId: $clientPageId',
          ),
        };
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: CloudOperationActorContext(
            accountId: session.ownerId,
            personaId: session.activePersona?.personaId,
            deviceActorId: contentApiContractDeviceId,
          ),
        );
      }

      CloudOperationInvocationContext commandContext(
        String clientPageId,
        String idempotencyKey,
      ) {
        final surface = switch (clientPageId) {
          ContentRequestPageIds.submitPostPublication =>
            AppUiSurfaces.createWorkspace,
          ContentRequestPageIds.deletePost => AppUiSurfaces.workBrowser,
          _ => AppUiSurfaces.homeFeed,
        };
        final base = queryContext(
          clientPageId == ContentRequestPageIds.submitPostPublication
              ? ContentRequestPageIds.getFeed
              : clientPageId,
        );
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
          actor: base.actor,
        );
      }

      return ContentApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        feed: RemoteContentDiscoveryFeedQuery(
          client: client,
          invocationContext: queryContext,
          blockedKeywordsLoader: () async => const <String>[],
        ),
        posts: RemoteContentPostReaderAdapter(
          client: client,
          invocationContext: queryContext,
        ),
        postDeletion: RemoteContentPostDeleteCommandWriter(
          client: client,
          invocationContext: commandContext,
        ),
        publication: RemoteContentPostPublicationWriter(
          client: client,
          invocationContext: commandContext,
        ),
        behaviors: RemoteContentBehaviorCommandAdapter(
          client: client,
          invocationContext: queryContext,
        ),
        reports: RemoteContentReportAdapter(
          client: client,
          invocationContext: queryContext,
        ),
        session: session,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RemoteContentDiscoveryFeedQuery feed;
  final RemoteContentPostReaderAdapter posts;
  final RemoteContentPostDeleteCommandWriter postDeletion;
  final RemoteContentPostPublicationWriter publication;
  final RemoteContentBehaviorCommandAdapter behaviors;
  final RemoteContentReportAdapter reports;
  final AuthSessionGrant session;

  Future<void> close() async {
    try {
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _ContentApiClientContext implements CloudClientContextProvider {
  const _ContentApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'content-api-contract',
      deviceActorId: contentApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
