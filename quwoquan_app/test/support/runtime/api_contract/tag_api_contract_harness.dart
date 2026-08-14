import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/tag_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_feedback_fact/application/tag_feedback_fact_appender.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';
import 'api_contract_environment.dart';

const tagApiContractDeviceId = 'tag-api-contract-device';

final class TagApiContractHarness {
  TagApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.catalog,
    required this.feedback,
    required this._accountLifecycle,
    required this._session,
  });

  static Future<TagApiContractHarness> create() async {
    final environment = ApiContractEnvironment.resolve();
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _TagApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: environment,
    );

    try {
      AuthSessionGrant? session;
      String? activeIdempotencyKey;

      CloudOperationInvocationContext invocationContext(String clientPageId) {
        final surface = switch (clientPageId) {
          UserRequestPageIds.loginAnonymous => AppUiSurfaces.appShell,
          UserRequestPageIds.closeAccount =>
            AppUiSurfaces.settingsAccountSecurity,
          _ => AppUiSurfaces.profileCareerInterests,
        };
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: switch (clientPageId) {
            UserRequestPageIds.closeAccount =>
              'tag-api-account-cleanup-${session?.ownerId}',
            _ => activeIdempotencyKey,
          },
          actor: CloudOperationActorContext(
            accountId: session?.ownerId,
            personaId: session?.activePersona?.personaId,
            deviceActorId: tagApiContractDeviceId,
          ),
        );
      }

      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: invocationContext,
      );
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'tag-api-contract-$suffix',
          deviceFingerprintHash: 'tag-api-contract-$suffix',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      final catalog = TagProductionComposition.catalogQuery(
        client: client,
        invocationContext: invocationContext,
      );
      final feedback = TagProductionComposition.feedbackFactAppender(
        client: client,
        invocationContext: (clientPageId) {
          if (activeIdempotencyKey == null) {
            throw StateError(
              'Tag feedback API contract requires an idempotency key',
            );
          }
          return invocationContext(clientPageId);
        },
      );

      final harness = TagApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        catalog: catalog,
        feedback: feedback,
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: invocationContext,
        ),
        session: session,
      );
      harness._setIdempotencyKey = (value) => activeIdempotencyKey = value;
      return harness;
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final AuthSessionGrant _session;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final TagCatalogQuery catalog;
  final TagFeedbackFactAppender feedback;
  late final void Function(String? value) _setIdempotencyKey;

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    _setIdempotencyKey(normalized);
    try {
      return await operation();
    } finally {
      _setIdempotencyKey(null);
    }
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'tag-api-cleanup-${_session.ownerId}',
        ),
      );
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

final class _TagApiClientContext implements CloudClientContextProvider {
  const _TagApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'tag-api-contract',
      deviceActorId: tagApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
