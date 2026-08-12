// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-entry-and-preview/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-overview-and-module-shell/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/object-homepage-gamma-real-data-closure/spec.md#gwt-002
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/missing-homepage-suggestion-and-review/spec.md#gwt-001
// readiness_case: homepage_get_entity_impact_app_api
// readiness_case: homepage_get_homepage_detail_app_api
// readiness_case: homepage_get_homepage_introduction_app_api
// readiness_case: homepage_get_homepage_related_groups_app_api
// readiness_case: homepage_get_homepage_review_summary_app_api
// readiness_case: homepage_get_homepage_shell_app_api
// readiness_case: homepage_get_object_page_bundle_app_api
// readiness_case: homepage_suggest_homepage_candidate_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _deviceId = 'entity-homepage-api-contract-device';
const _missingHomepageId = 'nonexistent_homepage_api_contract_000000';

_HomepageApiContractHarness? _harness;
late HomepageSearchItemView _publishedHomepage;

_HomepageApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async {
    _harness = await _HomepageApiContractHarness.create();
    _publishedHomepage = await _api.acquirePublishedHomepage();
  });
  tearDownAll(() => _harness?.close());

  test(
    'GetHomepageDetail returns authoritative detail and canonical failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetHomepageDetail,
        invoke: _api.query.getHomepageDetail,
        verify: (result) {
          expect(result.homepageId, _publishedHomepage.homepageId);
          expect(result.title, isNotEmpty);
          expect(result.homepageType, isNotEmpty);
          expect(result.status, HomepageStatus.published.wireName);
        },
      );
    },
  );

  test(
    'GetHomepageShell returns authoritative populated shell and failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetHomepageShell,
        invoke: _api.query.getHomepageShell,
        verify: (result) {
          expect(result.homepage.homepageId, _publishedHomepage.homepageId);
          expect(result.homepage.title, isNotEmpty);
          expect(result.homepage.homepageType, isNotEmpty);
          expect(
            result.reviewSummary != null ||
                (result.contentPreview?.isNotEmpty ?? false) ||
                (result.relatedGroups?.isNotEmpty ?? false),
            isTrue,
            reason: 'published shell must expose an authoritative value slice',
          );
        },
      );
    },
  );

  test(
    'GetHomepageIntroduction returns real sections and canonical failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetHomepageIntroduction,
        invoke: _api.introduction.getHomepageIntroduction,
        verify: (result) {
          expect(result.homepageId, _publishedHomepage.homepageId);
          expect(result.displayName, isNotEmpty);
          expect(result.summary, isNotEmpty);
          expect(result.sections, isNotEmpty);
          expect(
            result.sections.every((section) => section.title.isNotEmpty),
            isTrue,
          );
          expect(result.sourceUrls, isNotEmpty);
        },
      );
    },
  );

  test(
    'GetObjectPageBundle returns authoritative object slices and failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetObjectPageBundle,
        invoke: (homepageId) => _api.query.getObjectPageBundle(
          HomepageObjectPageBundleQuery(
            homepageId: homepageId,
            referralSource: 'api-integration',
            feedRequestId: 'entity-homepage-api-feed',
            recommendationTraceId: 'entity-homepage-api-trace',
            experimentBucket: 'contract',
            rolloutCohort: 'gamma',
          ),
        ),
        verify: (result) {
          expect(result.objectType, 'homepage');
          expect(result.objectId, _publishedHomepage.homepageId);
          expect(result.canonicalEntityId, isNotEmpty);
          expect(result.title, isNotEmpty);
          expect(result.tagRefs, isNotEmpty);
          expect(result.highlightItems, isNotEmpty);
          expect(result.relatedObjects, isNotEmpty);
        },
      );
    },
  );

  test('GetEntityImpact returns authoritative fact rows and failure', () async {
    await _verifyRead(
      operationId: AppCloudOperationIds.entityHomepageGetEntityImpact,
      invoke: _api.query.getEntityImpact,
      verify: (result) {
        expect(result.homepageId, _publishedHomepage.homepageId);
        expect(result.total, greaterThan(0));
        expect(result.items, isNotEmpty);
        expect(result.items.every((item) => item.impactId.isNotEmpty), isTrue);
        expect(
          result.items.every((item) => item.primaryText.isNotEmpty),
          isTrue,
        );
        expect(
          result.items.every((item) => item.evidenceSnapshotId.isNotEmpty),
          isTrue,
        );
      },
    );
  });

  test(
    'GetHomepageReviewSummary returns real aggregation and failure',
    () async {
      await _verifyRead(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        invoke: _api.query.getHomepageReviewSummary,
        verify: (result) {
          expect(result.averageRating, isNotNull);
          expect(result.ratingCount, greaterThan(0));
          expect(result.highlightTags, isNotNull);
          expect(result.highlightTags, isNotEmpty);
        },
      );
    },
  );

  test(
    'GetHomepageRelatedGroups returns authoritative groups and failure',
    () async {
      await _verifyRead(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
        invoke: _api.query.getHomepageRelatedGroups,
        verify: (result) {
          expect(result.groups, isNotNull);
          expect(result.groups, isNotEmpty);
          final group = result.groups!.first;
          expect(group.circleId, isNotEmpty);
          expect(group.name, isNotEmpty);
          expect(group.memberCount, greaterThan(0));
          expect(group.evidenceSnapshotId, isNotEmpty);
        },
      );
    },
  );

  test(
    'SuggestHomepageCandidate replays one candidate and stays private',
    () async {
      final suffix = _api.session.ownerId.replaceAll('-', '');
      final command = SuggestHomepageCandidateCommand(
        title: 'API候选主页${suffix.substring(0, 8)}',
        homepageType: HomepageType.sight.wireName,
        subtitle: 'candidate-bound API integration evidence',
        categoryTags: const <String>['travel', 'api-contract'],
        city: '杭州',
        sourcePlaceId: 'entity-homepage-api-$suffix',
        location: const HomepageGeoPointInput(lat: 30.25, lng: 120.15),
      );
      final idempotencyKey = 'entity-homepage-suggest-$suffix';

      final created = await _api.withIdempotencyKey(
        idempotencyKey,
        () => _api.command.suggest(command),
      );
      expect(created.homepageId, isNotEmpty);
      expect(created.title, command.title);
      expect(created.status, HomepageStatus.candidate);
      await _api.expectTelemetry(
        AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        succeeded: true,
        statusCode: 201,
      );

      final replayed = await _api.withIdempotencyKey(
        idempotencyKey,
        () => _api.command.suggest(command),
      );
      expect(replayed.homepageId, created.homepageId);
      expect(replayed.toWire(), created.toWire());
      await _api.expectTelemetry(
        AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        succeeded: true,
        statusCode: 201,
      );

      await _expectCanonicalFailure(
        operationId:
            AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        statusCode: 400,
        code: 'ENTITY.USER.invalid_homepage_type',
        invoke: () => _api.withIdempotencyKey(
          '$idempotencyKey-invalid',
          () => _api.command.suggest(
            SuggestHomepageCandidateCommand(
              title: '${command.title}非法类型',
              homepageType: 'invalid-homepage-type',
            ),
          ),
        ),
      );

      final publicResults = await _api.query.searchHomepages(
        HomepageSearchQuery(
          query: command.title,
          status: HomepageStatus.published.wireName,
          limit: 20,
        ),
      );
      expect(
        publicResults.items.any(
          (item) => item.homepageId == created.homepageId,
        ),
        isFalse,
      );
      await _api.expectTelemetry(
        AppCloudOperationIds.entityHomepageSearchHomepages,
        succeeded: true,
        statusCode: 200,
      );
    },
  );
}

Future<void> _verifyRead<T>({
  required String operationId,
  required Future<T> Function(String homepageId) invoke,
  required void Function(T result) verify,
}) async {
  final result = await invoke(_publishedHomepage.homepageId);
  verify(result);
  await _api.expectTelemetry(operationId, succeeded: true, statusCode: 200);
  await _expectCanonicalFailure(
    operationId: operationId,
    statusCode: 404,
    code: 'ENTITY.USER.homepage_not_found',
    invoke: () => invoke(_missingHomepageId),
  );
}

Future<void> _expectCanonicalFailure({
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
  expect(captured, isNotNull, reason: '$operationId must fail canonically');
  expect(captured!.statusCode, statusCode);
  expect(captured.code, code);
  expect(captured.requestId, isNotEmpty);
  expect(captured.traceId, isNotEmpty);
  expect(captured.sourceOperationId, operationId);
  final event = await _api.expectTelemetry(
    operationId,
    succeeded: false,
    statusCode: statusCode,
  );
  expect(event.requestId, captured.requestId);
  expect(event.traceId, captured.traceId);
}

final class _HomepageApiContractHarness {
  _HomepageApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.query,
    required this.introduction,
    required this.command,
    required this._accountLifecycle,
    required this.session,
    required this._setIdempotencyKey,
  });

  static Future<_HomepageApiContractHarness> create() async {
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
    const clientContext = _EntityHomepageApiClientContext();
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
          deviceActorId: _deviceId,
        ),
      );

      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) =>
            invocationContext(AppUiSurfaces.appShell, clientPageId),
      );
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'entity-homepage-api-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'entity-homepage-api-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;
      if (session.activePersona?.personaId.trim().isNotEmpty != true) {
        throw StateError('L3: candidate session has no active persona');
      }

      final queries = EntityProductionComposition.homepageQueryFacets(
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
            (clientPageId, surface, {idempotencyKey}) => invocationContext(
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
            (clientPageId, surface, {idempotencyKey}) => invocationContext(
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
      final accountLifecycle = RemoteAccountLifecycleCommandWriter(
        client: client,
        invocationContext: (clientPageId) => invocationContext(
          AppUiSurfaces.settingsAccountSecurity,
          clientPageId,
          idempotencyKey: 'entity-homepage-api-cleanup-${session?.ownerId}',
        ),
      );
      return _HomepageApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        query: queries.query,
        introduction: queries.introduction,
        command: commands.candidateWriter,
        accountLifecycle: accountLifecycle,
        session: session,
        setIdempotencyKey: (value) => activeIdempotencyKey = value,
      );
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
  final HomepageCandidateCommandWriter command;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final AuthSessionGrant session;
  final void Function(String? value) _setIdempotencyKey;
  var _observedEventCount = 0;
  var _idempotencyScopeActive = false;

  Future<HomepageSearchItemView> acquirePublishedHomepage() async {
    final slice = await query.searchHomepages(
      HomepageSearchQuery(
        query: '北京',
        status: HomepageStatus.published.wireName,
        limit: 50,
      ),
    );
    await expectTelemetry(
      AppCloudOperationIds.entityHomepageSearchHomepages,
      succeeded: true,
      statusCode: 200,
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
      throw StateError('nested homepage API idempotency scope is not allowed');
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

  Future<ProductionCloudOperationTelemetryEvent> expectTelemetry(
    String operationId, {
    required bool succeeded,
    required int statusCode,
  }) async {
    final events = await telemetry.waitForEvents(
      minimumCount: _observedEventCount + 1,
    );
    final matching = events
        .skip(_observedEventCount)
        .where((event) => event.canonicalOperationId == operationId)
        .toList(growable: false);
    _observedEventCount = events.length;
    if (matching.isEmpty) {
      throw StateError(
        'production telemetry did not emit a fresh $operationId event',
      );
    }
    final event = matching.last;
    expect(event.succeeded, succeeded);
    expect(event.statusCode, statusCode);
    expect(event.requestId, isNotEmpty);
    expect(event.traceId, isNotEmpty);
    return event;
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'entity-homepage-api-cleanup-${session.ownerId}',
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

final class _EntityHomepageApiClientContext
    implements CloudClientContextProvider {
  const _EntityHomepageApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'entity-homepage-api-contract',
      deviceActorId: _deviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
