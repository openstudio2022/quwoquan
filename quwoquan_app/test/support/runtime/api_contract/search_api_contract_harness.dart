import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/recent_search_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/adapters/search_feedback_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/search_query_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/adapters/hot_query_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const searchApiContractDeviceId = 'search-api-contract-device';

/// Production-only Search composition for real gateway API contracts.
///
/// The harness creates no business data and installs no substitute. Search,
/// feedback, and term-heat all travel through the generated operation client,
/// the production Remote adapters, and the production telemetry sink.
final class SearchApiContractHarness {
  SearchApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.search,
    required this.feedback,
    required this.hotQueries,
    required this.recentSearch,
    required this._accountLifecycle,
    required this._session,
  });

  static Future<SearchApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }
    final environment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == _apiContractEnv,
      orElse: () =>
          throw StateError('Unsupported API_CONTRACT_ENV: $_apiContractEnv'),
    );
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _SearchApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: environment,
        gatewayBaseUri: Uri.parse(_apiBase),
      ),
    );

    AuthSessionGrant? session;
    String? activeIdempotencyKey;

    CloudOperationInvocationContext invocationContext(
      AppUiSurface surface,
      String clientPageId,
    ) => CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: switch (clientPageId) {
        UserRequestPageIds.closeAccount =>
          'search-api-account-cleanup-${session?.ownerId}',
        SearchRequestPageIds.upsertRecentSearch ||
        SearchRequestPageIds.deleteRecentSearch ||
        SearchRequestPageIds.clearRecentSearches =>
          activeIdempotencyKey ??
              (throw StateError(
                '$clientPageId requires an explicit idempotency scope',
              )),
        _ => null,
      },
      actor: CloudOperationActorContext(
        accountId: session?.ownerId,
        personaId: session?.activePersona?.personaId,
        deviceActorId: searchApiContractDeviceId,
      ),
    );

    CloudOperationInvocationContext accountInvocationContext(
      String clientPageId,
    ) => invocationContext(
      clientPageId == UserRequestPageIds.closeAccount
          ? AppUiSurfaces.settingsAccountSecurity
          : AppUiSurfaces.appShell,
      clientPageId,
    );

    final accountSessions = RemoteAccountSessionCommandWriter(
      client: client,
      invocationContext: accountInvocationContext,
    );
    final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    try {
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'search-api-contract-$suffix',
          deviceFingerprintHash: 'search-api-contract-$suffix',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
    tokenProvider.accessToken = session.accessToken;

    final harness = SearchApiContractHarness._(
      httpClient: httpClient,
      telemetry: telemetry,
      search: RemoteCanonicalSearchQuery(
        client: client,
        invocationContext: (clientPageId) => invocationContext(
          AppUiSurfaces.globalSearchNetworkResults,
          clientPageId,
        ),
      ),
      feedback: RemoteSearchFeedbackAdapter(
        client: client,
        invocationContext: (clientPageId) => invocationContext(
          AppUiSurfaces.globalSearchNetworkResults,
          clientPageId,
        ),
      ),
      hotQueries: RemoteSearchHotQueryReader(
        client: client,
        invocationContext: (clientPageId) =>
            invocationContext(AppUiSurfaces.globalSearchLanding, clientPageId),
      ),
      recentSearch: RemoteRecentSearchAdapter(
        client: client,
        invocationContext: (clientPageId) =>
            invocationContext(AppUiSurfaces.globalSearchLanding, clientPageId),
      ),
      accountLifecycle: RemoteAccountLifecycleCommandWriter(
        client: client,
        invocationContext: accountInvocationContext,
      ),
      session: session,
    );
    harness._setIdempotencyKey = (value) => activeIdempotencyKey = value;
    return harness;
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RemoteCanonicalSearchQuery search;
  final RemoteSearchFeedbackAdapter feedback;
  final RemoteSearchHotQueryReader hotQueries;
  final RemoteRecentSearchAdapter recentSearch;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final AuthSessionGrant _session;
  late final void Function(String? value) _setIdempotencyKey;
  bool _idempotencyScopeActive = false;

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_idempotencyScopeActive) {
      throw StateError('nested Search API idempotency scope is not allowed');
    }
    _idempotencyScopeActive = true;
    _setIdempotencyKey(normalized);
    try {
      return await operation();
    } finally {
      _setIdempotencyKey(null);
      _idempotencyScopeActive = false;
    }
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'search-api-cleanup-${_session.ownerId}',
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

final class _SearchApiClientContext implements CloudClientContextProvider {
  const _SearchApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'search-api-contract',
      deviceActorId: searchApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
