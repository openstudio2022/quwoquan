// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// readiness_case: homepage_review_create_homepage_review_app_api
// readiness_case: homepage_review_update_homepage_review_app_api
// readiness_case: homepage_review_delete_homepage_review_app_api
// readiness_case: homepage_review_list_homepage_reviews_app_api
// readiness_case: homepage_review_get_my_homepage_review_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/api_contract_anonymous_session.dart';
import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

_HomepageReviewApiActor? _authorActor;
_HomepageReviewApiActor? _otherActor;
late HomepageSearchItemView _publishedHomepage;

_HomepageReviewApiActor get _author => _authorActor!;
_HomepageReviewApiActor get _other => _otherActor!;

void main() {
  setUpAll(() async {
    final runId = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final author = await _HomepageReviewApiActor.signIn(
      label: 'author',
      runId: runId,
    );
    _HomepageReviewApiActor? other;
    try {
      other = await _HomepageReviewApiActor.signIn(
        label: 'other',
        runId: runId,
      );
      _publishedHomepage = await author.acquirePublishedHomepage();
      _authorActor = author;
      _otherActor = other;
    } catch (_) {
      try {
        await other?.close();
      } finally {
        await author.close();
      }
      rethrow;
    }
  });

  tearDownAll(() async {
    try {
      await _otherActor?.close();
    } finally {
      await _authorActor?.close();
    }
  });

  test(
    'five production Remote operations replay and converge authoritatively',
    () async {
      final homepageId = _publishedHomepage.homepageId;
      final baselineSummary = await _author.expectSuccess(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        statusCode: 200,
        invoke: () => _author.homepage.getHomepageReviewSummary(homepageId),
      );
      expect(baselineSummary.ratingCount, greaterThan(0));
      expect(baselineSummary.averageRating, isNotNull);

      final createCommand = CreateHomepageReviewCommand(
        homepageId: homepageId,
        rating: 5,
        body: 'candidate-bound homepage review create',
        tagRefs: const <String>['review/api-contract'],
        authorDisplayNameSnapshot: 'API Contract Reviewer',
      );
      final created = await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-create',
        () async {
          final first = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
            statusCode: 201,
            invoke: () => _author.reviews.commandWriter.create(createCommand),
          );
          final replay = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
            statusCode: 201,
            invoke: () => _author.reviews.commandWriter.create(createCommand),
          );
          expect(replay.toWire(), first.toWire());
          return first;
        },
      );
      _expectActiveReview(
        created,
        homepageId: homepageId,
        authorPersonaId: _author.session.personaId,
        rating: 5,
        body: createCommand.body,
      );

      await _expectAuthoritativeReadback(created);
      await _author.waitForSummary(
        homepageId,
        baseline: baselineSummary,
        activeRating: 5,
      );

      await _other.withIdempotencyKey(
        'homepage-review-${_other.runId}-bola-update',
        () => _other.expectFailure(
          operationId:
              AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
          statusCode: 403,
          code: 'ENTITY.USER.permission_denied',
          invoke: () => _other.reviews.commandWriter.update(
            UpdateHomepageReviewCommand(
              reviewId: created.id,
              rating: 1,
              body: 'non-author mutation must not commit',
            ),
          ),
        ),
      );
      await _other.withIdempotencyKey(
        'homepage-review-${_other.runId}-bola-delete',
        () => _other.expectFailure(
          operationId:
              AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
          statusCode: 403,
          code: 'ENTITY.USER.permission_denied',
          invoke: () => _other.reviews.commandWriter.delete(
            DeleteHomepageReviewCommand(reviewId: created.id),
          ),
        ),
      );
      await _other.expectFailure(
        operationId:
            AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
        statusCode: 404,
        code: 'ENTITY.USER.review_not_found',
        invoke: () => _other.reviews.query.getMine(
          MyHomepageReviewQuery(homepageId: homepageId),
        ),
      );
      await _expectAuthoritativeReadback(created);

      final updateCommand = UpdateHomepageReviewCommand(
        reviewId: created.id,
        rating: 4,
        body: 'candidate-bound homepage review update',
        tagRefs: const <String>['review/api-contract', 'review/scenery'],
        authorDisplayNameSnapshot: 'API Contract Reviewer',
      );
      final updated = await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-update',
        () async {
          final first = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.update(updateCommand),
          );
          final replay = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.update(updateCommand),
          );
          expect(replay.toWire(), first.toWire());
          return first;
        },
      );
      _expectActiveReview(
        updated,
        homepageId: homepageId,
        authorPersonaId: _author.session.personaId,
        rating: 4,
        body: updateCommand.body,
      );
      expect(updated.id, created.id);
      await _expectAuthoritativeReadback(updated);
      await _author.waitForSummary(
        homepageId,
        baseline: baselineSummary,
        activeRating: 4,
      );

      final deleteCommand = DeleteHomepageReviewCommand(reviewId: created.id);
      final deleted = await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-delete',
        () async {
          final first = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.delete(deleteCommand),
          );
          final replay = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.delete(deleteCommand),
          );
          expect(replay.toWire(), first.toWire());
          return first;
        },
      );
      expect(deleted.id, created.id);
      expect(deleted.status, HomepageReviewStatus.deleted);

      final afterDelete = await _author.expectSuccess(
        operationId:
            AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
        statusCode: 200,
        invoke: () => _author.reviews.query.listByHomepage(
          HomepageReviewListQuery(homepageId: homepageId, limit: 100),
        ),
      );
      expect(afterDelete.items.any((item) => item.id == created.id), isFalse);
      final mineAfterDelete = await _author.expectSuccess(
        operationId:
            AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
        statusCode: 200,
        invoke: () => _author.reviews.query.getMine(
          MyHomepageReviewQuery(homepageId: homepageId),
        ),
      );
      expect(mineAfterDelete.id, created.id);
      expect(mineAfterDelete.status, HomepageReviewStatus.deleted);
      await _author.waitForSummary(homepageId, baseline: baselineSummary);
    },
  );

  test(
    'create and list preserve canonical missing-homepage failures',
    () async {
      final missingHomepageId = 'nonexistent_homepage_review_${_author.runId}';
      await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-missing-homepage',
        () => _author.expectFailure(
          operationId:
              AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
          statusCode: 404,
          code: 'ENTITY.USER.homepage_not_found',
          invoke: () => _author.reviews.commandWriter.create(
            CreateHomepageReviewCommand(
              homepageId: missingHomepageId,
              rating: 5,
            ),
          ),
        ),
      );
      await _author.expectFailure(
        operationId:
            AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
        statusCode: 404,
        code: 'ENTITY.USER.homepage_not_found',
        invoke: () => _author.reviews.query.listByHomepage(
          HomepageReviewListQuery(homepageId: missingHomepageId),
        ),
      );
    },
  );
}

Future<void> _expectAuthoritativeReadback(HomepageReviewView expected) async {
  final page = await _author.expectSuccess(
    operationId: AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
    statusCode: 200,
    invoke: () => _author.reviews.query.listByHomepage(
      HomepageReviewListQuery(homepageId: expected.homepageId, limit: 100),
    ),
  );
  expect(page.items, isNotEmpty);
  final matching = page.items
      .where((item) => item.id == expected.id)
      .toList(growable: false);
  expect(matching, hasLength(1));
  expect(matching.single.toWire(), expected.toWire());

  final mine = await _author.expectSuccess(
    operationId: AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
    statusCode: 200,
    invoke: () => _author.reviews.query.getMine(
      MyHomepageReviewQuery(homepageId: expected.homepageId),
    ),
  );
  expect(mine.toWire(), expected.toWire());
}

void _expectActiveReview(
  HomepageReviewView value, {
  required String homepageId,
  required String authorPersonaId,
  required int rating,
  required String? body,
}) {
  expect(value.id, isNotEmpty);
  expect(value.homepageId, homepageId);
  expect(value.authorPersonaId, authorPersonaId);
  expect(value.rating, rating);
  expect(value.status, HomepageReviewStatus.active);
  expect(value.body, body);
  expect(value.createdAt.isUtc, isTrue);
  expect(value.updatedAt.isUtc, isTrue);
}

final class _HomepageReviewApiActor {
  _HomepageReviewApiActor._({
    required this.label,
    required this.runId,
    required this.session,
    required Uri gatewayBaseUri,
    required this.telemetry,
  }) : _deviceId = 'homepage-review-api-$runId-$label-device',
       _tokenProvider = _MutableAccessTokenProvider(session.accessToken) {
    _httpClient = CloudHttpClient(authTokenProvider: _tokenProvider);
    _client = buildGeneratedCloudOperationClient(
      httpClient: _httpClient,
      clientContextProvider: _HomepageReviewApiClientContext(_deviceId),
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.values.firstWhere(
          (candidate) => candidate.name == _apiContractEnv,
          orElse: () => throw StateError(
            'Unsupported API_CONTRACT_ENV: $_apiContractEnv',
          ),
        ),
        gatewayBaseUri: gatewayBaseUri,
      ),
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
  final ApiContractAnonymousSession session;
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

  static Future<_HomepageReviewApiActor> signIn({
    required String label,
    required String runId,
  }) async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }
    final gatewayBaseUri = Uri.parse(_apiBase);
    if (!gatewayBaseUri.isAbsolute || gatewayBaseUri.scheme != 'https') {
      throw StateError(
        'L3: API_CONTRACT_BASE_URL must be an absolute first-party HTTPS URL',
      );
    }
    final loginClient = http.Client();
    late ApiContractAnonymousSession session;
    try {
      session = await ApiContractAnonymousSession.login(
        client: loginClient,
        baseUrl: _apiBase,
        subject: 'homepage-review-$runId-$label',
      );
    } finally {
      loginClient.close();
    }
    final deviceId = 'homepage-review-api-$runId-$label-device';
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: _HomepageReviewApiClientContext(deviceId),
    );
    return _HomepageReviewApiActor._(
      label: label,
      runId: runId,
      session: session,
      gatewayBaseUri: gatewayBaseUri,
      telemetry: telemetry,
    );
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
    expect(captured, isNotNull, reason: '$operationId must fail canonically');
    expect(captured!.statusCode, statusCode);
    expect(captured.code, code);
    expect(captured.requestId, isNotEmpty);
    expect(captured.traceId, isNotEmpty);
    expect(captured.sourceOperationId, operationId);
    final event = await _expectTelemetry(
      operationId,
      succeeded: false,
      statusCode: statusCode,
    );
    expect(event.requestId, captured.requestId);
    expect(event.traceId, captured.traceId);
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
      personaId: session.personaId,
      deviceActorId: _deviceId,
    ),
  );
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  const _MutableAccessTokenProvider(this.accessToken);

  final String accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _HomepageReviewApiClientContext
    implements CloudClientContextProvider {
  const _HomepageReviewApiClientContext(this._deviceActorId);

  final String _deviceActorId;

  @override
  CloudClientContextSnapshot snapshot() => CloudClientContextSnapshot(
    sessionId: 'homepage-review-api-$_deviceActorId',
    deviceActorId: _deviceActorId,
    platform: 'app',
    appVersion: 'api-integration',
    locale: 'zh-CN',
  );
}
