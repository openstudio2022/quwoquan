import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_query_reader.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_query_reader.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'api_contract_environment.dart';
import 'production_cloud_operation_telemetry_evidence.dart';

const entityApiContractDeviceId = 'entity-api-contract-device';

final class EntityApiContractHarness {
  EntityApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.query,
    required this.introduction,
    required this.candidateWriter,
    required this.claimRequests,
    required this.claimRequestReader,
    required this.statusReports,
    required this.statusReportReader,
    required this._accountLifecycle,
    required this.session,
  });

  static Future<EntityApiContractHarness> create() async {
    final environment = ApiContractEnvironment.resolve();
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _EntityApiClientContext();
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
      CloudOperationInvocationContext invocationContext(
        AppUiSurface surface,
        String clientPageId, {
        String? idempotencyKey,
      }) => CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        idempotencyKey: idempotencyKey,
        actor: CloudOperationActorContext(
          accountId: session!.ownerId,
          personaId: session.activePersona?.personaId,
          deviceActorId: entityApiContractDeviceId,
        ),
      );

      // 登录请求发生在会话建立前，必须使用匿名 actor context；
      // 带 session 断言的共享 context 只服务登录后的对象操作。
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: entityApiContractDeviceId,
          ),
        ),
      );
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'entity-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'entity-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      final facets = EntityProductionComposition.homepageQueryFacets(
        client: client,
        detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
            invocationContext(AppUiSurfaces.homepageDetail, clientPageId),
        introductionInvocationContext:
            (clientPageId, {cancellation, deadlineAt}) => invocationContext(
              AppUiSurfaces.homepageIntroduction,
              clientPageId,
            ),
        searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
            invocationContext(AppUiSurfaces.homepagePicker, clientPageId),
      );
      final submissionQueries =
          EntityProductionComposition.homepageSubmissionQueryFacets(
            client: client,
            claimRequestInvocationContext:
                (clientPageId, surface, {String? idempotencyKey}) =>
                    invocationContext(surface, clientPageId),
            statusReportInvocationContext:
                (clientPageId, surface, {String? idempotencyKey}) =>
                    invocationContext(surface, clientPageId),
          );
      final commands = EntityProductionComposition.homepageCommandFacets(
        client: client,
        invocationContext: (clientPageId, surface) => invocationContext(
          surface,
          clientPageId,
          idempotencyKey:
              activeIdempotencyKey ??
              (throw StateError(
                '$clientPageId requires an explicit idempotency scope',
              )),
        ),
        claimRequestInvocationContext:
            (clientPageId, surface, {String? idempotencyKey}) =>
                invocationContext(
                  surface,
                  clientPageId,
                  idempotencyKey:
                      idempotencyKey ??
                      activeIdempotencyKey ??
                      (throw StateError(
                        '$clientPageId requires an explicit idempotency scope',
                      )),
                ),
        statusReportInvocationContext:
            (clientPageId, surface, {String? idempotencyKey}) =>
                invocationContext(
                  surface,
                  clientPageId,
                  idempotencyKey:
                      idempotencyKey ??
                      activeIdempotencyKey ??
                      (throw StateError(
                        '$clientPageId requires an explicit idempotency scope',
                      )),
                ),
      );

      final harness = EntityApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        query: facets.query,
        introduction: facets.introduction,
        candidateWriter: commands.candidateWriter,
        claimRequests: commands.claimRequestWriter,
        claimRequestReader: submissionQueries.claimRequestReader,
        statusReports: commands.statusReportWriter,
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: (clientPageId) => invocationContext(
            AppUiSurfaces.settingsAccountSecurity,
            clientPageId,
            idempotencyKey:
                'entity-api-account-cleanup-'
                '${session?.ownerId ?? (throw StateError('missing account session'))}',
          ),
        ),
        statusReportReader: submissionQueries.statusReportReader,
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
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final HomepageQueryFacet query;
  final HomepageIntroductionQuery introduction;
  final HomepageCandidateCommandWriter candidateWriter;
  final HomepageClaimRequestCommandWriter claimRequests;
  final HomepageClaimRequestQueryReader claimRequestReader;
  final HomepageStatusReportCommandWriter statusReports;
  final HomepageStatusReportQueryReader statusReportReader;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final AuthSessionGrant session;
  late final void Function(String? value) _setIdempotencyKey;
  bool _idempotencyScopeActive = false;
  var _observedEventCount = 0;

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_idempotencyScopeActive) {
      throw StateError('nested Entity API idempotency scope is not allowed');
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

  Future<HomepageSearchItemView> acquirePublishedHomepage() async {
    final slice = await query.searchHomepages(
      HomepageSearchQuery(
        query: '北京',
        status: HomepageStatus.published.wireName,
        limit: 50,
      ),
    );
    final candidates = slice.items.where(
      (item) =>
          item.status == HomepageStatus.published &&
          item.homepageId.isNotEmpty &&
          item.canonicalEntityId.isNotEmpty &&
          item.title.isNotEmpty &&
          item.ratingCount > 0,
    );
    if (candidates.isEmpty) {
      throw StateError(
        'L3: production Search returned no authoritative published homepage',
      );
    }
    return candidates.first;
  }

  Future<ProductionCloudOperationTelemetryEvent> expectTelemetry(
    String operationId, {
    required bool succeeded,
    required int statusCode,
  }) async {
    final events = await telemetry.waitForEvents(
      minimumCount: _observedEventCount + 1,
    );
    final matching = events
        .sublist(_observedEventCount)
        .where((event) => event.canonicalOperationId == operationId)
        .toList(growable: false);
    _observedEventCount = events.length;
    if (matching.isEmpty) {
      throw StateError(
        'production telemetry did not emit a fresh $operationId event',
      );
    }
    final event = matching.last;
    if (event.succeeded != succeeded || event.statusCode != statusCode) {
      throw StateError(
        '$operationId telemetry mismatch: '
        'succeeded=${event.succeeded}, statusCode=${event.statusCode}',
      );
    }
    return event;
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'entity-api-cleanup-${session.ownerId}',
        ),
      );
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

final class EntityHomepageReviewApiActor {
  EntityHomepageReviewApiActor._({
    required this.label,
    required this.runId,
    required this.session,
    required CloudRuntimeEnvironment environment,
    required this.telemetry,
  }) : _deviceId = 'homepage-review-api-$runId-$label-device',
       _tokenProvider = _MutableAccessTokenProvider()
         ..accessToken = session.accessToken {
    _httpClient = CloudHttpClient(authTokenProvider: _tokenProvider);
    _client = buildGeneratedCloudOperationClient(
      httpClient: _httpClient,
      clientContextProvider: _EntityReviewApiClientContext(_deviceId),
      telemetrySink: telemetry.sink,
      environment: environment,
    );
    final homepageFacets = EntityProductionComposition.homepageQueryFacets(
      client: _client,
      detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
          _invocationContext(
            surface: AppUiSurfaces.homepageDetail,
            clientPageId: clientPageId,
          ),
      introductionInvocationContext:
          (clientPageId, {cancellation, deadlineAt}) => _invocationContext(
            surface: AppUiSurfaces.homepageIntroduction,
            clientPageId: clientPageId,
          ),
      searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
          _invocationContext(
            surface: AppUiSurfaces.homepagePicker,
            clientPageId: clientPageId,
          ),
    );
    homepage = homepageFacets.query;
    reviews = EntityProductionComposition.homepageReviewFacets(
      client: _client,
      invocationContext: (clientPageId, {required command}) =>
          _invocationContext(
            surface: AppUiSurfaces.homepageDetail,
            clientPageId: clientPageId,
            idempotencyKey: command
                ? _activeIdempotencyKey ??
                      (throw StateError(
                        '$clientPageId requires an explicit idempotency scope',
                      ))
                : null,
          ),
    );
    _accountLifecycle = RemoteAccountLifecycleCommandWriter(
      client: _client,
      invocationContext: (clientPageId) => _invocationContext(
        surface: AppUiSurfaces.settingsAccountSecurity,
        clientPageId: clientPageId,
        idempotencyKey: 'homepage-review-api-$runId-$label-cleanup',
      ),
    );
  }

  final String label;
  final String runId;
  final AuthSessionGrant session;
  final String _deviceId;
  final _MutableAccessTokenProvider _tokenProvider;
  final ProductionCloudOperationTelemetryEvidence telemetry;

  late final CloudHttpClient _httpClient;
  late final GeneratedCloudOperationClient _client;
  late final HomepageQueryFacet homepage;
  late final AppProductionHomepageReviewFacets reviews;
  late final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  String? _activeIdempotencyKey;
  var _observedEventCount = 0;
  var _idempotencyScopeActive = false;

  static Future<EntityHomepageReviewApiActor> create({
    required String label,
    required String runId,
  }) async {
    final environment = ApiContractEnvironment.resolve();
    final tokenProvider = _MutableAccessTokenProvider();
    final loginClient = CloudHttpClient(authTokenProvider: tokenProvider);
    final deviceId = 'homepage-review-api-$runId-$label-device';
    final clientContext = _EntityReviewApiClientContext(deviceId);
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    try {
      final client = buildGeneratedCloudOperationClient(
        httpClient: loginClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: environment,
      );
      final sessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: CloudOperationActorContext(deviceActorId: deviceId),
        ),
      );
      final session = await sessions.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'homepage-review-$runId-$label',
          deviceFingerprintHash: 'homepage-review-$runId-$label',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      if (session.activePersona?.personaId.trim().isNotEmpty != true) {
        throw StateError('L3: candidate session has no active persona');
      }
      return EntityHomepageReviewApiActor._(
        label: label,
        runId: runId,
        session: session,
        environment: environment,
        telemetry: telemetry,
      );
    } catch (_) {
      await telemetry.dispose();
      rethrow;
    } finally {
      loginClient.close();
    }
  }

  Future<HomepageSearchItemView> acquirePublishedHomepage() async {
    final slice = await expectSuccess(
      operationId: AppCloudOperationIds.entityHomepageSearchHomepages,
      statusCode: 200,
      invoke: () => homepage.searchHomepages(
        HomepageSearchQuery(
          query: '北京',
          status: HomepageStatus.published.wireName,
          limit: 50,
        ),
      ),
    );
    final candidates = slice.items.where(
      (item) =>
          item.status == HomepageStatus.published &&
          item.homepageId.isNotEmpty &&
          item.canonicalEntityId.isNotEmpty &&
          item.title.isNotEmpty &&
          item.ratingCount > 0,
    );
    if (candidates.isEmpty) {
      throw StateError(
        'L3: production Search returned no authoritative published homepage',
      );
    }
    return candidates.first;
  }

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_idempotencyScopeActive) {
      throw StateError('nested homepage review idempotency scope is forbidden');
    }
    _idempotencyScopeActive = true;
    _activeIdempotencyKey = normalized;
    try {
      return await operation();
    } finally {
      _activeIdempotencyKey = null;
      _idempotencyScopeActive = false;
    }
  }

  Future<T> expectSuccess<T>({
    required String operationId,
    required int statusCode,
    required Future<T> Function() invoke,
  }) async {
    final result = await invoke();
    await _expectTelemetry(
      operationId,
      succeeded: true,
      statusCode: statusCode,
    );
    return result;
  }

  Future<CloudException> expectFailure({
    required String operationId,
    required int statusCode,
    required String code,
    required Future<Object?> Function() invoke,
  }) async {
    CloudException? captured;
    try {
      await invoke();
    } on CloudException catch (error) {
      captured = error;
    }
    if (captured == null ||
        captured.statusCode != statusCode ||
        captured.code != code ||
        (captured.requestId?.trim().isEmpty ?? true) ||
        (captured.traceId?.trim().isEmpty ?? true) ||
        captured.sourceOperationId != operationId) {
      throw StateError('$operationId did not preserve its canonical failure');
    }
    final event = await _expectTelemetry(
      operationId,
      succeeded: false,
      statusCode: statusCode,
    );
    if (event.requestId != captured.requestId ||
        event.traceId != captured.traceId) {
      throw StateError('$operationId telemetry lost failure correlation');
    }
    return captured;
  }

  Future<HomepageReviewSummaryView> waitForSummary(
    String homepageId, {
    required HomepageReviewSummaryView baseline,
    int? activeRating,
  }) async {
    final expectedCount = baseline.ratingCount + (activeRating == null ? 0 : 1);
    final expectedAverage = activeRating == null
        ? baseline.averageRating!
        : ((baseline.averageRating! * baseline.ratingCount) + activeRating) /
              expectedCount;
    final deadline = DateTime.now().add(const Duration(seconds: 10));
    HomepageReviewSummaryView? latest;
    while (DateTime.now().isBefore(deadline)) {
      final current = await expectSuccess<HomepageReviewSummaryView>(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        statusCode: 200,
        invoke: () => homepage.getHomepageReviewSummary(homepageId),
      );
      latest = current;
      if (current.ratingCount == expectedCount &&
          current.averageRating != null &&
          (current.averageRating! - expectedAverage).abs() < 0.02) {
        return current;
      }
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    throw StateError(
      'L3: review summary did not converge for $homepageId: '
      'count=${latest?.ratingCount}, average=${latest?.averageRating}, '
      'expectedCount=$expectedCount, expectedAverage=$expectedAverage',
    );
  }

  Future<ProductionCloudOperationTelemetryEvent> _expectTelemetry(
    String operationId, {
    required bool succeeded,
    required int statusCode,
  }) async {
    final events = await telemetry.waitForEvents(
      minimumCount: _observedEventCount + 1,
    );
    final matching = events
        .sublist(_observedEventCount)
        .where((event) => event.canonicalOperationId == operationId)
        .toList(growable: false);
    _observedEventCount = events.length;
    if (matching.isEmpty) {
      throw StateError(
        'production telemetry did not emit a fresh $operationId event',
      );
    }
    final event = matching.last;
    if (event.succeeded != succeeded || event.statusCode != statusCode) {
      throw StateError('$operationId telemetry did not match the invocation');
    }
    return event;
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'homepage-review-api-$runId-$label-cleanup',
        ),
      );
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }

  CloudOperationInvocationContext _invocationContext({
    required AppUiSurface surface,
    required String clientPageId,
    String? idempotencyKey,
  }) => CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    idempotencyKey: idempotencyKey,
    actor: CloudOperationActorContext(
      accountId: session.ownerId,
      personaId: session.activePersona?.personaId,
      deviceActorId: _deviceId,
    ),
  );
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _EntityReviewApiClientContext
    implements CloudClientContextProvider {
  const _EntityReviewApiClientContext(this._deviceActorId);

  final String _deviceActorId;

  @override
  CloudClientContextSnapshot snapshot() => CloudClientContextSnapshot(
    sessionId: 'homepage-review-api-$_deviceActorId',
    deviceActorId: _deviceActorId,
    platform: 'web',
    appVersion: 'api-integration',
    locale: 'zh-CN',
  );
}

final class _EntityApiClientContext implements CloudClientContextProvider {
  const _EntityApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'entity-api-contract',
      deviceActorId: entityApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
